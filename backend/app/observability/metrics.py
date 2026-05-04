from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class InMemoryMetrics:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    timings_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def inc(self, key: str, by: int = 1) -> None:
        self.counters[key] += by

    def observe_ms(self, key: str, value: float) -> None:
        self.timings_ms[key].append(value)
