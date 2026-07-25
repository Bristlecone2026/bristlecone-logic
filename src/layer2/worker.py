"""
Bristlecone Logic - Layer 2: Worker Execution Engine
Processes sanitized tasks and determines execution steps or tool requirements.
"""

from typing import Dict, Any
from src.layer1.taxonomy import TaskCategory


class GeminiWorker:
    """Layer 2 Task Execution Engine."""

    async def execute_task(self, category: TaskCategory, intent: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes task logic based on taxonomy classification.
        In production, this handles Gemini API calls and prompt structuring.
        """
        requires_tools = (category == TaskCategory.DIRTY_WORK)

        return {
            "worker_status": "COMPLETED",
            "category": category.value,
            "requires_tools": requires_tools,
            "output": f"Successfully processed [{category.value}] workload.",
            "execution_metadata": {
                "estimated_tokens": len(intent.split()) * 4 + 100,
                "context_keys": list(context.keys())
            }
        }
