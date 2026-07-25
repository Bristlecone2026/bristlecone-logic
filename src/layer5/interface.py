"""
Bristlecone Logic - Layer 5: External Interface Engine
Standardizes M2M JSON payloads and guarantees API response protocol compliance.
"""

import time
from typing import Dict, Any


class ExternalInterface:
    """Layer 5 External API Protocol Handler."""

    @classmethod
    def format_m2m_response(cls, pipeline_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Formats raw orchestrator output into a standardized M2M payload response.
        """
        return {
            "protocol": "BRISTLECONE-M2M-v1",
            "timestamp": time.time(),
            "status": "SUCCESS",
            "execution": pipeline_output
        }
