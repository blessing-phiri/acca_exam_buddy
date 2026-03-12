"""
ACCA AA AI Marker - Frontend Entry Point
"""

import streamlit as st
import requests
import os
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="ACCA AA AI Marker",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'show_results' not in st.session_state:
    st.session_state['show_results'] = False
if 'last_result' not in st.session_state:
    st.session_state['last_result'] = None

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #2563EB;
        margin-bottom: 1rem;
    }
    .success-box {
        padding: 1rem;
        background-color: #D1FAE5;
        border-radius: 0.5rem;
        border-left: 0.5rem solid #10B981;
    }
    .info-box {
        padding: 1rem;
        background-color: #DBEAFE;
        border-radius: 0.5rem;
        border-left: 0.5rem solid #3B82F6;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">📝 ACCA AA AI Marker</h1>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://via.placeholder.com/300x100/1E3A8A/FFFFFF?text=ACCA+AA+Marker", use_column_width=True)
    st.markdown("### About")
    st.info(
        "This AI-powered tool helps ACCA AA students practice by "
        "automatically marking their exam answers against official "
        "marking schemes."
    )
    
    st.markdown("### Status")
    st.success("🟢 System Online")
    
    st.markdown("### Quick Stats")
    st.metric("Questions Marked", "0", delta="Today")
    st.metric("Accuracy", "90%", delta="Target")

# Main content
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown('<h2 class="sub-header">📤 Upload Your Answer</h2>', unsafe_allow_html=True)
    
    # Upload form
    with st.form("upload_form"):
        uploaded_file = st.file_uploader(
            "Choose a PDF or Word file",
            type=['pdf', 'docx'],
            help="Upload your ACCA AA exam answer"
        )
        
        col_paper, col_question = st.columns(2)
        with col_paper:
            paper = st.selectbox(
                "Paper",
                ["AA (Audit and Assurance)"],
                help="Select the ACCA paper"
            )
        with col_question:
            question = st.text_input(
                "Question Number (optional)",
                placeholder="e.g., 1(b) or leave blank for auto-detect"
            )
        
submitted = st.form_submit_button("🚀 Upload and Mark", type="primary")

if submitted and uploaded_file is not None:
    # Check backend connection
    if not api_client.health_check():
        st.error("❌ Backend not connected. Please start the backend server.")
    else:
        with st.spinner("Uploading file..."):
            try:
                # Upload file
                result = api_client.upload_file(uploaded_file, paper, question)
                upload_id = result["upload_id"]
                st.success("✅ Upload successful!")
                
                # Show progress
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                # Poll for status
                import time
                while True:
                    status = api_client.get_status(upload_id)
                    progress_bar.progress(status["progress"] / 100)
                    progress_text.text(f"Status: {status['status']} ({status['progress']}%)")
                    
                    if status["status"] == "complete":
                        break
                    elif status["status"] == "failed":
                        st.error("❌ Processing failed")
                        break
                    
                    time.sleep(1)
                
                if status["status"] == "complete":
                    # Get results
                    result_data = api_client.get_result(status["result_id"])
                    
                    # Store in session state
                    st.session_state['last_result'] = result_data
                    st.session_state['show_results'] = True
                    
                    st.success("✅ Marking complete!")
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
# After the form, show results if available
if st.session_state.get('show_results', False):
    st.markdown("---")
    st.markdown('<h2 class="sub-header">📊 Marking Results</h2>', unsafe_allow_html=True)
    
    result = st.session_state['last_result']
    
    # Score card
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Score", f"{result['total_marks']}/{result['max_marks']}")
    with col2:
        st.metric("Percentage", f"{result['percentage']}%")
    with col3:
        st.metric("Professional Marks", f"{sum(result['professional_marks'].values())}/2")
    
    # Question breakdown
    st.markdown("### 📝 Question Breakdown")
    for point in result['question_marks']:
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(f"**{point['point']}**")
            st.caption(point['explanation'])
        with col_b:
            marks = point['awarded']
            if marks == 1.0:
                st.markdown(f"<h3 style='color: green;'>✓ {marks}</h3>", unsafe_allow_html=True)
            elif marks == 0.5:
                st.markdown(f"<h3 style='color: orange;'>½ {marks}</h3>", unsafe_allow_html=True)
            else:
                st.markdown(f"<h3 style='color: red;'>✗ {marks}</h3>", unsafe_allow_html=True)
    
    # Professional marks breakdown
    st.markdown("### 🎯 Professional Marks")
    for skill, mark in result['professional_marks'].items():
        st.markdown(f"- **{skill.capitalize()}**: {mark}/0.5")
    
    # Feedback
    st.markdown("### 💬 Feedback")
    st.info(result['feedback'])
    
    # Citations
    with st.expander("📚 View Citations"):
        for citation in result['citations']:
            st.markdown(f"- {citation}")

with col2:
    st.markdown('<h2 class="sub-header">📋 Instructions</h2>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box">
    <strong>How to use:</strong>
    <ol>
        <li>Upload your answer (PDF or Word)</li>
        <li>Select the paper (AA only for now)</li>
        <li>Add question number (optional)</li>
        <li>Click "Upload and Mark"</li>
        <li>Wait 1-2 minutes for results</li>
        <li>Review detailed feedback</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 📊 Sample Results")
    st.markdown("""
    *Coming soon: View your marked answers here*
    """)

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #6B7280;'>"
    "© 2026 ACCA AA AI Marker | Built with ❤️ for ACCA students"
    "</div>",
    unsafe_allow_html=True
)