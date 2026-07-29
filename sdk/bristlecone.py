import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

class BristleconeClient:
    """
    Lightweight zero-dependency Python SDK for interacting with the Bristlecone M2M DAG API.
    """
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }
        encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
        
        req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"Bristlecone API Error ({e.code}): {error_body}") from e

    def submit_seedling(
        self, 
        project_id: int, 
        prompt: str, 
        model: str = "gpt-4o-mini", 
        extra_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submits a SEEDLING commit node to trigger autonomous agent processing.
        """
        payload = {
            "prompt": prompt,
            "model": model,
            **(extra_payload or {})
        }
        body = {
            "project_id": project_id,
            "agent_role": "seedling",
            "payload": payload
        }
        return self._request("POST", "/api/v1/dag/commits", data=body)

    def get_project_dag(self, project_id: int) -> Dict[str, Any]:
        """
        Retrieves the complete state graph for a project.
        """
        return self._request("GET", f"/api/v1/dag/projects/{project_id}")

    def wait_for_sapling(
        self, 
        seedling_id: str, 
        project_id: int, 
        timeout: float = 30.0, 
        poll_interval: float = 0.5
    ) -> Dict[str, Any]:
        """
        Polls the project DAG until a SAPLING node referencing the source seedling is returned.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            dag = self.get_project_dag(project_id)
            nodes = dag.get("nodes", [])
            for node in nodes:
                if node.get("agent_role") == "sapling" and node.get("payload", {}).get("source_commit_id") == seedling_id:
                    return node
            time.sleep(poll_interval)
        raise TimeoutError(f"Timed out waiting for SAPLING child node of {seedling_id}")
