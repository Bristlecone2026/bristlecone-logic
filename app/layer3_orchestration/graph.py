from app.layer2_microservices.router import execute_task
from app.layer2_microservices.schemas import TaskExecutionRequest
from app.layer3_orchestration.nodes import WorkerNode, InvigilatorNode, EvaluatorNode
from app.layer3_orchestration.state import AgentState, GraphStatus
from app.layer4_crypto.signer import PayloadSigner


class AgentGraphOrchestrator:
    """Executes the Worker-Invigilator-Layer2-Evaluator state graph loop with Layer 4 signing."""

    @classmethod
    async def run(cls, user_goal: str) -> AgentState:
        state = AgentState(user_goal=user_goal)

        while state.status not in (GraphStatus.COMPLETED, GraphStatus.FAILED):
            # Step 1: Worker Node drafts action
            state = await WorkerNode.process(state)

            # Step 2: Invigilator Node checks action safety
            state = await InvigilatorNode.process(state)

            if not state.invigilator_approved:
                if state.status == GraphStatus.FAILED:
                    break
                continue

            # Step 3: Layer 4 Sign Approved Payload
            payload_to_sign = {
                "task_id": state.task_draft["task_id"],
                "task_type": state.task_draft["task_type"],
                "priority": state.task_draft["priority"],
                "payload": state.task_draft["payload"],
            }
            state.task_draft["signature"] = PayloadSigner.sign_payload(payload_to_sign)

            # Step 4: Layer 2 Execution (Signature Verified)
            state.status = GraphStatus.EXECUTING
            request_schema = TaskExecutionRequest(**state.task_draft)
            response = await execute_task(request_schema)
            state.execution_result = response.model_dump()

            # Step 5: Evaluator Node assesses outcome
            state = await EvaluatorNode.process(state)

        return state
