# Agent Backend (`agent/`)

This folder contains the autonomous decision backend and persistent learning store.

## Contents

- `src/` - all runtime modules (orbit, commander, security, API orchestration, learning)
- `data/` - runtime JSONL telemetry and action-learning events

## Runtime responsibilities

- ingest live orbital data,
- compute collision risk,
- produce autonomous maneuver decisions,
- validate decisions against security policy,
- log and analyze behavior for continuous improvement.

## API surface

- `GET /` - backend homepage/status
- `GET /health` - health probe
- `GET /insights` - runtime analytics and recommendations
- `POST /scan` - live/simulated risk scan
- `POST /act` - autonomous command loop

## Production notes

- Keep this service stateless at request level, but persist learning events in `data/`.
- Rotate/backup `agent/data/agent_events.jsonl` during long-running operations.
- Use environment variables for all secrets and runtime knobs (`MAX_RETRIES`, keys, workspace).

