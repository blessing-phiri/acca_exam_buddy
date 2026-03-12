"""Streamlit frontend for ACCA AA AI Marker."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict

import streamlit as st

try:
    from frontend.services.api import APIClient
except ImportError:
    from services.api import APIClient


BACKEND_URL = os.getenv("API_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS = 1
POLL_TIMEOUT_SECONDS = 120


st.set_page_config(
    page_title="ACCA AA AI Marker",
    page_icon=":memo:",
    layout="wide",
    initial_sidebar_state="expanded",
)


if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_upload_id" not in st.session_state:
    st.session_state.last_upload_id = None
if "last_run_at" not in st.session_state:
    st.session_state.last_run_at = None


api_client = APIClient(BACKEND_URL)


st.markdown(
    """
    <style>
        .hero {
            background: linear-gradient(120deg, #0f766e 0%, #115e59 100%);
            border-radius: 14px;
            padding: 20px 22px;
            color: #f8fafc;
            margin-bottom: 14px;
        }
        .hero h1 {
            margin: 0;
            font-size: 2rem;
            line-height: 1.2;
        }
        .hero p {
            margin: 8px 0 0;
            opacity: 0.95;
            font-size: 1rem;
        }
        .card {
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 14px;
            background: #ffffff;
        }
        .small-muted {
            color: #64748b;
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
        <p>Upload an ACCA AA answer, receive marks, citations, and practical feedback in minutes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.header("Workspace")
    st.caption("Frontend settings and status")

    st.markdown(f"**Backend URL**\n\n`{BACKEND_URL}`")

    healthy = api_client.health_check()
    if healthy:
        st.success("Backend status: online")
    else:
        st.error("Backend status: offline")
        st.caption("Start backend with: `uvicorn backend.main:app --reload`")

    if st.session_state.last_run_at:
        st.markdown(
            f"<p class='small-muted'>Last run: {st.session_state.last_run_at}</p>",
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("Tips")
    st.markdown("- Upload PDF or DOCX only")
    st.markdown("- Add question number when known")
    st.markdown("- Keep answers readable and structured")


left_col, right_col = st.columns([2.2, 1.0], gap="large")

with left_col:
    tab_upload, tab_results = st.tabs(["Upload and Mark", "Latest Result"])

    with tab_upload:
        st.markdown("### Submit Answer")

        with st.form("upload_form", clear_on_submit=False):
            uploaded_file = st.file_uploader(
                "Answer file",
                type=["pdf", "docx"],
                help="Supported formats: PDF and DOCX",
            )

            form_col_1, form_col_2 = st.columns(2)
            with form_col_1:
                paper = st.selectbox("Paper", ["AA"], help="Current MVP supports AA")
            with form_col_2:
                question_number = st.text_input(
                    "Question number (optional)",
                    placeholder="e.g. 1(b)",
                )

            submit = st.form_submit_button("Submit for Marking", type="primary", use_container_width=True)

        if submit:
            if not uploaded_file:
                st.warning("Please upload a PDF or DOCX file before submitting.")
            elif not api_client.health_check():
                st.error("Backend is not reachable. Please start the API and try again.")
            else:
                try:
                    with st.spinner("Uploading answer..."):
                        upload_resp = api_client.upload_file(uploaded_file, paper, question_number or None)
                    upload_id = upload_resp["upload_id"]
                    st.session_state.last_upload_id = upload_id

                    st.success("Upload successful. Processing started.")
                    progress = st.progress(0)
                    status_text = st.empty()

                    start_time = time.time()
                    status_payload: Dict[str, Any] = {}

                    while time.time() - start_time <= POLL_TIMEOUT_SECONDS:
                        status_payload = api_client.get_status(upload_id)
                        pct = int(status_payload.get("progress", 0))
                        state = status_payload.get("status", "pending")
                        progress.progress(max(0, min(100, pct)))
                        status_text.info(f"Status: {state} ({pct}%)")

                        if state in {"complete", "completed"}:
                            break
                        if state == "failed":
                            break

                        time.sleep(POLL_INTERVAL_SECONDS)

                    final_state = status_payload.get("status")
                    if final_state in {"complete", "completed"}:
                        result_id = status_payload.get("result_id")
                        if not result_id:
                            st.error("Processing finished but no result ID was returned.")
                        else:
                            result = api_client.get_result(result_id)
                            st.session_state.last_result = result
                            st.session_state.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            st.success("Marking completed. Open the Latest Result tab.")
                    elif final_state == "failed":
                        st.error("Processing failed. Please try again.")
                    else:
                        st.warning("Processing is taking longer than expected. Check status again shortly.")

                except Exception as exc:
                    st.error(f"Request failed: {exc}")

    with tab_results:
        st.markdown("### Result Summary")
        result = st.session_state.last_result

        if not result:
            st.info("No marked result yet. Submit an answer in the Upload and Mark tab.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Score", f"{result.get('total_marks', 0)}/{result.get('max_marks', 0)}")
            m2.metric("Percentage", f"{result.get('percentage', 0)}%")

            prof = result.get("professional_marks", {}) or {}
            prof_total = sum(float(v) for v in prof.values()) if prof else 0
            m3.metric("Professional Marks", f"{prof_total}/2")

            st.markdown("#### Question Breakdown")
            points = result.get("question_marks", []) or []
            if not points:
                st.caption("No per-point breakdown was returned.")
            for idx, point in enumerate(points, start=1):
                title = point.get("point", f"Point {idx}")
                awarded = point.get("awarded", 0)
                explanation = point.get("explanation", "No explanation provided")
                with st.expander(f"{idx}. {title} - {awarded} marks", expanded=(idx == 1)):
                    st.write(explanation)

            st.markdown("#### Professional Marks")
            if not prof:
                st.caption("No professional marks returned.")
            else:
                for skill, value in prof.items():
                    st.write(f"- **{skill.title()}**: {value}/0.5")

            st.markdown("#### Feedback")
            st.info(result.get("feedback", "No feedback provided."))

            citations = result.get("citations", []) or []
            with st.expander("Citations"):
                if not citations:
                    st.caption("No citations provided.")
                else:
                    for c in citations:
                        st.write(f"- {c}")

            if st.button("Clear Current Result", use_container_width=True):
                st.session_state.last_result = None
                st.rerun()

with right_col:
    st.markdown("### How It Works")
    st.markdown(
        """
        1. Upload your answer (`.pdf` or `.docx`).
        2. System extracts and prepares text.
        3. Marking engine evaluates against rubric rules.
        4. You receive marks, rationale, and citations.
        """
    )

    st.markdown("### Current Scope")
    st.markdown("- Paper: **AA (Audit and Assurance)**")
    st.markdown("- Output: marks, breakdown, professional marks, feedback")
    st.markdown("- Workflow: upload -> process -> result")

    st.markdown("### Troubleshooting")
    st.markdown("- Backend offline: start API server and retry")
    st.markdown("- Invalid file: ensure extension is `.pdf` or `.docx`")
    st.markdown("- Long wait: verify backend logs and service health")


st.divider()
st.caption("ACCA AA AI Marker | Built for consistent and explainable marking")
