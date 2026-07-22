from app.layer2_microservices.router import execute_task
from app.layer2_microservices.schemas import TaskExecutionRequest
from app.layer3_orchestration.nodes import WorkerNode, InvigilatorNode, EvaluatorNode
from app.layer3_orchestration.state import AgentState, GraphStatus
from app.layer4_crypto.signer import PayloadSigner
from app.layer5_audit.logger import AuditLogger


class AgentGraphOrchestrator:
    """Executes the state graph loop with Layer 4 signing and Layer 5 audit logging."""

    @classmethod
    async def run(cls, user_goal: str) -> AgentState:
        state = AgentState(user_goal=user_goal)
        AuditLogger.log_event("SESSION_STARTED", {"user_goal": user_goal})

        while state.status not in (GraphStatus.COMPLETED, GraphStatus.FAILED):
            # Step 1: Worker Node drafts action
            state = await WorkerNode.process(state)
            AuditLogger.log_event("WORKER_DRAFT_CREATED", {
                "iteration": state.iteration_count,
                "task_draft": state.task_draft
            })

            # Step 2: Invigilator Node checks action safety
            state = await InvigilatorNode.process(state)
            AuditLogger.log_event("INVIGILATOR_CHECKED", {
                "iteration": state.iteration_count,
                "approved": state.invigilator_approved,
                "reason": state.rejection_reason
            })

            if not state.invigilator_approved:
                if state.status == GraphStatus.FAILED:
                    AuditLogger.log_event("WORKFLOW_FAILED", {"reason": state.rejection_reason})
                    break
                continue

            # Step 3: Layer 4 Sign Approved Payload
            payload_to_sign = {
                "task_id": state.task_draft["task_id"],
                "task_type": state.task_draft["task_type"],
                "priority": state.task_draft["priority"],
                "payload": state.task_draft["payload"],
            }
            signature = PayloadSigner.sign_payload(payload_to_sign)
            state.task_draft["signature"] = signature
            AuditLogger.log_event("PAYLOAD_SIGNED", {
                "task_id": state.task_draft["task_id"],
                "signature": signature
            })

            # Step 4: Layer 2 Execution
            state.status = GraphStatus.EXECUTING
            request_schema = TaskExecutionRequest(**state.task_draft)
            response = await execute_task(request_schema)
            state.execution_result = response.model_dump()
            AuditLogger.log_event("TASK_EXECUTED", {
                "task_id": state.task_draft["task_id"],
                "result": state.execution_result
            })

            # Step 5: Evaluator Node assesses outcome
            state = await EvaluatorNode.process(state)
            AuditLogger.log_event("EVALUATOR_VERIFIED", {
                "feedback": state.evaluator_feedback,
                "status": state.status.value
            })

        AuditLogger.log_event("SESSION_FINISHED", {
            "final_status": state.status.value,
            "total_iterations": state.iteration_count
        })

        return state
