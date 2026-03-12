"""
Knowledge Base Ingestion Script
Run with: python scripts/ingest_knowledge.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.knowledge_base import KnowledgeBase
from pathlib import Path
import json
import time
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def ingest_all(kb: KnowledgeBase, data_dir: str = "data/raw"):
    """
    Ingest all ACCA documents from data/raw directory
    
    Expected structure:
    data/raw/
        marking_schemes/
            AA_MJ25_marking.pdf
            AA_MJ24_marking.pdf
        examiner_reports/
            AA_MJ25_examiner.pdf
            AA_MJ24_examiner.pdf
        technical/
            article1.pdf
    """
    stats = {
        "marking_schemes": 0,
        "examiner_reports": 0,
        "technical": 0,
        "errors": []
    }
    
    # Process marking schemes
    ms_dir = Path(data_dir) / "marking_schemes"
    if ms_dir.exists():
        print(f"\n📚 Processing marking schemes from {ms_dir}")
        for file_path in ms_dir.glob("*.pdf"):
            print(f"  Ingesting: {file_path.name}")
            
            # Extract metadata from filename
            filename = file_path.stem
            parts = filename.split('_')
            
            metadata = {
                "paper": parts[0] if len(parts) > 0 else "AA",
                "year": parts[1] if len(parts) > 1 else "unknown",
                "type": "marking_scheme",
                "source_file": file_path.name
            }
            
            try:
                result = kb.ingest_marking_scheme(str(file_path), metadata)
                if result.get("success"):
                    stats["marking_schemes"] += 1
                    print(f"    ✅ Added {result['chunk_count']} chunks")
                else:
                    stats["errors"].append(f"{file_path.name}: {result.get('error')}")
                    print(f"    ❌ Failed: {result.get('error')}")
            except Exception as e:
                stats["errors"].append(f"{file_path.name}: {str(e)}")
                print(f"    ❌ Error: {str(e)}")
            
            time.sleep(0.5)  # Be nice to the system
    
    # Process examiner reports
    er_dir = Path(data_dir) / "examiner_reports"
    if er_dir.exists():
        print(f"\n📝 Processing examiner reports from {er_dir}")
        for file_path in er_dir.glob("*.pdf"):
            print(f"  Ingesting: {file_path.name}")
            
            parts = file_path.stem.split('_')
            metadata = {
                "paper": parts[0] if len(parts) > 0 else "AA",
                "year": parts[1] if len(parts) > 1 else "unknown",
                "type": "examiner_report",
                "source_file": file_path.name
            }
            
            try:
                result = kb.ingest_examiner_report(str(file_path), metadata)
                if result.get("success"):
                    stats["examiner_reports"] += 1
                    print(f"    ✅ Added {result['chunk_count']} chunks")
                else:
                    stats["errors"].append(f"{file_path.name}: {result.get('error')}")
                    print(f"    ❌ Failed: {result.get('error')}")
            except Exception as e:
                stats["errors"].append(f"{file_path.name}: {str(e)}")
                print(f"    ❌ Error: {str(e)}")
            
            time.sleep(0.5)
    
    return stats

def test_retrieval(kb: KnowledgeBase):
    """Test retrieval with sample queries"""
    print("\n🔍 Testing Retrieval")
    print("=" * 50)
    
    test_queries = [
        "What are the audit risks for a new IT system?",
        "How should I handle ethical threats from familiarity?",
        "What substantive procedures for trade receivables?",
        "How are professional marks awarded?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 40)
        
        # Retrieve marking rules
        rules = kb.retrieve_marking_rules(query, n_results=2)
        print(f"Found {len(rules)} marking rules:")
        for i, rule in enumerate(rules):
            print(f"  {i+1}. {rule['document'][:100]}...")
            if rule.get('metadata'):
                print(f"     Source: {rule['metadata'].get('paper', 'unknown')}")
        
        # Retrieve examiner guidance
        guidance = kb.retrieve_examiner_guidance(query, n_results=1)
        if guidance:
            print(f"\nExaminer guidance: {guidance[0]['document'][:150]}...")

def main():
    parser = argparse.ArgumentParser(description="Ingest ACCA documents into knowledge base")
    parser.add_argument("--dir", type=str, default="data/raw", help="Data directory to ingest")
    parser.add_argument("--test", action="store_true", help="Run retrieval tests after ingestion")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base statistics")
    
    args = parser.parse_args()
    
    print("🧠 ACCA Knowledge Base Ingestor")
    print("=" * 50)
    
    # Initialize knowledge base
    kb = KnowledgeBase()
    
    if args.stats:
        stats = kb.get_knowledge_summary()
        print("\n📊 Knowledge Base Statistics")
        print(json.dumps(stats, indent=2))
        return
    
    if args.test:
        test_retrieval(kb)
        return
    
    # Run ingestion
    print(f"\n📂 Ingesting from: {args.dir}")
    stats = ingest_all(kb, args.dir)
    
    print("\n" + "=" * 50)
    print("📊 Ingestion Complete")
    print("=" * 50)
    print(f"Marking Schemes: {stats['marking_schemes']}")
    print(f"Examiner Reports: {stats['examiner_reports']}")
    print(f"Technical Articles: {stats['technical']}")
    
    if stats['errors']:
        print(f"\n❌ Errors ({len(stats['errors'])}):")
        for error in stats['errors']:
            print(f"  - {error}")
    
    # Show final stats
    print("\n📊 Final Knowledge Base State:")
    final_stats = kb.get_knowledge_summary()
    for coll, stat in final_stats['vector_stats'].items():
        print(f"  {coll}: {stat['count']} chunks")

if __name__ == "__main__":
    main()