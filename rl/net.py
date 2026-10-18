"""Candidate-scoring actor/critic and versioned local checkpoints (optional PyTorch)."""
from __future__ import annotations

from pathlib import Path
import os
import random

import torch
from torch import nn

from app.hand_store import open_private_record
from rl.encoding import ENCODING_VERSION, KINDS, encode
from rl.history import HISTORY_LENGTH


def configure_determinism(device: str, enabled: bool = False) -> dict:
    """Opt into process-wide deterministic kernels before CUDA initialization.

    With no opt-in, retain the caller's PyTorch settings and record their actual value.
    Deterministic execution applies to the same hardware/software, not across backends.
    """
    workspace = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if enabled:
        if device == "cuda":
            if workspace not in (None, ":4096:8", ":16:8"):
                raise ValueError("Deterministic CUDA requires CUBLAS_WORKSPACE_CONFIG=:4096:8")
            if workspace is None and torch.cuda.is_initialized():
                raise RuntimeError("Set CUBLAS_WORKSPACE_CONFIG before initializing CUDA")
            workspace = os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
    active = torch.are_deterministic_algorithms_enabled()
    return {"enabled": active,
            "warn_only": torch.is_deterministic_algorithms_warn_only_enabled() if active else False,
            "cublas_workspace_config": workspace if active and device == "cuda" else None}


def resolve_device(device: str) -> torch.device:
    """Require an explicitly available device, without silent CPU fallback."""
    if device not in ("cpu", "mps", "cuda"):
        raise ValueError("Device must be cpu, mps or cuda")
    if device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS is unavailable in this process; check GPU access outside sandbox")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; check the driver and PyTorch CUDA build")
    return torch.device(device)


def get_device_rng_state(device: str) -> torch.Tensor | None:
    """Keep accelerator RNG separate from the CPU stream in portable checkpoints."""
    if device == "mps":
        return torch.mps.get_rng_state()
    if device == "cuda":
        return torch.cuda.get_rng_state()
    return None


def set_device_rng_state(device: str, state: torch.Tensor | None) -> None:
    """Restore the selected accelerator stream when resuming on the same backend."""
    if device in ("mps", "cuda"):
        if state is None:
            raise ValueError("Checkpoint is missing accelerator RNG state")
        backend = torch.mps if device == "mps" else torch.cuda
        backend.set_rng_state(state)


def batch(observations: list[dict], device: str = "cpu", *, history: bool = False) -> tuple:
    """Pad only the candidate axis; padded actions have exactly zero probability."""
    encoded = [encode(obs) for obs in observations]
    states = torch.tensor([state for state, _ in encoded])
    count = max(len(actions) for _, actions in encoded)
    actions = torch.zeros(len(encoded), count, len(encoded[0][1][0]))
    mask = torch.zeros(len(encoded), count, dtype=torch.bool)
    for i, (_, candidates) in enumerate(encoded):
        actions[i, :len(candidates)] = torch.tensor(candidates)
        mask[i, :len(candidates)] = True
    # Pack on CPU, then transfer each tensor once instead of each candidate row.
    packed = (states.to(device), actions.to(device), mask.to(device))
    if not history:
        return packed
    past_states = torch.zeros(len(encoded), HISTORY_LENGTH, states.shape[-1])
    past_actions = torch.zeros(len(encoded), HISTORY_LENGTH, actions.shape[-1])
    lengths = torch.zeros(len(encoded), dtype=torch.long)
    for i, obs in enumerate(observations):
        entries = obs.get("decision_history", [])
        if len(entries) > HISTORY_LENGTH:
            raise ValueError("Decision history exceeds the three-decision window")
        lengths[i] = len(entries)
        for j, (state, action) in enumerate(entries):
            past_states[i, j] = torch.tensor(state)
            past_actions[i, j] = torch.tensor(action)
    return packed + (past_states.to(device), past_actions.to(device), lengths.to(device))


