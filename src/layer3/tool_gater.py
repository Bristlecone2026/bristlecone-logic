"""
Bristlecone Logic - Layer 3: ToolGater & Security Policy Engine
Enforces explicit permissions and sandboxed execution for external tools.
"""

from typing import Dict, Any, List
from src.layer1.taxonomy import TaskCategory


class ToolGater:
    """Zero-Trust Tool Policy Enforcement Engine."""

    # Explicit allowlist of permissible tools per category
    ALLOWED_TOOLS = {
        TaskCategory.DIRTY_WORK: ["pdf_parser", "web_scraper", "compliance_scanner"],
        TaskCategory.STRUCTURED: ["json_transformer", "schema_validator"],
        TaskCategory.COMMODITY: []  # No tool execution permitted on commodity tier
    }

    @classmethod
    def evaluate_and_execute(cls, category: TaskCategory, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates tool execution rights against category rules and runs approved tools.
        Raises PermissionError if tool access is unauthorized.
        """
        allowed = cls.ALLOWED_TOOLS.get(category, [])

        if tool_name not in allowed:
            raise PermissionError(
                f"Tool '{tool_name}' unauthorized for category [{category.value}]. Allowed tools: {allowed}"
            )

        # Mock sandboxed execution
        return {
            "tool_name": tool_name,
            "status": "EXECUTED",
            "sandboxed": True,
            "result_summary": f"Executed '{tool_name}' successfully with {len(params)} parameter(s)."
        }
