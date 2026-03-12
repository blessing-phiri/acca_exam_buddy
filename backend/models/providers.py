"""LLM provider classes for DeepSeek, MiniMax, and mock mode."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _join_url(base_url: str, path: str) -> str:
    base = (base_url or "").strip()
    if not base:
        return path
    if not base.endswith("/"):
        base += "/"
    return urljoin(base, path.lstrip("/"))


def _trimmed(value: Optional[str]) -> str:
    return (value or "").strip()


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    placeholders = {
        "",
        "your-group-id",
        "your-key",
        "your-api-key",
        "sk-your-key-here",
        "mmsk-your-key-here",
        "replace-me",
        "changeme",
    }
    return lowered in placeholders


class DeepSeekProvider:
    """DeepSeek API provider using OpenAI-compatible chat endpoint."""

    def __init__(self) -> None:
        self.api_key = _trimmed(os.getenv("DEEPSEEK_API_KEY"))
        self.base_url = _trimmed(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
        self.model_name = _trimmed(os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner"))
        self.timeout_seconds = float(_trimmed(os.getenv("LLM_TIMEOUT_SECONDS", "60")) or 60)

        if _is_placeholder(self.api_key):
            logger.warning("DEEPSEEK_API_KEY missing or placeholder")

    async def generate(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4000) -> str:
        """Generate a response from DeepSeek."""
        if _is_placeholder(self.api_key):
            raise RuntimeError("DeepSeek not configured: set a valid DEEPSEEK_API_KEY in .env")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are an expert ACCA marker. Always respond with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        endpoint = _join_url(self.base_url, "/chat/completions")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=True) as client:
                response = await client.post(endpoint, headers=headers, json=payload)

            # Some models reject response_format; retry without it once.
            if response.status_code == 400 and "response_format" in (response.text or ""):
                payload.pop("response_format", None)
                async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=True) as client:
                    response = await client.post(endpoint, headers=headers, json=payload)

            response.raise_for_status()
            data = response.json()
            return self._extract_content(data)

        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot reach DeepSeek API ({endpoint}). Check internet/firewall/proxy and DEEPSEEK_BASE_URL"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("DeepSeek API timed out. Increase LLM_TIMEOUT_SECONDS or check network") from exc
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:300]
            raise RuntimeError(f"DeepSeek API HTTP {exc.response.status_code}: {body}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("DeepSeek API error: %s", exc)
            raise

    async def health_check(self) -> Dict[str, Any]:
        try:
            _ = await self.generate('Return JSON: {"ok": true}', max_tokens=32)
            return {
                "ok": True,
                "provider": "deepseek",
                "model": self.model_name,
                "base_url": self.base_url,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "provider": "deepseek",
                "model": self.model_name,
                "base_url": self.base_url,
                "error": str(exc),
            }

    def _extract_content(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek API returned no choices")

        message = choices[0].get("message") or {}
        content = message.get("content")

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
            joined = "".join(text_parts).strip()
            if joined:
                return joined

        raise RuntimeError("DeepSeek API returned empty content")


class MiniMaxProvider:
    """MiniMax API provider used as fallback."""

    def __init__(self) -> None:
        self.api_key = _trimmed(os.getenv("MINIMAX_API_KEY"))
        self.group_id = _trimmed(os.getenv("MINIMAX_GROUP_ID"))
        self.model_name = _trimmed(os.getenv("MINIMAX_MODEL", "MiniMax-M2.5"))
        self.timeout_seconds = float(_trimmed(os.getenv("LLM_TIMEOUT_SECONDS", "60")) or 60)

        if _is_placeholder(self.api_key) or _is_placeholder(self.group_id):
            logger.warning("MINIMAX credentials missing or placeholder")

    async def generate(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4000) -> str:
        """Generate a response from MiniMax."""
        if _is_placeholder(self.api_key) or _is_placeholder(self.group_id):
            raise RuntimeError("MiniMax not configured: set valid MINIMAX_API_KEY and MINIMAX_GROUP_ID in .env")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"https://api.minimax.chat/v1/text/chatcompletion?GroupId={self.group_id}"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are an expert ACCA marker. Respond with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=True) as client:
                response = await client.post(url, headers=headers, json=payload)

            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("MiniMax API returned no choices")
            content = (choices[0].get("message") or {}).get("content")
            if not content:
                raise RuntimeError("MiniMax API returned empty content")
            return str(content)

        except httpx.ConnectError as exc:
            raise RuntimeError("Cannot reach MiniMax API. Check internet/firewall/proxy") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("MiniMax API timed out. Increase LLM_TIMEOUT_SECONDS or check network") from exc
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:300]
            raise RuntimeError(f"MiniMax API HTTP {exc.response.status_code}: {body}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("MiniMax API error: %s", exc)
            raise

    async def health_check(self) -> Dict[str, Any]:
        try:
            _ = await self.generate('Return JSON: {"ok": true}', max_tokens=32)
            return {
                "ok": True,
                "provider": "minimax",
                "model": self.model_name,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "provider": "minimax",
                "model": self.model_name,
                "error": str(exc),
            }


class MockProvider:
    """Mock provider for testing without external API calls."""

    def __init__(self) -> None:
        self.model_name = "mock"

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        await asyncio.sleep(0.2)
        return json.dumps(
            {
                "total_marks": 12.5,
                "max_marks": 16,
                "question_marks": [
                    {
                        "point": "Identified IT system risk",
                        "awarded": 0.5,
                        "explanation": "Correctly identified risk from new system",
                    },
                    {
                        "point": "Explained impact on completeness",
                        "awarded": 0.5,
                        "explanation": "Linked to completeness assertion",
                    },
                    {
                        "point": "Auditor response - test controls",
                        "awarded": 1.0,
                        "explanation": "Described specific testing procedures",
                    },
                ],
                "professional_marks": {
                    "structure": 0.5,
                    "terminology": 0.5,
                    "practicality": 0.5,
                    "commercial_awareness": 0.5,
                },
                "feedback": "Good answer with specific risks and practical responses.",
                "citations": ["ISA 240", "ISA 315"],
                "confidence_score": 0.85,
            }
        )

    async def health_check(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "provider": "mock",
            "model": self.model_name,
        }
