"""
API service for frontend-backend communication
"""

import requests
import streamlit as st
import os
from typing import Optional, Dict, Any

class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        
    def health_check(self) -> bool:
        """Check if backend is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def upload_file(self, file, paper: str, question: Optional[str] = None) -> Dict[str, Any]:
        """Upload a file for marking"""
        url = f"{self.base_url}/api/v1/upload"
        
        files = {"file": (file.name, file, file.type)}
        data = {"paper": paper}
        if question:
            data["question_number"] = question
            
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        return response.json()
    
    def get_status(self, upload_id: str) -> Dict[str, Any]:
        """Get processing status"""
        url = f"{self.base_url}/api/v1/status/{upload_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_result(self, result_id: str) -> Dict[str, Any]:
        """Get marking result"""
        url = f"{self.base_url}/api/v1/result/{result_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

# Initialize client
api_client = APIClient()

# Check connection on startup
if not api_client.health_check():
    st.sidebar.warning("⚠️ Backend not connected. Start with: uvicorn backend.main:app --reload")
else:
    st.sidebar.success("✅ Backend connected")