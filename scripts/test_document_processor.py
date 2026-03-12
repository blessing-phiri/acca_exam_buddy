"""
Test script for document processor
Run with: python scripts/test_document_processor.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.document_processor import DocumentProcessor
from backend.services.processing_service import ProcessingService
import json
from pathlib import Path

def test_with_sample():
    """Test document processor with sample files"""
    
    processor = DocumentProcessor()
    
    # Test with a sample text if no files available
    sample_text = """
    Requirement (a) - 4 marks
    
    Explain the responsibilities of the auditor under ISA 240.
    
    The auditor must obtain reasonable assurance that the financial statements 
    are free from material misstatement, whether caused by fraud or error.
    
    Requirement (b) - 6 marks
    
    Describe audit procedures for testing revenue.
    """
    
    print("=" * 50)
    print("Testing Document Processor")
    print("=" * 50)
    
    # Test question detection
    print("\n1. Testing question detection...")
    questions = processor.detect_questions(sample_text)
    print(f"   Found {len(questions)} questions")
    for q in questions:
        print(f"   - {q.get('type')} {q.get('part', q.get('number', ''))}: {q.get('marks', '?')} marks")
    
    # Test marking point extraction
    print("\n2. Testing marking point extraction...")
    marking_scheme = """
    1 mark for identifying the risk
    ½ mark for explaining the impact
    Award 1 mark if the response is practical
    • Test controls
    • Review documentation
    """
    points = processor.extract_marking_points(marking_scheme)
    print(f"   Found {len(points)} marking points")
    for p in points:
        print(f"   - {p.get('marks')} mark: {p.get('criteria')[:50]}...")
    
    # Test text cleaning
    print("\n3. Testing text cleaning...")
    messy_text = "This  is   a   test.\n\n\nWith extra   spaces.\nPage 1 of 5\nMore text."
    cleaned = processor.clean_text(messy_text)
    print(f"   Original: {repr(messy_text[:50])}")
    print(f"   Cleaned:  {repr(cleaned[:50])}")
    
    print("\n✅ All tests completed!")

def test_with_real_file(file_path: str):
    """Test with an actual PDF or DOCX file"""
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    print(f"\nTesting with real file: {file_path}")
    print("=" * 50)
    
    processor = DocumentProcessor()
    result = processor.process(file_path)
    
    if result.get("success"):
        print(f"✅ Successfully processed")
        print(f"   File type: {result.get('file_type')}")
        print(f"   Text length: {len(result.get('text', ''))} characters")
        print(f"   Preview: {result.get('text', '')[:200]}...")
    else:
        print(f"❌ Failed: {result.get('error')}")

if __name__ == "__main__":
    test_with_sample()
    
    # If command line argument provided, test that file
    if len(sys.argv) > 1:
        test_with_real_file(sys.argv[1])