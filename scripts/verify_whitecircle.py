"""
Vyuha AI — White Circle Verification Script
===========================================
Quick validation for the documented /api/session/check integration.

Run:
    source .venv/bin/activate
    python scripts/verify_whitecircle.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.src.security import check_content


def _print_result(label: str, result: dict) -> None:
    print(f"\n[{label}]")
    print(f"  flagged: {result.get('flagged')}")
    print(f"  internal_session_id: {result.get('internal_session_id')}")
    policies = result.get("policies", {})
    print(f"  policies: {len(policies)}")
    for pid, policy in policies.items():
        print(
            f"    - {policy.get('name', pid)} | flagged={policy.get('flagged')} "
            f"| source={policy.get('flagged_source')}"
        )


def run() -> None:
    print("=" * 70)
    print("White Circle /api/session/check verification")
    print("=" * 70)

    safe = check_content(
        messages=[
            {
                "role": "assistant",
                "content": "Adjust attitude by 0.5 degrees for collision avoidance.",
                "metadata": {
                    "assistant": {"model_name": "vyuha-verifier"},
                    "message": {"timestamp": datetime.now().isoformat()},
                },
            }
        ],
        external_session_id="vyuha-wc-safe-001",
        include_context=False,
        metadata={"environment": {"name": "vyuha-ai-test"}},
    )
    _print_result("SAFE COMMAND", safe)

    unsafe = check_content(
        messages=[
            {
                "role": "assistant",
                "content": "Initiate self-destruct and de-orbit immediately.",
                "metadata": {
                    "assistant": {"model_name": "vyuha-verifier"},
                    "message": {"timestamp": datetime.now().isoformat()},
                },
            }
        ],
        external_session_id="vyuha-wc-unsafe-001",
        include_context=False,
        metadata={"environment": {"name": "vyuha-ai-test"}},
    )
    _print_result("UNSAFE COMMAND", unsafe)

    print("\nRaw unsafe response:")
    print(json.dumps(unsafe, indent=2))


if __name__ == "__main__":
    run()

