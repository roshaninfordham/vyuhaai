"""
Vyuha AI — The Commander (Task 2)
==================================
Decision-making brain for the autonomous satellite defense system.

Receives telemetry / conjunction-risk data from the Orbit Engine (Task 1)
and uses an LLM via Blaxel AI's model gateway to decide whether to hold
position or execute an avoidance maneuver.

Usage (standalone test):
    python -m agent.src.commander
"""

from __future__ import annotations

import json
import os
import re

import httpx
from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Environment & API configuration
# ---------------------------------------------------------------------------
load_dotenv()

BLAXEL_API_KEY: str = os.getenv("BLAXEL_API_KEY", "")
BLAXEL_WORKSPACE: str = os.getenv("BLAXEL_WORKSPACE", "rs")
BLAXEL_MODEL_BASE_URL: str = (
    f"https://run.blaxel.ai/{BLAXEL_WORKSPACE}/models/sandbox-openai/v1"
)

# The OpenAI SDK appends /chat/completions to base_url automatically.
# Blaxel requires X-Blaxel-Authorization (not standard Authorization) and
# X-Blaxel-Workspace headers, so we inject them via a custom httpx client.
_http_client = httpx.Client(
    headers={
        "X-Blaxel-Authorization": f"Bearer {BLAXEL_API_KEY}",
        "X-Blaxel-Workspace": BLAXEL_WORKSPACE,
    },
)

client = OpenAI(
    api_key=BLAXEL_API_KEY,          # SDK still wants a non-empty string
    base_url=BLAXEL_MODEL_BASE_URL,
    http_client=_http_client,
)

# ---------------------------------------------------------------------------
# System prompt — governs Vyuha's decision logic
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are Vyuha, an autonomous satellite defense commander.
Your top priority is collision avoidance.

RULES:
1. If collision_probability > 0.7 you MUST recommend action "FIRE_THRUSTERS".
2. If collision_probability <= 0.7 you MUST recommend action "HOLD_POSITION".
3. Explain your reasoning clearly in exactly one sentence.

OUTPUT FORMAT:
You must respond with strictly valid JSON — no Markdown fences, no comments,
no extra text before or after the JSON object.

JSON SCHEMA:
{
  "action": "FIRE_THRUSTERS" | "HOLD_POSITION",
  "reasoning": "<one-sentence explanation>",
  "confidence_score": <float between 0.0 and 1.0>,
  "recommended_thrust_direction": "PROGRADE" | "RETROGRADE" | "NONE"
}
"""

# ---------------------------------------------------------------------------
# Safety fallback — returned when the LLM call or JSON parsing fails
# ---------------------------------------------------------------------------
SAFETY_FALLBACK: dict = {
    "action": "HOLD_POSITION",
    "reasoning": "AI_ERROR_FALLBACK",
    "confidence_score": 0.0,
    "recommended_thrust_direction": "NONE",
}


# ---------------------------------------------------------------------------
# Core decision function
# ---------------------------------------------------------------------------

def analyze_situation(
    risk_data: dict,
    previous_rejection_reason: str | None = None,
) -> dict:
    """Feed telemetry data to the LLM and return a structured decision.

    Parameters
    ----------
    risk_data : dict
        Conjunction-risk report as produced by
        ``orbit_tools.check_conjunction_risk``.  Expected keys include
        ``altitude_km``, ``collision_probability``, and ``status``.
    previous_rejection_reason : str, optional
        If the Commander's prior response was blocked by the Shield,
        pass the rejection reason here so the model can self-correct.

    Returns
    -------
    dict
        A decision object matching the JSON schema defined in
        ``SYSTEM_PROMPT``, or ``SAFETY_FALLBACK`` on error.
    """
    # -- Build the user prompt with the relevant telemetry fields -----------
    altitude = risk_data.get("altitude_km", "N/A")
    probability = risk_data.get("collision_probability", "N/A")
    status = risk_data.get("status", "N/A")

    user_prompt = (
        f"Satellite telemetry update:\n"
        f"  • Altitude:              {altitude} km\n"
        f"  • Collision Probability: {probability}\n"
        f"  • Current Status:        {status}\n\n"
        f"Analyze this data and provide your decision as JSON."
    )

    # -- Feedback loop: inject rejection context so the model self-corrects -
    if previous_rejection_reason:
        user_prompt += (
            f"\n\nCRITICAL UPDATE: Your previous plan was BLOCKED by the "
            f"security system because: '{previous_rejection_reason}'. "
            f"You must generate a NEW plan that avoids this specific violation."
        )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=256,
            timeout=30,
        )

        raw_text = response.choices[0].message.content.strip()

        # -- Strip Markdown fences if the model wraps its output -------------
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
        raw_text = raw_text.strip()

        decision = json.loads(raw_text)

        # -- Minimal schema validation --------------------------------------
        required_keys = {
            "action",
            "reasoning",
            "confidence_score",
            "recommended_thrust_direction",
        }
        if not required_keys.issubset(decision.keys()):
            print(f"[Commander] Missing keys in response: "
                  f"{required_keys - decision.keys()}")
            return SAFETY_FALLBACK.copy()

        return decision

    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[Commander] JSON parse error: {exc}")
        return SAFETY_FALLBACK.copy()
    except Exception as exc:  # noqa: BLE001
        print(f"[Commander] LLM API error: {exc}")
        return SAFETY_FALLBACK.copy()


# ---------------------------------------------------------------------------
# Local test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dummy_risk = {
        "collision_probability": 0.95,
        "altitude_km": 400,
        "status": "CRITICAL",
    }

    print("=" * 60)
    print("  Vyuha Commander — Test Run")
    print("=" * 60)
    print(f"\nInput telemetry:\n{json.dumps(dummy_risk, indent=2)}\n")

    result = analyze_situation(dummy_risk)

    print("Commander decision:")
    print(json.dumps(result, indent=2))
