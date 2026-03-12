"""
Quick test to verify all components are working
Run with: python test_setup.py
"""

import sys
import os
from pathlib import Path

print("🔍 Testing ACCA Exam Buddy Setup...\n")

# Test Python version
print(f"Python: {sys.version.split()[0]} ✓")

# Test imports
try:
    import fastapi
    print(f"FastAPI: {fastapi.__version__} ✓")
except ImportError:
    print("❌ FastAPI not installed")

try:
    import streamlit
    print(f"Streamlit: {streamlit.__version__} ✓")
except ImportError:
    print("❌ Streamlit not installed")

try:
    import chromadb
    print(f"ChromaDB: {chromadb.__version__} ✓")
except ImportError:
    print("❌ ChromaDB not installed")

try:
    import PyPDF2
    print(f"PyPDF2: {PyPDF2.__version__} ✓")
except ImportError:
    print("❌ PyPDF2 not installed")

# Test environment
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
if api_key and api_key != "sk-your-key-here":
    print(f"DeepSeek API key: ✓ (starts with {api_key[:5]}...)")
else:
    print("⚠️  DeepSeek API key not set in .env")

# Test paths
venv_path = Path("./venv")
if venv_path.exists():
    print("Virtual environment: ✓")
else:
    print("❌ Virtual environment not found")

print("\n✅ Setup verification complete!")