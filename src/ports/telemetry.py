from abc import ABC, abstractmethod
from typing import Dict
from dataclasses import dataclass
from time import time


@dataclass
class TraceContext:
    trace_id: str
    span_id: str
    operation: str
    start_time: float

    def finish(self, success: bool = True, error: str = None):
        # No-op placeholder; real impl would send to tracer
        _ = (success, error)
        return time() - self.start_time


class TelemetryPort(ABC):
    """Observability interface."""

    @abstractmethod
    def record_metric(self, name: str, value: float, tags: Dict[str, str]) -> None:
        ...

    @abstractmethod
    def record_latency(self, operation: str, duration_ms: float) -> None:
        ...

    @abstractmethod
    def log_structured(self, level: str, message: str, context: Dict) -> None:
        ...

    @abstractmethod
    def start_trace(self, operation: str) -> TraceContext:
        ...

