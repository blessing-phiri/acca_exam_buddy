"""
Quick test to verify setup.
Run with: python test_setup.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

print("Testing ACCA Exam Buddy Setup...\n")
print(f"Python: {sys.version.split()[0]} OK")


def check_import(module_name: str, label: str) -> None:
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", "unknown")
        print(f"{label}: {version} OK")
    except ImportError:
        print(f"MISSING: {label}")


check_import("fastapi", "FastAPI")
check_import("streamlit", "Streamlit")
check_import("chromadb", "ChromaDB")
check_import("PyPDF2", "PyPDF2")
check_import("docx", "python-docx")

from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")
if api_key and api_key != "sk-your-key-here":
    print(f"DeepSeek API key: OK (starts with {api_key[:5]}...)")
else:
    print("WARNING: DeepSeek API key not set in .env")

if Path("./venv").exists():
    print("Virtual environment: OK")
else:
    print("MISSING: Virtual environment not found")

print("\nSetup verification complete.")