def _board_tokens(states: torch.Tensor) -> tuple[torch.Tensor, ...]:
    """Reshape encoding v1 without adding information: 34 tiles, four seats, one global."""
    # v1: 113 header fields, four 221-field players, 38 last-discard fields.
    players = states[:, 113:997].reshape(-1, 4, 221)
    melds = players[:, :, 46:].reshape(-1, 4, 5, 35)
    tiles = torch.cat((states[:, :102].reshape(-1, 3, 34).transpose(1, 2),
                       players[:, :, :34].transpose(1, 2),
                       melds[:, :, :, :34].reshape(-1, 20, 34).transpose(1, 2),
                       states[:, 997:1031, None]), dim=-1)
    seats = torch.cat((players[:, :, 34:46], melds[:, :, :, 34]), dim=-1)
    global_state = torch.cat((states[:, 102:113], states[:, 1031:]), dim=-1)
    return tiles, seats, global_state


class PolicyValueNet(nn.Module):
    """Score each legal action conditioned on state; estimate undiscounted net payment."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: int = 128,
                 *, architecture: str = "mlp") -> None:
        super().__init__()
        if architecture not in ("mlp", "transformer", "hierarchical", "temporal"):
            raise ValueError("Unknown policy architecture")
        if architecture != "mlp" and (
                ENCODING_VERSION != 1 or obs_dim != 1035 or hidden % 4):
            raise ValueError("Board Transformer requires encoding v1 and four attention heads")
        self.dimensions = (obs_dim, act_dim, hidden)
        self.architecture = architecture
        if architecture == "mlp":
            self.state = nn.Sequential(nn.Linear(obs_dim, hidden), nn.ReLU())
            self.policy = nn.Sequential(nn.Linear(hidden + act_dim, hidden), nn.ReLU(),
                                        nn.Linear(hidden, 1))
            self.value = nn.Linear(hidden, 1)
        else:
            self.tiles = nn.Linear(28, hidden)
            self.seats = nn.Linear(17, hidden)
            self.global_state = nn.Linear(15, hidden)
            self.tile_id = nn.Embedding(34, hidden)
            self.suit = nn.Embedding(4, hidden)
            self.rank = nn.Embedding(10, hidden)
            self.seat_id = nn.Embedding(4, hidden)
            self.register_buffer("tile_suits", torch.tensor([i // 9 for i in range(27)]
                                                            + [3] * 7))
            self.register_buffer("tile_ranks", torch.tensor([i % 9 + 1 for i in range(27)]
                                                            + [0] * 7))
            layer = nn.TransformerEncoderLayer(hidden, 4, hidden * 4, dropout=0,
                                               batch_first=True, norm_first=True)
            self.state = nn.TransformerEncoder(layer, 3, norm=nn.LayerNorm(hidden),
                                               enable_nested_tensor=False)
            self.action = nn.Linear(act_dim, hidden)
            self.query_norm = nn.LayerNorm(hidden)
            self.attention = nn.MultiheadAttention(hidden, 4, dropout=0, batch_first=True)
            self.action_ff = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, hidden * 4),
                                           nn.ReLU(), nn.Linear(hidden * 4, hidden))
            self.policy = nn.Linear(hidden, 1)
            self.value = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))
            if architecture in ("hierarchical", "temporal"):
                self.action_type = nn.Linear(hidden, len(KINDS))
            if architecture == "temporal":
                self.past_action = nn.Linear(act_dim, hidden)
                self.position = nn.Embedding(HISTORY_LENGTH + 1, hidden)
                temporal_layer = nn.TransformerEncoderLayer(
                    hidden, 4, hidden * 4, dropout=0, batch_first=True, norm_first=True)
                self.temporal = nn.TransformerEncoder(
                    temporal_layer, 3, norm=nn.LayerNorm(hidden), enable_nested_tensor=False)

    def prepare(self, observations: list[dict]) -> tuple:
        """Pack the architecture's visible inputs on its selected device."""
        return batch(observations, str(next(self.parameters()).device),
                     history=self.architecture == "temporal")

    def _board_memory(self, states: torch.Tensor) -> torch.Tensor:
        tiles, seats, global_state = _board_tokens(states)
        tile_ids = torch.arange(34, device=states.device)
        tile_tokens = (self.tiles(tiles) + self.tile_id(tile_ids)
                       + self.suit(self.tile_suits) + self.rank(self.tile_ranks))
        seat_tokens = self.seats(seats) + self.seat_id(torch.arange(4, device=states.device))
        return self.state(torch.cat((self.global_state(global_state)[:, None],
                                     tile_tokens, seat_tokens), dim=1))

    def forward(self, states: torch.Tensor, actions: torch.Tensor,
                mask: torch.Tensor, past_states: torch.Tensor | None = None,
                past_actions: torch.Tensor | None = None,
                lengths: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor]:
        """Produce logits over candidates and an unbounded value for each observation."""
        if self.architecture == "mlp":
            hidden = self.state(states)
            joined = torch.cat((hidden[:, None].expand(-1, actions.shape[1], -1), actions), -1)
        else:
            memory = self._board_memory(states)
            hidden = memory[:, 0]
            if self.architecture == "temporal":
                if past_states is None:
                    raise ValueError("Temporal policy requires inputs from model.prepare")
                past = self._board_memory(past_states.flatten(0, 1))[:, 0]
                past = past.reshape(states.shape[0], HISTORY_LENGTH, -1)
                past = past + self.past_action(past_actions)
                tokens = torch.cat((past, hidden[:, None]), dim=1)
                index = lengths[:, None, None].expand(-1, 1, hidden.shape[-1])
                tokens = tokens.scatter(1, index, hidden[:, None])
                positions = torch.arange(HISTORY_LENGTH + 1, device=states.device)
                tokens = tokens + self.position(positions)
                padding = positions[None] > lengths[:, None]
                causal = positions[None, :] > positions[:, None]
                context = self.temporal(tokens, mask=causal, src_key_padding_mask=padding)
                hidden = context.gather(1, index).squeeze(1)
                memory = torch.cat((hidden[:, None], memory[:, 1:]), dim=1)
            query = self.action(actions)
            attended, _ = self.attention(self.query_norm(query), memory, memory,
                                         need_weights=False)
            joined = query + attended
            joined = joined + self.action_ff(joined)
        logits = self.policy(joined).squeeze(-1).masked_fill(~mask, -torch.inf)
        if self.architecture in ("hierarchical", "temporal"):
            # Factor the complete legal-candidate distribution, not just the tile ID.
            membership = (actions[:, :, :len(KINDS)] > 0.5) & mask[:, :, None]
            present = membership.any(dim=1)
            type_log_probs = self.action_type(hidden).masked_fill(~present, -torch.inf)
            type_log_probs = type_log_probs.log_softmax(-1)
            grouped = logits[:, :, None].masked_fill(~membership, -torch.inf)
            # Absent groups need finite reductions to keep their backward pass finite.
            grouped = torch.where(present[:, None, :], grouped, torch.zeros_like(grouped))
            normalizers = grouped.logsumexp(dim=1)
            types = actions[:, :, :len(KINDS)].argmax(-1)
            logits = (type_log_probs.gather(1, types) + logits
                      - normalizers.gather(1, types)).masked_fill(~mask, -torch.inf)
        return logits, self.value(hidden).squeeze(-1)

    @torch.no_grad()
    def choose(self, obs: dict) -> dict:
        """Choose deterministically from a safe player-view observation."""
        logits, _ = self(*self.prepare([obs]))
        return obs["legal_actions"][int(logits[0].argmax())]


