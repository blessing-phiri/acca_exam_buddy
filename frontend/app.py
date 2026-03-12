"""Streamlit frontend for ACCA AA AI Marker."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

try:
    from frontend.services.api import APIClient
except ImportError:
    from services.api import APIClient


BACKEND_URL = os.getenv("API_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1"))


def _init_state() -> None:
    defaults: Dict[str, Any] = {
        "last_result": None,
        "last_upload_id": None,
        "last_run_at": None,
        "jobs": [],
        "llm_health": None,
        "llm_health_checked_at": None,
        "kb_stats": None,
        "kb_stats_checked_at": None,
        "ui_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _fmt_dt(raw: Optional[str]) -> str:
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return raw


def _status_label(status: str) -> str:
    mapping = {
        "pending": "Queued",
        "extracting": "Extracting text",
        "cleaning": "Cleaning content",
        "analyzing": "Analyzing answer",
        "marking": "Marking with engine",
        "complete": "Complete",
        "completed": "Complete",
        "failed": "Failed",
    }
    return mapping.get((status or "").lower(), status or "Unknown")


def _status_help(status: str) -> str:
    mapping = {
        "pending": "Waiting for worker to start.",
        "extracting": "Reading and extracting document text.",
        "cleaning": "Normalizing extracted content.",
        "analyzing": "Detecting question structure and metadata.",
        "marking": "Scoring against marking guidance.",
        "complete": "Result is available.",
        "completed": "Result is available.",
        "failed": "Processing failed. Check details and retry.",
    }
    return mapping.get((status or "").lower(), "")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return fallback


def _job_index(upload_id: str) -> int:
    for idx, job in enumerate(st.session_state.jobs):
        if job.get("upload_id") == upload_id:
            return idx
    return -1


def _upsert_job(job: Dict[str, Any]) -> None:
    job["updated_at"] = datetime.now().isoformat()
    idx = _job_index(job["upload_id"])
    if idx >= 0:
        existing = st.session_state.jobs[idx]
        merged = {**existing, **job}
        st.session_state.jobs[idx] = merged
    else:
        st.session_state.jobs.insert(0, job)


def _refresh_single_job(api_client: APIClient, upload_id: str, fetch_result: bool = False) -> Dict[str, Any]:
    status_payload = api_client.get_status(upload_id)
    updated_job = {
        "upload_id": upload_id,
        "status": status_payload.get("status", "unknown"),
        "progress": int(status_payload.get("progress", 0)),
        "result_id": status_payload.get("result_id"),
        "updated_at": status_payload.get("updated_at") or datetime.now().isoformat(),
    }
    _upsert_job(updated_job)

    if fetch_result and status_payload.get("result_id"):
        result = api_client.get_result(status_payload["result_id"])
        st.session_state.last_result = result
        st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return status_payload


def _refresh_active_jobs(api_client: APIClient) -> None:
    for job in list(st.session_state.jobs):
        status = (job.get("status") or "").lower()
        if status in {"complete", "completed", "failed"}:
            continue
        try:
            _refresh_single_job(api_client, job["upload_id"], fetch_result=True)
        except Exception as exc:  # noqa: BLE001
            _upsert_job({
                "upload_id": job["upload_id"],
                "status": "failed",
                "error": str(exc),
            })


def _summarize_professional_marks(prof: Dict[str, Any]) -> tuple[float, float]:
    if not prof:
        return 0.0, 0.0
    total = sum(_safe_float(v, 0.0) for v in prof.values())
    max_score = max(2.0, len(prof) * 0.5)
    return total, max_score


st.set_page_config(
    page_title="ACCA AA AI Marker",
    page_icon=":ledger:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_init_state()
api_client = APIClient(BACKEND_URL)

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Source+Sans+3:wght@400;600;700&display=swap');

        :root {
            --brand-ink: #0b3a35;
            --brand-primary: #0f766e;
            --brand-secondary: #115e59;
            --brand-soft: #d9f3ee;
            --surface: #ffffff;
            --surface-muted: #f7fbfa;
            --edge: #d8e5e2;
            --danger: #a73131;
            --ok: #1f7a44;
            --text-muted: #4d6460;
        }

        html, body, [class*="css"] {
            font-family: "Source Sans 3", sans-serif;
            color: var(--brand-ink);
        }

        .stApp {
            background: radial-gradient(circle at top right, #eaf8f5 0%, #f7fbfa 42%, #ffffff 100%);
        }

        .hero {
            background: linear-gradient(125deg, #0f766e 0%, #115e59 45%, #134e4a 100%);
            border-radius: 18px;
            padding: 24px;
            color: #f3fffd;
            border: 1px solid rgba(255, 255, 255, 0.2);
            margin-bottom: 14px;
            box-shadow: 0 10px 30px rgba(15, 118, 110, 0.18);
        }

        .hero h1 {
            font-family: "Space Grotesk", sans-serif;
            margin: 0;
            font-size: 2.1rem;
            line-height: 1.15;
            letter-spacing: -0.02em;
        }

        .hero p {
            margin: 10px 0 0;
            opacity: 0.95;
            font-size: 1.02rem;
        }

        .info-card {
            background: var(--surface);
            border: 1px solid var(--edge);
            border-radius: 14px;
            padding: 12px 14px;
        }

        .small-muted {
            color: var(--text-muted);
            font-size: 0.92rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>ACCA AA AI Marker</h1>
        <p>Production workflow for upload, extraction, AI marking, and explainable feedback.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

backend_ok = api_client.health_check()

with st.sidebar:
    st.header("Operations")
    st.caption("Runtime health and controls")
    st.markdown(f"**Backend URL**\n\n`{BACKEND_URL}`")

    if backend_ok:
        st.success("Backend: online")
    else:
        st.error("Backend: offline")
        st.caption("Start backend with: `uvicorn backend.main:app --reload`")

    health_col_1, health_col_2 = st.columns(2)
    with health_col_1:
        if st.button("Check LLM", use_container_width=True, disabled=not backend_ok):
            try:
                st.session_state.llm_health = api_client.get_llm_health()
                st.session_state.llm_health_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as exc:  # noqa: BLE001
                st.session_state.llm_health = {"overall_ok": False, "error": str(exc)}
                st.session_state.llm_health_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with health_col_2:
        if st.button("KB Stats", use_container_width=True, disabled=not backend_ok):
            try:
                st.session_state.kb_stats = api_client.get_knowledge_stats()
                st.session_state.kb_stats_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as exc:  # noqa: BLE001
                st.session_state.kb_stats = {"error": str(exc)}
                st.session_state.kb_stats_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if st.session_state.llm_health_checked_at:
        st.caption(f"LLM checked: {st.session_state.llm_health_checked_at}")
        llm_health = st.session_state.llm_health or {}
        if llm_health.get("overall_ok"):
            st.success("LLM: reachable")
        else:
            st.warning("LLM: issue detected")
            with st.expander("LLM details"):
                st.json(llm_health)

    if st.session_state.kb_stats_checked_at:
        st.caption(f"KB stats checked: {st.session_state.kb_stats_checked_at}")
        kb_stats = st.session_state.kb_stats or {}
        if "error" in kb_stats:
            st.warning(f"KB stats unavailable: {kb_stats['error']}")
        else:
            st.metric("Registry Docs", kb_stats.get("documents_count", 0))

    st.divider()
    st.subheader("Usage Notes")
    st.markdown("- Upload PDF or DOCX only")
    st.markdown("- Use question number when available")
    st.markdown("- Check LLM before live marking batches")

metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)

total_jobs = len(st.session_state.jobs)
active_jobs = len([job for job in st.session_state.jobs if (job.get("status") or "").lower() not in {"complete", "completed", "failed"}])
complete_jobs = len([job for job in st.session_state.jobs if (job.get("status") or "").lower() in {"complete", "completed"}])

metric_col_1.metric("Backend", "Online" if backend_ok else "Offline")
metric_col_2.metric("Jobs", total_jobs)
metric_col_3.metric("Active", active_jobs)
metric_col_4.metric("Completed", complete_jobs)

st.markdown("\n")

tab_upload, tab_jobs, tab_result = st.tabs(["Upload & Mark", "Job Queue", "Latest Result"])

with tab_upload:
    st.markdown("### Submit Answer")
    st.caption("Upload a student answer and optionally wait for full completion in this session.")

    with st.form("upload_form", clear_on_submit=False):
        uploaded_file = st.file_uploader(
            "Answer file",
            type=["pdf", "docx"],
            help="Supported formats: PDF and DOCX",
        )

        form_col_1, form_col_2, form_col_3 = st.columns([1, 1, 1.2])
        with form_col_1:
            paper = st.selectbox("Paper", ["AA"], help="Current production scope")
        with form_col_2:
            question_number = st.text_input("Question (optional)", placeholder="e.g. 1(b)")
        with form_col_3:
            wait_seconds = st.slider("Wait for completion (seconds)", min_value=30, max_value=300, value=120, step=10)

        submit = st.form_submit_button("Upload and Process", type="primary", use_container_width=True)

    if submit:
        if not uploaded_file:
            st.warning("Please upload a PDF or DOCX file before submitting.")
        elif not backend_ok:
            st.error("Backend is not reachable. Start the API and retry.")
        else:
            try:
                with st.spinner("Uploading file and creating job..."):
                    upload_resp = api_client.upload_file(uploaded_file, paper, question_number or None)

                upload_id = upload_resp["upload_id"]
                st.session_state.last_upload_id = upload_id

                _upsert_job(
                    {
                        "upload_id": upload_id,
                        "filename": getattr(uploaded_file, "name", "uploaded_file"),
                        "paper": paper,
                        "question_number": question_number,
                        "status": "pending",
                        "progress": 5,
                        "created_at": datetime.now().isoformat(),
                        "result_id": None,
                    }
                )

                st.success(f"Upload successful. Tracking job `{upload_id}`")
                progress = st.progress(5)
                status_block = st.empty()

                started = time.time()
                final_status = None
                last_payload: Dict[str, Any] = {}

                while time.time() - started <= wait_seconds:
                    last_payload = _refresh_single_job(api_client, upload_id, fetch_result=False)
                    state = (last_payload.get("status") or "pending").lower()
                    pct = max(0, min(100, int(last_payload.get("progress", 0))))
                    progress.progress(pct)
                    status_block.info(f"{_status_label(state)} ({pct}%) - {_status_help(state)}")

                    if state in {"complete", "completed", "failed"}:
                        final_status = state
                        break

                    time.sleep(POLL_INTERVAL_SECONDS)

                if final_status in {"complete", "completed"}:
                    result_id = last_payload.get("result_id")
                    if result_id:
                        result_payload = api_client.get_result(result_id)
                        st.session_state.last_result = result_payload
                        st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        _upsert_job({"upload_id": upload_id, "status": "complete", "progress": 100, "result_id": result_id})
                        st.success("Marking completed. Open the Latest Result tab.")
                    else:
                        st.warning("Processing finished but result ID was not returned.")
                elif final_status == "failed":
                    error_message = str(last_payload.get("error") or "Processing failed")
                    _upsert_job({"upload_id": upload_id, "status": "failed", "error": error_message})
                    st.error(error_message)
                else:
                    st.info("Job is still running. Open Job Queue to refresh status.")

            except Exception as exc:  # noqa: BLE001
                st.error(f"Upload workflow failed: {exc}")

with tab_jobs:
    st.markdown("### Job Queue")
    st.caption("Track active and completed uploads. Refresh without re-uploading.")

    queue_col_1, queue_col_2 = st.columns([1, 1])
    with queue_col_1:
        if st.button("Refresh Active Jobs", use_container_width=True, disabled=not st.session_state.jobs):
            _refresh_active_jobs(api_client)
            st.rerun()
    with queue_col_2:
        if st.button("Clear Queue", use_container_width=True, disabled=not st.session_state.jobs):
            st.session_state.jobs = []
            st.rerun()

    if not st.session_state.jobs:
        st.info("No jobs yet. Upload a file in the Upload & Mark tab.")
    else:
        for job in st.session_state.jobs:
            upload_id = job.get("upload_id", "-")
            status = (job.get("status") or "unknown").lower()
            progress = int(job.get("progress", 0) or 0)

            with st.container(border=True):
                top_col_1, top_col_2, top_col_3 = st.columns([2.8, 1.2, 1.2])
                with top_col_1:
                    st.markdown(f"**{job.get('filename', 'Uploaded file')}**")
                    st.caption(
                        f"Upload ID: `{upload_id}` | Paper: {job.get('paper', '-')}")
                with top_col_2:
                    st.metric("Status", _status_label(status))
                with top_col_3:
                    st.metric("Progress", f"{progress}%")

                st.progress(max(0, min(100, progress)))
                if job.get("error"):
                    st.error(str(job.get("error")))

                action_col_1, action_col_2 = st.columns(2)
                with action_col_1:
                    if st.button("Refresh Job", key=f"refresh_{upload_id}", use_container_width=True):
                        try:
                            _refresh_single_job(api_client, upload_id, fetch_result=True)
                            st.rerun()
                        except Exception as exc:  # noqa: BLE001
                            _upsert_job({"upload_id": upload_id, "status": "failed", "error": str(exc)})
                            st.rerun()
                with action_col_2:
                    result_id = job.get("result_id")
                    if st.button("Load Result", key=f"load_{upload_id}", use_container_width=True, disabled=not result_id):
                        try:
                            st.session_state.last_result = api_client.get_result(result_id)
                            st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            st.success("Result loaded into Latest Result tab.")
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"Failed to load result: {exc}")

with tab_result:
    st.markdown("### Latest Result")
    result = st.session_state.last_result

    if not result:
        st.info("No result loaded yet. Complete a job or load one from Job Queue.")
    else:
        total_marks = _safe_float(result.get("total_marks"), 0.0)
        max_marks = _safe_float(result.get("max_marks"), 0.0)
        percentage = _safe_float(result.get("percentage"), 0.0)
        prof = result.get("professional_marks", {}) or {}
        prof_total, prof_max = _summarize_professional_marks(prof)

        r_col_1, r_col_2, r_col_3, r_col_4 = st.columns(4)
        r_col_1.metric("Total Score", f"{total_marks}/{max_marks}")
        r_col_2.metric("Percentage", f"{percentage:.2f}%")
        r_col_3.metric("Professional", f"{prof_total:.2f}/{prof_max:.2f}")
        r_col_4.metric("Model", str(result.get("model_used", "n/a")))

        st.markdown("#### Breakdown")
        points = result.get("question_marks", []) or []
        if not points:
            st.caption("No per-point breakdown returned.")
        else:
            for idx, point in enumerate(points, start=1):
                title = point.get("point", f"Point {idx}")
                awarded = _safe_float(point.get("awarded"), 0.0)
                explanation = point.get("explanation", "No explanation provided")
                with st.expander(f"{idx}. {title} - {awarded} marks", expanded=(idx == 1)):
                    st.write(explanation)

        st.markdown("#### Professional Marks")
        if not prof:
            st.caption("No professional marks returned.")
        else:
            for skill, value in prof.items():
                st.write(f"- **{str(skill).replace('_', ' ').title()}**: {_safe_float(value):.2f}")

        st.markdown("#### Feedback")
        st.info(result.get("feedback", "No feedback provided."))

        citations = result.get("citations", []) or []
        with st.expander("Citations", expanded=False):
            if not citations:
                st.caption("No citations returned.")
            else:
                for item in citations:
                    st.write(f"- {item}")

        with st.expander("Raw JSON", expanded=False):
            st.code(json.dumps(result, indent=2), language="json")

        st.download_button(
            label="Download Result JSON",
            data=json.dumps(result, indent=2),
            file_name=f"marking_result_{result.get('id', 'latest')}.json",
            mime="application/json",
            use_container_width=True,
        )

        if st.button("Clear Latest Result", use_container_width=True):
            st.session_state.last_result = None
            st.rerun()

st.divider()
if st.session_state.last_run_at:
    st.caption(f"Last completed run: {st.session_state.last_run_at}")
else:
    st.caption("No completed run yet in this session.")
