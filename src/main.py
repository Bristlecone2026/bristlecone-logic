"""
Bristlecone Logic - Main FastAPI Engine
Exposes the M2M microservice pipeline wrapped with Layer 0 x402 payment gating.
"""

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from src.layer0.payment import verify_x402_payment
from src.orchestrator import Layer3Orchestrator

app = FastAPI(
    title="Bristlecone Logic M2M Engine",
    description="Zero-Trust M2M microservice pipeline with Layer 0 x402 payment enforcement.",
    version="1.0.0"
)

# Initialize Orchestrator
orchestrator = Layer3Orchestrator()


class M2MTaskRequest(BaseModel):
    intent: str = Field(..., description="Natural language intent or processing instruction")
    context_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata or parameters")


@app.get("/health")
async def health_check():
    return {"status": "HEALTHY", "service": "Bristlecone Logic M2M Engine"}


@app.post("/v1/execute-task")
async def execute_task(
    payload: M2MTaskRequest,
    payment_info: Dict[str, Any] = Depends(verify_x402_payment)
):
    """
    Main M2M Execution Endpoint:
    1. Layer 0: Payment verified via Depends(verify_x402_payment).
    2. Layers 1-5: Intent processed through Zero-Trust Orchestrator.
    3. Returns: Execution payload + payment receipt + cryptographic signature.
    """
    try:
        execution_result = await orchestrator.process_intent(
            user_intent=payload.intent,
            context=payload.context_data
        )

        return {
            "status": "SUCCESS",
            "payment": payment_info,
            "execution": execution_result
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Execution dropped by Zero-Trust Orchestrator: {str(e)}"
        )
