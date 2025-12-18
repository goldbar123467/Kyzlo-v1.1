from typing import Dict
import time
import uuid

from ...ports.telemetry import TelemetryPort, TraceContext


class PrometheusAdapter(TelemetryPort):
    """Minimal telemetry adapter (stdout-based placeholder)."""

    def __init__(self, port: int = 8000):
        self.port = port

    def start(self):
        # Placeholder: no server started to keep dependencies light.
        pass

    def record_metric(self, name: str, value: float, tags: Dict[str, str]) -> None:
        print(f"[metric] {name}={value} tags={tags}")

    def record_latency(self, operation: str, duration_ms: float) -> None:
        print(f"[latency] {operation} {duration_ms:.2f}ms")

    def log_structured(self, level: str, message: str, context: Dict) -> None:
        print(f"[{level}] {message} | {context}")

    def start_trace(self, operation: str) -> TraceContext:
        return TraceContext(
            trace_id=str(uuid.uuid4()), span_id=str(uuid.uuid4())[:8], operation=operation, start_time=time.time()
        )

