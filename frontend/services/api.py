"""API service for frontend-backend communication."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(method=method, url=url, **kwargs)
        except requests.RequestException as exc:
            raise RuntimeError(f"Network request failed: {exc}") from exc

        if response.ok:
            if not response.text:
                return {}
            return response.json()

        detail = None
        try:
            payload = response.json()
            detail = payload.get("detail")
        except Exception:  # noqa: BLE001
            detail = response.text

        if isinstance(detail, dict):
            message = detail.get("error") or detail.get("message") or str(detail)
        else:
            message = str(detail) if detail else f"HTTP {response.status_code}"

        raise RuntimeError(f"API error ({response.status_code}): {message}")

    def health_check(self) -> bool:
        """Check if backend is healthy."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def upload_file(self, file, paper: str, question: Optional[str] = None) -> Dict[str, Any]:
        """Upload a file for marking."""
        files = {"file": (file.name, file, getattr(file, "type", "application/octet-stream"))}
        data = {"paper": paper}
        if question:
            data["question_number"] = question

        return self._request("POST", "/api/v1/upload", files=files, data=data, timeout=30)

    def get_status(self, upload_id: str) -> Dict[str, Any]:
        """Get processing status."""
        return self._request("GET", f"/api/v1/status/{upload_id}", timeout=15)

    def get_result(self, result_id: str) -> Dict[str, Any]:
        """Get marking result."""
        return self._request("GET", f"/api/v1/result/{result_id}", timeout=30)

    def get_marking_types(self) -> Dict[str, Any]:
        """Get supported marking question types."""
        return self._request("GET", "/api/v1/mark/types", timeout=15)

    def get_llm_health(self) -> Dict[str, Any]:
        """Get LLM provider health diagnostics."""
        return self._request("GET", "/api/v1/mark/llm-health", timeout=40)

    def get_knowledge_stats(self) -> Dict[str, Any]:
        """Get knowledge base stats."""
        return self._request("GET", "/api/v1/knowledge/stats", timeout=20)

    def trigger_scrape(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger ACCA resource scraping and ingestion."""
        return self._request("POST", "/api/v1/knowledge/scrape/run", json=payload, timeout=120)

    def list_knowledge_documents(
        self,
        collection: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List knowledge base document registry entries."""
        params: Dict[str, Any] = {}
        if collection:
            params["collection"] = collection
        if document_type:
            params["document_type"] = document_type
        return self._request("GET", "/api/v1/knowledge/documents", params=params, timeout=20)


# Default client used by the app; no UI side effects here.
api_client = APIClient()
