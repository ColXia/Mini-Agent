"""Prometheus-compatible metrics collection system."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Callable


class MetricType(str, Enum):
    """Types of metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricLabel:
    """Label for a metric sample."""

    name: str
    value: str


@dataclass
class MetricSample:
    """A single metric sample."""

    value: float
    labels: tuple[MetricLabel, ...] = field(default_factory=tuple)
    timestamp: float | None = None


@dataclass
class HistogramBucket:
    """A histogram bucket."""

    upper_bound: float
    count: int = 0


class Counter:
    """A monotonically increasing counter."""

    def __init__(
        self,
        name: str,
        description: str = "",
        *,
        namespace: str = "mini_agent",
    ) -> None:
        self.name = f"{namespace}_{name}" if namespace else name
        self.description = description
        self._value: float = 0.0
        self._lock = RLock()

    def inc(self, amount: float = 1.0) -> None:
        """Increment the counter."""
        if amount < 0:
            raise ValueError("Counter can only be incremented")
        with self._lock:
            self._value += amount

    def labels(self, **kwargs: str) -> "LabeledCounter":
        """Return a labeled counter instance."""
        return LabeledCounter(self, tuple(MetricLabel(k, v) for k, v in kwargs.items()))

    def collect(self) -> list[MetricSample]:
        """Collect current metric value."""
        with self._lock:
            return [MetricSample(value=self._value)]

    def expose(self) -> str:
        """Expose in Prometheus format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} counter")
        for sample in self.collect():
            label_str = ""
            if sample.labels:
                label_str = "{" + ", ".join(f'{l.name}="{l.value}"' for l in sample.labels) + "}"
            lines.append(f"{self.name}{label_str} {sample.value}")
        return "\n".join(lines)


class LabeledCounter:
    """A counter with labels."""

    def __init__(self, counter: Counter, labels: tuple[MetricLabel, ...]) -> None:
        self._counter = counter
        self._labels = labels
        self._value: float = 0.0

    def inc(self, amount: float = 1.0) -> None:
        """Increment the labeled counter."""
        if amount < 0:
            raise ValueError("Counter can only be incremented")
        self._value += amount


class Gauge:
    """A gauge that can go up and down."""

    def __init__(
        self,
        name: str,
        description: str = "",
        *,
        namespace: str = "mini_agent",
    ) -> None:
        self.name = f"{namespace}_{name}" if namespace else name
        self.description = description
        self._value: float = 0.0
        self._lock = RLock()

    def set(self, value: float) -> None:
        """Set the gauge to a specific value."""
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment the gauge."""
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement the gauge."""
        with self._lock:
            self._value -= amount

    def labels(self, **kwargs: str) -> "LabeledGauge":
        """Return a labeled gauge instance."""
        return LabeledGauge(self, tuple(MetricLabel(k, v) for k, v in kwargs.items()))

    def collect(self) -> list[MetricSample]:
        """Collect current metric value."""
        with self._lock:
            return [MetricSample(value=self._value)]

    def expose(self) -> str:
        """Expose in Prometheus format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} gauge")
        for sample in self.collect():
            label_str = ""
            if sample.labels:
                label_str = "{" + ", ".join(f'{l.name}="{l.value}"' for l in sample.labels) + "}"
            lines.append(f"{self.name}{label_str} {sample.value}")
        return "\n".join(lines)


class LabeledGauge:
    """A gauge with labels."""

    def __init__(self, gauge: Gauge, labels: tuple[MetricLabel, ...]) -> None:
        self._gauge = gauge
        self._labels = labels
        self._value: float = 0.0

    def set(self, value: float) -> None:
        """Set the labeled gauge."""
        self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment the labeled gauge."""
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement the labeled gauge."""
        self._value -= amount