def save_checkpoint(path: Path, model: PolicyValueNet, spec: dict, *, stage: str,
                    optimizer: torch.optim.Optimizer, progress: dict) -> None:
    """Publish a complete owner-only checkpoint without overwriting another run."""
    payload = {"format_version": 1, "encoding_version": ENCODING_VERSION, "spec": spec,
               "dimensions": model.dimensions, "model": model.state_dict(), "stage": stage,
               "architecture": model.architecture, "device": next(model.parameters()).device.type,
               "optimizer": optimizer.state_dict(), "progress": progress,
               "torch_rng": torch.get_rng_state(), "python_rng": random.getstate(),
               "device_rng": get_device_rng_state(next(model.parameters()).device.type)}
    # The binary buffer shares the existing atomic private-output lifecycle.
    with open_private_record(path) as handle:
        torch.save(payload, handle.buffer)


def load_checkpoint(path: Path, spec: dict, device: str = "cpu") -> tuple[PolicyValueNet, dict]:
    """Load tensors and primitives only, rejecting changed rules or observation contracts."""
    target = resolve_device(device)
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if (payload.get("format_version") != 1
            or payload.get("encoding_version") != ENCODING_VERSION
            or payload.get("spec") != spec):
        raise ValueError("Checkpoint rules, engine or encoding do not match")
    model = PolicyValueNet(*payload["dimensions"], architecture=payload.get("architecture", "mlp"))
    model.load_state_dict(payload["model"])
    model.to(target).eval()
    return model, payload
