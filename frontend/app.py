"""Client-facing Streamlit app for ACCA Exam Buddie."""

from __future__ import annotations

import os
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

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

THEME_PRESETS: Dict[str, Dict[str, str]] = {
    "Dark": {
        "bg": "linear-gradient(180deg, #071615 0%, #0a1d1b 50%, #102322 100%)",
        "card": "#102a28",
        "card_soft": "#173836",
        "text": "#ecfffb",
        "muted": "#a9c8c3",
        "border": "#2a4d49",
        "accent": "#1eb5a5",
        "accent_dark": "#158678",
        "hero": "linear-gradient(120deg, #0f766e 0%, #0b5e57 50%, #0a3f3c 100%)",
    },
    "Light": {
        "bg": "radial-gradient(circle at top right, #e8f8f4 0%, #f8fcfb 40%, #ffffff 100%)",
        "card": "#ffffff",
        "card_soft": "#f6fcfb",
        "text": "#103f39",
        "muted": "#5f7470",
        "border": "#d3e5e2",
        "accent": "#0f766e",
        "accent_dark": "#115e59",
        "hero": "linear-gradient(125deg, #0f766e 0%, #115e59 50%, #134e4a 100%)",
    },
}

PDF_PAGE_WIDTH = 595
PDF_PAGE_HEIGHT = 842
PDF_MARGIN_X = 48
PDF_TOP_Y = PDF_PAGE_HEIGHT - 118
PDF_BOTTOM_Y = 56

STYLE_MAP: Dict[str, Tuple[str, int, int, Tuple[float, float, float]]] = {
    "title": ("F2", 17, 24, (0.07, 0.20, 0.19)),
    "section": ("F2", 12, 18, (0.07, 0.20, 0.19)),
    "text": ("F1", 10, 15, (0.13, 0.23, 0.22)),
    "bullet": ("F1", 10, 15, (0.13, 0.23, 0.22)),
    "small": ("F1", 9, 13, (0.30, 0.40, 0.39)),
    "spacer": ("F1", 1, 10, (0.13, 0.23, 0.22)),
}