class Histogram:
    """A histogram for observing distributions."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        description: str = "",
        *,
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
        namespace: str = "mini_agent",
    ) -> None:
        self.name = f"{namespace}_{name}" if namespace else name
        self.description = description
        self.buckets = sorted(buckets)
        self._lock = RLock()
        self._bucket_counts: dict[float, int] = {b: 0 for b in self.buckets}
        self._bucket_counts[float("inf")] = 0
        self._sum: float = 0.0
        self._count: int = 0

    def observe(self, value: float) -> None:
        """Observe a value."""
        with self._lock:
            self._sum += value
            self._count += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[bucket] += 1
            self._bucket_counts[float("inf")] += 1

    def time(self) -> "HistogramTimer":
        """Return a timer context manager."""
        return HistogramTimer(self)

    def collect(self) -> list[MetricSample]:
        """Collect histogram samples."""
        with self._lock:
            samples = []
            cumulative = 0
            for bucket in self.buckets + (float("inf"),):
                cumulative += self._bucket_counts[bucket]
                samples.append(MetricSample(
                    value=cumulative,
                    labels=(MetricLabel("le", str(bucket) if bucket != float("inf") else "+Inf"),),
                ))
            samples.append(MetricSample(value=self._sum, labels=(MetricLabel("le", "sum"),)))
            samples.append(MetricSample(value=self._count, labels=(MetricLabel("le", "count"),)))
            return samples

    def expose(self) -> str:
        """Expose in Prometheus format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} histogram")
        for sample in self.collect():
            label_str = ""
            if sample.labels:
                label_str = "{" + ", ".join(f'{l.name}="{l.value}"' for l in sample.labels) + "}"
            lines.append(f"{self.name}{label_str} {sample.value}")
        return "\n".join(lines)


class HistogramTimer:
    """Timer context manager for histograms."""

    def __init__(self, histogram: Histogram) -> None:
        self._histogram = histogram
        self._start: float | None = None

    def __enter__(self) -> "HistogramTimer":
        self._start = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._start is not None:
            elapsed = time.time() - self._start
            self._histogram.observe(elapsed)


class MetricsRegistry:
    """Registry for all metrics."""

    def __init__(self, namespace: str = "mini_agent") -> None:
        self.namespace = namespace
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = RLock()

    def counter(
        self,
        name: str,
        description: str = "",
    ) -> Counter:
        """Get or create a counter."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description, namespace=self.namespace)
            return self._counters[name]

    def gauge(
        self,
        name: str,
        description: str = "",
    ) -> Gauge:
        """Get or create a gauge."""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description, namespace=self.namespace)
            return self._gauges[name]

    def histogram(
        self,
        name: str,
        description: str = "",
        *,
        buckets: tuple[float, ...] = Histogram.DEFAULT_BUCKETS,
    ) -> Histogram:
        """Get or create a histogram."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets=buckets, namespace=self.namespace)
            return self._histograms[name]

    def expose(self) -> str:
        """Expose all metrics in Prometheus format."""
        lines = []
        for counter in self._counters.values():
            lines.append(counter.expose())
        for gauge in self._gauges.values():
            lines.append(gauge.expose())
        for histogram in self._histograms.values():
            lines.append(histogram.expose())
        return "\n".join(lines)

    def collect_all(self) -> dict[str, list[MetricSample]]:
        """Collect all metrics."""
        return {
            "counters": {name: c.collect() for name, c in self._counters.items()},
            "gauges": {name: g.collect() for name, g in self._gauges.items()},
            "histograms": {name: h.collect() for name, h in self._histograms.items()},
        }


# Global metrics registry
_registry: MetricsRegistry | None = None


def get_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


def counter(name: str, description: str = "") -> Counter:
    """Get or create a counter from the global registry."""
    return get_registry().counter(name, description)


def gauge(name: str, description: str = "") -> Gauge:
    """Get or create a gauge from the global registry."""
    return get_registry().gauge(name, description)


def histogram(
    name: str,
    description: str = "",
    *,
    buckets: tuple[float, ...] = Histogram.DEFAULT_BUCKETS,
) -> Histogram:
    """Get or create a histogram from the global registry."""
    return get_registry().histogram(name, description, buckets=buckets)


def expose_metrics() -> str:
    """Expose all metrics in Prometheus format."""
    return get_registry().expose()
