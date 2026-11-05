"""Bounded native searches; workers receive visible observations, never live tables."""
from __future__ import annotations

import configparser
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import threading
import time

from bots.meowcats import MeowCaTSStrategy
from domain.rules.ruleset import Ruleset


@dataclass
class Search:
    """One cancellable decision with a deadline including time spent in the queue."""

    future: Future
    cancelled: threading.Event

    def cancel(self) -> None:
        """Keep capacity reserved until dequeue; running work has a bounded deadline."""
        self.cancelled.set()


class NativeSearches:
    """At most two long-lived native processes and two queued decisions per web server."""

    def __init__(self, executable: Path, runtime: Path, *, timeout: float = 15.0) -> None:
        self.executable = executable.resolve()
        self.runtime = runtime.resolve()
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='seat-ai')
        self.slots = threading.BoundedSemaphore(4)
        self.lock = threading.Lock()
        self.searches: dict[int, Search] = {}
        self.local = threading.local()
        self.strategies: set[MeowCaTSStrategy] = set()
        self.closed = False

    def submit(self, observation: dict, rules: Ruleset) -> Search | None:
        """Accept bounded work without waiting for a worker or native initialization."""
        with self.lock:
            if self.closed or not self.slots.acquire(blocking=False):
                return None
            cancelled = threading.Event()
            deadline = time.monotonic() + self.timeout
            future = self.executor.submit(
                self._choose, deepcopy(observation), deepcopy(rules), cancelled, deadline)
            search = Search(future, cancelled)
            self.searches[id(search)] = search
        future.add_done_callback(lambda _: self._finished(search))
        return search

    def _finished(self, search: Search) -> None:
        with self.lock:
            self.searches.pop(id(search), None)
            self.slots.release()

    def _choose(self, observation: dict, rules: Ruleset,
                cancelled: threading.Event, deadline: float) -> dict:
        def remaining() -> float:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise TimeoutError('Native decision cancelled or deadline exceeded')
            return deadline - time.monotonic()

        config = configparser.ConfigParser()
        config.read(self.runtime / 'config.ini')
        required = {
            'MCTS': {'TotalSampleCount': '2000', 'ThreadNum': '0', 'WaitReleaseTree': '1',
                     'UseTime': '0'},
            'BaseConfig': {'SampleCount': '2000', 'SampleFirstRound': '100',
                           'SamplePerRound': '100', 'UseTime': '0'},
            'Multithread': {'ThreadNum': '0'},
        }
        if any(config.get(section, key, fallback=None) != value
               for section, values in required.items() for key, value in values.items()):
            raise ValueError('Advanced AI requires the fixed 2000-sample single-thread runtime')
        # Cancellation or an expired deadline must not cost the warm bridge.
        remaining()
        # Each worker thread keeps one bridge; reloading native tables dominated latency.
        strategy = getattr(self.local, 'strategy', None)
        if strategy is not None and not strategy.alive:
            # Died while idle (e.g. OOM kill); keep its stderr for diagnosis.
            self._discard(strategy)
            strategy = None
        if strategy is None:
            strategy = MeowCaTSStrategy(self.executable, self.runtime, rules,
                                        timeout=remaining())
            self.local.strategy = strategy
            with self.lock:
                self.strategies.add(strategy)
        # Outside the try: a search cancelled during cold start keeps the new bridge.
        strategy.timeout = remaining()
        try:
            # Rules travel with each request, so tables with different rules share the bridge.
            return strategy.choose(observation, rules)
        except BaseException:
            # Invalid input leaves the bridge alive; IPC failures already reaped it.
            if not strategy.alive:
                self._discard(strategy)
            raise
        finally:
            strategy.latencies.clear()  # The web path never reads it; avoid unbounded growth.

    def _discard(self, strategy: MeowCaTSStrategy) -> None:
        """Forget a failed or dead bridge, keeping its stderr log for diagnosis."""
        strategy.close()
        if getattr(self.local, 'strategy', None) is strategy:
            self.local.strategy = None
        with self.lock:
            self.strategies.discard(strategy)

    def close(self) -> None:
        """Cancel queued decisions and reap all running bridges before shutdown."""
        with self.lock:
            self.closed = True
            searches = list(self.searches.values())
        for search in searches:
            search.cancel()
        self.executor.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            strategies, self.strategies = list(self.strategies), set()
        for strategy in strategies:
            died = not strategy.alive  # Keep stderr of a bridge that died while idle.
            strategy.close()
            if not died:
                strategy.error_log.unlink(missing_ok=True)
