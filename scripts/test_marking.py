"""
Test Marking Engine
Run with: python scripts/test_marking.py
"""

import sys
import os
import asyncio
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.marking_service import MarkingService
from backend.llm.providers import MockProvider
import argparse
from datetime import datetime

# Sample test cases from examiner's report
TEST_CASES = [
    {
        "name": "Good Audit Risk Answer",
        "question": "Describe EIGHT audit risks and explain the auditor's response to each risk in planning the audit of Pimento Co.",
        "answer": """
Risk 1: New IT System Implementation
The company is implementing a new IT system for inventory management. This creates a risk of incomplete or inaccurate data transfer during the transition period.
Explanation: This could affect the completeness and accuracy of inventory records, leading to misstatement of inventory valuation.
Auditor Response: Review system implementation plans, perform test data runs through the new system, and increase sample sizes for inventory testing during the transition period.

Risk 2: Reliance on Internal Audit
The internal audit department only visits stores every 24 months, which may not be frequent enough to detect control deficiencies.
Explanation: This creates a detection risk as the auditor may rely on ineffective internal audit work.
Auditor Response: Assess the effectiveness of internal audit by reviewing their reports and testing a sample of their work. Do not automatically rely on their findings.
        """,
        "max_marks": 16,
        "type": "audit_risk"
    },
    {
        "name": "Weak Audit Risk Answer",
        "question": "Describe EIGHT audit risks and explain the auditor's response to each risk in planning the audit of Pimento Co.",
        "answer": """
There is a risk of material misstatement. The auditor should do more testing. There might be fraud. The auditor should be careful.
        """,
        "max_marks": 16,
        "type": "audit_risk"
    },
    {
        "name": "Ethical Threats Answer",
        "question": "Identify and explain THREE ethical threats which may affect the audit of Pimento Co and recommend safeguards.",
        "answer": """
1. Self-interest threat: The audit fee is based on a percentage of profit. This could cause the audit team to overlook adjustments that would reduce profit.
Safeguard: The audit firm should negotiate a fixed fee based on work required, not contingent on profit.

2. Familiarity threat: The audit manager's daughter works as the finance director's assistant.
Safeguard: Remove the audit manager from the engagement and assign a different manager.

3. Intimidation threat: The finance director has threatened to put the audit out to tender if the audit team questions certain estimates.
Safeguard: Document all discussions with the finance director and escalate to an independent partner for review.
        """,
        "max_marks": 6,
        "type": "ethical_threats"
    }
]

async def run_tests(use_mock: bool = False):
    """Run marking tests"""
    
    print("🧪 Testing Marking Engine")
    print("=" * 50)
    
    # Initialize service
    service = MarkingService()
    
    # Override with mock if requested
    if use_mock:
        service.primary_llm = MockProvider()
        print("Using MOCK provider (no API calls)\n")
    
    results = []
    
    for test in TEST_CASES:
        print(f"\n📝 Test: {test['name']}")
        print("-" * 40)
        
        start_time = datetime.now()
        
        try:
            result = await service.mark_answer(
                question_text=test['question'],
                student_answer=test['answer'],
                max_marks=test['max_marks'],
                question_type=test['type']
            )
            
            time_taken = (datetime.now() - start_time).total_seconds()
            
            print(f"✅ Success!")
            print(f"   Total Marks: {result['total_marks']}/{test['max_marks']}")
            print(f"   Confidence: {result.get('confidence_score', 0):.2f}")
            print(f"   Time: {time_taken:.1f}s")
            print(f"   Needs Review: {result.get('needs_review', False)}")
            
            if result.get('professional_marks'):
                prof_total = sum(result['professional_marks'].values())
                print(f"   Professional Marks: {prof_total}/2")
            
            results.append({
                "test": test['name'],
                "success": True,
                "result": result
            })
            
        except Exception as e:
            print(f"❌ Failed: {str(e)}")
            results.append({
                "test": test['name'],
                "success": False,
                "error": str(e)
            })
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    print(f"Total Tests: {len(results)}")
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    
    if successful:
        avg_marks = sum(r['result']['total_marks'] for r in successful) / len(successful)
        print(f"Average Marks: {avg_marks:.2f}")
    
    # Save results
    output_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Test marking engine")
    parser.add_argument("--mock", action="store_true", help="Use mock provider (no API calls)")
    parser.add_argument("--case", type=int, help="Run specific test case (0-based index)")
    
    args = parser.parse_args()
    
    if args.case is not None:
        # Run single test case
        if args.case < 0 or args.case >= len(TEST_CASES):
            print(f"Invalid test case. Available: 0-{len(TEST_CASES)-1}")
            return
        
        test = TEST_CASES[args.case]
        print(f"Running single test: {test['name']}")
        asyncio.run(run_tests(use_mock=args.mock))
    else:
        # Run all tests
        asyncio.run(run_tests(use_mock=args.mock))

if __name__ == "__main__":
    main()