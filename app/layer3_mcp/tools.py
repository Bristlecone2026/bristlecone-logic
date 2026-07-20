import platform
from app.layer3_mcp.mcp_registry import mcp_registry


@mcp_registry.register_tool(
    name="get_node_telemetry",
    description="Retrieves local system environment metrics and OS telemetry.",
    schema={
        "type": "object",
        "properties": {
            "verbose": {"type": "boolean", "description": "Include extended platform details"}
        },
        "required": []
    }
)
async def get_node_telemetry(verbose: bool = False) -> dict:
    data = {
        "system": platform.system(),
        "release": platform.release(),
        "python_version": platform.python_version(),
    }
    if verbose:
        data["processor"] = platform.processor()
        data["architecture"] = platform.architecture()[0]
    return data
