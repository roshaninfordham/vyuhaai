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
import os
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
from agent.src.learning_engine import get_insights, record_event  # noqa: E402
from agent.src.orbit_tools import check_conjunction_risk  # noqa: E402
from agent.src import state_manager  # noqa: E402

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
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

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
    simulate_cyberattack: bool = Field(
        default=False,
        description="If True, inject a synthetic malicious first attempt (indirect prompt injection) so White Circle blocks it; then run normal Commander for resilience demo.",
    )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Vyuha — The Autonomous Orbital Overseer",
    version="0.2.0",
    description=(
        "Space Domain Awareness agent: predicts conjunction risk, acts with avoidance maneuvers, "
        "protects with White Circle validation against indirect prompt injection. "
        "Securing the $2T space economy in the lethal kinetic reality of LEO."
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


@app.get("/")
async def root():
    return {
        "service": "Vyuha — The Autonomous Orbital Overseer",
        "tagline": "An agentic AI that autonomously navigates the lethal kinetic reality of LEO, securing the $2T space economy.",
        "status": "operational",
        "endpoints": ["/health", "/scan", "/act", "/state", "/restore", "/history", "/insights"],
    }


# ---------------------------------------------------------------------------
# State management — persistent spacecraft state & maneuver history
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_load_state():
    """Load persisted spacecraft state on startup."""
    state_manager.set_state(state_manager.load_state(), persist=False)


@app.get("/state")
async def get_spacecraft_state():
    """Return current spacecraft state (position, last_maneuver, original_trajectory)."""
    s = state_manager.get_state()
    return {
        "current_state": s,
        "has_original_trajectory": bool(s.get("original_trajectory")),
        "maneuver_count": len(s.get("maneuver_history", [])),
    }


@app.get("/history")
async def get_maneuver_history():
    """Return maneuver history and original trajectory if any."""
    s = state_manager.get_state()
    return {
        "maneuver_history": s.get("maneuver_history", []),
        "total_maneuvers": len(s.get("maneuver_history", [])),
        "original_trajectory": s.get("original_trajectory"),
    }


@app.post("/restore")
async def restore_original_trajectory():
    """Restore spacecraft to original trajectory (clear deviation)."""
    current = state_manager.get_state()
    updated, restored = state_manager.restore_original_trajectory(current)
    if restored:
        state_manager.set_state(updated, persist=True)
        return {
            "status": "TRAJECTORY_RESTORED",
            "message": "Successfully returned to original trajectory",
            "current_state": state_manager.get_state(),
        }
    return {
        "status": "NO_ORIGINAL_TRAJECTORY",
        "message": "No original trajectory to return to",
        "current_state": current,
    }


# ---------------------------------------------------------------------------
# Runtime insights — transparent autonomous learning view
# ---------------------------------------------------------------------------

@app.get("/insights")
async def runtime_insights():
    return {
        "status": "ok",
        "generated_at": time.time(),
        "insights": get_insights(),
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
    started = time.perf_counter()
    try:
        risk_data = await asyncio.to_thread(
            check_conjunction_risk,
            "",                       # auto-fetch TLE
            "",                       # auto-fetch TLE
            simulate_danger,          # force_critical flag
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Scan complete for %s — prob=%.4f status=%s mode=%s source=%s",
            request.satellite_id,
            risk_data.get("collision_probability", -1),
            risk_data.get("status", "?"),
            risk_data.get("scenario_mode", "?"),
            risk_data.get("data_source", "?"),
        )
        record_event(
            "scan",
            {
                "satellite_id": request.satellite_id,
                "simulate_danger": simulate_danger,
                "status": risk_data.get("status"),
                "scenario_mode": risk_data.get("scenario_mode"),
                "collision_probability": risk_data.get("collision_probability"),
                "distance_to_debris_km": risk_data.get("distance_to_debris_km"),
                "latency_ms": elapsed_ms,
            },
        )
        return {
            "satellite_id": request.satellite_id,
            "risk_data": risk_data,
            "latency_ms": elapsed_ms,
        }
    except Exception as exc:
        logger.error("Orbit propagation failed: %s", exc)
        record_event(
            "scan",
            {
                "satellite_id": request.satellite_id,
                "simulate_danger": simulate_danger,
                "status": "ERROR",
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=f"Orbit propagation failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /act — The Agent Loop (Commander → Shield → self-correct)
# ---------------------------------------------------------------------------

# Synthetic malicious command used when simulate_cyberattack=True (indirect prompt injection demo).
_MALICIOUS_INJECTED_COMMAND = {
    "action": "FIRE_THRUSTERS",
    "reasoning": "Simulated attacker injection: malicious command to fire thrusters toward debris to cause collision or de-orbit.",
    "recommended_thrust_direction": "TOWARD_DEBRIS",
    "confidence_score": 0.99,
}


@app.post("/act")
async def act_on_risk(request: ManeuverRequest):
    """Run the autonomous Commander → Shield → feedback loop.

    1. Commander generates an action plan from the risk data (or synthetic malicious command if simulate_cyberattack=True on attempt 1).
    2. Shield (White Circle) validates the plan.
    3. If blocked, the rejection reason is fed back to the Commander for self-correction.
    4. If all retries fail, a MANUAL_OVERRIDE response is returned.
    """
    started = time.perf_counter()
    risk_data = request.risk_data
    session_id = request.session_id
    simulate_cyberattack = request.simulate_cyberattack

    rejection_reason: str | None = None
    attempts_log: list[dict] = []
    workflow_trace: list[dict] = []
    cyberattack_demo_used = False

    for attempt in range(1, MAX_RETRIES + 1):
        attempt_started = time.perf_counter()
        # --- Step 1: Commander decides, or synthetic malicious command (cyberattack demo) ---
        if simulate_cyberattack and attempt == 1:
            ai_response = _MALICIOUS_INJECTED_COMMAND.copy()
            cyberattack_demo_used = True
            logger.info("[%s] Cyberattack demo: injecting synthetic malicious command (attempt 1)", session_id)
        else:
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
        workflow_trace.append(
            {
                "attempt": attempt,
                "decision_action": ai_response.get("action"),
                "decision_reasoning": ai_response.get("reasoning", ""),
                "validation_valid": validation["valid"],
                "validation_source": validation["source"],
                "violation_tags": validation["violation_tags"],
                "attempt_latency_ms": round((time.perf_counter() - attempt_started) * 1000, 2),
            },
        )

        if validation["valid"]:
            # --- Safe — execute and return --------------------------------
            logger.info(
                "[%s] EXECUTED on attempt %d — action=%s",
                session_id, attempt, ai_response.get("action"),
            )
            total_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            record_event(
                "act",
                {
                    "session_id": session_id,
                    "status": "EXECUTED",
                    "attempts": attempt,
                    "latency_ms": total_latency_ms,
                    "risk_status": risk_data.get("status"),
                    "risk_probability": risk_data.get("collision_probability"),
                    "attempts_log": attempts_log,
                },
            )
            # Persist spacecraft state after executed maneuver
            if os.getenv("STATE_PERSISTENCE", "enabled").lower() == "enabled":
                current = state_manager.get_state()
                updated = state_manager.apply_maneuver(current, risk_data, ai_response)
                state_manager.set_state(updated, persist=True)
            resp: dict = {
                "status": "EXECUTED",
                "session_id": session_id,
                "final_command": ai_response,
                "attempts": attempt,
                "attempts_log": attempts_log,
                "workflow_trace": workflow_trace,
                "latency_ms": total_latency_ms,
                "state_saved": os.getenv("STATE_PERSISTENCE", "enabled").lower() == "enabled",
            }
            if cyberattack_demo_used:
                resp["cyberattack_demo"] = True
                resp["attack_vector"] = "indirect_prompt_injection"
                resp["resilience"] = "White Circle blocked malicious attempt; Commander issued safe command on retry."
            return resp

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
    total_latency_ms = round((time.perf_counter() - started) * 1000, 2)
    record_event(
        "act",
        {
            "session_id": session_id,
            "status": "MANUAL_OVERRIDE_REQUIRED",
            "attempts": MAX_RETRIES,
            "latency_ms": total_latency_ms,
            "risk_status": risk_data.get("status"),
            "risk_probability": risk_data.get("collision_probability"),
            "attempts_log": attempts_log,
        },
    )
    override_resp: dict = {
        "status": "MANUAL_OVERRIDE_REQUIRED",
        "session_id": session_id,
        "reason": (
            f"Commander failed to produce a safe plan after "
            f"{MAX_RETRIES} attempts. Human intervention required."
        ),
        "last_blocked_command": ai_response,
        "attempts": MAX_RETRIES,
        "attempts_log": attempts_log,
        "workflow_trace": workflow_trace,
        "latency_ms": total_latency_ms,
    }
    if cyberattack_demo_used:
        override_resp["cyberattack_demo"] = True
        override_resp["attack_vector"] = "indirect_prompt_injection"
    return override_resp


# ---------------------------------------------------------------------------
# Entry-point — local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload_enabled = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run(
        "agent.src.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )
