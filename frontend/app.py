"""Streamlit frontend for ACCA AA AI Marker."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import streamlit as st

try:
    from frontend.services.api import APIClient
except ImportError:
    from services.api import APIClient


BACKEND_URL = os.getenv("API_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1"))
DEFAULT_WAIT_SECONDS = int(os.getenv("DEFAULT_WAIT_SECONDS", "120"))
FRONTEND_MODE = os.getenv("FRONTEND_MODE", "client").strip().lower()
CLIENT_MODE = FRONTEND_MODE != "admin"


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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return fallback


def _fmt_iso(raw: Optional[str]) -> str:
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return raw


def _status_copy(status: str) -> tuple[str, str]:
    key = (status or "").strip().lower()
    labels = {
        "pending": ("Queued", "Your file is waiting to be processed."),
        "extracting": ("Reading File", "We are extracting text from your document."),
        "cleaning": ("Preparing Content", "We are cleaning and structuring your answer."),
        "analyzing": ("Analyzing", "We are detecting question structure and context."),
        "marking": ("Marking", "The AI marker is scoring your answer now."),
        "complete": ("Complete", "Your feedback is ready."),
        "completed": ("Complete", "Your feedback is ready."),
        "failed": ("Failed", "Something went wrong. Please try again."),
    }
    return labels.get(key, (status or "Unknown", ""))


def _job_index(upload_id: str) -> int:
    for idx, item in enumerate(st.session_state.jobs):
        if item.get("upload_id") == upload_id:
            return idx
    return -1


def _upsert_job(job: Dict[str, Any]) -> None:
    idx = _job_index(job["upload_id"])
    if idx >= 0:
        existing = st.session_state.jobs[idx]
        st.session_state.jobs[idx] = {**existing, **job, "updated_at": datetime.now().isoformat()}
    else:
        st.session_state.jobs.insert(0, {**job, "updated_at": datetime.now().isoformat()})


def _refresh_job(api_client: APIClient, upload_id: str, fetch_result: bool = False) -> Dict[str, Any]:
    payload = api_client.get_status(upload_id)
    _upsert_job(
        {
            "upload_id": upload_id,
            "status": payload.get("status", "unknown"),
            "progress": int(payload.get("progress", 0)),
            "result_id": payload.get("result_id"),
            "error": payload.get("error"),
        }
    )

    if fetch_result and payload.get("result_id"):
        result = api_client.get_result(payload["result_id"])
        st.session_state.last_result = result
        st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return payload


def _refresh_active_jobs(api_client: APIClient) -> None:
    for job in list(st.session_state.jobs):
        state = (job.get("status") or "").lower()
        if state in {"failed", "complete", "completed"}:
            continue
        try:
            _refresh_job(api_client, job["upload_id"], fetch_result=True)
        except Exception as exc:  # noqa: BLE001
            _upsert_job({"upload_id": job["upload_id"], "status": "failed", "error": str(exc)})


def _score_band(percentage: float) -> str:
    if percentage >= 75:
        return "Strong"
    if percentage >= 50:
        return "Good"
    if percentage >= 40:
        return "Borderline"
    return "Needs Improvement"


st.set_page_config(
    page_title="ACCA AA Marker",
    page_icon=":ledger:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_init_state()
api_client = APIClient(BACKEND_URL)
backend_ok = api_client.health_check()

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Source+Sans+3:wght@400;600;700&display=swap');

        :root {
            --ink: #103f39;
            --teal: #0f766e;
            --teal-dark: #115e59;
            --mint: #d8f4ef;
            --edge: #d3e5e2;
            --soft: #f7fcfb;
            --muted: #5f7470;
        }

        html, body, [class*="css"] {
            font-family: "Source Sans 3", sans-serif;
            color: var(--ink);
        }

        .stApp {
            background: radial-gradient(circle at top right, #e8f8f4 0%, #f8fcfb 40%, #ffffff 100%);
        }

        .hero {
            background: linear-gradient(125deg, #0f766e 0%, #115e59 50%, #134e4a 100%);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 18px;
            padding: 24px;
            color: #f3fffd;
            margin-bottom: 14px;
            box-shadow: 0 10px 24px rgba(15, 118, 110, 0.18);
        }

        .hero h1 {
            font-family: "Space Grotesk", sans-serif;
            margin: 0;
            font-size: 2.05rem;
            letter-spacing: -0.02em;
        }

        .hero p {
            margin: 10px 0 0;
            font-size: 1.03rem;
            opacity: 0.96;
        }

        .tiny {
            color: var(--muted);
            font-size: 0.9rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>ACCA AA AI Marker</h1>
        <p>Upload your answer, wait a moment, and get clear marks with practical feedback.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Student Workspace")
    if backend_ok:
        st.success("Service is online")
    else:
        st.error("Service is offline")
        st.caption("Please try again in a moment.")

    if CLIENT_MODE:
        st.markdown("### How To Use")
        st.markdown("1. Upload your PDF or DOCX answer")
        st.markdown("2. Wait while we process and mark")
        st.markdown("3. Read your score and improvement notes")
    else:
        st.caption(f"Mode: `{FRONTEND_MODE}`")
        st.markdown(f"Backend URL: `{BACKEND_URL}`")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("LLM Health", use_container_width=True, disabled=not backend_ok):
                try:
                    st.session_state.llm_health = api_client.get_llm_health()
                    st.session_state.llm_health_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                except Exception as exc:  # noqa: BLE001
                    st.session_state.llm_health = {"error": str(exc)}
                    st.session_state.llm_health_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with c2:
            if st.button("KB Stats", use_container_width=True, disabled=not backend_ok):
                try:
                    st.session_state.kb_stats = api_client.get_knowledge_stats()
                    st.session_state.kb_stats_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                except Exception as exc:  # noqa: BLE001
                    st.session_state.kb_stats = {"error": str(exc)}
                    st.session_state.kb_stats_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if st.session_state.llm_health_checked_at:
            st.caption(f"LLM checked: {st.session_state.llm_health_checked_at}")
            with st.expander("LLM Details"):
                st.json(st.session_state.llm_health)

        if st.session_state.kb_stats_checked_at:
            st.caption(f"KB checked: {st.session_state.kb_stats_checked_at}")
            with st.expander("KB Details"):
                st.json(st.session_state.kb_stats)

summary_col_1, summary_col_2, summary_col_3 = st.columns(3)
summary_col_1.metric("Backend", "Online" if backend_ok else "Offline")
summary_col_2.metric("Uploads This Session", len(st.session_state.jobs))
summary_col_3.metric("Last Completed", st.session_state.last_run_at or "-")

if CLIENT_MODE:
    tabs = st.tabs(["Submit Answer", "My Result"])
    tab_submit, tab_result = tabs
    tab_operations = None
else:
    tabs = st.tabs(["Submit Answer", "My Result", "Operations"])
    tab_submit, tab_result, tab_operations = tabs

with tab_submit:
    st.markdown("### Submit Your Answer")
    st.caption("Accepted file types: PDF and DOCX")

    with st.form("upload_form", clear_on_submit=False):
        uploaded_file = st.file_uploader("Answer File", type=["pdf", "docx"])

        row_1, row_2, row_3 = st.columns([1.0, 1.1, 1.2])
        with row_1:
            paper = st.selectbox("Paper", ["AA"])
        with row_2:
            question_number = st.text_input("Question (optional)", placeholder="e.g. 1(b)")
        with row_3:
            wait_seconds = st.slider("Wait for result (seconds)", min_value=30, max_value=300, value=DEFAULT_WAIT_SECONDS, step=10)

        submit = st.form_submit_button("Upload and Mark", type="primary", use_container_width=True)

    if submit:
        if not uploaded_file:
            st.warning("Please upload your answer file first.")
        elif not backend_ok:
            st.error("The marking service is currently offline. Please try again shortly.")
        else:
            try:
                with st.spinner("Uploading your file..."):
                    upload_response = api_client.upload_file(uploaded_file, paper, question_number or None)

                upload_id = upload_response["upload_id"]
                st.session_state.last_upload_id = upload_id
                _upsert_job(
                    {
                        "upload_id": upload_id,
                        "filename": getattr(uploaded_file, "name", "uploaded_file"),
                        "paper": paper,
                        "question_number": question_number,
                        "status": "pending",
                        "progress": 5,
                        "result_id": None,
                        "created_at": datetime.now().isoformat(),
                    }
                )

                st.success("Upload successful. Marking has started.")
                progress = st.progress(5)
                status_box = st.empty()

                started_at = time.time()
                latest_payload: Dict[str, Any] = {}
                finished = False

                while time.time() - started_at <= wait_seconds:
                    latest_payload = _refresh_job(api_client, upload_id, fetch_result=False)
                    state = (latest_payload.get("status") or "pending").lower()
                    pct = max(0, min(100, int(latest_payload.get("progress", 0))))
                    progress.progress(pct)
                    label, helper = _status_copy(state)
                    status_box.info(f"{label} ({pct}%)\n\n{helper}")

                    if state in {"complete", "completed", "failed"}:
                        finished = True
                        break
                    time.sleep(POLL_INTERVAL_SECONDS)

                final_state = (latest_payload.get("status") or "").lower()
                if finished and final_state in {"complete", "completed"}:
                    result_id = latest_payload.get("result_id")
                    if result_id:
                        result = api_client.get_result(result_id)
                        st.session_state.last_result = result
                        st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        _upsert_job({"upload_id": upload_id, "status": "complete", "progress": 100, "result_id": result_id})
                        st.success("Your result is ready in the My Result tab.")
                    else:
                        st.warning("Marking completed, but no result ID was returned. Please refresh from Operations.")
                elif finished and final_state == "failed":
                    error_msg = str(latest_payload.get("error") or "Processing failed. Please retry.")
                    _upsert_job({"upload_id": upload_id, "status": "failed", "error": error_msg})
                    st.error(error_msg)
                else:
                    st.info("Your file is still processing. You can check it again in a few moments.")

            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not process this upload: {exc}")

with tab_result:
    st.markdown("### My Result")
    result = st.session_state.last_result

    if not result:
        st.info("No result yet. Submit an answer in the first tab.")
    else:
        total_marks = _safe_float(result.get("total_marks"))
        max_marks = max(_safe_float(result.get("max_marks"), 1.0), 1.0)
        percentage = _safe_float(result.get("percentage"), (total_marks / max_marks) * 100)

        r1, r2, r3 = st.columns(3)
        r1.metric("Score", f"{total_marks:.2f}/{max_marks:.2f}")
        r2.metric("Percentage", f"{percentage:.1f}%")
        r3.metric("Performance Band", _score_band(percentage))

        st.progress(max(0.0, min(1.0, percentage / 100.0)))

        st.markdown("#### Feedback")
        st.info(result.get("feedback", "No feedback provided."))

        st.markdown("#### Mark Breakdown")
        points = result.get("question_marks", []) or []
        if not points:
            st.caption("Detailed marking points were not returned for this submission.")
        else:
            for idx, item in enumerate(points, start=1):
                point_title = item.get("point", f"Point {idx}")
                awarded = _safe_float(item.get("awarded"), 0.0)
                explanation = item.get("explanation", "No explanation provided")
                with st.expander(f"{idx}. {point_title} ({awarded:.2f} marks)", expanded=(idx == 1)):
                    st.write(explanation)

        prof = result.get("professional_marks", {}) or {}
        if prof:
            st.markdown("#### Professional Skills")
            for skill, value in prof.items():
                st.write(f"- **{str(skill).replace('_', ' ').title()}**: {_safe_float(value):.2f}")

        citations = result.get("citations", []) or []
        if citations:
            with st.expander("References Used"):
                for cite in citations:
                    st.write(f"- {cite}")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Check Latest Upload Status", use_container_width=True, disabled=not st.session_state.last_upload_id):
                try:
                    payload = _refresh_job(api_client, st.session_state.last_upload_id, fetch_result=True)
                    state = payload.get("status", "unknown")
                    st.success(f"Latest upload status: {_status_copy(state)[0]}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not refresh latest upload: {exc}")
        with c2:
            if st.button("Clear Current Result", use_container_width=True):
                st.session_state.last_result = None
                st.rerun()

        if not CLIENT_MODE:
            with st.expander("Raw Result JSON"):
                st.code(json.dumps(result, indent=2), language="json")

            st.download_button(
                label="Download Result JSON",
                data=json.dumps(result, indent=2),
                file_name=f"marking_result_{result.get('id', 'latest')}.json",
                mime="application/json",
                use_container_width=True,
            )

if tab_operations is not None:
    with tab_operations:
        st.markdown("### Operations")
        st.caption("Admin-only operational visibility")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Refresh Active Jobs", use_container_width=True, disabled=not st.session_state.jobs):
                _refresh_active_jobs(api_client)
                st.rerun()
        with c2:
            if st.button("Clear Job Queue", use_container_width=True, disabled=not st.session_state.jobs):
                st.session_state.jobs = []
                st.rerun()

        if not st.session_state.jobs:
            st.info("No jobs tracked in this session.")
        else:
            for job in st.session_state.jobs:
                state = job.get("status", "unknown")
                label, helper = _status_copy(state)
                with st.container(border=True):
                    top_1, top_2, top_3 = st.columns([2.2, 1.2, 1.0])
                    top_1.markdown(f"**{job.get('filename', 'Uploaded File')}**")
                    top_1.caption(f"Upload ID: `{job.get('upload_id', '-')}`")
                    top_2.metric("Status", label)
                    top_3.metric("Progress", f"{int(job.get('progress', 0) or 0)}%")
                    st.caption(helper)

                    if job.get("error"):
                        st.error(str(job["error"]))

                    op1, op2 = st.columns(2)
                    with op1:
                        if st.button("Refresh", key=f"ops_refresh_{job.get('upload_id')}", use_container_width=True):
                            try:
                                _refresh_job(api_client, job["upload_id"], fetch_result=True)
                                st.rerun()
                            except Exception as exc:  # noqa: BLE001
                                _upsert_job({"upload_id": job["upload_id"], "status": "failed", "error": str(exc)})
                                st.rerun()
                    with op2:
                        if st.button("Load Result", key=f"ops_load_{job.get('upload_id')}", use_container_width=True, disabled=not job.get("result_id")):
                            try:
                                result = api_client.get_result(job["result_id"])
                                st.session_state.last_result = result
                                st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                st.success("Result loaded into My Result tab.")
                            except Exception as exc:  # noqa: BLE001
                                st.error(f"Failed to load result: {exc}")

st.divider()
st.caption(f"Mode: {'Client' if CLIENT_MODE else 'Admin'} | Last update: {_fmt_iso(datetime.now().isoformat())}")
