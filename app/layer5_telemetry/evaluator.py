from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field


class TelemetryEntry(BaseModel):
    task_id: str
    action: str
    status: str
    execution_time_ms: float
    passed_quality_gate: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TelemetryJudge:
    def __init__(self):
        self._logs: List[TelemetryEntry] = []

    def log_and_evaluate(self, task_id: str, action: str, status: str, execution_time_ms: float) -> TelemetryEntry:
        # Quality Gate: Status must be completed & latency under 1000ms
        passed = (status == "completed") and (execution_time_ms < 1000.0)
        entry = TelemetryEntry(
            task_id=task_id,
            action=action,
            status=status,
            execution_time_ms=execution_time_ms,
            passed_quality_gate=passed
        )
        self._logs.append(entry)
        return entry

    def get_telemetry_summary(self) -> Dict[str, Any]:
        total = len(self._logs)
        passed = sum(1 for log in self._logs if log.passed_quality_gate)
        return {
            "entity": "Bristlecone Logic, LLC",
            "total_executions": total,
            "passed_quality_gates": passed,
            "quality_score_pct": round((passed / total) * 100, 2) if total > 0 else 100.0,
            "recent_audit_trail": [log.model_dump() for log in self._logs[-5:]]
        }


telemetry_judge = TelemetryJudge()