def _init_state() -> None:
    defaults: Dict[str, Any] = {
        "last_upload_id": None,
        "last_result": None,
        "last_run_at": None,
        "jobs": [],
        "last_tutor_ingest": None,
        "llm_health": None,
        "kb_stats": None,
        "theme_mode": "Dark",
        "last_bulk_submission": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return fallback


def _status_copy(status: str) -> Tuple[str, str]:
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
            "student_name": status_payload.get("student_name"),
            "filename": status_payload.get("filename"),
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


def _clean_name(value: Optional[str], fallback: str = "Student") -> str:
    if value is None:
        return fallback
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or fallback


def _safe_file_fragment(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or fallback


def _wrap_text(text: Any, width: int = 92) -> List[str]:
    chunks: List[str] = []
    for paragraph in str(text or "").splitlines():
        part = " ".join(paragraph.split()).strip()
        if not part:
            chunks.append("")
            continue
        wrapped = textwrap.wrap(part, width=width, break_long_words=True, break_on_hyphens=False)
        chunks.extend(wrapped or [part])
    return chunks or [""]


def _pdf_escape(value: str) -> str:
    latin = value.encode("latin-1", "replace").decode("latin-1")
    return latin.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_text(x: float, y: float, text: str, font: str, size: int, color: Tuple[float, float, float]) -> str:
    safe_text = _pdf_escape(text)
    r, g, b = color
    return f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} Td ({safe_text}) Tj ET"


def _build_pdf_lines(result: Dict[str, Any]) -> List[Tuple[str, str]]:
    student_name = _clean_name(result.get("student_name"), fallback="Student")
    total_marks = _safe_float(result.get("total_marks"))
    max_marks = max(_safe_float(result.get("max_marks"), 1.0), 1.0)
    percentage = _safe_float(result.get("percentage"), (total_marks / max_marks) * 100)
    created_at = str(result.get("created_at") or datetime.now().isoformat())
    created_label = created_at.replace("T", " ")[:19]

    lines: List[Tuple[str, str]] = [
        ("title", "Student Feedback Report"),
        ("small", f"Candidate: {student_name}"),
        ("small", f"Generated: {created_label}"),
        ("small", f"Submission ID: {result.get('upload_id', '-')}"),
        ("spacer", ""),
        ("section", "Score Summary"),
        ("text", f"Overall Score: {total_marks:.2f} / {max_marks:.2f}"),
        ("text", f"Percentage: {percentage:.1f}%"),
        ("text", f"Performance Band: {_score_band(percentage)}"),
        ("spacer", ""),
        ("section", "Marker Feedback"),
    ]

    for row in _wrap_text(result.get("feedback") or "No feedback returned."):
        lines.append(("text", row))

    points = result.get("question_marks", []) or []
    if points:
        lines.append(("spacer", ""))
        lines.append(("section", "Detailed Breakdown"))
        for idx, point in enumerate(points, start=1):
            title = str(point.get("point") or f"Point {idx}")
            awarded = _safe_float(point.get("awarded"))
            lines.append(("bullet", f"- {idx}. {title} ({awarded:.2f} marks)"))
            for expl in _wrap_text(point.get("explanation") or "No explanation provided", width=86):
                lines.append(("text", f"  {expl}"))

    professional = result.get("professional_marks", {}) or {}
    if professional:
        lines.append(("spacer", ""))
        lines.append(("section", "Professional Marks"))
        for skill, value in professional.items():
            lines.append(("bullet", f"- {str(skill).replace('_', ' ').title()}: {_safe_float(value):.2f}"))

    citations = result.get("citations", []) or []
    if citations:
        lines.append(("spacer", ""))
        lines.append(("section", "References Used"))
        for cite in citations:
            lines.append(("bullet", f"- {str(cite)}"))

    return lines


def _paginate_pdf_lines(lines: List[Tuple[str, str]]) -> List[List[Tuple[str, str]]]:
    pages: List[List[Tuple[str, str]]] = []
    current: List[Tuple[str, str]] = []
    remaining_height = PDF_TOP_Y - PDF_BOTTOM_Y

    for style, text in lines:
        _, _, leading, _ = STYLE_MAP.get(style, STYLE_MAP["text"])
        if remaining_height - leading < 0 and current:
            pages.append(current)
            current = []
            remaining_height = PDF_TOP_Y - PDF_BOTTOM_Y
        current.append((style, text))
        remaining_height -= leading

    if current:
        pages.append(current)

    if not pages:
        pages = [[("text", "No feedback available")]]
    return pages


def _render_pdf_page(page_lines: List[Tuple[str, str]], page_no: int, total_pages: int) -> str:
    ops: List[str] = []

    ops.append("q")
    ops.append("0.06 0.40 0.38 rg")
    ops.append(f"0 {PDF_PAGE_HEIGHT - 86} {PDF_PAGE_WIDTH} 86 re f")
    ops.append("Q")

    ops.append(_pdf_text(PDF_MARGIN_X, PDF_PAGE_HEIGHT - 52, APP_NAME, "F2", 18, (1.0, 1.0, 1.0)))
    ops.append(_pdf_text(PDF_MARGIN_X, PDF_PAGE_HEIGHT - 71, "ACCA Marking Feedback", "F1", 10, (0.89, 1.0, 0.98)))
    ops.append(_pdf_text(PDF_PAGE_WIDTH - 118, PDF_PAGE_HEIGHT - 71, f"Page {page_no}/{total_pages}", "F1", 9, (0.89, 1.0, 0.98)))

    y = PDF_TOP_Y
    for style, text in page_lines:
        font, size, leading, color = STYLE_MAP.get(style, STYLE_MAP["text"])
        if style == "spacer":
            y -= leading
            continue
        ops.append(_pdf_text(PDF_MARGIN_X, y, text, font, size, color))
        y -= leading

    return "\n".join(ops)


def _build_feedback_pdf(result: Dict[str, Any]) -> bytes:
    lines = _build_pdf_lines(result)
    pages = _paginate_pdf_lines(lines)
    page_streams = [_render_pdf_page(page_lines, idx + 1, len(pages)) for idx, page_lines in enumerate(pages)]

    page_obj_nums = [3 + (i * 2) for i in range(len(page_streams))]
    content_obj_nums = [num + 1 for num in page_obj_nums]
    font_regular_obj = 3 + (len(page_streams) * 2)
    font_bold_obj = font_regular_obj + 1
    max_obj = font_bold_obj

    objects: Dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    kids = " ".join(f"{num} 0 R" for num in page_obj_nums)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_streams)} >>".encode("latin-1")

    for page_obj, content_obj, stream in zip(page_obj_nums, content_obj_nums, page_streams):
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH} {PDF_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_regular_obj} 0 R /F2 {font_bold_obj} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        )
        objects[page_obj] = page_dict.encode("latin-1")

        stream_bytes = stream.encode("latin-1", "replace")
        content = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
            + stream_bytes
            + b"\nendstream"
        )
        objects[content_obj] = content

    objects[font_regular_obj] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects[font_bold_obj] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"

    output = bytearray()
    output.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets = [0] * (max_obj + 1)
    for obj_num in range(1, max_obj + 1):
        offsets[obj_num] = len(output)
        output.extend(f"{obj_num} 0 obj\n".encode("latin-1"))
        output.extend(objects[obj_num])
        output.extend(b"\nendobj\n")

    xref_start = len(output)
    output.extend(f"xref\n0 {max_obj + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for obj_num in range(1, max_obj + 1):
        output.extend(f"{offsets[obj_num]:010d} 00000 n \n".encode("latin-1"))

    trailer = f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    output.extend(trailer.encode("latin-1"))
    return bytes(output)


def _parse_student_names(raw: str) -> List[str]:
    names: List[str] = []
    for row in (raw or "").splitlines():
        clean = " ".join(row.split()).strip()
        if clean:
            names.append(clean)
    return names


def _inject_theme_css(theme_mode: str, admin_mode: bool) -> None:
    palette = THEME_PRESETS.get(theme_mode, THEME_PRESETS["Dark"])
    hide_toolbar_css = ""
    if not admin_mode:
        hide_toolbar_css = """
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer,
        header [title="Deploy"] {
            visibility: hidden !important;
            display: none !important;
        }
        """

    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Source+Sans+3:wght@400;600;700&display=swap');

            :root {{
                --app-bg: {palette['bg']};
                --card-bg: {palette['card']};
                --card-soft: {palette['card_soft']};
                --text-color: {palette['text']};
                --muted-text: {palette['muted']};
                --border: {palette['border']};
                --accent: {palette['accent']};
                --hero-bg: {palette['hero']};
            }}

            .stApp {{
                background: var(--app-bg);
                color: var(--text-color);
                font-family: "Source Sans 3", sans-serif;
            }}

            [data-testid="stSidebar"] {{
                background: var(--card-soft);
                border-right: 1px solid var(--border);
            }}

            [data-testid="stMetric"],
            [data-testid="stVerticalBlockBorderWrapper"],
            [data-testid="stFileUploaderDropzone"] {{
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 12px;
            }}

            div[data-baseweb="input"] > div,
            div[data-baseweb="textarea"] > div,
            div[data-baseweb="select"] > div {{
                background-color: var(--card-bg) !important;
                border-color: var(--border) !important;
            }}

            [data-testid="stTabs"] button {{
                color: var(--muted-text);
                border-bottom: 2px solid transparent;
                font-weight: 600;
            }}

            [data-testid="stTabs"] button[aria-selected="true"] {{
                color: var(--text-color);
                border-bottom-color: var(--accent);
            }}

            .hero {{
                background: var(--hero-bg);
                border-radius: 18px;
                padding: 24px;
                color: #f3fffd;
                margin-bottom: 14px;
                border: 1px solid rgba(255,255,255,0.16);
            }}

            .hero h1 {{
                font-family: "Space Grotesk", sans-serif;
                margin: 0;
                font-size: 2.05rem;
                letter-spacing: -0.02em;
            }}

            .hero p {{
                margin: 10px 0 0;
                font-size: 1.02rem;
                opacity: 0.97;
            }}

            .student-chip {{
                background: rgba(30, 181, 165, 0.16);
                border: 1px solid rgba(30, 181, 165, 0.35);
                color: var(--text-color);
                border-radius: 999px;
                padding: 4px 10px;
                display: inline-block;
                font-size: 0.86rem;
                margin-bottom: 8px;
            }}

            {hide_toolbar_css}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _hide_streamlit_deploy_controls(admin_mode: bool) -> None:
    if admin_mode:
        return
    # Extra guard in case Streamlit changes header markup.
    components.html(
        """
        <script>
            const hideDeploy = () => {
                const selectors = [
                    '[title="Deploy"]',
                    'button[kind="header"]',
                    '#MainMenu',
                    '[data-testid="stToolbar"]'
                ];
                selectors.forEach((sel) => {
                    document.querySelectorAll(sel).forEach((el) => {
                        const t = (el.innerText || el.textContent || '').toLowerCase();
                        if (sel.includes('Deploy') || t.includes('deploy') || sel === '#MainMenu' || sel.includes('stToolbar')) {
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                        }
                    });
                });
            };
            hideDeploy();
            new MutationObserver(hideDeploy).observe(document.body, { childList: true, subtree: true });
        </script>
        """,
        height=0,
        width=0,
    )


st.set_page_config(
    page_title=APP_NAME,
    page_icon=":books:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_init_state()
api_client = APIClient(BACKEND_URL)
backend_ok = api_client.health_check()

with st.sidebar:
    st.header("Workspace")
    selected_theme = st.radio("Theme", ["Dark", "Light"], key="theme_mode", horizontal=True)

    if backend_ok:
        st.success("Service is online")
    else:
        st.error("Service is offline")

    st.markdown("### Quick Start")
    st.markdown("1. Paste the full question context")
    st.markdown("2. Upload or type the student answer")
    st.markdown("3. Download branded PDF feedback")

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

_inject_theme_css(selected_theme, ADMIN_MODE)
_hide_streamlit_deploy_controls(ADMIN_MODE)

st.markdown(
    f"""
    <div class="hero">
        <h1>{APP_NAME}</h1>
        <p>Upload or type an ACCA answer, include question context, and receive clear marks with professional feedback.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Backend", "Online" if backend_ok else "Offline")
metric_2.metric("Tracked Submissions", len(st.session_state.jobs))
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
            student_name = st.text_input("Student Name (optional)", placeholder="e.g. Tariro Moyo")
            question_text = st.text_area(
                "Question Context",
                placeholder="Paste the full exam question or requirement here...",
                help="Required: this gives the marker the exact context.",
                height=130,
            )
            answer_file = st.file_uploader("Answer File", type=["pdf", "docx"])

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
            elif not answer_file:
                st.warning("Please upload a PDF or DOCX answer file.")
            elif not backend_ok:
                st.error("Service is currently offline. Please try again shortly.")
            else:
                try:
                    with st.spinner("Uploading and starting marking..."):
                        upload_resp = api_client.upload_file(
                            file=answer_file,
                            paper=paper,
                            question=question_number or None,
                            question_text=question_text,
                            max_marks=max_marks,
                            student_name=student_name or None,
                        )

                    upload_id = upload_resp["upload_id"]
                    st.session_state.last_upload_id = upload_id
                    _upsert_job(
                        {
                            "upload_id": upload_id,
                            "filename": getattr(answer_file, "name", "uploaded_file"),
                            "student_name": _clean_name(student_name, fallback="Student"),
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
            typed_student = st.text_input("Student Name (optional)", key="typed_student", placeholder="e.g. Ashley Ndlovu")
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
                            student_name=typed_student or None,
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
                                "student_name": _clean_name(typed_student, fallback="Student"),
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
        st.caption("Refresh any tracked submission and load results when complete.")
        if not st.session_state.jobs:
            st.info("No submission tracked yet.")
        else:
            options: Dict[str, str] = {}
            for job in st.session_state.jobs:
                student = _clean_name(job.get("student_name"), fallback="Student")
                filename = str(job.get("filename") or "uploaded")
                upload_id = str(job.get("upload_id") or "")
                label = f"{student} | {filename} | {upload_id[:8]}"
                options[label] = upload_id

            selected_label = st.selectbox("Tracked submissions", list(options.keys()))
            selected_upload_id = options[selected_label]
            st.write(f"Selected Upload ID: `{selected_upload_id}`")

            if st.button("Refresh Selected Status", use_container_width=True):
                try:
                    payload = _refresh_job(api_client, selected_upload_id, fetch_result=True)
                    label, helper = _status_copy(payload.get("status", "unknown"))
                    st.success(f"Status: {label}")
                    if helper:
                        st.caption(helper)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not refresh status: {exc}")

with tutor_tab:
    st.markdown("### Tutor Workspace")
    tutor_subtabs = st.tabs(["Guide Upload", "Bulk Student Marking"])

    with tutor_subtabs[0]:
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
            c1.metric("Type", str(latest.get("doc_type", "-")).replace("_", " ").title())
            c2.metric("Stored", "Yes" if latest.get("saved_path") else "No")
            c3.metric("Chunks", (latest.get("ingestion") or {}).get("chunk_count", 0))
            with st.expander("Upload summary"):
                st.write(f"Path: `{latest.get('saved_path', '-')}`")
                ingestion = latest.get("ingestion") or {}
                st.write(f"Collection: `{ingestion.get('collection', '-')}`")
                st.write(f"Document ID: `{ingestion.get('document_id', '-')}`")

    with tutor_subtabs[1]:
        st.caption("Queue multiple student scripts at once and tag each upload with a student name.")
        with st.form("tutor_bulk_form", clear_on_submit=False):
            bulk_question_text = st.text_area(
                "Shared Question Context",
                placeholder="Paste the full question context used by this group...",
                help="Required for reliable marking.",
                height=130,
            )
            bulk_files = st.file_uploader(
                "Student Answer Files",
                type=["pdf", "docx"],
                accept_multiple_files=True,
                key="bulk_files",
            )
            bulk_names = st.text_area(
                "Student Names (one per line, same order as files)",
                placeholder="Alice Banda\nBrian Ncube\nCarla Moyo",
                height=110,
            )

            b1, b2, b3, b4 = st.columns([1.0, 1.0, 1.0, 1.2])
            with b1:
                bulk_paper = st.selectbox("Paper", ["AA"], key="bulk_paper")
            with b2:
                bulk_qnum = st.text_input("Question No. (optional)", key="bulk_qnum", placeholder="e.g. 1(b)")
            with b3:
                bulk_max = st.number_input(
                    "Max Marks",
                    min_value=1.0,
                    max_value=100.0,
                    value=16.0,
                    step=1.0,
                    key="bulk_max",
                )
            with b4:
                bulk_wait = st.slider(
                    "Optional quick wait",
                    min_value=0,
                    max_value=120,
                    value=0,
                    step=10,
                    key="bulk_wait",
                )

            auto_fill_names = st.checkbox("Auto-fill missing names from filenames", value=True)
            submit_bulk = st.form_submit_button("Queue Bulk Marking", type="primary", use_container_width=True)

        if submit_bulk:
            if not bulk_question_text.strip():
                st.warning("Please provide the shared question context.")
            elif not bulk_files:
                st.warning("Please upload at least one student file.")
            elif not backend_ok:
                st.error("Service is currently offline. Please try again shortly.")
            else:
                provided_names = _parse_student_names(bulk_names)
                if len(provided_names) > len(bulk_files):
                    st.error("You provided more names than files. Please align the list and try again.")
                else:
                    assignments: List[Tuple[Any, str]] = []
                    for idx, student_file in enumerate(bulk_files):
                        if idx < len(provided_names):
                            name = provided_names[idx]
                        elif auto_fill_names:
                            name = _clean_name(Path(getattr(student_file, "name", f"student_{idx + 1}")).stem.replace("_", " "))
                        else:
                            name = f"Student {idx + 1}"
                        assignments.append((student_file, name))

                    successes: List[Dict[str, str]] = []
                    failures: List[str] = []

                    with st.spinner(f"Queueing {len(assignments)} scripts..."):
                        for student_file, student_name in assignments:
                            try:
                                upload_resp = api_client.upload_file(
                                    file=student_file,
                                    paper=bulk_paper,
                                    question=bulk_qnum or None,
                                    question_text=bulk_question_text,
                                    max_marks=bulk_max,
                                    student_name=student_name,
                                )
                                upload_id = upload_resp.get("upload_id")
                                if upload_id:
                                    st.session_state.last_upload_id = upload_id
                                    _upsert_job(
                                        {
                                            "upload_id": upload_id,
                                            "filename": getattr(student_file, "name", "uploaded_file"),
                                            "student_name": student_name,
                                            "status": "pending",
                                            "progress": 5,
                                            "result_id": None,
                                        }
                                    )
                                    successes.append(
                                        {
                                            "Student": student_name,
                                            "File": getattr(student_file, "name", "uploaded_file"),
                                            "Upload ID": upload_id,
                                            "Status": "Queued",
                                        }
                                    )
                            except Exception as exc:  # noqa: BLE001
                                failures.append(f"{getattr(student_file, 'name', 'uploaded_file')}: {exc}")

                    if bulk_wait > 0 and successes:
                        start = time.time()
                        while time.time() - start <= bulk_wait:
                            for item in successes:
                                current_upload_id = item["Upload ID"]
                                try:
                                    status_payload = _refresh_job(api_client, current_upload_id, fetch_result=False)
                                    status_label, _ = _status_copy(status_payload.get("status", "pending"))
                                    item["Status"] = status_label
                                except Exception:  # noqa: BLE001
                                    item["Status"] = "Queued"
                            time.sleep(POLL_INTERVAL_SECONDS)

                    st.session_state.last_bulk_submission = successes

                    if successes:
                        st.success(f"Bulk queue complete: {len(successes)} submission(s) accepted.")
                        st.dataframe(successes, use_container_width=True, hide_index=True)
                    if failures:
                        st.error("Some files could not be queued:")
                        for failure in failures:
                            st.write(f"- {failure}")

        if st.session_state.last_bulk_submission:
            with st.expander("Last bulk queue summary", expanded=False):
                st.dataframe(st.session_state.last_bulk_submission, use_container_width=True, hide_index=True)

with results_tab:
    st.markdown("### Results")
    result = st.session_state.last_result

    if not result:
        st.info("No result available yet. Submit from the Student or Tutor workspace.")
    else:
        student_name = _clean_name(result.get("student_name"), fallback="Student")
        total_marks = _safe_float(result.get("total_marks"))
        max_marks = max(_safe_float(result.get("max_marks"), 1.0), 1.0)
        percentage = _safe_float(result.get("percentage"), (total_marks / max_marks) * 100)

        st.markdown(f"<div class='student-chip'>Candidate: {student_name}</div>", unsafe_allow_html=True)

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

        professional = result.get("professional_marks", {}) or {}
        if professional:
            st.markdown("#### Professional Marks")
            for skill, value in professional.items():
                st.write(f"- **{str(skill).replace('_', ' ').title()}**: {_safe_float(value):.2f}")

        citations = result.get("citations", []) or []
        if citations:
            with st.expander("References"):
                for cite in citations:
                    st.write(f"- {cite}")

        pdf_bytes = _build_feedback_pdf(result)
        file_stub = _safe_file_fragment(student_name, fallback="student")

        d1, d2 = st.columns(2)
        with d1:
            if st.button("Clear Result", use_container_width=True):
                st.session_state.last_result = None
                st.rerun()
        with d2:
            st.download_button(
                label="Download Feedback PDF",
                data=pdf_bytes,
                file_name=f"{file_stub}_feedback_{str(result.get('id', 'latest'))[:8]}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        if ADMIN_MODE:
            with st.expander("Developer JSON"):
                st.json(result)

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
                student_name = _clean_name(job.get("student_name"), fallback="Student")
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2.0, 1.0, 1.0])
                    c1.write(f"{student_name} - {job.get('filename', 'uploaded')}")
                    c1.caption(f"Upload ID: `{job.get('upload_id', '-')}`")
                    c2.metric("Status", label)
                    c3.metric("Progress", f"{int(job.get('progress', 0) or 0)}%")
                    if helper:
                        st.caption(helper)
                    if job.get("error"):
                        st.error(str(job["error"]))

st.divider()
st.caption(f"{APP_NAME} | {'Admin' if ADMIN_MODE else 'Client'} mode")
