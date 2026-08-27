"""Bristlecone Logic™ Framework Integrations."""

__all__ = [
    "BristleconeJsonRepairTool",
    "BristleconeSafeEvalTool",
    "BristleconeDnsAuditTool",
    "repair_json_tool",
    "safe_eval_tool",
    "audit_dns_tool",
]


def __getattr__(name: str):
    if name in {"BristleconeJsonRepairTool", "BristleconeSafeEvalTool", "BristleconeDnsAuditTool"}:
        from .langchain import BristleconeJsonRepairTool, BristleconeSafeEvalTool, BristleconeDnsAuditTool
        return locals()[name]
    if name in {"repair_json_tool", "safe_eval_tool", "audit_dns_tool"}:
        from .crewai import repair_json_tool, safe_eval_tool, audit_dns_tool
        return locals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
