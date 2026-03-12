"""
Website resource scraper for ACCA knowledge ingestion.

Features:
- Crawls ACCA pages for PDF and technical article links
- Downloads PDFs and organizes by type
- Auto-ingests downloaded content into the knowledge base
- Applies request delay for respectful scraping
- Tracks manual fallback items for protected/login-gated resources
"""

from __future__ import annotations
import hashlib
import logging
import os
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from backend.services.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class AnchorExtractor(HTMLParser):
    """Extract href + anchor text pairs."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self._active_href: Optional[str] = None
        self._active_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._active_href = href
            self._active_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_href is None:
            return
        cleaned = data.strip()
        if cleaned:
            self._active_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._active_href is not None:
            self.links.append((self._active_href, " ".join(self._active_parts).strip()))
            self._active_href = None
            self._active_parts = []


@dataclass
class LinkCandidate:
    url: str
    label: str
    source_url: str


class ResourceScraper:
    """Crawl, download, and ingest ACCA resources."""

    def __init__(
        self,
        kb: KnowledgeBase,
        base_download_dir: str = "data/raw",
        request_delay_seconds: float = 1.0,
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ) -> None:
        self.kb = kb
        self.base_download_dir = Path(base_download_dir)
        self.request_delay_seconds = max(0.0, request_delay_seconds)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.session = requests.Session()
        self._last_request_at = 0.0

        for folder in ["marking_schemes", "examiner_reports", "technical"]:
            os.makedirs(self.base_download_dir / folder, exist_ok=True)

    def run(
        self,
        start_url: str,
        paper: str = "AA",
        auto_ingest: bool = True,
        max_pages: int = 30,
        max_pdf_downloads: int = 100,
        include_html_articles: bool = True,
    ) -> Dict:
        run_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        visited_pages: List[str] = []
        pdf_candidates: Dict[str, LinkCandidate] = {}
        article_candidates: Dict[str, LinkCandidate] = {}
        errors: List[Dict] = []
        downloaded_files: List[Dict] = []
        ingested_items: List[Dict] = []

        queue = deque([(start_url, 0)])
        seen_pages = set()
        base_domain = urlparse(start_url).netloc

        while queue and len(visited_pages) < max_pages:
            current_url, depth = queue.popleft()
            if current_url in seen_pages:
                continue
            seen_pages.add(current_url)

            response = self._request(current_url)
            if response is None:
                errors.append({"url": current_url, "error": "Failed to fetch page"})
                continue

            visited_pages.append(current_url)
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "pdf" in content_type or current_url.lower().endswith(".pdf"):
                pdf_candidates[current_url] = LinkCandidate(url=current_url, label="PDF", source_url=current_url)
                continue

            links = self._extract_links(current_url, response.text)
            for link in links:
                parsed = urlparse(link.url)
                if not parsed.scheme.startswith("http"):
                    continue
                if parsed.netloc != base_domain:
                    continue

                if self._is_pdf_url(link.url):
                    pdf_candidates.setdefault(link.url, link)
                    continue

                if include_html_articles and self._is_technical_article_url(link.url):
                    article_candidates.setdefault(link.url, link)

                if depth < 1 and self._should_follow_page(link.url):
                    queue.append((link.url, depth + 1))

        pdf_urls = list(pdf_candidates.values())[:max_pdf_downloads]
        for candidate in pdf_urls:
            category = self._categorize_resource(candidate.url, candidate.label)
            download_result = self._download_pdf(candidate.url, category)

            if not download_result.get("success"):
                reason = download_result.get("error", "Download failed")
                errors.append({"url": candidate.url, "error": reason})
                self.kb.add_manual_fallback(candidate.url, reason, context={"source_url": candidate.source_url})
                continue

            downloaded_files.append(download_result)

            if auto_ingest:
                ingest_result = self._auto_ingest_file(
                    file_path=download_result["file_path"],
                    category=category,
                    paper=paper,
                    source_url=candidate.url,
                )
                ingested_items.append({"source": candidate.url, "result": ingest_result})
                if not ingest_result.get("success"):
                    errors.append({"url": candidate.url, "error": ingest_result.get("error")})

        if auto_ingest and include_html_articles:
            for candidate in article_candidates.values():
                result = self.kb.ingest_technical_article_from_url(
                    url=candidate.url,
                    metadata={"paper": paper, "source_type": "technical_article_page"},
                    timeout=self.timeout_seconds,
                )
                ingested_items.append({"source": candidate.url, "result": result})
                if not result.get("success"):
                    errors.append({"url": candidate.url, "error": result.get("error")})

        summary = {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(),
            "start_url": start_url,
            "visited_pages": len(visited_pages),
            "pdf_links_found": len(pdf_candidates),
            "pdfs_downloaded": len(downloaded_files),
            "html_articles_found": len(article_candidates),
            "auto_ingest": auto_ingest,
            "ingested_items": len([item for item in ingested_items if item.get("result", {}).get("success")]),
            "errors_count": len(errors),
            "errors": errors,
            "downloads": downloaded_files,
        }

        run_path = self.kb.save_scrape_run(summary)
        summary["run_record"] = run_path
        return summary

    def _request(self, url: str) -> Optional[requests.Response]:
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout_seconds,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ACCAExamBuddy/1.0",
                        "Accept": "text/html,application/pdf,application/xhtml+xml",
                    },
                )
                self._last_request_at = time.monotonic()

                if response.status_code in {401, 403}:
                    self.kb.add_manual_fallback(url, f"Access denied ({response.status_code})", context={"source": "scraper"})
                    return None

                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue

                response.raise_for_status()
                return response
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.max_retries:
                    logger.warning("Request failed for %s: %s", url, exc)
                    return None
                time.sleep(1.2 * (attempt + 1))
        return None

    def _respect_rate_limit(self) -> None:
        if self.request_delay_seconds <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)

    def _extract_links(self, base_url: str, html: str) -> List[LinkCandidate]:
        parser = AnchorExtractor()
        parser.feed(html)
        candidates: List[LinkCandidate] = []

        for href, label in parser.links:
            absolute = urljoin(base_url, href).split("#", 1)[0]
            candidates.append(LinkCandidate(url=absolute, label=label, source_url=base_url))

        return candidates

    def _is_pdf_url(self, url: str) -> bool:
        return url.lower().endswith(".pdf") or ".pdf?" in url.lower()

    def _is_technical_article_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return "technical-articles" in path and path.endswith(".html") and not path.endswith("technical-articles.html")

    def _should_follow_page(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        keywords = ["exam-support-resources", "technical-articles", "study-resources", "f8"]
        return any(keyword in path for keyword in keywords)

    def _categorize_resource(self, url: str, label: str) -> str:
        combined = f"{url} {label}".lower()
        if "examiner" in combined and "report" in combined:
            return "examiner_reports"
        if "marking" in combined or "mark scheme" in combined or "scheme" in combined:
            return "marking_schemes"
        return "technical"

    def _download_pdf(self, url: str, category: str) -> Dict:
        response = self._request(url)
        if response is None:
            return {"success": False, "error": "Failed to fetch PDF"}

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "pdf" not in content_type and not self._is_pdf_url(url):
            return {"success": False, "error": f"Not a PDF response (Content-Type: {content_type})"}

        filename = self._build_filename(url)
        folder = self.base_download_dir / category
        os.makedirs(folder, exist_ok=True)

        output_path = folder / filename
        if output_path.exists():
            stem = output_path.stem
            suffix = output_path.suffix
            output_path = folder / f"{stem}_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]}{suffix}"

        with open(output_path, "wb") as file:
            file.write(response.content)

        return {
            "success": True,
            "url": url,
            "category": category,
            "file_path": str(output_path),
            "size": output_path.stat().st_size,
        }

    def _build_filename(self, url: str) -> str:
        parsed = urlparse(url)
        raw_name = Path(parsed.path).name or f"resource_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}.pdf"
        raw_name = raw_name.split("?", 1)[0]
        if not raw_name.lower().endswith(".pdf"):
            raw_name += ".pdf"

        safe = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)
        return safe[:180]

    def _auto_ingest_file(self, file_path: str, category: str, paper: str, source_url: str) -> Dict:
        metadata = {
            "paper": paper,
            "source_url": source_url,
            "source_type": "scraped_pdf",
            "scraped_at": datetime.now().isoformat(),
        }

        if category == "marking_schemes":
            metadata["type"] = "marking_scheme"
            return self.kb.ingest_marking_scheme(file_path, metadata)
        if category == "examiner_reports":
            metadata["type"] = "examiner_report"
            return self.kb.ingest_examiner_report(file_path, metadata)

        metadata["type"] = "technical_article"
        return self.kb.ingest_technical_document(file_path, metadata)

