from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict

LOG_FILE = Path("audit_log.jsonl")


class AuditLogger:
    """Provides append-only, structured audit logging for all agent state events."""

    @classmethod
    def log_event(cls, event_type: str, details: Dict[str, Any]) -> None:
        """Appends a timestamped JSON event record to the audit file."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details,
        }
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
