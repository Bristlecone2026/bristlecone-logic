"""
Bristlecone Logic - Orchestrator
Coordinates Layer 1 classification, Layer 2 execution, Layer 3 tool gating, and Layer 4 telemetry.
"""

from typing import Dict, Any, Optional
from src.layer1.taxonomy import TaxonomyEngine
from src.layer2.worker import GeminiWorker
from src.layer3.tool_gater import ToolGater
from src.layer4.audit_logger import AuditLogger


class Layer3Orchestrator:
    def __init__(self):
        self.taxonomy = TaxonomyEngine()
        self.worker = GeminiWorker()
        self.tool_gater = ToolGater()
        self.audit_logger = AuditLogger()

    async def process_intent(self, user_intent: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes intent through the pipeline:
        1. Layer 1: Sanitize & Classify Intent
        2. Layer 2: Gemini Worker Processing
        3. Layer 3: ToolGater Security Check & Tool Dispatch (if required)
        4. Layer 4: Audit Logging & Immutable Telemetry
        """
        context = context or {}

        # Layer 1 Processing
        category, taxonomy_meta = self.taxonomy.classify_and_validate(user_intent, context)

        # Layer 2 Processing
        worker_result = await self.worker.execute_task(category, taxonomy_meta["sanitized_intent"], context)

        # Layer 3 Processing (Dynamic Tool Gating)
        tool_execution_result = None
        if worker_result.get("requires_tools"):
            requested_tool = context.get("tool_name", "web_scraper")
            tool_params = context.get("tool_params", {})
            tool_execution_result = self.tool_gater.evaluate_and_execute(category, requested_tool, tool_params)

        pipeline_data = {
            "intent": taxonomy_meta["sanitized_intent"],
            "category": category.value,
            "status": "PROCESSED",
            "taxonomy_metadata": taxonomy_meta,
            "worker_result": worker_result,
            "tool_execution": tool_execution_result,
            "pipeline_stage": "Layer4_Telemetry_Passed"
        }

        # Layer 4 Telemetry Envelope (Pass snapshot to prevent circular reference)
        telemetry_envelope = self.audit_logger.record_telemetry(
            intent=taxonomy_meta["sanitized_intent"],
            category=category.value,
            result_data=dict(pipeline_data)
        )

        pipeline_data["telemetry"] = telemetry_envelope
        return pipeline_data
