"""Lightweight Prometheus metrics in the text exposition format.

Implements just enough of the format (counters, gauges, histograms) for the
metrics this app needs, without pulling in prometheus_client. Exposed via the
GET /metrics endpoint. Counter/histogram buckets are recorded in-process; a
registry object holds all metrics.
"""

import threading
import time
from typing import Dict, List, Optional, Tuple


class Counter:
    def __init__(self, name: str, help: str, labelnames: Optional[List[str]] = None):
        self.name = name
        self.help = help
        self.labelnames = labelnames or []
        self._values: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def _labels(self, labels: dict) -> Tuple[str, ...]:
        return tuple(str(labels.get(k, "")) for k in self.labelnames)

    def inc(self, amount: float = 1, labels: Optional[dict] = None) -> None:
        key = self._labels(labels or {})
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def render(self) -> str:
        with self._lock:
            items = list(self._values.items())
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for key, value in items:
            suffix = ",".join(f'{k}="{v}"' for k, v in zip(self.labelnames, key))
            suffix = "{" + suffix + "}" if suffix else ""
            lines.append(f"{self.name}{suffix} {value}")
        return "\n".join(lines) + "\n"


class Gauge:
    def __init__(self, name: str, help: str, labelnames: Optional[List[str]] = None):
        self.name = name
        self.help = help
        self.labelnames = labelnames or []
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = float(value)

    def render(self) -> str:
        return f"# HELP {self.name} {self.help}\n# TYPE {self.name} gauge\n{self.name} {self._value}\n"


class Histogram:
    def __init__(self, name: str, help: str, buckets: Optional[List[float]] = None):
        self.name = name
        self.help = help
        self.buckets = buckets or [0.1, 0.5, 1, 5, 10, 30, 60, 300, 1800, 3600]
        self._counts: List[int] = [0] * (len(self.buckets) + 1)
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._sum += value
            self._count += 1
            idx = 0
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    idx = i
                    break
            else:
                idx = len(self.buckets)
            # bucket is "le" cumulative
            for i in range(idx, len(self.buckets) + 1):
                self._counts[i] += 1

    def render(self) -> str:
        with self._lock:
            counts = list(self._counts)
            total = self._count
            total_sum = self._sum
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for i, bound in enumerate(self.buckets):
            lines.append(f'{self.name}_bucket{{le="{bound}"}} {counts[i]}')
        lines.append(f'{self.name}_bucket{{le="+Inf"}} {counts[len(self.buckets)]}')
        lines.append(f"{self.name}_sum {total_sum}")
        lines.append(f"{self.name}_count {total}")
        return "\n".join(lines) + "\n"


class Registry:
    def __init__(self):
        self._metrics: List[object] = []

    def register(self, metric: object) -> object:
        self._metrics.append(metric)
        return metric

    def render(self) -> str:
        return "".join(m.render() for m in self._metrics)


# ---- Application metrics -----------------------------------------------------

registry = Registry()

jobs_total = registry.register(Counter(
    "migrator_jobs_total",
    "Total jobs processed, by outcome (completed/failed/cancelled)",
    labelnames=["outcome"],
))
messages_copied = registry.register(Counter(
    "migrator_messages_copied_total",
    "Total email messages copied by imapsync",
))
messages_skipped = registry.register(Counter(
    "migrator_messages_skipped_total",
    "Total email messages skipped (already present on target)",
))
calendar_items = registry.register(Counter(
    "migrator_calendar_items_total",
    "Total calendar items uploaded",
))
contacts_items = registry.register(Counter(
    "migrator_contacts_total",
    "Total contacts uploaded",
))
task_items = registry.register(Counter(
    "migrator_tasks_total",
    "Total task items uploaded",
))
queue_depth = registry.register(Gauge(
    "migrator_queue_depth",
    "Number of jobs currently waiting in the Redis queue",
))
running_jobs = registry.register(Gauge(
    "migrator_running_jobs",
    "Number of jobs currently being processed",
))
job_duration = registry.register(Histogram(
    "migrator_job_duration_seconds",
    "Wall-clock duration of completed jobs",
))


def render_metrics() -> str:
    return registry.render()
