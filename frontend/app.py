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
            with st.spinner("Processing your answer..."):
                # This is where we'll call the backend
                st.success("✅ Upload successful! Processing started.")
                st.info("⏳ Estimated time: 1-2 minutes")
                
                # Placeholder for progress
                progress_bar = st.progress(0)
                for i in range(100):
                    # Simulate progress
                    progress_bar.progress(i + 1)
                
                st.markdown('<div class="success-box">✅ Marking complete! Check the Results tab.</div>', 
                          unsafe_allow_html=True)

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