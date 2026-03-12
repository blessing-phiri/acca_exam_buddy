"""
Knowledge base service.
Handles ingestion and retrieval of ACCA knowledge documents.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from backend.services.document_processor import DocumentProcessor
from backend.services.vector_store import VectorStore
from backend.utils.text_utils import extract_keywords

logger = logging.getLogger(__name__)


class LinkExtractor(HTMLParser):
    """Extract links and their text from HTML content."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self._active_href: Optional[str] = None
        self._active_text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._active_href = href
            self._active_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_href is not None:
            cleaned = data.strip()
            if cleaned:
                self._active_text_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._active_href is not None:
            anchor_text = " ".join(self._active_text_parts).strip()
            self.links.append((self._active_href, anchor_text))
            self._active_href = None
            self._active_text_parts = []


class ArticleTextExtractor(HTMLParser):
    """Extract readable text while skipping script/style blocks."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_stack: List[str] = []
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag_lower = tag.lower()
        if tag_lower in {"script", "style", "noscript"}:
            self._skip_stack.append(tag_lower)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._skip_stack and self._skip_stack[-1] == tag_lower:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if cleaned:
            self._parts.append(cleaned)

    @property
    def text(self) -> str:
        return "\n".join(self._parts)


class TitleExtractor(HTMLParser):
    """Extract the document title from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._inside_title = False
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            cleaned = data.strip()
            if cleaned:
                self._parts.append(cleaned)

    @property
    def title(self) -> str:
        return " ".join(self._parts).strip()


