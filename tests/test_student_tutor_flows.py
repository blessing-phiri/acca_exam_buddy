"""Integration tests for typed answer and tutor guide upload flows."""

from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient


def _get_client() -> TestClient:
    os.environ["MARKING_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "hash"
    from backend.main import app

    return TestClient(app)


def test_upload_text_answer_flow() -> None:
    client = _get_client()
    payload = {
        "question_text": "Explain two audit risks and suitable responses.",
        "answer_text": "Revenue may be overstated due to management pressure. The auditor should perform cut-off testing and inspect supporting contracts.",
        "paper": "AA",
        "question_number": "1(a)",
        "max_marks": 8,
    }

    response = client.post("/api/v1/upload/text", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["status"] == "complete"
    assert data.get("result_id")
    result = data.get("result", {})
    assert 0 <= float(result.get("total_marks", 0)) <= 8


def test_tutor_upload_guide_flow() -> None:
    client = _get_client()

    content = (
        "Audit risks should be specific to the scenario and linked to assertions. "
        "Award one mark for each valid risk and one mark for a practical auditor response. "
    ) * 3

    response = client.post(
        "/api/v1/knowledge/upload-guide",
        files={"file": ("custom_guide.txt", io.BytesIO(content.encode("utf-8")), "text/plain")},
        data={
            "doc_type": "technical_article",
            "paper": "AA",
            "year": "2026",
            "question_type": "audit_risk",
            "notes": "Tutor custom guide",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["doc_type"] == "technical_article"
    assert data.get("saved_path")
    ingestion = data.get("ingestion", {})
    assert ingestion.get("success") is True
