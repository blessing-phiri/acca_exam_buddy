"""Integration tests for marking API endpoints."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient


def _get_client() -> TestClient:
    os.environ["MARKING_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "hash"
    from backend.main import app

    return TestClient(app)


def test_mark_endpoint_schema() -> None:
    client = _get_client()
    payload = {
        "question_text": "Identify and explain TWO audit risks.",
        "student_answer": "There is a risk of revenue overstatement and poor receivables recoverability.",
        "max_marks": 8,
        "paper_code": "AA",
    }

    response = client.post("/api/v1/mark/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert 0 <= data["total_marks"] <= payload["max_marks"]
    assert data["max_marks"] == payload["max_marks"]
    assert isinstance(data["question_marks"], list)
    assert isinstance(data["professional_marks"], dict)
    assert isinstance(data["citations"], list)


def test_batch_endpoint_and_status() -> None:
    client = _get_client()
    payload = {
        "paper_code": "AA",
        "answers": [
            {
                "question_text": "Explain one ethical threat.",
                "student_answer": "Familiarity threat may arise when the auditor has worked too long with the client.",
                "max_marks": 4,
            }
        ],
    }

    response = client.post("/api/v1/mark/batch", json=payload)
    assert response.status_code == 200
    batch = response.json()

    status_response = client.get(f"/api/v1/mark/batch/{batch['batch_id']}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["batch_id"] == batch["batch_id"]
    assert status_payload["total"] == 1
