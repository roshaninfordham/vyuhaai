# Backend Modules (`agent/src/`)

## Module map

- `orbit_tools.py`
  - MCP tool server (`FastMCP`) for orbital processing.
  - `fetch_live_tle()` pulls ISS TLE from CelesTrak.
  - `check_conjunction_risk(..., force_critical=False)` supports hybrid demo mode.
  - `calculate_avoidance_maneuver(...)` computes burn recommendations.

- `commander.py`
  - LLM decision engine (Blaxel model gateway + fallback path).
  - Enforces strict JSON output format.
  - Supports feedback loop input (`previous_rejection_reason`).

- `security.py`
  - Command validation using White Circle (OpenAI-compatible).
  - Local deny-list fallback for resilient demos.

- `learning_engine.py`
  - Persistent event logging (`agent_events.jsonl`).
  - Aggregates failures, latency, sources, and recommendations.

- `main.py`
  - FastAPI orchestration layer.
  - Endpoints: `/`, `/health`, `/scan`, `/act`, `/insights`.
  - Connects orbit -> commander -> security -> learning analytics.

## Autonomy logic in `/act`

1. Commander proposes action.
2. Security validates.
3. If blocked: rejection reason is fed back to commander.
4. Retries up to `MAX_RETRIES`.
5. Returns executed command or manual override status.
6. Logs full trace for continuous learning.

## Improvement loop

Data emitted per mission cycle:
- scan status + telemetry + latency
- action attempts + validation path + violation tags
- success/failure + total latency

`/insights` turns that into:
- KPIs (success rate, avg latency),
- error hotspots,
- recommended changes for next run.

