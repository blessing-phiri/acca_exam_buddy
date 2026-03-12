"""
API service for frontend-backend communication
"""

from typing import Optional, Dict, Any
import requests


class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    def health_check(self) -> bool:
        """Check if backend is healthy."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def upload_file(self, file, paper: str, question: Optional[str] = None) -> Dict[str, Any]:
        """Upload a file for marking."""
        url = f"{self.base_url}/api/v1/upload"
        files = {"file": (file.name, file, file.type)}
        data = {"paper": paper}
        if question:
            data["question_number"] = question

        response = requests.post(url, files=files, data=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_status(self, upload_id: str) -> Dict[str, Any]:
        """Get processing status."""
        url = f"{self.base_url}/api/v1/status/{upload_id}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_result(self, result_id: str) -> Dict[str, Any]:
        """Get marking result."""
        url = f"{self.base_url}/api/v1/result/{result_id}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_knowledge_stats(self) -> Dict[str, Any]:
        """Get knowledge base stats."""
        url = f"{self.base_url}/api/v1/knowledge/stats"
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()

    def trigger_scrape(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger ACCA resource scraping and ingestion."""
        url = f"{self.base_url}/api/v1/knowledge/scrape/run"
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    def list_knowledge_documents(self, collection: Optional[str] = None, document_type: Optional[str] = None) -> Dict[str, Any]:
        """List knowledge base document registry entries."""
        url = f"{self.base_url}/api/v1/knowledge/documents"
        params: Dict[str, Any] = {}
        if collection:
            params["collection"] = collection
        if document_type:
            params["document_type"] = document_type
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

# Default client used by the app; no UI side effects here.
api_client = APIClient()

