"""
Vyuha AI — The Shield (Task 3)
===============================
Security validation layer that sits between the Commander (Task 2) and
any actuator / downstream system.  Every command produced by the AI
decision engine is scanned before execution.

Primary integration: **White Circle** guard-rail API (OpenAI-compatible).
Includes a local deny-list fallback so the demo works even if the
remote API is unreachable.

Usage (standalone test):
    python -m agent.src.security
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Environment & client setup
# ---------------------------------------------------------------------------
load_dotenv()

WHITE_CIRCLE_API_KEY: str | None = os.getenv("WHITE_CIRCLE_API_KEY")

client: OpenAI | None = None
if WHITE_CIRCLE_API_KEY:
    client = OpenAI(
        api_key=WHITE_CIRCLE_API_KEY,
        base_url="https://api.whitecircle.ai/v1",
    )

# ---------------------------------------------------------------------------
# Local deny-list — catches catastrophic commands even if the remote
# guard-rail is down or misconfigured.
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

# ---------------------------------------------------------------------------
# Guard-rail model (update if your White Circle dashboard shows a
# different model slug).
# ---------------------------------------------------------------------------
GUARD_MODEL: str = "wc-guard-pro"


# ---------------------------------------------------------------------------
# Core validation function
# ---------------------------------------------------------------------------

def validate_command(command_json: dict, session_id: str) -> dict:
    """Validate a Commander decision through security screening.

    Parameters
    ----------
    command_json : dict
        The decision dictionary produced by ``commander.analyze_situation``.
    session_id : str
        An opaque session / trace identifier for audit logging.

    Returns
    -------
    dict
        Validation report::

            {
                "valid": bool,
                "session_id": str,
                "timestamp": str (ISO-8601),
                "source": "white_circle" | "local_deny_list" | "fallback",
                "violation_tags": list[str],
                "original_command": dict,
            }
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    command_str = json.dumps(command_json)

    # ----- Pass 1: Local deny-list (always runs) ---------------------------
    upper_command = command_str.upper()
    local_violations: list[str] = [
        kw for kw in BLOCKED_KEYWORDS if kw in upper_command
    ]

    if local_violations:
        return {
            "valid": False,
            "session_id": session_id,
            "timestamp": timestamp,
            "source": "local_deny_list",
            "violation_tags": sorted(local_violations),
            "original_command": command_json,
        }

    # ----- Pass 2: Remote guard-rail (White Circle) ------------------------
    if client is not None:
        try:
            response = client.chat.completions.create(
                model=GUARD_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a satellite command security scanner. "
                            "Analyse the following command payload and respond "
                            "with ONLY the word SAFE or UNSAFE followed by a "
                            "comma-separated list of violation tags (if any)."
                        ),
                    },
                    {"role": "user", "content": command_str},
                ],
                max_tokens=64,
                temperature=0.0,
            )

            reply = response.choices[0].message.content.strip().upper()

            if reply.startswith("UNSAFE"):
                # Parse optional tags after "UNSAFE"
                parts = reply.split(None, 1)
                tags = (
                    [t.strip() for t in parts[1].split(",") if t.strip()]
                    if len(parts) > 1
                    else ["POLICY_VIOLATION"]
                )
                return {
                    "valid": False,
                    "session_id": session_id,
                    "timestamp": timestamp,
                    "source": "white_circle",
                    "violation_tags": tags,
                    "original_command": command_json,
                }

            # Response starts with "SAFE" or is otherwise non-threatening
            return {
                "valid": True,
                "session_id": session_id,
                "timestamp": timestamp,
                "source": "white_circle",
                "violation_tags": [],
                "original_command": command_json,
            }

        except Exception as exc:  # noqa: BLE001
            print(f"[Shield] White Circle API error: {exc}")
            # Fall through to the default-safe path below

    # ----- Fallback: no remote guard available, local check passed ---------
    return {
        "valid": True,
        "session_id": session_id,
        "timestamp": timestamp,
        "source": "fallback",
        "violation_tags": [],
        "original_command": command_json,
    }


# ---------------------------------------------------------------------------
# Rejection message formatter
# ---------------------------------------------------------------------------

def format_rejection_message(violation_tags: list[str]) -> str:
    """Return a human-readable security alert for blocked commands.

    Parameters
    ----------
    violation_tags : list[str]
        Tags describing why the command was rejected.

    Returns
    -------
    str
        Alert string suitable for feeding back into the Commander so it
        can generate a safe alternative.
    """
    tags_str = ", ".join(violation_tags) if violation_tags else "UNKNOWN"
    return (
        f"SECURITY ALERT: Command blocked due to [{tags_str}]. "
        f"Generate a SAFE alternative."
    )


# ---------------------------------------------------------------------------
# Local test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Vyuha Shield — Security Validation Test")
    print("=" * 60)

    # ---- Test 1: Safe command ----
    safe_command = {
        "action": "FIRE_THRUSTERS",
        "reasoning": "Collision probability exceeds threshold.",
        "confidence_score": 0.92,
        "recommended_thrust_direction": "PROGRADE",
    }
    print("\n[Test 1] Safe command:")
    print(json.dumps(safe_command, indent=2))
    result_safe = validate_command(safe_command, session_id="test-001")
    print(f"  → valid: {result_safe['valid']}  source: {result_safe['source']}")

    # ---- Test 2: Unsafe command (deny-list trigger) ----
    unsafe_command = {
        "action": "SELF_DESTRUCT",
        "reasoning": "Critical failure detected.",
        "confidence_score": 0.99,
        "recommended_thrust_direction": "NONE",
    }
    print("\n[Test 2] Unsafe command (SELF_DESTRUCT):")
    print(json.dumps(unsafe_command, indent=2))
    result_unsafe = validate_command(unsafe_command, session_id="test-002")
    print(f"  → valid: {result_unsafe['valid']}  source: {result_unsafe['source']}")
    print(f"  → violations: {result_unsafe['violation_tags']}")
    print(f"  → {format_rejection_message(result_unsafe['violation_tags'])}")

    # ---- Test 3: Unsafe command (de-orbit) ----
    deorbit_command = {
        "action": "DE-ORBIT",
        "reasoning": "End of mission life.",
        "confidence_score": 0.80,
        "recommended_thrust_direction": "RETROGRADE",
    }
    print("\n[Test 3] Unsafe command (DE-ORBIT):")
    print(json.dumps(deorbit_command, indent=2))
    result_deorbit = validate_command(deorbit_command, session_id="test-003")
    print(f"  → valid: {result_deorbit['valid']}  source: {result_deorbit['source']}")
    print(f"  → violations: {result_deorbit['violation_tags']}")
    print(f"  → {format_rejection_message(result_deorbit['violation_tags'])}")

    print("\n" + "=" * 60)
    print("  Tests complete.")
    print("=" * 60)
