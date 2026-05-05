from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from datetime import datetime
from src.db import Execute, ClientSideDb
from src.report import calculate_operational_time, calculate_system_status, calculate_software_errors, calculate_error_logs, calculate_camera_cycles, calculate_downtime_periods
import traceback, asyncio


db = Execute()
client_db = ClientSideDb(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client_db.connect_all_db()
    yield
    await db.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    today = datetime.now().strftime("%Y-%m-%d")
    return templates.TemplateResponse(request, "index.html", {"today": today})


@app.get("/machines")
async def machines():
    try:
        data = await client_db.mill_machine_name()
        return JSONResponse({"status": "ok", "machines": data})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})


def to_24h(time_str: str, period: str) -> str:
    """Convert 12-hour time string + AM/PM period to 24-hour format (HH:MM)."""
    dt = datetime.strptime(f"{time_str} {period.upper()}", "%I:%M %p")
    return dt.strftime("%H:%M")


@app.post("/generate")
async def generate(payload: dict):
    try:
        mill_name          = payload.get("mill_name", "").strip()
        machine_name       = payload.get("machine_name", "").strip()
        db_name            = payload.get("db_name", "").strip()
        start_date         = payload.get("start_date", "").strip()
        start_time         = payload.get("start_time", "").strip()
        start_time_period  = payload.get("start_time_period", "").strip().upper()
        end_date           = payload.get("end_date", "").strip()
        end_time           = payload.get("end_time", "").strip()
        end_time_period    = payload.get("end_time_period", "").strip().upper()

        missing = []
        if not mill_name:         missing.append("Mill Name")
        if not machine_name:      missing.append("Machine Name")
        if not db_name:           missing.append("DB Name")
        if not start_date:        missing.append("Start Date")
        if not start_time:        missing.append("Start Time")
        if not start_time_period: missing.append("Start Time Period (AM/PM)")
        if not end_date:          missing.append("End Date")
        if not end_time:          missing.append("End Time")
        if not end_time_period:   missing.append("End Time Period (AM/PM)")

        if missing:
            return JSONResponse(
                status_code=422,
                content={"status": "error", "message": f"Required fields missing: {', '.join(missing)}"}
            )

        if start_time_period not in ("AM", "PM"):
            return JSONResponse(status_code=422, content={"status": "error", "message": "Invalid start time period; must be AM or PM"})
        if end_time_period not in ("AM", "PM"):
            return JSONResponse(status_code=422, content={"status": "error", "message": "Invalid end time period; must be AM or PM"})

        start_time_24h = to_24h(start_time, start_time_period)
        end_time_24h   = to_24h(end_time, end_time_period)

        start_datetime = f"{start_date} {start_time_24h}"
        end_datetime   = f"{end_date} {end_time_24h}"
        uptime_data, active_cameras, revolution_data, alarm_data, last_updated = await asyncio.gather(
            client_db.uptime_data(start_datetime, end_datetime, db_name),
            client_db.active_cameras(db_name),
            client_db.revolution_data(start_datetime, end_datetime, db_name),
            client_db.alarm_data(start_datetime, end_datetime, db_name),
            client_db.last_updated_at(db_name)
        )
        last_updated_at = last_updated[0]["timestamp"] if last_updated else "-"
        op_time     = calculate_operational_time(uptime_data, start_datetime, end_datetime)
        sys_status  = calculate_system_status(uptime_data)
        sw_errors   = calculate_software_errors(uptime_data)
        err_logs    = calculate_error_logs(uptime_data, active_cameras)
        cam_cycles       = calculate_camera_cycles(uptime_data, active_cameras)
        downtime_periods = calculate_downtime_periods(uptime_data, start_datetime, end_datetime)
        cam_cycle_counts = {}
        for c in cam_cycles:
            cam_cycle_counts[c["cam_name"]] = cam_cycle_counts.get(c["cam_name"], 0) + 1
        cam_cycle_summary = ", ".join(f"{name}: {count}" for name, count in cam_cycle_counts.items()) or "0"
        defect_count = {}
        for defect in alarm_data:
            name = defect.get("defect_name", "Unknown")
            defect_count[name] = defect_count.get(name, 0) + 1

        data = {
            "status": "ok",
            "mill_name": mill_name,
            "machine_name": machine_name,
            "start_date": start_date,
            "start_time": f"{start_time} {start_time_period}",
            "end_date": end_date,
            "end_time": f"{end_time} {end_time_period}",
            "last_updated_at": last_updated_at,
            "machine_performance": [
                {
                    "category": "Operational Time",
                    "rows": [
                        {"name": "Total Uptime",   "value": op_time["total_uptime"],   "cls": "val-green"},
                        {"name": "Total Downtime", "value": op_time["total_downtime"], "cls": "val-red"},
                    ]
                },
                {
                    "category": "System Status",
                    "rows": [
                        {"name": "Jacquard Machine Run Time", "value": sys_status["machine_run_time"], "cls": "val-blue"},
                        {"name": "Jacquard Machine Downtime", "value": sys_status["machine_downtime"],  "cls": ""},
                    ]
                },
                {
                    "category": "Error Logs",
                    "rows": [
                        {"name": "Software Errors Duration", "value": err_logs["software_errors_duration"], "cls": "val-red"},
                        {"name": "Camera Off Duration",      "value": err_logs["camera_off_duration"],      "cls": "val-red"},
                        {"name": "Camera Off Cycles",        "value": cam_cycle_summary,                    "cls": ""},
                    ]
                },
            ],
            "software_errors": sw_errors,
            "camera_cycles": cam_cycles,
            "production_summary": [
                {"name": "Total Revolution",       "value": f"{len(revolution_data)} doff", "cls": ""},
                {"name": "Total Defects Detected", "value": str(len(alarm_data)), "cls": "val-red"},
            ],
            "defect_distribution": defect_count,
            "downtime_periods": downtime_periods
        }
        return JSONResponse(data)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7778, reload=True)
