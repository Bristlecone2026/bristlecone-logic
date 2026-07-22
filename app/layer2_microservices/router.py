import time
from fastapi import APIRouter
from app.layer1_schemas.base import AgentTaskRequest, AgentTaskResponse, AgentStatus
from app.layer3_mcp.mcp_registry import mcp_registry
from app.layer4_ledgers.treasury import treasury
from app.layer5_telemetry.evaluator import telemetry_judge
import app.layer3_mcp.tools  # Register tools on import

router = APIRouter(prefix="/task", tags=["Layer 2 Microservices"])

@router.get("/mcp/tools")
async def list_mcp_tools():
    return {"available_tools": mcp_registry.list_tools()}

@router.get("/treasury/status")
async def get_treasury_status():
    return treasury.get_treasury_summary()

@router.get("/telemetry/summary")
async def get_telemetry_summary():
    return telemetry_judge.get_telemetry_summary()

@router.post("/execute", response_model=AgentTaskResponse)
async def execute_task(request: AgentTaskRequest) -> AgentTaskResponse:
    start_time = time.time()

    if request.action == "ping":
        result_data = {
            "message": "Pong from Layer 2 microservice node",
            "received_params": request.parameters
        }
        status = AgentStatus.COMPLETED
        error_msg = None

    elif request.action == "cambium_data":
        operation = request.parameters.get("operation", "summarize_keys")
        payload = request.parameters.get("payload", {})
        try:
            if operation == "transform_uppercase" and isinstance(payload, str):
                processed = payload.upper()
            elif operation == "summarize_keys" and isinstance(payload, dict):
                processed = {"key_count": len(payload.keys()), "keys": list(payload.keys())}
            else:
                processed = {"processed_payload": payload, "operation": operation}

            result_data = {
                "handler": "cambium_data_processor",
                "operation": operation,
                "output": processed
            }
            status = AgentStatus.COMPLETED
            error_msg = None
        except Exception as e:
            result_data = None
            status = AgentStatus.FAILED
            error_msg = f"Cambium data error: {str(e)}"

    elif request.action == "seedling_batch":
        items = request.parameters.get("items", [])
        if not isinstance(items, list):
            result_data = None
            status = AgentStatus.FAILED
            error_msg = "Parameter 'items' must be a list"
        else:
            processed_items = [
                {"sub_id": idx + 1, "status": "completed", "data": item}
                for idx, item in enumerate(items)
            ]
            result_data = {
                "handler": "seedling_batch_processor",
                "total_processed": len(processed_items),
                "items": processed_items
            }
            status = AgentStatus.COMPLETED
            error_msg = None

    elif request.action == "mcp_tool":
        tool_name = request.parameters.get("tool_name")
        tool_args = request.parameters.get("args", {})
        try:
            result_data = await mcp_registry.execute_tool(tool_name, tool_args)
            status = AgentStatus.COMPLETED
            error_msg = None
        except Exception as e:
            result_data = None
            status = AgentStatus.FAILED
            error_msg = str(e)

    elif request.action == "financial_transfer":
        amount = request.parameters.get("amount_usd", 0.0)
        if treasury.verify_transaction_safety(amount):
            result_data = {
                "transfer_status": "approved",
                "amount_usd": amount,
                "ledger": "XRPL/Mercury"
            }
            status = AgentStatus.COMPLETED
            error_msg = None
        else:
            result_data = None
            status = AgentStatus.FAILED
            error_msg = f"Transaction amount ${amount} exceeds financial safety gate limit (${treasury.max_single_tx_usd})"

    else:
        result_data = None
        status = AgentStatus.FAILED
        error_msg = f"Unknown or unauthorized action '{request.action}'"

    execution_ms = (time.time() - start_time) * 1000

    # Layer 5 Telemetry & Quality Evaluation
    telemetry_judge.log_and_evaluate(
        task_id=request.task_id,
        action=request.action,
        status=status.value,
        execution_time_ms=execution_ms
    )

    return AgentTaskResponse(
        task_id=request.task_id,
        status=status,
        result=result_data,
        error=error_msg,
        execution_time_ms=round(execution_ms, 2)
    )
import time
from fastapi import APIRouter, HTTPException, status
from app.layer2_microservices.schemas import (
    TaskExecutionRequest,
    TaskExecutionResponse,
    TaskType,
)

router = APIRouter(tags=["Layer 2 Microservices"])

@router.post(
    "/tasks/execute",
    response_model=TaskExecutionResponse,
    summary="Execute Layer 2 Microservice Routine",
)
async def execute_task(request: TaskExecutionRequest) -> TaskExecutionResponse:
    start_time = time.perf_counter()

    # Deterministic microservice execution dispatch
    if request.task_type == TaskType.DATA_CLEANING:
        result = {"processed_records": len(request.payload.get("records", [])), "status": "cleaned"}
    elif request.task_type == TaskType.SYSTEM_INSPECTION:
        result = {"cpu_check": "ok", "memory_check": "ok", "target": request.payload.get("target", "localhost")}
    elif request.task_type == TaskType.TRANSFORMATION:
        result = {"transformed_keys": list(request.payload.keys())}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported task type: {request.task_type}",
        )

    execution_time = (time.perf_counter() - start_time) * 1000

    return TaskExecutionResponse(
        task_id=request.task_id,
        status="completed",
        execution_time_ms=round(execution_time, 2),
        result=result,
    )
import time
from fastapi import APIRouter, HTTPException, status
from app.layer2_microservices.schemas import (
    TaskExecutionRequest,
    TaskExecutionResponse,
    TaskType,
)
from app.layer4_crypto.signer import PayloadSigner

router = APIRouter(tags=["Layer 2 Microservices"])

@router.post(
    "/tasks/execute",
    response_model=TaskExecutionResponse,
    summary="Execute Layer 2 Microservice Routine",
)
async def execute_task(request: TaskExecutionRequest) -> TaskExecutionResponse:
    start_time = time.perf_counter()

    # Layer 4 Cryptographic Verification Gate
    payload_to_verify = {
        "task_id": request.task_id,
        "task_type": request.task_type.value,
        "priority": request.priority.value,
        "payload": request.payload,
    }
    
    if not PayloadSigner.verify_signature(payload_to_verify, request.signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Layer 4 Signature Verification Failed: Tampered or unsigned payload detected",
        )

    # Deterministic microservice execution dispatch
    if request.task_type == TaskType.DATA_CLEANING:
        result = {"processed_records": len(request.payload.get("records", [])), "status": "cleaned"}
    elif request.task_type == TaskType.SYSTEM_INSPECTION:
        result = {"cpu_check": "ok", "memory_check": "ok", "target": request.payload.get("target", "localhost")}
    elif request.task_type == TaskType.TRANSFORMATION:
        result = {"transformed_keys": list(request.payload.keys())}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported task type: {request.task_type}",
        )

    execution_time = (time.perf_counter() - start_time) * 1000

    return TaskExecutionResponse(
        task_id=request.task_id,
        status="completed",
        execution_time_ms=round(execution_time, 2),
        result=result,
    )
