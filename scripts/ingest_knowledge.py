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


def ingest_all(
    kb: KnowledgeBase,
    data_dir: str = "data/raw",
    paper: str = "AA",
    include_web: bool = False,
    web_index_url: str = "https://www.accaglobal.com/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html",
    max_web_articles: int = 15,
) -> Dict:
    base = Path(data_dir)
    stats = {
        "marking_schemes": 0,
        "examiner_reports": 0,
        "technical_local": 0,
        "technical_web": 0,
        "total_chunks": 0,
        "errors": [],
    }

    marking_files = list_files(base / "marking_schemes", {".pdf", ".docx"})
    print(f"Marking schemes found: {len(marking_files)}")
    for file_path in marking_files:
        metadata = parse_filename_metadata(file_path, "marking_scheme", paper)
        print(f"  Ingesting marking scheme: {file_path.name}")
        result = kb.ingest_marking_scheme(str(file_path), metadata)
        if result.get("success"):
            stats["marking_schemes"] += 1
            stats["total_chunks"] += int(result.get("chunk_count", 0))
            print(f"    OK - {result.get('chunk_count', 0)} chunks")
        else:
            error = f"{file_path.name}: {result.get('error', 'Unknown error')}"
            stats["errors"].append(error)
            print(f"    FAIL - {result.get('error')}")

    examiner_files = list_files(base / "examiner_reports", {".pdf", ".docx"})
    print(f"Examiner reports found: {len(examiner_files)}")
    for file_path in examiner_files:
        metadata = parse_filename_metadata(file_path, "examiner_report", paper)
        print(f"  Ingesting examiner report: {file_path.name}")
        result = kb.ingest_examiner_report(str(file_path), metadata)
        if result.get("success"):
            stats["examiner_reports"] += 1
            stats["total_chunks"] += int(result.get("chunk_count", 0))
            print(f"    OK - {result.get('chunk_count', 0)} chunks")
        else:
            error = f"{file_path.name}: {result.get('error', 'Unknown error')}"
            stats["errors"].append(error)
            print(f"    FAIL - {result.get('error')}")

    technical_files = list_files(base / "technical", SUPPORTED_DOC_EXTENSIONS)
    print(f"Local technical files found: {len(technical_files)}")
    for file_path in technical_files:
        metadata = parse_filename_metadata(file_path, "technical_article", paper)
        print(f"  Ingesting technical file: {file_path.name}")
        result = kb.ingest_technical_document(str(file_path), metadata)
        if result.get("success"):
            stats["technical_local"] += 1
            stats["total_chunks"] += int(result.get("chunk_count", 0))
            print(f"    OK - {result.get('chunk_count', 0)} chunks")
        else:
            error = f"{file_path.name}: {result.get('error', 'Unknown error')}"
            stats["errors"].append(error)
            print(f"    FAIL - {result.get('error')}")

    if include_web:
        print(f"Crawling technical web index: {web_index_url}")
        result = kb.ingest_technical_articles_from_index(
            index_url=web_index_url,
            metadata={"paper": paper, "source_type": "website"},
            max_articles=max_web_articles,
        )
        if result.get("success"):
            stats["technical_web"] += int(result.get("ingested", 0))
            stats["total_chunks"] += int(result.get("total_chunks", 0))
            for web_error in result.get("errors", []):
                stats["errors"].append(f"{web_error.get('url')}: {web_error.get('error')}")
            print(
                f"  Web ingest summary - discovered: {result.get('discovered', 0)}, "
                f"ingested: {result.get('ingested', 0)}, failed: {result.get('failed', 0)}"
            )
        else:
            stats["errors"].append(f"web_index: {result.get('error')}")
            print(f"  FAIL - {result.get('error')}")

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
        print(f"\nQuery: {query}")
        marking = kb.retrieve_marking_rules(query, n_results=2)
        technical = kb.retrieve_technical_references(query, n_results=2)
        examiner = kb.retrieve_examiner_guidance(query, n_results=1)

        print(f"  Marking rules: {len(marking)}")
        print(f"  Technical references: {len(technical)}")
        print(f"  Examiner guidance: {len(examiner)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ACCA documents into the knowledge base")
    parser.add_argument("--dir", type=str, default="data/raw", help="Data directory to ingest")
    parser.add_argument("--paper", type=str, default="AA", help="Default paper code")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base statistics")
    parser.add_argument("--test", action="store_true", help="Run retrieval tests")
    parser.add_argument("--include-web", action="store_true", help="Ingest technical articles from ACCA web index")
    parser.add_argument(
        "--web-index-url",
        type=str,
        default="https://www.accaglobal.com/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html",
        help="Technical article index URL",
    )
    parser.add_argument("--max-web-articles", type=int, default=15, help="Max web articles to ingest")

    args = parser.parse_args()

    print("ACCA Knowledge Base Ingestor")
    print("=" * 50)

    kb = KnowledgeBase()

    if args.stats:
        summary = kb.get_knowledge_summary()
        print(summary)
        return

    if args.test:
        test_retrieval(kb)
        return

    stats = ingest_all(
        kb=kb,
        data_dir=args.dir,
        paper=args.paper,
        include_web=args.include_web,
        web_index_url=args.web_index_url,
        max_web_articles=args.max_web_articles,
    )

    print("\nIngestion complete")
    print("=" * 50)
    print(f"Marking schemes ingested: {stats['marking_schemes']}")
    print(f"Examiner reports ingested: {stats['examiner_reports']}")
    print(f"Technical local ingested: {stats['technical_local']}")
    print(f"Technical web ingested: {stats['technical_web']}")
    print(f"Total chunks stored: {stats['total_chunks']}")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for error in stats["errors"]:
            print(f"  - {error}")

    print("\nKnowledge base summary:")
    print(kb.get_knowledge_summary())


if __name__ == "__main__":
    main()
