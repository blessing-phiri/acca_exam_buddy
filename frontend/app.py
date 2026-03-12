"""Client-facing Streamlit app for ACCA Exam Buddie."""

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


APP_NAME = "ACCA Exam Buddie"
BACKEND_URL = os.getenv("API_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1"))
DEFAULT_WAIT_SECONDS = int(os.getenv("DEFAULT_WAIT_SECONDS", "120"))
FRONTEND_MODE = os.getenv("FRONTEND_MODE", "client").strip().lower()
ADMIN_MODE = FRONTEND_MODE == "admin"


def _init_state() -> None:
    defaults: Dict[str, Any] = {
        "last_upload_id": None,
        "last_result": None,
        "last_run_at": None,
        "jobs": [],
        "last_tutor_ingest": None,
        "llm_health": None,
        "kb_stats": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return fallback


def _status_copy(status: str) -> tuple[str, str]:
    key = (status or "").strip().lower()
    mapping = {
        "pending": ("Queued", "Your submission is waiting in the queue."),
        "extracting": ("Reading File", "We are extracting text from your document."),
        "cleaning": ("Preparing", "We are cleaning and structuring your answer."),
        "analyzing": ("Analyzing", "We are understanding question boundaries and context."),
        "marking": ("Marking", "The AI marker is scoring your answer."),
        "complete": ("Complete", "Your result is ready."),
        "completed": ("Complete", "Your result is ready."),
        "failed": ("Failed", "Something went wrong. Please try again."),
    }
    return mapping.get(key, (status or "Unknown", ""))


def _job_index(upload_id: str) -> int:
    for idx, item in enumerate(st.session_state.jobs):
        if item.get("upload_id") == upload_id:
            return idx
    return -1


def _upsert_job(job: Dict[str, Any]) -> None:
    idx = _job_index(job["upload_id"])
    payload = {**job, "updated_at": datetime.now().isoformat()}
    if idx >= 0:
        st.session_state.jobs[idx] = {**st.session_state.jobs[idx], **payload}
    else:
        st.session_state.jobs.insert(0, payload)


def _refresh_job(api_client: APIClient, upload_id: str, fetch_result: bool = False) -> Dict[str, Any]:
    status_payload = api_client.get_status(upload_id)
    _upsert_job(
        {
            "upload_id": upload_id,
            "status": status_payload.get("status", "unknown"),
            "progress": int(status_payload.get("progress", 0)),
            "result_id": status_payload.get("result_id"),
            "error": status_payload.get("error"),
        }
    )

    result_id = status_payload.get("result_id")
    if fetch_result and result_id:
        result = api_client.get_result(result_id)
        st.session_state.last_result = result
        st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return status_payload


def _score_band(percentage: float) -> str:
    if percentage >= 75:
        return "Strong"
    if percentage >= 50:
        return "Good"
    if percentage >= 40:
        return "Borderline"
    return "Needs Improvement"


st.set_page_config(
    page_title=APP_NAME,
    page_icon=":books:",
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
            --soft: #f7fcfb;
            --edge: #d3e5e2;
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
            border-radius: 18px;
            padding: 24px;
            color: #f3fffd;
            margin-bottom: 14px;
            box-shadow: 0 10px 24px rgba(15, 118, 110, 0.18);
            border: 1px solid rgba(255,255,255,0.2);
        }

        .hero h1 {
            font-family: "Space Grotesk", sans-serif;
            margin: 0;
            font-size: 2.1rem;
            letter-spacing: -0.02em;
        }

        .hero p {
            margin: 10px 0 0;
            font-size: 1.03rem;
            opacity: 0.96;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero">
        <h1>{APP_NAME}</h1>
        <p>Upload or type an ACCA answer, include the question context, and receive clear marks with practical feedback.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Workspace")
    if backend_ok:
        st.success("Service is online")
    else:
        st.error("Service is offline")

    st.markdown("### Quick Start")
    st.markdown("1. Paste or upload the question context")
    st.markdown("2. Upload your answer file or type your answer")
    st.markdown("3. Review marks and feedback")

    if ADMIN_MODE:
        st.divider()
        st.caption(f"Admin mode | Backend: `{BACKEND_URL}`")
        if st.button("Check LLM Health", use_container_width=True, disabled=not backend_ok):
            try:
                st.session_state.llm_health = api_client.get_llm_health()
            except Exception as exc:  # noqa: BLE001
                st.session_state.llm_health = {"error": str(exc)}

        if st.button("Check KB Stats", use_container_width=True, disabled=not backend_ok):
            try:
                st.session_state.kb_stats = api_client.get_knowledge_stats()
            except Exception as exc:  # noqa: BLE001
                st.session_state.kb_stats = {"error": str(exc)}

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Backend", "Online" if backend_ok else "Offline")
metric_2.metric("Submissions", len(st.session_state.jobs))
metric_3.metric("Last Result", st.session_state.last_run_at or "-")

main_tabs = ["Student", "Tutor", "Results"]
if ADMIN_MODE:
    main_tabs.append("Admin")

tabs = st.tabs(main_tabs)
student_tab = tabs[0]
tutor_tab = tabs[1]
results_tab = tabs[2]
admin_tab = tabs[3] if ADMIN_MODE else None

with student_tab:
    st.markdown("### Student Workspace")
    student_subtabs = st.tabs(["Upload Document", "Type Answer", "Track Submission"])

    with student_subtabs[0]:
        st.caption("Best when your answer is already in PDF or DOCX.")
        with st.form("student_upload_form", clear_on_submit=False):
            question_text = st.text_area(
                "Question Context",
                placeholder="Paste the full exam question or requirement here...",
                help="Required: this gives the marker the exact context.",
                height=130,
            )
            upload_file = st.file_uploader("Answer File", type=["pdf", "docx"])

            col_1, col_2, col_3, col_4 = st.columns([1.0, 1.0, 1.0, 1.2])
            with col_1:
                paper = st.selectbox("Paper", ["AA"], key="upload_paper")
            with col_2:
                question_number = st.text_input("Question No. (optional)", placeholder="e.g. 1(b)")
            with col_3:
                max_marks = st.number_input("Max Marks", min_value=1.0, max_value=100.0, value=16.0, step=1.0)
            with col_4:
                wait_seconds = st.slider("Wait (seconds)", min_value=30, max_value=300, value=DEFAULT_WAIT_SECONDS, step=10)

            submit_upload = st.form_submit_button("Submit and Mark", type="primary", use_container_width=True)

        if submit_upload:
            if not question_text.strip():
                st.warning("Please provide the question context.")
            elif not upload_file:
                st.warning("Please upload a PDF or DOCX answer file.")
            elif not backend_ok:
                st.error("Service is currently offline. Please try again shortly.")
            else:
                try:
                    with st.spinner("Uploading and starting marking..."):
                        upload_resp = api_client.upload_file(
                            file=upload_file,
                            paper=paper,
                            question=question_number or None,
                            question_text=question_text,
                            max_marks=max_marks,
                        )

                    upload_id = upload_resp["upload_id"]
                    st.session_state.last_upload_id = upload_id
                    _upsert_job(
                        {
                            "upload_id": upload_id,
                            "filename": getattr(upload_file, "name", "uploaded_file"),
                            "status": "pending",
                            "progress": 5,
                            "result_id": None,
                        }
                    )

                    st.success("Upload received. Processing has started.")
                    progress = st.progress(5)
                    info = st.empty()

                    start = time.time()
                    payload: Dict[str, Any] = {}
                    done = False
                    while time.time() - start <= wait_seconds:
                        payload = _refresh_job(api_client, upload_id, fetch_result=False)
                        status = payload.get("status", "pending")
                        pct = max(0, min(100, int(payload.get("progress", 0))))
                        label, helper = _status_copy(status)
                        progress.progress(pct)
                        info.info(f"{label} ({pct}%)\n\n{helper}")

                        if status.lower() in {"complete", "completed", "failed"}:
                            done = True
                            break
                        time.sleep(POLL_INTERVAL_SECONDS)

                    final_status = (payload.get("status") or "").lower()
                    if done and final_status in {"complete", "completed"} and payload.get("result_id"):
                        st.session_state.last_result = api_client.get_result(payload["result_id"])
                        st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        _upsert_job({"upload_id": upload_id, "status": "complete", "progress": 100, "result_id": payload["result_id"]})
                        st.success("Marking complete. Check the Results tab.")
                    elif done and final_status == "failed":
                        st.error(payload.get("error") or "Processing failed.")
                    else:
                        st.info("Still processing. Use Track Submission to refresh later.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not complete upload: {exc}")

    with student_subtabs[1]:
        st.caption("Best when students want to type directly in the app.")
        with st.form("student_typed_form", clear_on_submit=False):
            typed_question = st.text_area(
                "Question Context",
                placeholder="Paste the full exam question or requirement here...",
                height=120,
            )
            typed_answer = st.text_area(
                "Your Answer",
                placeholder="Type your answer here...",
                height=220,
            )

            t1, t2, t3 = st.columns([1.0, 1.0, 1.0])
            with t1:
                typed_paper = st.selectbox("Paper", ["AA"], key="typed_paper")
            with t2:
                typed_qnum = st.text_input("Question No. (optional)", key="typed_qnum", placeholder="e.g. 1(b)")
            with t3:
                typed_max = st.number_input("Max Marks", min_value=1.0, max_value=100.0, value=16.0, step=1.0, key="typed_max")

            submit_typed = st.form_submit_button("Mark Typed Answer", type="primary", use_container_width=True)

        if submit_typed:
            if not typed_question.strip():
                st.warning("Please provide the question context.")
            elif not typed_answer.strip():
                st.warning("Please type the student answer.")
            elif not backend_ok:
                st.error("Service is currently offline. Please try again shortly.")
            else:
                try:
                    with st.spinner("Marking typed answer..."):
                        payload = api_client.upload_text_answer(
                            question_text=typed_question,
                            answer_text=typed_answer,
                            paper=typed_paper,
                            question_number=typed_qnum or None,
                            max_marks=typed_max,
                        )

                    upload_id = payload.get("upload_id")
                    result_id = payload.get("result_id")
                    result = payload.get("result") or {}

                    if upload_id:
                        st.session_state.last_upload_id = upload_id
                        _upsert_job(
                            {
                                "upload_id": upload_id,
                                "filename": "typed_answer.txt",
                                "status": "complete",
                                "progress": 100,
                                "result_id": result_id,
                            }
                        )

                    st.session_state.last_result = result
                    st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.success("Typed answer marked successfully. Open the Results tab.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not mark typed answer: {exc}")

    with student_subtabs[2]:
        st.caption("Refresh the latest submission if you left before processing finished.")
        if not st.session_state.last_upload_id:
            st.info("No submission tracked yet.")
        else:
            st.write(f"Latest Upload ID: `{st.session_state.last_upload_id}`")
            if st.button("Refresh Latest Status", use_container_width=True):
                try:
                    payload = _refresh_job(api_client, st.session_state.last_upload_id, fetch_result=True)
                    label, helper = _status_copy(payload.get("status", "unknown"))
                    st.success(f"Status: {label}")
                    if helper:
                        st.caption(helper)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not refresh status: {exc}")

with tutor_tab:
    st.markdown("### Tutor Workspace")
    st.caption("Upload custom marking guides when your classroom questions differ from built-in resources.")

    with st.form("tutor_guide_upload_form", clear_on_submit=False):
        guide_file = st.file_uploader("Guide File", type=["pdf", "docx", "txt", "md", "html", "htm"], key="guide_file")

        g1, g2, g3, g4 = st.columns([1.2, 1.0, 1.0, 1.0])
        with g1:
            doc_type = st.selectbox(
                "Guide Type",
                options=["marking_scheme", "examiner_report", "technical_article"],
                format_func=lambda x: {
                    "marking_scheme": "Marking Scheme",
                    "examiner_report": "Examiner Report",
                    "technical_article": "Technical Reference",
                }[x],
            )
        with g2:
            guide_paper = st.selectbox("Paper", ["AA"], key="guide_paper")
        with g3:
            guide_year = st.text_input("Year (optional)", placeholder="e.g. 2025")
        with g4:
            guide_qtype = st.text_input("Question Type (optional)", placeholder="e.g. audit_risk")

        guide_notes = st.text_area("Notes (optional)", placeholder="Any tutor notes for this guide", height=90)

        submit_guide = st.form_submit_button("Upload Guide", type="primary", use_container_width=True)

    if submit_guide:
        if not guide_file:
            st.warning("Please select a guide file to upload.")
        elif not backend_ok:
            st.error("Service is currently offline. Please try again shortly.")
        else:
            try:
                with st.spinner("Uploading and ingesting guide..."):
                    ingest_payload = api_client.upload_tutor_guide(
                        file=guide_file,
                        doc_type=doc_type,
                        paper=guide_paper,
                        year=guide_year or None,
                        question_type=guide_qtype or None,
                        notes=guide_notes or None,
                    )
                st.session_state.last_tutor_ingest = ingest_payload
                st.success("Tutor guide uploaded and ingested successfully.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Guide upload failed: {exc}")

    if st.session_state.last_tutor_ingest:
        latest = st.session_state.last_tutor_ingest
        st.markdown("#### Latest Tutor Upload")
        c1, c2, c3 = st.columns(3)
        c1.metric("Type", latest.get("doc_type", "-"))
        c2.metric("Stored", "Yes" if latest.get("saved_path") else "No")
        c3.metric("Chunks", (latest.get("ingestion") or {}).get("chunk_count", 0))
        with st.expander("Details"):
            st.json(latest)

with results_tab:
    st.markdown("### Results")
    result = st.session_state.last_result

    if not result:
        st.info("No result available yet. Submit from the Student workspace.")
    else:
        total_marks = _safe_float(result.get("total_marks"))
        max_marks = max(_safe_float(result.get("max_marks"), 1.0), 1.0)
        percentage = _safe_float(result.get("percentage"), (total_marks / max_marks) * 100)

        m1, m2, m3 = st.columns(3)
        m1.metric("Score", f"{total_marks:.2f}/{max_marks:.2f}")
        m2.metric("Percentage", f"{percentage:.1f}%")
        m3.metric("Band", _score_band(percentage))
        st.progress(max(0.0, min(1.0, percentage / 100.0)))

        st.markdown("#### Feedback")
        st.info(result.get("feedback", "No feedback returned."))

        points = result.get("question_marks", []) or []
        st.markdown("#### Breakdown")
        if not points:
            st.caption("No detailed breakdown returned.")
        else:
            for idx, point in enumerate(points, start=1):
                title = point.get("point", f"Point {idx}")
                awarded = _safe_float(point.get("awarded"), 0.0)
                explanation = point.get("explanation", "No explanation provided")
                with st.expander(f"{idx}. {title} ({awarded:.2f} marks)", expanded=(idx == 1)):
                    st.write(explanation)

        prof = result.get("professional_marks", {}) or {}
        if prof:
            st.markdown("#### Professional Marks")
            for skill, value in prof.items():
                st.write(f"- **{str(skill).replace('_', ' ').title()}**: {_safe_float(value):.2f}")

        citations = result.get("citations", []) or []
        if citations:
            with st.expander("References"):
                for cite in citations:
                    st.write(f"- {cite}")

        d1, d2 = st.columns(2)
        with d1:
            if st.button("Clear Result", use_container_width=True):
                st.session_state.last_result = None
                st.rerun()
        with d2:
            st.download_button(
                label="Download JSON",
                data=json.dumps(result, indent=2),
                file_name=f"marking_result_{result.get('id', 'latest')}.json",
                mime="application/json",
                use_container_width=True,
            )

if admin_tab is not None:
    with admin_tab:
        st.markdown("### Admin")
        st.caption("Technical diagnostics for operators.")

        if st.button("Run LLM Health Check", use_container_width=True, disabled=not backend_ok):
            try:
                st.session_state.llm_health = api_client.get_llm_health()
            except Exception as exc:  # noqa: BLE001
                st.session_state.llm_health = {"error": str(exc)}

        if st.button("Run KB Stats Check", use_container_width=True, disabled=not backend_ok):
            try:
                st.session_state.kb_stats = api_client.get_knowledge_stats()
            except Exception as exc:  # noqa: BLE001
                st.session_state.kb_stats = {"error": str(exc)}

        if st.session_state.llm_health:
            st.markdown("#### LLM Health")
            st.json(st.session_state.llm_health)

        if st.session_state.kb_stats:
            st.markdown("#### KB Stats")
            st.json(st.session_state.kb_stats)

        st.markdown("#### Job Queue")
        if not st.session_state.jobs:
            st.info("No jobs tracked in this session.")
        else:
            for job in st.session_state.jobs:
                label, helper = _status_copy(job.get("status", "unknown"))
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2.0, 1.0, 1.0])
                    c1.write(job.get("filename", "uploaded"))
                    c1.caption(f"Upload ID: `{job.get('upload_id', '-')}`")
                    c2.metric("Status", label)
                    c3.metric("Progress", f"{int(job.get('progress', 0) or 0)}%")
                    if helper:
                        st.caption(helper)
                    if job.get("error"):
                        st.error(str(job["error"]))

st.divider()
st.caption(f"{APP_NAME} | {'Admin' if ADMIN_MODE else 'Client'} mode")
