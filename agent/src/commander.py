"""
Vyuha AI — The Commander (Task 2)
==================================
Decision-making brain for the autonomous satellite defense system.

Receives telemetry / conjunction-risk data from the Orbit Engine (Task 1)
and uses an LLM via **Blaxel AI's** model gateway to decide whether to hold
position or execute an avoidance maneuver.

Two execution paths (selected automatically):
  1. **Blaxel SDK** (``BLModel``) — preferred when ``blaxel`` is installed
     and ``BL_WORKSPACE`` is configured.  Gives automatic telemetry,
     token refresh, and deployment compatibility.
  2. **Direct OpenAI client** — fallback that uses ``httpx`` to inject
     Blaxel's non-standard auth headers manually.

Usage (standalone test):
    python -m agent.src.commander
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Environment & API configuration
# ---------------------------------------------------------------------------
load_dotenv()

logger = logging.getLogger("vyuha.commander")

BLAXEL_API_KEY: str = os.getenv("BLAXEL_API_KEY", "")
BLAXEL_WORKSPACE: str = os.getenv("BLAXEL_WORKSPACE", "rs")
BLAXEL_MODEL_NAME: str = os.getenv("BLAXEL_MODEL_NAME", "sandbox-openai")
BLAXEL_MODEL_BASE_URL: str = (
    f"https://run.blaxel.ai/{BLAXEL_WORKSPACE}/models/{BLAXEL_MODEL_NAME}/v1"
)

# ---------------------------------------------------------------------------
# Path 1 — Blaxel SDK (preferred)
# ---------------------------------------------------------------------------
_bl_model = None
try:
    from blaxel.core.models import BLModel
    _bl_model = BLModel(BLAXEL_MODEL_NAME)
    logger.info("Blaxel SDK BLModel initialised for '%s'", BLAXEL_MODEL_NAME)
except Exception:
    logger.info("Blaxel SDK unavailable — using direct OpenAI client fallback")

# ---------------------------------------------------------------------------
# Path 2 — Direct OpenAI client via custom httpx (fallback)
# ---------------------------------------------------------------------------
_http_client = httpx.Client(
    headers={
        "X-Blaxel-Authorization": f"Bearer {BLAXEL_API_KEY}",
        "X-Blaxel-Workspace": BLAXEL_WORKSPACE,
    },
    timeout=30.0,
)

_openai_client = OpenAI(
    api_key=BLAXEL_API_KEY,
    base_url=BLAXEL_MODEL_BASE_URL,
    http_client=_http_client,
)

# ---------------------------------------------------------------------------
# System prompt — governs Vyuha's decision logic
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are Vyuha, an autonomous satellite defense commander.
Your top priority is collision avoidance.

You now have access to TWO sensor modalities:
  1. Telemetry (Orbit Engine) — altitude, collision probability, status.
  2. Optical Sensors (Visual Analysis) — description of the onboard camera feed.

RULES:
1. If collision_probability > 0.7 you MUST recommend action "FIRE_THRUSTERS".
2. If collision_probability <= 0.7 you MUST recommend action "HOLD_POSITION".
3. If Visual Analysis confirms debris or a collision risk, INCREASE your
   confidence_score and cite "Optical Confirmation" in your reasoning.
4. Explain your reasoning clearly in exactly one sentence.

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
# Internal: call LLM via the best available path
# ---------------------------------------------------------------------------

async def _call_llm_async(messages: list[dict]) -> str:
    """Call the Blaxel-hosted LLM asynchronously via the SDK."""
    if _bl_model is None:
        raise RuntimeError("BLModel not available")

    url, _type, model = await _bl_model.get_parameters()

    # Build an async OpenAI client pointing at the resolved URL
    async_http = httpx.AsyncClient(
        headers={
            "X-Blaxel-Authorization": f"Bearer {BLAXEL_API_KEY}",
            "X-Blaxel-Workspace": BLAXEL_WORKSPACE,
        },
        timeout=30.0,
    )
    from openai import AsyncOpenAI
    async_client = AsyncOpenAI(
        api_key=BLAXEL_API_KEY,
        base_url=f"{url}/v1",
        http_client=async_http,
    )
    try:
        response = await async_client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=256,
        )
        return response.choices[0].message.content
    finally:
        await async_http.aclose()


def _call_llm_sync(messages: list[dict]) -> str:
    """Call the Blaxel-hosted LLM synchronously via the direct OpenAI client."""
    response = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2,
        max_tokens=256,
        timeout=30,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Core decision function
# ---------------------------------------------------------------------------

def analyze_situation(
    risk_data: dict,
    previous_rejection_reason: str | None = None,
    visual_description: str = "No visual data.",
) -> dict:
    """Feed telemetry + visual data to the LLM and return a structured decision.

    Parameters
    ----------
    risk_data : dict
        Conjunction-risk report as produced by
        ``orbit_tools.check_conjunction_risk``.  Expected keys include
        ``altitude_km``, ``collision_probability``, and ``status``.
    previous_rejection_reason : str, optional
        If the Commander's prior response was blocked by the Shield,
        pass the rejection reason here so the model can self-correct.
    visual_description : str
        Description from the optical sensor / Overshoot AI vision analysis.
        Defaults to "No visual data." if no vision feed is available.

    Returns
    -------
    dict
        A decision object matching the JSON schema defined in
        ``SYSTEM_PROMPT``, or ``SAFETY_FALLBACK`` on error.
    """
    # -- Build the user prompt with telemetry + visual fields ---------------
    altitude = risk_data.get("altitude_km", "N/A")
    probability = risk_data.get("collision_probability", "N/A")
    status = risk_data.get("status", "N/A")

    user_prompt = (
        f"Satellite telemetry update:\n"
        f"  • Altitude:              {altitude} km\n"
        f"  • Collision Probability: {probability}\n"
        f"  • Current Status:        {status}\n\n"
        f"Optical sensor analysis:\n"
        f"  {visual_description}\n\n"
        f"Analyze ALL inputs (telemetry + visual) and provide your decision as JSON."
    )

    # -- Feedback loop: inject rejection context so the model self-corrects -
    if previous_rejection_reason:
        user_prompt += (
            f"\n\nCRITICAL UPDATE: Your previous plan was BLOCKED by the "
            f"security system because: '{previous_rejection_reason}'. "
            f"You must generate a NEW plan that avoids this specific violation."
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    start = time.perf_counter()

    try:
        # Prefer async SDK path; fall back to sync direct client
        try:
            raw_text = asyncio.get_event_loop().run_until_complete(
                _call_llm_async(messages),
            )
        except (RuntimeError, Exception):
            # Either no event loop, BLModel unavailable, or SDK error
            raw_text = _call_llm_sync(messages)

        elapsed = round((time.perf_counter() - start) * 1000)
        raw_text = raw_text.strip()

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
            logger.warning(
                "Missing keys in response: %s", required_keys - decision.keys(),
            )
            return SAFETY_FALLBACK.copy()

        logger.info(
            "Decision: %s (confidence=%.2f) in %d ms",
            decision["action"],
            decision.get("confidence_score", 0),
            elapsed,
        )
        return decision

    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("JSON parse error: %s", exc)
        return SAFETY_FALLBACK.copy()
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM API error: %s", exc)
        return SAFETY_FALLBACK.copy()


# ---------------------------------------------------------------------------
# Local test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

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
