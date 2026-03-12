"""Check LLM provider health for ACCA marker.
Run: .\\venv\\Scripts\\python.exe scripts/check_llm_health.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.marking_service import MarkingService


async def main() -> None:
    service = MarkingService()
    payload = await service.get_llm_health()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
