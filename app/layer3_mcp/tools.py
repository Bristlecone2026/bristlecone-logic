import os
import platform
from typing import Optional
from app.layer3_mcp.mcp_registry import mcp_registry

WORKSPACE_DIR = "/tmp/bristlecone_workspace"
STATE_STORE = {}

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

@mcp_registry.register_tool(
    name="sandboxed_file_writer",
    description="Writes file content safely inside a dedicated workspace directory.",
    schema={
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Target filename to create or overwrite"},
            "content": {"type": "string", "description": "Text content to write to the file"}
        },
        "required": ["filename", "content"]
    }
)
async def sandboxed_file_writer(filename: str, content: str) -> dict:
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(WORKSPACE_DIR, safe_filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "status": "success",
        "file_path": file_path,
        "bytes_written": len(content)
    }

@mcp_registry.register_tool(
    name="system_state_store",
    description="Gets or sets key-value runtime state in memory.",
    schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get", "set"], "description": "State operation to perform"},
            "key": {"type": "string", "description": "State variable key name"},
            "value": {"type": "string", "description": "Value to set (required for 'set')"}
        },
        "required": ["action", "key"]
    }
)
async def system_state_store(action: str, key: str, value: Optional[str] = None) -> dict:
    if action == "set":
        STATE_STORE[key] = value
        return {"status": "updated", "key": key, "value": value}
    elif action == "get":
        val = STATE_STORE.get(key, None)
        return {"status": "retrieved", "key": key, "value": val}
    else:
        raise ValueError(f"Unsupported action '{action}'")