class KnowledgeBase:
    """Main knowledge base for ACCA marking."""

    def __init__(self, vector_store: Optional[VectorStore] = None) -> None:
        self.vector_store = vector_store or VectorStore()
        self.processor = DocumentProcessor()
        self.data_dir = "data/knowledge"
        os.makedirs(self.data_dir, exist_ok=True)

        self.valid_papers = ["AA", "AAA", "F8"]
        self.question_types = [
            "audit_risk",
            "ethical_threats",
            "substantive_procedures",
            "internal_control",
            "audit_report",
            "going_concern",
            "professional_marks",
        ]

    def ingest_marking_scheme(self, file_path: str, metadata: Dict) -> Dict:
        logger.info("Ingesting marking scheme: %s", file_path)
        process_result = self.processor.process(file_path)
        if not process_result.get("success", False):
            return {"success": False, "error": process_result.get("error", "Processing failed")}

        text = process_result.get("text", "")
        chunks = self._chunk_marking_scheme(text, metadata)
        ids = self.vector_store.add_document_chunks(
            collection_name="marking_schemes",
            chunks=[chunk["text"] for chunk in chunks],
            metadatas=[chunk["metadata"] for chunk in chunks],
        )

        record_file = self._save_ingestion_record(
            source=file_path,
            collection="marking_schemes",
            metadata=metadata,
            chunk_count=len(chunks),
            chunk_ids=ids,
        )

        return {
            "success": True,
            "collection": "marking_schemes",
            "chunk_count": len(chunks),
            "ids": ids,
            "record_file": record_file,
        }

    def ingest_examiner_report(self, file_path: str, metadata: Dict) -> Dict:
        logger.info("Ingesting examiner report: %s", file_path)
        process_result = self.processor.process(file_path)
        if not process_result.get("success", False):
            return {"success": False, "error": process_result.get("error", "Processing failed")}

        text = process_result.get("text", "")
        sections = self._extract_examiner_sections(text)

        chunks: List[Dict] = []
        for section in sections:
            chunks.append(
                {
                    "text": section["text"],
                    "metadata": {
                        **metadata,
                        "section_type": section["type"],
                        "question_ref": section.get("question_ref", "general"),
                        "insight_type": section.get("insight_type", "general"),
                    },
                }
            )

        ids = self.vector_store.add_document_chunks(
            collection_name="examiner_reports",
            chunks=[chunk["text"] for chunk in chunks],
            metadatas=[chunk["metadata"] for chunk in chunks],
        )

        record_file = self._save_ingestion_record(
            source=file_path,
            collection="examiner_reports",
            metadata=metadata,
            chunk_count=len(chunks),
            chunk_ids=ids,
        )

        return {
            "success": True,
            "collection": "examiner_reports",
            "chunk_count": len(chunks),
            "ids": ids,
            "record_file": record_file,
        }

    def ingest_technical_document(self, file_path: str, metadata: Dict) -> Dict:
        """Ingest local technical content from PDF/DOCX/TXT/MD/HTML files."""
        logger.info("Ingesting technical document: %s", file_path)
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        suffix = path.suffix.lower()
        if suffix in {".pdf", ".docx"}:
            process_result = self.processor.process(str(path))
            if not process_result.get("success", False):
                return {"success": False, "error": process_result.get("error", "Processing failed")}
            raw_text = process_result.get("text", "")
        else:
            try:
                raw_text = path.read_text(encoding="utf-8", errors="ignore")
                if suffix in {".html", ".htm"}:
                    raw_text = self._extract_article_text(raw_text)
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": f"Failed to read {file_path}: {exc}"}

        base_metadata = {
            **metadata,
            "type": "technical_article",
            "source_file": path.name,
            "source_path": str(path),
            "file_ext": suffix,
        }
        return self._ingest_technical_text(raw_text=raw_text, base_metadata=base_metadata)

    def ingest_technical_article_from_url(self, url: str, metadata: Optional[Dict] = None, timeout: int = 30) -> Dict:
        """Fetch and ingest a technical article from a website URL."""
        logger.info("Ingesting technical article URL: %s", url)

        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ACCAExamBuddy/1.0",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Failed to fetch URL {url}: {exc}"}

        html = response.text
        title = self._extract_html_title(html) or url
        article_text = self._extract_article_text(html)

        base_metadata = {
            **(metadata or {}),
            "type": "technical_article",
            "source_url": url,
            "source_title": title,
        }
        return self._ingest_technical_text(raw_text=article_text, base_metadata=base_metadata)

    def ingest_technical_articles_from_index(
        self,
        index_url: str,
        metadata: Optional[Dict] = None,
        max_articles: int = 20,
    ) -> Dict:
        """
        Crawl a technical-articles index page and ingest each article page.

        Returns ingestion summary with successes/failures per URL.
        """
        logger.info("Discovering technical article links from index: %s", index_url)
        try:
            response = requests.get(
                index_url,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ACCAExamBuddy/1.0",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Failed to fetch index URL {index_url}: {exc}"}

        links = self._extract_article_links(index_url, response.text)
        if max_articles > 0:
            links = links[:max_articles]

        ingested = 0
        failed = 0
        total_chunks = 0
        errors: List[Dict] = []
        results: List[Dict] = []

        for url in links:
            result = self.ingest_technical_article_from_url(url, metadata=metadata)
            results.append({"url": url, "result": result})

            if result.get("success"):
                ingested += 1
                total_chunks += int(result.get("chunk_count", 0))
            else:
                failed += 1
                errors.append({"url": url, "error": result.get("error", "Unknown error")})

        return {
            "success": True,
            "index_url": index_url,
            "discovered": len(links),
            "ingested": ingested,
            "failed": failed,
            "total_chunks": total_chunks,
            "errors": errors,
            "results": results,
        }

    def retrieve_marking_rules(
        self,
        question_text: str,
        question_type: Optional[str] = None,
        paper: str = "AA",
        n_results: int = 5,
    ) -> List[Dict]:
        keywords = extract_keywords(question_text)
        filter_dict = {"paper": paper} if paper else None

        if question_type:
            if filter_dict is None:
                filter_dict = {}
            filter_dict["question_type"] = question_type

        return self.vector_store.hybrid_search(
            collection_name="marking_schemes",
            query=question_text,
            keywords=keywords,
            n_results=n_results,
            filter_dict=filter_dict,
        )

    def retrieve_examiner_guidance(
        self,
        question_text: str,
        question_type: Optional[str] = None,
        n_results: int = 3,
    ) -> List[Dict]:
        filter_dict = {"question_type": question_type} if question_type else None
        return self.vector_store.search(
            collection_name="examiner_reports",
            query=question_text,
            n_results=n_results,
            filter_dict=filter_dict,
        )

    def retrieve_technical_references(
        self,
        query: str,
        paper: str = "AA",
        n_results: int = 5,
    ) -> List[Dict]:
        filter_dict = {"paper": paper} if paper else None
        keywords = extract_keywords(query)
        return self.vector_store.hybrid_search(
            collection_name="technical_articles",
            query=query,
            keywords=keywords,
            n_results=n_results,
            filter_dict=filter_dict,
        )

    def get_knowledge_summary(self) -> Dict:
        stats = {}
        for collection_name in ["marking_schemes", "examiner_reports", "technical_articles"]:
            stats[collection_name] = self.vector_store.get_collection_stats(collection_name)

        ingested_files = list(Path(self.data_dir).glob("ingestion_*.json"))
        return {
            "vector_stats": stats,
            "ingested_files_count": len(ingested_files),
            "status": "ready",
        }

    def _chunk_marking_scheme(self, text: str, base_metadata: Dict) -> List[Dict]:
        chunks: List[Dict] = []
        lines = text.split("\n")
        current_chunk: List[str] = []
        current_question = None
        current_marks = None

        question_patterns = [
            r"Question\s+(\d+)",
            r"Requirement\s*\(([a-z])\)",
            r"\(([a-z])\)\s+marks?\s*(\d+)",
            r"Part\s+\(([a-z])\)",
        ]

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            is_new_question = False
            for pattern in question_patterns:
                match = re.search(pattern, stripped, re.IGNORECASE)
                if match:
                    is_new_question = True
                    if len(match.groups()) >= 1:
                        current_question = match.group(1)
                    if len(match.groups()) >= 2:
                        try:
                            current_marks = float(match.group(2))
                        except Exception:  # noqa: BLE001
                            current_marks = None
                    break

            if is_new_question and current_chunk:
                chunk_text = "\n".join(current_chunk)
                if len(chunk_text) > 50:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "metadata": {
                                **base_metadata,
                                "question_ref": current_question,
                                "marks": current_marks,
                                "chunk_type": "question",
                            },
                        }
                    )
                current_chunk = [stripped]
            else:
                current_chunk.append(stripped)

        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            if len(chunk_text) > 50:
                chunks.append(
                    {
                        "text": chunk_text,
                        "metadata": {
                            **base_metadata,
                            "question_ref": current_question,
                            "marks": current_marks,
                            "chunk_type": "question",
                        },
                    }
                )

        marking_points = self.processor.extract_marking_points(text)
        for index, point in enumerate(marking_points):
            chunks.append(
                {
                    "text": point["criteria"],
                    "metadata": {
                        **base_metadata,
                        "marks": point["marks"],
                        "chunk_type": "marking_point",
                        "point_index": index,
                    },
                }
            )

        return chunks

    def _extract_examiner_sections(self, text: str) -> List[Dict]:
        sections: List[Dict] = []

        mistake_patterns = [
            r"common mistakes?(.*?)(?=\n\n|\Z)",
            r"common errors?(.*?)(?=\n\n|\Z)",
            r"weaknesses(.*?)(?=\n\n|\Z)",
        ]
        for pattern in mistake_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                candidate = match.strip()
                if candidate:
                    sections.append(
                        {
                            "text": candidate,
                            "type": "examiner_comment",
                            "insight_type": "common_mistakes",
                        }
                    )

        good_patterns = [
            r"good answers?(.*?)(?=\n\n|\Z)",
            r"strong answers?(.*?)(?=\n\n|\Z)",
            r"excellent responses?(.*?)(?=\n\n|\Z)",
        ]
        for pattern in good_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                candidate = match.strip()
                if candidate:
                    sections.append(
                        {
                            "text": candidate,
                            "type": "examiner_comment",
                            "insight_type": "good_example",
                        }
                    )

        partial_patterns = [
            r"partial credit(.*?)(?=\n\n|\Z)",
            r"half mark(.*?)(?=\n\n|\Z)",
            r"1/2 mark(.*?)(?=\n\n|\Z)",
            r"½ mark(.*?)(?=\n\n|\Z)",
        ]
        for pattern in partial_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                candidate = match.strip()
                if candidate:
                    sections.append(
                        {
                            "text": candidate,
                            "type": "examiner_comment",
                            "insight_type": "partial_credit",
                        }
                    )

        if not sections:
            questions = self.processor.detect_questions(text)
            for question in questions:
                candidate = question.get("text", "")
                if candidate:
                    sections.append(
                        {
                            "text": candidate,
                            "type": "question_feedback",
                            "question_ref": question.get("part", question.get("number", "unknown")),
                        }
                    )

        if not sections:
            chunks = self._chunk_text_for_rag(text)
            for chunk in chunks:
                sections.append({"text": chunk, "type": "general"})

        return sections

    def _ingest_technical_text(self, raw_text: str, base_metadata: Dict) -> Dict:
        cleaned = self.processor.clean_text(raw_text)
        if len(cleaned) < 80:
            return {"success": False, "error": "Insufficient text extracted from technical source"}

        text_chunks = self._chunk_text_for_rag(cleaned)
        if not text_chunks:
            return {"success": False, "error": "No chunks generated from technical content"}

        chunk_payloads: List[Dict] = []
        for index, chunk_text in enumerate(text_chunks):
            chunk_payloads.append(
                {
                    "text": chunk_text,
                    "metadata": {
                        **base_metadata,
                        "chunk_type": "technical_reference",
                        "chunk_index": index,
                        "chunk_total": len(text_chunks),
                    },
                }
            )

        ids = self.vector_store.add_document_chunks(
            collection_name="technical_articles",
            chunks=[chunk["text"] for chunk in chunk_payloads],
            metadatas=[chunk["metadata"] for chunk in chunk_payloads],
        )

        source = base_metadata.get("source_url") or base_metadata.get("source_file") or "technical_source"
        record_file = self._save_ingestion_record(
            source=str(source),
            collection="technical_articles",
            metadata=base_metadata,
            chunk_count=len(text_chunks),
            chunk_ids=ids,
        )

        return {
            "success": True,
            "collection": "technical_articles",
            "chunk_count": len(text_chunks),
            "ids": ids,
            "record_file": record_file,
        }

    def _extract_article_links(self, index_url: str, html: str) -> List[str]:
        parser = LinkExtractor()
        parser.feed(html)

        base_domain = urlparse(index_url).netloc
        normalized: List[str] = []
        seen = set()

        for href, _label in parser.links:
            absolute = urljoin(index_url, href).split("#", 1)[0]
            parsed = urlparse(absolute)

            if not parsed.scheme.startswith("http"):
                continue
            if parsed.netloc != base_domain:
                continue
            if "/technical-articles/" not in parsed.path:
                continue
            if parsed.path.endswith("technical-articles.html"):
                continue
            if not parsed.path.endswith(".html"):
                continue

            if absolute not in seen:
                seen.add(absolute)
                normalized.append(absolute)

        return normalized

    def _extract_html_title(self, html: str) -> str:
        parser = TitleExtractor()
        parser.feed(html)
        return parser.title

    def _extract_article_text(self, html: str) -> str:
        parser = ArticleTextExtractor()
        parser.feed(html)
        return parser.text

    def _chunk_text_for_rag(self, text: str, max_chars: int = 1200, overlap_chars: int = 180) -> List[str]:
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if len(paragraph.strip()) >= 40]

        if not paragraphs:
            cleaned = text.strip()
            if not cleaned:
                return []
            return [cleaned[i : i + max_chars] for i in range(0, len(cleaned), max_chars)]

        chunks: List[str] = []
        current_parts: List[str] = []
        current_len = 0

        for paragraph in paragraphs:
            para_len = len(paragraph)
            if para_len > max_chars:
                if current_parts:
                    chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_len = 0

                start = 0
                while start < para_len:
                    end = min(start + max_chars, para_len)
                    piece = paragraph[start:end]
                    if piece.strip():
                        chunks.append(piece.strip())
                    if end >= para_len:
                        break
                    start = max(end - overlap_chars, start + 1)
                continue

            separator_len = 2 if current_parts else 0
            if current_len + para_len + separator_len <= max_chars:
                current_parts.append(paragraph)
                current_len += para_len + separator_len
                continue

            if current_parts:
                chunks.append("\n\n".join(current_parts))

            if overlap_chars > 0 and chunks:
                previous_tail = chunks[-1][-overlap_chars:]
                current_parts = [previous_tail, paragraph]
                current_len = len(previous_tail) + len(paragraph)
            else:
                current_parts = [paragraph]
                current_len = para_len

        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 40]

    def _save_ingestion_record(
        self,
        source: str,
        collection: str,
        metadata: Dict,
        chunk_count: int,
        chunk_ids: List[str],
    ) -> str:
        record = {
            "source": source,
            "collection": collection,
            "metadata": metadata,
            "chunk_count": chunk_count,
            "chunk_ids": chunk_ids,
            "ingested_at": datetime.now().isoformat(),
        }

        record_name = f"ingestion_{hashlib.md5(source.encode('utf-8')).hexdigest()}_{collection}.json"
        record_path = os.path.join(self.data_dir, record_name)
        with open(record_path, "w", encoding="utf-8") as file:
            json.dump(record, file, indent=2)

        return record_path

