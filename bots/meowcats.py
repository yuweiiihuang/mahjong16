"""POSIX process adapter for an explicitly built, isolated MeowCaTS bridge."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import isfinite
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import threading
from time import monotonic

from domain.analysis import visible_count_global
from domain.rules.hands import is_valid_chow_start
from domain.rules.ruleset import Ruleset

# Upstream MoveType and MeldType values; tile indices are the same 9+9+9+7 layout.
_MOVES = {"PASS": 1, "DISCARD": 3, "PONG": 7, "GANG": 8, "ANGANG": 9, "KAKAN": 10}
_MELDS = {"CHI": 3, "PONG": 4, "GANG": 5, "KAKAN": 5, "ANGANG": 6}


def _tile(value: object) -> int:
    if type(value) is not int or not 0 <= value < 34:
        raise ValueError("Expected a non-flower tile index")
    return value


def _request(obs: dict, rules: Ruleset, sequence: int) -> tuple[bytes, list[dict]]:
    """Serialize only decision-time visible data, masking even raw other-seat dark kongs."""
    pid = obs["player"]
    players = obs["players"]
    if pid not in range(4) or len(players) != 4 or obs["phase"] not in ("TURN", "REACTION"):
        raise ValueError("Expected an enriched four-player observation")
    hand = [_tile(t) for t in obs["hand"]]
    if obs.get("drawn") is not None:
        hand.append(_tile(obs["drawn"]))
    counts = Counter(hand)
    if any(n > 4 for n in counts.values()):
        raise ValueError("Too many copies in concealed hand")
    public = deepcopy(obs["melds_all"])
    if len(public) != 4:
        raise ValueError("Expected public melds for four seats")
    kongs = 0
    for seat, melds in enumerate(public):
        for meld in melds:
            if meld["type"] in ("GANG", "ANGANG", "KAKAN"):
                kongs += 1
            if seat != pid and meld["type"] == "ANGANG":
                meld["tiles"] = [None] * 4
    visible = {"hand": hand, "melds_all": public, "rivers": obs["rivers"]}
    unseen = [4 - visible_count_global(t, visible) for t in range(34)]
    if any(not 0 <= n <= 4 for n in unseen):
        raise ValueError("Visible tile counts are inconsistent")
    flowers = [t for player in players for t in player["flowers"]]
    if len(set(flowers)) != len(flowers) or any(type(t) is not int or not 34 <= t < 42
                                             for t in flowers):
        raise ValueError("Invalid public flowers")
    remaining = obs["n_remaining"]
    hidden_flowers = 8 - len(flowers) if rules.include_flowers else 0
    if type(remaining) is not int or not 0 <= hidden_flowers <= remaining <= 144:
        raise ValueError("Invalid remaining wall count")
    reserved = rules.dead_wall_base + (kongs if rules.dead_wall_mode == "gang_plus_one" else 0)
    # shortcut: uniform flower positions approximate live normal draws; no wall order is read.
    draws = (max(0, remaining - reserved) * (remaining - hidden_flowers) // remaining
             if remaining else 0)
    meld_codes = []
    for meld in obs["melds"]:
        kind = meld["type"]
        tiles = [_tile(t) for t in meld["tiles"]]
        if kind not in _MELDS or len(tiles) != (4 if kind in ("GANG", "ANGANG", "KAKAN") else 3):
            raise ValueError("Invalid own meld")
        target = min(tiles)
        if kind == "CHI":
            if (not is_valid_chow_start(target)
                    or sorted(tiles) != [target, target + 1, target + 2]):
                raise ValueError("Invalid chow")
        elif len(set(tiles)) != 1:
            raise ValueError("Invalid triplet or kong")
        meld_codes.extend((_MELDS[kind], target))
    if len(meld_codes) > 10 or len(hand) + 3 * len(obs["melds"]) not in (16, 17):
        raise ValueError("Invalid concealed/meld hand size")
    mapped = {}
    for action in obs["legal_actions"]:
        kind = action["type"]
        if kind in ("HU", "TING"):
            continue
        if kind == "CHI":
            target = _tile(obs["last_discard"]["tile"])
            tiles = sorted([target, *[_tile(t) for t in action["use"]]])
            if (len(tiles) != 3 or not is_valid_chow_start(tiles[0])
                    or tiles != list(range(tiles[0], tiles[0] + 3))):
                raise ValueError("Invalid legal chow")
            code = (4 + tiles.index(target), target)
        else:
            if kind not in _MOVES:
                raise ValueError("Unsupported legal action")
            code = (_MOVES[kind], -1 if kind == "PASS" else
                    _tile(obs["last_discard"]["tile"] if kind in ("PONG", "GANG")
                          else action["tile"]))
        mapped.setdefault(code, action)
    ordered = sorted(mapped)
    actions = [mapped[code] for code in ordered]
    if not ordered:
        raise ValueError("No supported legal candidate")
    tokens = [1, sequence, int(obs["phase"] == "REACTION"), draws,
              *[counts[t] for t in range(34)], len(obs["melds"]), *meld_codes,
              *unseen, len(ordered), *[n for code in ordered for n in code]]
    line = (" ".join(map(str, tokens)) + "\n").encode("ascii")
    if len(line) > 2048:
        raise ValueError("Bridge request exceeds protocol bound")
    return line, actions


class MeowCaTSStrategy:
    """Own one POSIX bridge; use enriched player_observation, never an environment object."""

    def __init__(self, executable: str | Path, runtime_dir: str | Path, rules: Ruleset,
                 *, timeout: float = 15.0) -> None:
        if os.name != "posix" or not isfinite(timeout) or timeout <= 0:
            raise ValueError("MeowCaTS requires POSIX pipes and a positive finite timeout")
        if (rules.n_players != 4 or rules.initial_hand != 16
                or rules.dead_wall_mode not in ("fixed", "gang_plus_one")
                or type(rules.dead_wall_base) is not int or rules.dead_wall_base < 0):
            raise ValueError("Unsupported rules")
        self.rules = deepcopy(rules)
        self.timeout = timeout
        self.sequence = 0
        self.latencies: list[float] = []
        self.forced = 0
        self._buffer = bytearray()
        self._lock = threading.RLock()
        self._process = None
        self._stderr = tempfile.NamedTemporaryFile(
            prefix="meowcats-", suffix=".log", dir=runtime_dir, delete=False)
        self.error_log = Path(self._stderr.name)
        try:
            self._process = subprocess.Popen(
                [str(Path(executable).resolve())], cwd=runtime_dir,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr, bufsize=0)
            os.set_blocking(self._process.stdin.fileno(), False)
            os.set_blocking(self._process.stdout.fileno(), False)
            if self._receive(monotonic() + timeout) != b"READY 1":
                raise RuntimeError("Wrong MeowCaTS bridge handshake")
        except BaseException:
            self.close()
            raise

    def _receive(self, deadline: float) -> bytes:
        with selectors.DefaultSelector() as selector:
            selector.register(self._process.stdout, selectors.EVENT_READ)
            while b"\n" not in self._buffer:
                if len(self._buffer) > 2048:
                    raise RuntimeError("Bridge response exceeds protocol bound")
                if not selector.select(max(0, deadline - monotonic())):
                    raise TimeoutError("MeowCaTS response deadline exceeded")
                chunk = os.read(self._process.stdout.fileno(), 4096)
                if not chunk:
                    raise RuntimeError(f"MeowCaTS exited; see {self.error_log}")
                self._buffer.extend(chunk)
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer[:] = rest
            if len(line) > 2048:
                raise RuntimeError("Bridge response exceeds protocol bound")
            return bytes(line)

    def choose(self, obs: dict) -> dict:
        """Choose a host-legal action using only enriched, masked public-player observations."""
        with self._lock:
            try:
                actions = obs["legal_actions"]
                if not actions:
                    raise ValueError("No legal action")
                for action in actions:
                    if action["type"] == "HU":
                        self.forced += 1
                        return deepcopy(action)
                if len(actions) == 1:
                    self.forced += 1
                    return deepcopy(actions[0])
                self.sequence += 1
                data, candidates = _request(obs, self.rules, self.sequence)
                started = monotonic()
                deadline = started + self.timeout
                with selectors.DefaultSelector() as selector:
                    selector.register(self._process.stdin, selectors.EVENT_WRITE)
                    while data:
                        if not selector.select(max(0, deadline - monotonic())):
                            raise TimeoutError("MeowCaTS write deadline exceeded")
                        try:
                            written = os.write(self._process.stdin.fileno(), data)
                        except BlockingIOError:
                            continue
                        data = data[written:]
                reply = self._receive(deadline).split()
                if len(reply) != 3 or reply[:2] != [b"OK", str(self.sequence).encode()]:
                    raise RuntimeError(f"Malformed MeowCaTS response: {reply!r}")
                index = int(reply[2])
                if not 0 <= index < len(candidates):
                    raise RuntimeError("MeowCaTS selected an invalid candidate")
                self.latencies.append(monotonic() - started)
                return deepcopy(candidates[index])
            except BaseException:
                self.close()
                raise

    def close(self) -> None:
        """Reap the owned process, including failed initialization and timed-out searches."""
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        self._stderr.close()

    def __enter__(self) -> MeowCaTSStrategy:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
