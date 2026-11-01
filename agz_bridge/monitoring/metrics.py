"""Collects runtime performance metrics, token usage, and request history."""
import time
from collections import deque
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RequestRecord(BaseModel):
    timestamp: float
    client_id: str
    model: str
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    is_stream: bool
    status: str
    error: Optional[str] = None


class MetricsCollector:
    def __init__(self, history_limit: int = 100):
        self.start_time = time.time()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_duration = 0.0
        self.last_latency = 0.0
        self._history: deque[RequestRecord] = deque(maxlen=history_limit)

    def record_request(
        self,
        client_id: str,
        model: str,
        duration: float,
        input_tokens: int,
        output_tokens: int,
        is_stream: bool,
        status: str = "SUCCESS",
        error: Optional[str] = None
    ):
        self.total_requests += 1
        if status == "SUCCESS":
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_duration += duration
        self.last_latency = duration

        self._history.append(
            RequestRecord(
                timestamp=time.time(),
                client_id=client_id,
                model=model,
                duration_seconds=round(duration, 3),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                is_stream=is_stream,
                status=status,
                error=error
            )
        )

    def get_summary(self) -> Dict[str, Any]:
        avg_latency = (
            self.total_duration / self.successful_requests
            if self.successful_requests > 0
            else 0.0
        )
        return {
            "uptime_seconds": int(time.time() - self.start_time),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "avg_latency_seconds": round(avg_latency, 3),
            "last_latency_seconds": round(self.last_latency, 3),
            "recent_requests": [r.model_dump() for r in list(self._history)[-20:]]
        }


_metrics_instance: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
