"""Manual marking engine smoke test.
Run with: python scripts/test_marking.py --mock
"""

from __future__ import annotations

__test__ = False

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.providers import MockProvider
from backend.services.marking_service import MarkingService

TEST_CASES = [
    {
        "name": "Good Audit Risk Answer",
        "question": "Describe EIGHT audit risks and explain the auditor response to each.",
        "answer": "There is a risk from a new IT system rollout and data migration errors. The auditor should test controls and perform data reconciliation procedures.",
        "max_marks": 16,
        "type": "audit_risk",
    },
    {
        "name": "Weak Audit Risk Answer",
        "question": "Describe EIGHT audit risks and explain the auditor response to each.",
        "answer": "There is risk and the auditor should do more testing.",
        "max_marks": 16,
        "type": "audit_risk",
    },
    {
        "name": "Ethical Threats Answer",
        "question": "Identify and explain THREE ethical threats and safeguards.",
        "answer": "A familiarity threat may arise if staff relationships become too close. Safeguard: rotate senior engagement staff.",
        "max_marks": 6,
        "type": "ethical_threats",
    },
]


async def run_tests(use_mock: bool = False) -> None:
    print("Testing Marking Engine")
    print("=" * 50)

    service = MarkingService()
    if use_mock:
        service.primary_llm = MockProvider()
        service.fallback_llm = None
        print("Using mock provider (no API calls).")

    results = []
    for test in TEST_CASES:
        print(f"\nTest: {test['name']}")
        print("-" * 40)
        started = datetime.now()

        try:
            result = await service.mark_answer(
                question_text=test["question"],
                student_answer=test["answer"],
                max_marks=test["max_marks"],
                question_type=test["type"],
            )
            elapsed = (datetime.now() - started).total_seconds()
            print("Success")
            print(f"  Total Marks: {result['total_marks']}/{test['max_marks']}")
            print(f"  Confidence: {result.get('confidence_score', 0):.2f}")
            print(f"  Time: {elapsed:.2f}s")
            results.append({"test": test["name"], "success": True, "result": result})
        except Exception as exc:  # noqa: BLE001
            print(f"Failed: {exc}")
            results.append({"test": test["name"], "success": False, "error": str(exc)})

    passed = len([item for item in results if item.get("success")])
    print("\nSummary")
    print("=" * 50)
    print(f"Total: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(results) - passed}")

    output_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)
    print(f"Results written to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual marking engine test")
    parser.add_argument("--mock", action="store_true", help="Use mock provider")
    args = parser.parse_args()

    asyncio.run(run_tests(use_mock=args.mock))


if __name__ == "__main__":
    main()
