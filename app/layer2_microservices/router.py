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
