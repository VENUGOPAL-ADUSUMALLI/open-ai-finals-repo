from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class A2AEnvelope:
    run_id: str
    batch_id: str
    candidate_id: int | None
    agent_name: str
    stage: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] = field(default_factory=dict)
    status: str = 'SUCCESS'
    error_code: str = ''
    error_message: str = ''
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    latency_ms: int = 0
    model_name: str = ''
    token_usage: dict[str, Any] = field(default_factory=dict)

    def complete(self, payload: dict[str, Any], model_name: str = '', token_usage: dict | None = None):
        self.response_payload = payload
        self.completed_at = datetime.now(timezone.utc)
        self.latency_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        self.model_name = model_name
        self.token_usage = token_usage or {}
        self.status = 'SUCCESS'

    def fail(self, code: str, message: str):
        self.completed_at = datetime.now(timezone.utc)
        self.latency_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        self.status = 'FAILED'
        self.error_code = code
        self.error_message = message
