from typing import Callable, Dict, Any, List
from pydantic import BaseModel, Field


class MCPToolDefinition(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any]


class MCPRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, MCPToolDefinition] = {}

    def register_tool(self, name: str, description: str, schema: Dict[str, Any]):
        def decorator(func: Callable):
            self._tools[name] = func
            self._schemas[name] = MCPToolDefinition(
                name=name,
                description=description,
                parameters_schema=schema
            )
            return func
        return decorator

    def list_tools(self) -> List[MCPToolDefinition]:
        return list(self._schemas.values())

    async def execute_tool(self, name: str, kwargs: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered in the MCP Registry.")
        return await self._tools[name](**kwargs)


mcp_registry = MCPRegistry()
