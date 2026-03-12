"""
LLM Provider Classes
Handles API calls to different LLM providers
"""

import os
import httpx
import json
import asyncio
from typing import Optional, Dict, Any
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class DeepSeekProvider:
    """DeepSeek R1 API provider"""
    
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.model_name = "deepseek-reasoner"  # R1 model
        
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY not found in environment")
    
    async def generate(self, 
                      prompt: str,
                      temperature: float = 0.1,
                      max_tokens: int = 4000) -> str:
        """Generate response from DeepSeek"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # DeepSeek uses OpenAI-compatible API
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are an expert ACCA marker. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                return result['choices'][0]['message']['content']
                
            except httpx.TimeoutException:
                logger.error("DeepSeek API timeout")
                raise
            except Exception as e:
                logger.error(f"DeepSeek API error: {str(e)}")
                raise

class MiniMaxProvider:
    """MiniMax M2.5 API provider (fallback)"""
    
    def __init__(self):
        self.api_key = os.getenv("MINIMAX_API_KEY")
        self.group_id = os.getenv("MINIMAX_GROUP_ID")
        self.model_name = "MiniMax-M2.5"
        
        if not self.api_key or not self.group_id:
            logger.warning("MINIMAX credentials not found in environment")
    
    async def generate(self,
                      prompt: str,
                      temperature: float = 0.1,
                      max_tokens: int = 4000) -> str:
        """Generate response from MiniMax"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # MiniMax API format
        url = f"https://api.minimax.chat/v1/text/chatcompletion?GroupId={self.group_id}"
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are an expert ACCA marker. Respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                return result['choices'][0]['message']['content']
                
            except Exception as e:
                logger.error(f"MiniMax API error: {str(e)}")
                raise

class MockProvider:
    """Mock provider for testing without API calls"""
    
    def __init__(self):
        self.model_name = "mock"
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Return mock response"""
        
        # Simulate API delay
        await asyncio.sleep(1)
        
        return json.dumps({
            "total_marks": 12.5,
            "max_marks": 16,
            "question_marks": [
                {
                    "point": "Identified IT system risk",
                    "awarded": 0.5,
                    "explanation": "Correctly identified risk from new system"
                },
                {
                    "point": "Explained impact on completeness",
                    "awarded": 0.5,
                    "explanation": "Linked to completeness assertion"
                },
                {
                    "point": "Auditor response - test controls",
                    "awarded": 1.0,
                    "explanation": "Described specific testing procedures"
                }
            ],
            "professional_marks": {
                "structure": 0.5,
                "terminology": 0.5,
                "practicality": 0.5
            },
            "feedback": "Good answer with specific risks and practical responses.",
            "citations": ["ISA 240", "ISA 315"],
            "confidence_score": 0.85
        })