"""
Knowledge base ingestion CLI.
Run with: python scripts/ingest_knowledge.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.knowledge_base import KnowledgeBase
from backend.services.resource_scraper import ResourceScraper


load_dotenv()

SUPPORTED_DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}


def parse_filename_metadata(file_path: Path, doc_type: str, fallback_paper: str) -> Dict:
    stem = file_path.stem.lower()
    year_match = re.search(r"(20\d{2}|\b[msdj][a-z]?\d{2}\b)", stem, re.IGNORECASE)

    detected_paper = fallback_paper
    for paper in ["AAA", "AA", "F8"]:
        if paper.lower() in stem:
            detected_paper = paper
            break

    return {
        "paper": detected_paper,
        "year": year_match.group(1).upper() if year_match else "unknown",
        "type": doc_type,
        "source_file": file_path.name,
    }


def list_files(directory: Path, extensions: Iterable[str]) -> List[Path]:
    if not directory.exists():
        return []
    allowed = {ext.lower() for ext in extensions}
    return sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in allowed)


def ingest_all(kb: KnowledgeBase, data_dir: str = "data/raw", paper: str = "AA") -> Dict:
    base = Path(data_dir)
    stats = {
        "marking_schemes": 0,
        "examiner_reports": 0,
        "technical_local": 0,
        "total_chunks": 0,
        "errors": [],
    }

    marking_files = list_files(base / "marking_schemes", {".pdf", ".docx"})
    print(f"Marking schemes found: {len(marking_files)}")
    for file_path in marking_files:
        metadata = parse_filename_metadata(file_path, "marking_scheme", paper)
        result = kb.ingest_marking_scheme(str(file_path), metadata)
        if result.get("success"):
            stats["marking_schemes"] += 1
            stats["total_chunks"] += int(result.get("chunk_count", 0))
            print(f"  OK marking scheme: {file_path.name} ({result.get('chunk_count', 0)} chunks)")
        else:
            error = f"{file_path.name}: {result.get('error', 'Unknown error')}"
            stats["errors"].append(error)
            print(f"  FAIL marking scheme: {error}")

    examiner_files = list_files(base / "examiner_reports", {".pdf", ".docx"})
    print(f"Examiner reports found: {len(examiner_files)}")
    for file_path in examiner_files:
        metadata = parse_filename_metadata(file_path, "examiner_report", paper)
        result = kb.ingest_examiner_report(str(file_path), metadata)
        if result.get("success"):
            stats["examiner_reports"] += 1
            stats["total_chunks"] += int(result.get("chunk_count", 0))
            print(f"  OK examiner report: {file_path.name} ({result.get('chunk_count', 0)} chunks)")
        else:
            error = f"{file_path.name}: {result.get('error', 'Unknown error')}"
            stats["errors"].append(error)
            print(f"  FAIL examiner report: {error}")

    technical_files = list_files(base / "technical", SUPPORTED_DOC_EXTENSIONS)
    print(f"Local technical files found: {len(technical_files)}")
    for file_path in technical_files:
        metadata = parse_filename_metadata(file_path, "technical_article", paper)
        result = kb.ingest_technical_document(str(file_path), metadata)
        if result.get("success"):
            stats["technical_local"] += 1
            stats["total_chunks"] += int(result.get("chunk_count", 0))
            print(f"  OK technical file: {file_path.name} ({result.get('chunk_count', 0)} chunks)")
        else:
            error = f"{file_path.name}: {result.get('error', 'Unknown error')}"
            stats["errors"].append(error)
            print(f"  FAIL technical file: {error}")

    return stats


def test_retrieval(kb: KnowledgeBase) -> None:
    print("Retrieval smoke test")
    print("=" * 50)

    queries = [
        "What are the audit risks for a new IT system?",
        "How should I handle ethical threats from familiarity?",
        "What substantive procedures for trade receivables?",
        "How are professional marks awarded?",
    ]

    for query in queries:
        marking = kb.retrieve_marking_rules(query, n_results=2)
        technical = kb.retrieve_technical_references(query, n_results=2)
        examiner = kb.retrieve_examiner_guidance(query, n_results=1)

        print(f"\nQuery: {query}")
        print(f"  Marking rules: {len(marking)}")
        print(f"  Technical references: {len(technical)}")
        print(f"  Examiner guidance: {len(examiner)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ACCA documents into the knowledge base")
    parser.add_argument("--dir", type=str, default="data/raw", help="Data directory to ingest")
    parser.add_argument("--paper", type=str, default="AA", help="Default paper code")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base statistics")
    parser.add_argument("--test", action="store_true", help="Run retrieval tests")

    parser.add_argument("--scrape", action="store_true", help="Crawl ACCA website, download PDFs, and auto-ingest")
    parser.add_argument(
        "--scrape-url",
        type=str,
        default="https://www.accaglobal.com/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html",
        help="Start URL for ACCA scraping",
    )
    parser.add_argument("--scrape-max-pages", type=int, default=30, help="Maximum pages to crawl")
    parser.add_argument("--scrape-max-pdfs", type=int, default=100, help="Maximum PDFs to download")
    parser.add_argument("--scrape-delay", type=float, default=1.0, help="Delay between requests (seconds)")
    parser.add_argument("--scrape-no-auto-ingest", action="store_true", help="Only download resources, do not ingest")

    args = parser.parse_args()

    print("ACCA Knowledge Base Ingestor")
    print("=" * 50)

    kb = KnowledgeBase()

    if args.stats:
        print(kb.get_knowledge_summary())
        return

    if args.test:
        test_retrieval(kb)
        return

    local_stats = ingest_all(kb=kb, data_dir=args.dir, paper=args.paper)

    scrape_result = None
    if args.scrape:
        scraper = ResourceScraper(kb=kb, request_delay_seconds=args.scrape_delay)
        scrape_result = scraper.run(
            start_url=args.scrape_url,
            paper=args.paper,
            auto_ingest=not args.scrape_no_auto_ingest,
            max_pages=args.scrape_max_pages,
            max_pdf_downloads=args.scrape_max_pdfs,
            include_html_articles=True,
        )

    print("\nIngestion complete")
    print("=" * 50)
    print(f"Marking schemes ingested: {local_stats['marking_schemes']}")
    print(f"Examiner reports ingested: {local_stats['examiner_reports']}")
    print(f"Technical local ingested: {local_stats['technical_local']}")
    print(f"Total local chunks stored: {local_stats['total_chunks']}")

    if local_stats["errors"]:
        print(f"\nLocal ingestion errors ({len(local_stats['errors'])}):")
        for error in local_stats["errors"]:
            print(f"  - {error}")

    if scrape_result:
        print("\nScrape summary")
        print("-" * 50)
        print(f"Visited pages: {scrape_result['visited_pages']}")
        print(f"PDF links found: {scrape_result['pdf_links_found']}")
        print(f"PDFs downloaded: {scrape_result['pdfs_downloaded']}")
        print(f"HTML technical articles found: {scrape_result['html_articles_found']}")
        print(f"Auto-ingested items: {scrape_result['ingested_items']}")
        print(f"Errors: {scrape_result['errors_count']}")

    print("\nKnowledge base summary:")
    print(kb.get_knowledge_summary())


if __name__ == "__main__":
    main()
