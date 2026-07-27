import os
import requests
from typing import Optional, Dict, Any

API_URL = os.getenv("API_URL", "http://api:8000")

class APIClient:
    def __init__(self, base_url: str = API_URL):
        self.base_url = base_url.rstrip("/")

    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate with FastAPI OAuth2 password flow."""
        url = f"{self.base_url}/api/v1/auth/token"
        payload = {"username": username, "password": password}
        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException:
            return None

    def get_me(self, token: str) -> Optional[Dict[str, Any]]:
        """Fetch current authenticated user details."""
        url = f"{self.base_url}/api/v1/users/me"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException:
            return None

    def run_agent(self, token: str, intent: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Trigger an agent orchestration workflow."""
        url = f"{self.base_url}/api/v1/agent/run"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"intent": intent, "context": context or {}}
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}: {response.text}"}
        except requests.RequestException as e:
            return {"error": str(e)}
