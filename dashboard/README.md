# Mission Control Dashboard (`dashboard/`)

Streamlit command center for transparent autonomous operations.

## Main goals

- show live orbital context,
- trigger safe and simulated critical flows,
- visualize agent reasoning and guardrail outcomes,
- expose runtime learning analytics in real time.

## Features

- **Hybrid controls**
  - `SCAN SECTOR (LIVE)` -> real telemetry path
  - `SIMULATE ATTACK (DEMO)` -> forced critical scenario path

- **Orbital visualization**
  - ISS marker with nearby satellite context
  - debris visualization in critical mode
  - threat overlays and orbit track

- **Agentic transparency**
  - attempt-by-attempt chain of thought view
  - security block/approve status per attempt
  - per-attempt latency and validator source

- **Learning panel**
  - success rate
  - blocked attempts
  - scan/act average latency
  - violation-frequency chart
  - improvement recommendations from backend analytics

## Run

```bash
source .venv/bin/activate
streamlit run dashboard/app.py --server.port 8501
```

Environment:
- `VYUHA_API_URL` (default `http://localhost:8000`)
- `BLAXEL_API_KEY` / `BL_API_KEY` + `BLAXEL_WORKSPACE` (for private cloud calls)

