"""
Bristlecone Logic - AgentTrust Guardrail Integration
===================================================
Pre-flight SSRF boundary enforcement and AST JSON deliverable healing
for autonomous agents executing decentralized contracts on AgentTrust.
"""

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import urllib.request
import urllib.error

logger = logging.getLogger("bristlecone_logic.integrations.agent_trust")


class AgentTrustSecurityException(Exception):
    """Raised when an untrusted or hostile target is rejected by pre-flight."""
    pass


class AgentTrustDeliverableException(Exception):
    """Raised when task deliverable output cannot be recovered by AST repair."""
    pass


class AgentTrustGuard:
    """
    Drop-in security middleware for AgentTrust autonomous workers.
    Enforces deterministic SSRF pre-flight filtering and AST deliverable recovery.
    """

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8000",
        api_key: Optional[str] = None,
        tenant_id: Optional[str] = None,
        timeout: float = 3.0
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.timeout = timeout
        self.tenant_id = tenant_id or os.getenv("BRISTLECONE_TENANT_ID") or "agent_trust_worker"
        self.api_key = api_key or os.getenv("BRISTLECONE_API_KEY") or self.tenant_id

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Tenant-ID": self.tenant_id
        }

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.gateway_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            if e.code == 402:
                raise PermissionError("Bristlecone x402 Tollbooth: Insufficient credits or invalid key.")
            raise RuntimeError(f"Bristlecone gateway error ({e.code}): {err_body}")

    def audit_target(self, url_or_domain: str) -> Dict[str, Any]:
        """
        Validates target host safety against Bristlecone's hardened CIDR engine.
        Rejects loopbacks, RFC 1918, RFC 1122, and AWS/GCP/Alibaba/Oracle IMDS.
        """
        parsed = urlparse(url_or_domain)
        target = parsed.hostname if parsed.hostname else url_or_domain
        target = target.split(":")[0].strip()

        result = self._post("/tools/audit-dns", {"domain": target})
        if not result.get("is_safe", False):
            reason = result.get("reason", "UNKNOWN_REFUSAL")
            logger.warning(f"SSRF violation prevented: {target} -> {reason}")
            raise AgentTrustSecurityException(f"Host '{target}' rejected: {reason}")

        return result

    def audit_spec_targets(self, job_spec: str) -> List[Dict[str, Any]]:
        """Extracts and verifies every URL present in an untrusted job spec."""
        urls = re.findall(r"https?://[^\s<>\"')]+", job_spec)
        results = []
        for url in urls:
            results.append(self.audit_target(url))
        return results

    def heal_deliverable(self, raw_deliverable: str) -> Dict[str, Any]:
        """
        Normalizes raw model text, stripping markdown blocks and repairing broken JSON.
        Ensures the payload satisfies RFC 8259 before referee evaluation.
        """
        result = self._post("/tools/repair-json", {"raw_json": raw_deliverable})
        if not result.get("valid", False):
            raise AgentTrustDeliverableException(f"Deliverable repair failed: {result.get('error')}")
        return result.get("repaired", {})
