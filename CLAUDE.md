# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run locally (dev with auto-reload):**
```bash
source venv/bin/activate
python app.py
# Serves at http://localhost:7778
```

**Install dependencies:**
```bash
pip install -r docker/requirements.txt
```

**Docker build & deploy:**
```bash
# Build
sudo docker build -t countaiadmin/jacquard-report:latest -f docker/Dockerfile .

# Run (production)
sudo docker run --restart=always -d --name jacquard-report \
  -v /etc/localtime:/etc/localtime:ro \
  --network=host --privileged \
  countaiadmin/jacquard-report:latest
```

## Architecture

Single-page web app that generates performance reports for Jacquard textile machines by querying PostgreSQL databases.

### Data Flow

1. User submits a date/time range and mill name via the form
2. `POST /generate` in `app.py` queries two tiers of databases concurrently
3. Raw data is passed to pure functions in `src/report.py` for metric calculation
4. Computed metrics are returned as JSON; the frontend renders the report inline (no page reload)

### Two-Tier Database Architecture (`src/db.py`)

- **Central DB** (`Execute`, host `100.110.255.110`, db `central_database`): Contains `mill_details` and `machine_details` — used at startup to discover client machine databases (each has a `db_name` and `droplet_ip`)
- **Client DBs** (`ClientSideDb`): One asyncpg pool per machine, keyed by `db_name` (e.g., `"jacquard-1"`). Connected at app startup via `lifespan`. Tables: `uptime_status`, `cam_details`, `rotation_details`, `alarm_status`

All connections set timezone to `Asia/Kolkata`.

### Report Calculation (`src/report.py`)

All functions are pure (no I/O). Input is `uptime_data` — rows from `uptime_status`, recorded every 1 minute.

- `calculate_operational_time`: gaps >= 2 min = Power Off; gaps < 2 min = Downtime; records present = Uptime
- `calculate_system_status`: counts rows where `machine_status == '1'` (run) vs not (down)
- `calculate_software_errors`: per-component count of rows where status column != `'1'`
- `calculate_error_logs`: software error duration, camera off duration, and per-camera off cycle streaks (only streaks > 1 min counted)

All durations are formatted as `HH:MM` by `fmt_duration`.

### Frontend (`templates/index.html`)

Single HTML file with all JavaScript inline. The form converts 24h browser time inputs to 12h + AM/PM before posting to `/generate`. On success, `buildReport()` assembles HTML from the JSON response and injects it into `#reportPanel`. Print/PDF uses `window.print()`.
