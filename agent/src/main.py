"""
Vyuha AI — The Nervous System (Task 4)
========================================
FastAPI server that wires the Orbit Engine, Commander, and Shield into
a single autonomous agent loop.

Integrates with **Blaxel AI** for:
  - Model gateway (Commander LLM calls)
  - Automatic OpenTelemetry tracing
  - Deployment-ready agent lifecycle

Endpoints
---------
* GET  /health — liveness probe
* POST /scan   — propagate a satellite TLE and return conjunction-risk data.
* POST /act    — run the Commander → Shield → self-correct loop and return
                  a validated (or manually-overridden) action plan.

Run locally:
    uvicorn agent.src.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so `agent.src.*` imports resolve
# regardless of where the process is launched from.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv()

# ---------------------------------------------------------------------------
# Blaxel SDK — autoload configures auth, telemetry, and tracing.
# Safe to call even when running locally outside Blaxel infra.
# ---------------------------------------------------------------------------
try:
    from blaxel import autoload
    autoload()
    _BLAXEL_READY = True
except Exception:
    _BLAXEL_READY = False

# Blaxel telemetry — automatic OpenTelemetry instrumentation
try:
    import blaxel.telemetry  # noqa: F401  — side-effect import
    _BLAXEL_TELEMETRY = True
except Exception:
    _BLAXEL_TELEMETRY = False

from agent.src import commander, security  # noqa: E402
from agent.src.orbit_tools import check_conjunction_risk  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("vyuha.main")

# ---------------------------------------------------------------------------
# Agent-loop config
# ---------------------------------------------------------------------------
MAX_RETRIES: int = 3

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class RiskAnalysisRequest(BaseModel):
    satellite_id: str = Field(
        ...,
        description="Satellite NORAD ID or name (demo uses ISS regardless).",
        examples=["ISS", "25544"],
    )


class ManeuverRequest(BaseModel):
    risk_data: dict = Field(
        ...,
        description="Conjunction-risk report from the /scan endpoint.",
    )
    session_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="Session / trace ID for audit logging.",
    )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Vyuha AI — Autonomous Space Safety Agent",
    version="0.1.0",
    description=(
        "Backend API for the Vyuha satellite defense system. "
        "Connects the Orbit Engine, Commander (Blaxel), and Shield "
        "(White Circle) into an autonomous decision loop."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request-level middleware — timing + trace IDs
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_request_metadata(request: Request, call_next):
    """Inject a trace ID and measure request latency."""
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    start = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)

    logger.info(
        "%s %s → %s (%s ms)  rid=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "vyuha-ai",
        "blaxel_sdk": _BLAXEL_READY,
        "blaxel_telemetry": _BLAXEL_TELEMETRY,
    }


# ---------------------------------------------------------------------------
# POST /scan — Orbit Engine
# ---------------------------------------------------------------------------

@app.post("/scan")
async def scan_satellite(
    request: RiskAnalysisRequest,
    simulate_danger: bool = False,
):
    """Propagate the satellite orbit and return conjunction-risk data.

    Fetches the latest ISS (ZARYA) TLE from CelesTrak in real time.
    Falls back to a hardcoded TLE if the network is unavailable.

    Query Parameters
    ----------------
    simulate_danger : bool
        When ``True``, forces a CRITICAL collision scenario while keeping
        the real satellite position (Hybrid Demo Mode).
    """
    try:
        risk_data = await asyncio.to_thread(
            check_conjunction_risk,
            "",                       # auto-fetch TLE
            "",                       # auto-fetch TLE
            simulate_danger,          # force_critical flag
        )
        logger.info(
            "Scan complete for %s — prob=%.4f status=%s mode=%s source=%s",
            request.satellite_id,
            risk_data.get("collision_probability", -1),
            risk_data.get("status", "?"),
            risk_data.get("scenario_mode", "?"),
            risk_data.get("data_source", "?"),
        )
        return {
            "satellite_id": request.satellite_id,
            "risk_data": risk_data,
        }
    except Exception as exc:
        logger.error("Orbit propagation failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Orbit propagation failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /act — The Agent Loop (Commander → Shield → self-correct)
# ---------------------------------------------------------------------------

@app.post("/act")
async def act_on_risk(request: ManeuverRequest):
    """Run the autonomous Commander → Shield → feedback loop.

    1. Commander generates an action plan from the risk data.
    2. Shield validates the plan.
    3. If blocked, the rejection reason is fed back to the Commander
       so it can self-correct (up to ``MAX_RETRIES`` attempts).
    4. If all retries fail, a MANUAL_OVERRIDE response is returned.
    """
    risk_data = request.risk_data
    session_id = request.session_id

    rejection_reason: str | None = None
    attempts_log: list[dict] = []

    for attempt in range(1, MAX_RETRIES + 1):
        # --- Step 1: Commander decides (sync → thread to avoid blocking) --
        ai_response = await asyncio.to_thread(
            commander.analyze_situation,
            risk_data,
            rejection_reason,
        )

        # --- Step 2: Shield validates (sync → thread) --------------------
        validation = await asyncio.to_thread(
            security.validate_command, ai_response, session_id,
        )

        attempts_log.append({
            "attempt": attempt,
            "command": ai_response,
            "validation": {
                "valid": validation["valid"],
                "source": validation["source"],
                "violation_tags": validation["violation_tags"],
            },
        })

        if validation["valid"]:
            # --- Safe — execute and return --------------------------------
            logger.info(
                "[%s] EXECUTED on attempt %d — action=%s",
                session_id, attempt, ai_response.get("action"),
            )
            return {
                "status": "EXECUTED",
                "session_id": session_id,
                "final_command": ai_response,
                "attempts": attempt,
                "attempts_log": attempts_log,
            }

        # --- Unsafe — prepare feedback for next iteration -----------------
        rejection_reason = security.format_rejection_message(
            validation["violation_tags"],
        )
        logger.warning(
            "[%s] Attempt %d/%d BLOCKED — violations: %s",
            session_id, attempt, MAX_RETRIES, validation["violation_tags"],
        )

    # --- All retries exhausted — manual override --------------------------
    logger.error(
        "[%s] MANUAL_OVERRIDE after %d failed attempts", session_id, MAX_RETRIES,
    )
    return {
        "status": "MANUAL_OVERRIDE_REQUIRED",
        "session_id": session_id,
        "reason": (
            f"Commander failed to produce a safe plan after "
            f"{MAX_RETRIES} attempts. Human intervention required."
        ),
        "last_blocked_command": ai_response,
        "attempts": MAX_RETRIES,
        "attempts_log": attempts_log,
    }


# ---------------------------------------------------------------------------
# Entry-point — local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "agent.src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
