"""Core marking service that orchestrates RAG + LLM scoring."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from backend.models.prompts import PromptBuilder
from backend.models.providers import DeepSeekProvider, MiniMaxProvider, MockProvider
from backend.services.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class QuestionType(str, Enum):
    AUDIT_RISK = "audit_risk"
    ETHICAL_THREATS = "ethical_threats"
    SUBSTANTIVE_PROCEDURES = "substantive_procedures"
    INTERNAL_CONTROL = "internal_control"
    AUDIT_REPORT = "audit_report"
    GOING_CONCERN = "going_concern"
    PROFESSIONAL_MARKS = "professional_marks"


class MarkingService:
    """Main marking engine."""

    def __init__(self) -> None:
        self.knowledge_base = KnowledgeBase()
        self.primary_llm, self.fallback_llm = self._configure_providers()
        self._active_model_name = getattr(self.primary_llm, "model_name", type(self.primary_llm).__name__)
        self.stats: Dict[str, Any] = {
            "total_marked": 0,
            "avg_confidence": 0.0,
            "avg_time_ms": 0.0,
            "by_type": {},
        }

    async def mark_answer(
        self,
        question_text: str,
        student_answer: str,
        max_marks: float,
        question_type: Optional[str] = None,
        paper_code: str = "AA",
        context: Optional[Dict] = None,
    ) -> Dict:
        """Mark a student answer end-to-end."""
        started = datetime.now()
        normalized_max = max(1.0, float(max_marks))
        detected_type = self._normalize_question_type(question_type, question_text)

        logger.info("Marking answer type=%s max_marks=%s", detected_type.value, normalized_max)

        marking_rules = self._retrieve_marking_rules(
            question_text=question_text,
            question_type=detected_type.value,
            paper_code=paper_code,
        )
        examiner_guidance = self._retrieve_examiner_guidance(
            question_text=question_text,
            question_type=detected_type.value,
        )

        prompt = self._build_prompt(
            question_type=detected_type,
            question_text=question_text,
            student_answer=student_answer,
            marking_rules=marking_rules,
            examiner_guidance=examiner_guidance,
            max_marks=normalized_max,
            context=context,
        )

        llm_response = await self._call_llm_with_retry(prompt)
        parsed = self._parse_llm_response(llm_response, normalized_max)
        result = self._ensure_result_schema(parsed, normalized_max)

        elapsed_ms = (datetime.now() - started).total_seconds() * 1000
        result["question_type"] = detected_type.value
        result["paper_code"] = paper_code
        result["processing_time_ms"] = elapsed_ms
        result["model_used"] = self._active_model_name
        result["confidence_score"] = self._calculate_confidence(result, normalized_max)
        result["needs_review"] = result["confidence_score"] < 0.7

        await self._store_for_consistency(
            result=result,
            answer_text=student_answer,
            paper_code=paper_code,
            question_type=detected_type.value,
        )

        self._update_stats(result)
        return result

    def _configure_providers(self) -> Tuple[Any, Optional[Any]]:
        mode = os.getenv("MARKING_PROVIDER", "auto").strip().lower()
        has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
        has_minimax = bool(os.getenv("MINIMAX_API_KEY", "").strip() and os.getenv("MINIMAX_GROUP_ID", "").strip())

        primary: Any
        fallback: Optional[Any] = None

        if mode == "mock":
            primary = MockProvider()
            return primary, None

        if mode == "deepseek" and has_deepseek:
            primary = DeepSeekProvider()
        elif mode == "minimax" and has_minimax:
            primary = MiniMaxProvider()
        elif has_deepseek:
            primary = DeepSeekProvider()
        elif has_minimax:
            primary = MiniMaxProvider()
        else:
            primary = MockProvider()
            logger.warning("No LLM API credentials configured; using MockProvider")

        if isinstance(primary, DeepSeekProvider) and has_minimax:
            fallback = MiniMaxProvider()
        elif not isinstance(primary, MockProvider):
            fallback = MockProvider()

        return primary, fallback

    def _normalize_question_type(self, explicit_type: Optional[str], question_text: str) -> QuestionType:
        if explicit_type:
            lowered = explicit_type.strip().lower()
            for value in QuestionType:
                if lowered == value.value:
                    return value
        return self._detect_question_type(question_text)

    def _detect_question_type(self, question_text: str) -> QuestionType:
        text_lower = (question_text or "").lower()
        if any(term in text_lower for term in ["audit risk", "risk of material misstatement"]):
            return QuestionType.AUDIT_RISK
        if any(term in text_lower for term in ["ethical threat", "safeguard", "ethics"]):
            return QuestionType.ETHICAL_THREATS
        if any(term in text_lower for term in ["substantive procedure", "audit procedure"]):
            return QuestionType.SUBSTANTIVE_PROCEDURES
        if any(term in text_lower for term in ["internal control", "control deficiency"]):
            return QuestionType.INTERNAL_CONTROL
        if any(term in text_lower for term in ["auditor's report", "audit opinion"]):
            return QuestionType.AUDIT_REPORT
        if "going concern" in text_lower:
            return QuestionType.GOING_CONCERN
        return QuestionType.AUDIT_RISK

    def _retrieve_marking_rules(self, question_text: str, question_type: str, paper_code: str) -> List[Dict]:
        results = self.knowledge_base.retrieve_marking_rules(
            question_text=question_text,
            question_type=question_type,
            paper=paper_code,
            n_results=5,
        )
        return [
            {
                "text": hit.get("document", ""),
                "marks": (hit.get("metadata") or {}).get("marks", "unknown"),
                "source": (hit.get("metadata") or {}).get("paper", "unknown"),
                "relevance": max(0.0, 1 - float(hit.get("distance", 0.0))),
            }
            for hit in results
            if hit.get("document")
        ]

    def _retrieve_examiner_guidance(self, question_text: str, question_type: str) -> List[str]:
        hits = self.knowledge_base.retrieve_examiner_guidance(
            question_text=question_text,
            question_type=question_type,
            n_results=3,
        )
        return [item.get("document", "") for item in hits if item.get("document")]

    def _build_prompt(
        self,
        question_type: QuestionType,
        question_text: str,
        student_answer: str,
        marking_rules: List[Dict],
        examiner_guidance: List[str],
        max_marks: float,
        context: Optional[Dict],
    ) -> str:
        if question_type == QuestionType.AUDIT_RISK:
            return PromptBuilder.build_audit_risk_prompt(
                question_text=question_text,
                student_answer=student_answer,
                marking_rules=marking_rules,
                examiner_guidance=examiner_guidance,
                max_marks=max_marks,
                context=context,
            )
        if question_type == QuestionType.ETHICAL_THREATS:
            return PromptBuilder.build_ethical_threats_prompt(
                question_text=question_text,
                student_answer=student_answer,
                marking_rules=marking_rules,
                examiner_guidance=examiner_guidance,
                max_marks=max_marks,
                context=context,
            )
        if question_type == QuestionType.SUBSTANTIVE_PROCEDURES:
            return PromptBuilder.build_procedures_prompt(
                question_text=question_text,
                student_answer=student_answer,
                marking_rules=marking_rules,
                examiner_guidance=examiner_guidance,
                max_marks=max_marks,
                context=context,
            )
        return self._build_generic_prompt(
            question_text=question_text,
            student_answer=student_answer,
            marking_rules=marking_rules,
            examiner_guidance=examiner_guidance,
            max_marks=max_marks,
            context=context,
        )

    def _build_generic_prompt(
        self,
        question_text: str,
        student_answer: str,
        marking_rules: List[Dict],
        examiner_guidance: List[str],
        max_marks: float,
        context: Optional[Dict] = None,
    ) -> str:
        serialized_rules = json.dumps(marking_rules[:8], ensure_ascii=False)
        serialized_guidance = json.dumps(examiner_guidance[:8], ensure_ascii=False)
        serialized_context = json.dumps(context or {}, ensure_ascii=False)

        return (
            "You are an expert ACCA AA marker. Evaluate the student answer strictly and respond with valid JSON only.\n\n"
            f"QUESTION:\n{question_text}\n\n"
            f"MAXIMUM MARKS: {max_marks}\n\n"
            f"MARKING RULES: {serialized_rules}\n"
            f"EXAMINER GUIDANCE: {serialized_guidance}\n"
            f"EXTRA CONTEXT: {serialized_context}\n\n"
            f"STUDENT ANSWER:\n{student_answer}\n\n"
            "JSON schema:\n"
            "{\n"
            '  "total_marks": 0.0,\n'
            f'  "max_marks": {max_marks},\n'
            '  "question_marks": [{"point": "string", "awarded": 0.0, "explanation": "string"}],\n'
            '  "professional_marks": {"structure": 0.0, "terminology": 0.0, "practicality": 0.0, "commercial_awareness": 0.0},\n'
            '  "feedback": "string",\n'
            '  "citations": ["string"]\n'
            "}"
        )

    async def _call_llm_with_retry(self, prompt: str, max_retries: int = 2) -> str:
        providers: List[Any] = [self.primary_llm]
        if self.fallback_llm is not None:
            providers.append(self.fallback_llm)

        errors: List[str] = []
        for provider_index, provider in enumerate(providers):
            attempts = max_retries if provider_index == 0 else 1
            for attempt in range(attempts):
                try:
                    self._active_model_name = getattr(provider, "model_name", type(provider).__name__)
                    return await provider.generate(prompt)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "LLM call failed provider=%s attempt=%s error=%s",
                        type(provider).__name__,
                        attempt + 1,
                        exc,
                    )
                    errors.append(f"{type(provider).__name__}: {exc}")

        raise RuntimeError("All LLM attempts failed: " + " | ".join(errors))

    def _parse_llm_response(self, response: str, max_marks: float) -> Dict:
        payload = (response or "").strip()
        if not payload:
            return self._extract_from_text("", max_marks)

        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = payload.find("{")
        end = payload.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(payload[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return self._extract_from_text(payload, max_marks)

    def _extract_from_text(self, text: str, max_marks: float) -> Dict:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        mark_pattern = re.compile(r"total[:\s]*(\d+(?:\.\d+)?)", re.IGNORECASE)
        total_marks = 0.0
        for line in lines:
            match = mark_pattern.search(line)
            if match:
                total_marks = float(match.group(1))
                break

        total_marks = max(0.0, min(total_marks, max_marks))
        return {
            "total_marks": total_marks,
            "max_marks": max_marks,
            "question_marks": [],
            "professional_marks": {"structure": 0.0, "terminology": 0.0, "practicality": 0.0, "commercial_awareness": 0.0},
            "feedback": (text or "Unable to parse structured marking output.")[:800],
            "citations": [],
        }

    def _ensure_result_schema(self, payload: Dict, max_marks: float) -> Dict:
        result = dict(payload or {})
        raw_total = result.get("total_marks", 0.0)
        try:
            total_marks = float(raw_total)
        except Exception:  # noqa: BLE001
            total_marks = 0.0
        total_marks = max(0.0, min(total_marks, max_marks))

        question_marks_raw = result.get("question_marks", [])
        question_marks: List[Dict[str, Any]] = []
        if isinstance(question_marks_raw, list):
            for index, item in enumerate(question_marks_raw):
                if not isinstance(item, dict):
                    continue
                point = str(item.get("point") or f"Point {index + 1}")
                explanation = str(item.get("explanation") or "No explanation provided")
                try:
                    awarded = float(item.get("awarded", 0.0))
                except Exception:  # noqa: BLE001
                    awarded = 0.0
                question_marks.append(
                    {
                        "point": point,
                        "awarded": max(0.0, min(awarded, max_marks)),
                        "explanation": explanation,
                    }
                )

        if total_marks == 0.0 and question_marks:
            total_marks = max(0.0, min(sum(float(item["awarded"]) for item in question_marks), max_marks))

        professional_marks_raw = result.get("professional_marks") or {}
        professional_marks: Dict[str, float] = {}
        if isinstance(professional_marks_raw, dict):
            for key, value in professional_marks_raw.items():
                try:
                    professional_marks[str(key)] = float(value)
                except Exception:  # noqa: BLE001
                    continue

        feedback = str(result.get("feedback") or "No feedback generated.")
        citations_raw = result.get("citations") or []
        citations: List[str] = [str(item) for item in citations_raw] if isinstance(citations_raw, list) else [str(citations_raw)]

        return {
            "total_marks": round(total_marks, 2),
            "max_marks": max_marks,
            "question_marks": question_marks,
            "professional_marks": professional_marks,
            "feedback": feedback,
            "citations": citations,
        }

    def _calculate_confidence(self, result: Dict, max_marks: float) -> float:
        confidence = 0.95
        if not result.get("question_marks"):
            confidence -= 0.25
        if not result.get("professional_marks"):
            confidence -= 0.1
        if len((result.get("feedback") or "").strip()) < 30:
            confidence -= 0.15
        if not result.get("citations"):
            confidence -= 0.05

        total = float(result.get("total_marks", 0.0))
        if max_marks > 0:
            ratio = total / max_marks
            if ratio < 0.05 or ratio > 0.98:
                confidence -= 0.05

        return max(0.0, min(1.0, confidence))

    async def _store_for_consistency(self, result: Dict, answer_text: str, paper_code: str, question_type: str) -> None:
        try:
            self.knowledge_base.ingest_student_answer(
                answer_text=answer_text,
                metadata={
                    "paper": paper_code,
                    "question_type": question_type,
                    "source_type": "marked_answer",
                    "awarded_marks": result.get("total_marks"),
                    "max_marks": result.get("max_marks"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Consistency storage skipped: %s", exc)

    def _update_stats(self, result: Dict) -> None:
        self.stats["total_marked"] += 1
        q_type = result.get("question_type", "unknown")

        by_type = self.stats["by_type"].setdefault(
            q_type,
            {"count": 0, "total_confidence": 0.0, "total_time": 0.0},
        )
        by_type["count"] += 1
        by_type["total_confidence"] += float(result.get("confidence_score", 0.0))
        by_type["total_time"] += float(result.get("processing_time_ms", 0.0))

        all_confidence = [item["total_confidence"] for item in self.stats["by_type"].values()]
        all_time = [item["total_time"] for item in self.stats["by_type"].values()]
        total_marked = max(1, int(self.stats["total_marked"]))
        self.stats["avg_confidence"] = sum(all_confidence) / total_marked
        self.stats["avg_time_ms"] = sum(all_time) / total_marked

    def get_stats(self) -> Dict:
        return self.stats
