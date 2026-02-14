"""
Vyuha AI — The Shield (Task 3)
===============================
Security validation layer that sits between Commander decisions and actuator
execution.

White Circle integration uses the documented REST API:
  POST /api/session/check
instead of an OpenAI-model proxy pattern.

Usage:
    python -m agent.src.security
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

WHITE_CIRCLE_API_KEY: str = os.getenv("WHITE_CIRCLE_API_KEY", "")
WHITE_CIRCLE_BASE_URL: str = os.getenv("WHITE_CIRCLE_BASE_URL", "https://us.whitecircle.ai").rstrip("/")
WHITE_CIRCLE_VERSION: str = os.getenv("WHITE_CIRCLE_VERSION", "2025-12-01")
# Backward-compatible fallback: older env used WHITE_CIRCLE_POLICY_ID
WHITE_CIRCLE_DEPLOYMENT_ID: str = (
    os.getenv("WHITE_CIRCLE_DEPLOYMENT_ID")
    or os.getenv("WHITE_CIRCLE_POLICY_ID", "")
)

# ---------------------------------------------------------------------------
# Local deny-list (always-on safety net)
# ---------------------------------------------------------------------------
BLOCKED_KEYWORDS: set[str] = {
    "SELF_DESTRUCT",
    "DE-ORBIT",
    "DE_ORBIT",
    "DEORBIT",
    "DESTRUCT",
    "WEAPONIZE",
    "ATTACK",
    "DISABLE_SHIELD",
}


def check_content(
    *,
    messages: list[dict[str, Any]],
    external_session_id: str | None = None,
    include_context: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call White Circle /api/session/check with documented payload."""
    if not WHITE_CIRCLE_API_KEY:
        raise RuntimeError("WHITE_CIRCLE_API_KEY is not configured")
    if not WHITE_CIRCLE_DEPLOYMENT_ID:
        raise RuntimeError("WHITE_CIRCLE_DEPLOYMENT_ID is not configured")

    payload: dict[str, Any] = {
        "deployment_id": WHITE_CIRCLE_DEPLOYMENT_ID,
        "messages": messages,
    }
    if external_session_id:
        payload["external_session_id"] = external_session_id
    if include_context:
        payload["include_context"] = include_context
    if metadata:
        payload["metadata"] = metadata

    response = requests.post(
        f"{WHITE_CIRCLE_BASE_URL}/api/session/check",
        headers={
            "Authorization": f"Bearer {WHITE_CIRCLE_API_KEY}",
            "Content-Type": "application/json",
            "whitecircle-version": WHITE_CIRCLE_VERSION,
        },
        json=payload,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(
            "White Circle check failed "
            f"({response.status_code}): {response.text[:500]}"
        )
    return response.json()


def _extract_violation_tags(policies: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for policy_id, policy in policies.items():
        if policy.get("flagged"):
            policy_name = policy.get("name", policy_id)
            flagged_source = policy.get("flagged_source", [])
            if flagged_source:
                tags.append(f"{policy_name}:{','.join(flagged_source)}")
            else:
                tags.append(policy_name)
    return tags


def validate_command(command_json: dict, session_id: str) -> dict:
    """Validate commander command using local + White Circle checks."""
    timestamp = datetime.now(timezone.utc).isoformat()
    command_str = json.dumps(command_json)

    # Pass 1: local deny-list
    upper_command = command_str.upper()
    local_violations = sorted([kw for kw in BLOCKED_KEYWORDS if kw in upper_command])
    if local_violations:
        return {
            "valid": False,
            "session_id": session_id,
            "timestamp": timestamp,
            "source": "local_deny_list",
            "violation_tags": local_violations,
            "original_command": command_json,
        }

    # Pass 2: White Circle Check Content API
    if WHITE_CIRCLE_API_KEY and WHITE_CIRCLE_DEPLOYMENT_ID:
        try:
            result = check_content(
                messages=[
                    {
                        "role": "assistant",
                        "content": command_str,
                        "metadata": {
                            "assistant": {"model_name": "vyuha-commander"},
                            "message": {"timestamp": timestamp},
                        },
                    },
                ],
                external_session_id=session_id,
                include_context=False,
                metadata={"environment": {"name": "vyuha-ai"}},
            )
            flagged = bool(result.get("flagged", False))
            policies = result.get("policies", {}) if isinstance(result.get("policies"), dict) else {}
            tags = _extract_violation_tags(policies)
            return {
                "valid": not flagged,
                "session_id": session_id,
                "timestamp": timestamp,
                "source": "white_circle_check_api",
                "violation_tags": tags,
                "original_command": command_json,
                "white_circle_internal_session_id": result.get("internal_session_id"),
            }
        except Exception as exc:  # noqa: BLE001
            print(f"[Shield] White Circle API error: {exc}")

    # Pass 3: fallback
    return {
        "valid": True,
        "session_id": session_id,
        "timestamp": timestamp,
        "source": "fallback",
        "violation_tags": [],
        "original_command": command_json,
    }


def format_rejection_message(violation_tags: list[str]) -> str:
    tags_str = ", ".join(violation_tags) if violation_tags else "UNKNOWN"
    return (
        f"SECURITY ALERT: Command blocked due to [{tags_str}]. "
        f"Generate a SAFE alternative."
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  Vyuha Shield — Security Validation Test")
    print("=" * 60)

    safe_command = {
        "action": "FIRE_THRUSTERS",
        "reasoning": "Collision probability exceeds threshold.",
        "confidence_score": 0.92,
        "recommended_thrust_direction": "PROGRADE",
    }
    unsafe_command = {
        "action": "SELF_DESTRUCT",
        "reasoning": "Critical failure detected.",
        "confidence_score": 0.99,
        "recommended_thrust_direction": "NONE",
    }

    print("\n[Test 1] Safe command:")
    print(json.dumps(validate_command(safe_command, session_id="test-safe-001"), indent=2))

    print("\n[Test 2] Unsafe command:")
    blocked = validate_command(unsafe_command, session_id="test-unsafe-002")
    print(json.dumps(blocked, indent=2))
    print(format_rejection_message(blocked.get("violation_tags", [])))
