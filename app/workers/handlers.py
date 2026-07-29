import logging
import os
import httpx
from typing import Dict, Any
from uuid import UUID
from app.database import AsyncSessionLocal
from app.models.dag import DendroRole
from app.services.dag_service import create_commit_node

logger = logging.getLogger("bristlecone.workers")

async def call_llm_provider(prompt: str, model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """
    Calls an OpenAI-compatible LLM endpoint if LLM_API_KEY or OPENAI_API_KEY is set.
    Falls back to structured synthetic completion if unconfigured.
    """
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    
    if not api_key:
        logger.info("[Layer 2 Worker] No LLM_API_KEY detected. Operating in mock/fallback mode.")
        return {
            "text": f"[MOCK AGENT EXECUTION] Completed task for prompt: '{prompt}'",
            "provider": "mock",
            "model": model
        }

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an autonomous M2M execution agent in the Bristlecone network. Execute the task concisely and return a structured response."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
            completion_text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "text": completion_text,
                "provider": "openai_compatible",
                "model": model,
                "usage": usage
            }
        except Exception as e:
            logger.error(f"[Layer 2 Worker] LLM API Call Failed: {e}")
            return {
                "text": f"EXECUTION ERROR: Failed to execute LLM provider task ({str(e)})",
                "provider": "error_fallback",
                "model": model
            }

async def process_seedling_commit(
    commit_id: UUID,
    organization_id: int,
    project_id: int,
    payload: Dict[str, Any]
) -> None:
    """
    Layer 2 Worker Task: Processes an incoming SEEDLING commit node,
    invokes LLM/Agent execution on the prompt, and posts a
    SAPLING child node containing the response.
    """
    logger.info(f"[Layer 2 Worker] Processing SEEDLING commit: {commit_id}")
    
    prompt = (
        payload.get("prompt") or 
        payload.get("task") or 
        payload.get("input") or 
        payload.get("status") or 
        "Execute default agent workflow"
    )
    model = payload.get("model", "gpt-4o-mini")

    llm_result = await call_llm_provider(prompt=prompt, model=model)
    
    output_payload = {
        "source_commit_id": str(commit_id),
        "status": "completed",
        "prompt": prompt,
        "execution": llm_result,
        "metadata": {
            "agent_engine": "bristlecone-v2-llm-worker"
        }
    }
    
    async with AsyncSessionLocal() as session:
        try:
            sapling_node = await create_commit_node(
                db=session,
                organization_id=organization_id,
                project_id=project_id,
                agent_role=DendroRole.SAPLING,
                payload=output_payload,
                parent_ids=[commit_id]
            )
            logger.info(
                f"[Layer 2 Worker] Successfully created SAPLING commit: {sapling_node.id} "
                f"linked to parent {commit_id}"
            )
        except Exception as e:
            logger.error(f"[Layer 2 Worker] Failed to process SEEDLING commit {commit_id}: {e}")
