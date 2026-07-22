import uuid
from app.layer2_microservices.schemas import TaskType, TaskPriority
from app.layer3_orchestration.state import AgentState, GraphStatus


class WorkerNode:
    """Drafts microservice task payloads based on the user goal or feedback."""

    @staticmethod
    async def process(state: AgentState) -> AgentState:
        state.status = GraphStatus.WORKING
        state.iteration_count += 1

        # Example deterministic task generation based on goal keywords
        goal = state.user_goal.lower()
        
        if "clean" in goal or "records" in goal:
            task_type = TaskType.DATA_CLEANING
            payload = {"records": [1, 2, 3, 4, 5]}
        elif "inspect" in goal or "health" in goal:
            task_type = TaskType.SYSTEM_INSPECTION
            payload = {"target": "localhost"}
        else:
            task_type = TaskType.TRANSFORMATION
            payload = {"source": "raw_feed", "key": "value"}

        # Build draft
        state.task_draft = {
            "task_id": f"task-{uuid.uuid4().hex[:8]}",
            "task_type": task_type.value,
            "priority": TaskPriority.HIGH.value,
            "payload": payload,
            "timeout_seconds": 30,
        }

        # If previous iteration was rejected, attempt correction logic
        if state.rejection_reason:
            state.task_draft["payload"]["corrected"] = True

        return state


class InvigilatorNode:
    """The Proctor: Enforces safety policy, loop caps, and schema rules before execution."""

    ALLOWED_TARGETS = {"localhost", "node-1", "127.0.0.1"}

    @classmethod
    async def process(cls, state: AgentState) -> AgentState:
        state.status = GraphStatus.INVIGILATING

        # Safeguard 1: Loop threshold check
        if state.iteration_count > state.max_iterations:
            state.invigilator_approved = False
            state.rejection_reason = f"Exceeded max iterations limit ({state.max_iterations})"
            state.status = GraphStatus.FAILED
            return state

        draft = state.task_draft
        if not draft:
            state.invigilator_approved = False
            state.rejection_reason = "Missing task draft"
            state.status = GraphStatus.REJECTED
            return state

        # Safeguard 2: Target verification for system inspection
        payload = draft.get("payload", {})
        if draft.get("task_type") == TaskType.SYSTEM_INSPECTION.value:
            target = payload.get("target")
            if target not in cls.ALLOWED_TARGETS:
                state.invigilator_approved = False
                state.rejection_reason = f"Unauthorized target '{target}'"
                state.status = GraphStatus.REJECTED
                return state

        # Approval granted
        state.invigilator_approved = True
        state.rejection_reason = None
        state.status = GraphStatus.APPROVED
        return state


class EvaluatorNode:
    """The Judge: Inspects output after Layer 2 execution to confirm task resolution."""

    @staticmethod
    async def process(state: AgentState) -> AgentState:
        state.status = GraphStatus.EVALUATING

        result = state.execution_result
        if result and result.get("status") == "completed":
            state.status = GraphStatus.COMPLETED
            state.evaluator_feedback = "Task executed and verified successfully."
        else:
            state.status = GraphStatus.REJECTED
            state.evaluator_feedback = "Execution returned incomplete status."

        return state
