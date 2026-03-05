from datetime import datetime, timedelta

SOFTWARE_COLS = [
    'software_status', 'controller_status', 'ml_status',
    'alarm_status',    'monitor_status',    'report_status', 'redis_status',
]


def fmt_duration(td: timedelta) -> str:
    total_minutes = max(0, int(td.total_seconds()) // 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h:02d}:{m:02d}"


def calculate_operational_time(uptime_data: list, start_str: str, end_str: str) -> dict:
    """
    Calculate Total Uptime and Total Downtime.

    Iterates every minute in the shift range. If a record exists for that
    minute it counts as 1 minute of Uptime, otherwise 1 minute of Downtime.
    """
    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
    end_dt   = datetime.strptime(end_str,   "%Y-%m-%d %H:%M")

    recorded_minutes = {
        datetime.strptime(r["formatted_timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        for r in uptime_data
    }

    uptime_min   = 0
    downtime_min = 0
    current = start_dt
    while current < end_dt:
        if current.strftime("%Y-%m-%d %H:%M") in recorded_minutes:
            uptime_min += 1
        else:
            downtime_min += 1
        current += timedelta(minutes=1)

    return {
        "total_uptime":   fmt_duration(timedelta(minutes=uptime_min)),
        "total_downtime": fmt_duration(timedelta(minutes=downtime_min)),
    }


COMPONENT_COLS = {
    'Software':   'software_status',
    'Controller': 'controller_status',
    'ML':         'ml_status',
    'Alarm':      'alarm_status',
    'Monitor':    'monitor_status',
    'Report':     'report_status',
    'Redis':      'redis_status',
}


def calculate_software_errors(uptime_data: list) -> list:
    """
    For each software component, count rows where its status column != '1'.
    Each such row = 1 minute of error duration.
    Returns list of {component, duration} dicts.
    """
    counts = {comp: 0 for comp in COMPONENT_COLS}

    for row in uptime_data:
        for comp, col in COMPONENT_COLS.items():
            if row.get(col) != '1':
                counts[comp] += 1

    return [
        {'component': comp, 'duration': fmt_duration(timedelta(minutes=mins))}
        for comp, mins in counts.items()
    ]


def calculate_system_status(uptime_data: list) -> dict:
    """
    Jacquard Machine Run Time  : rows where machine_status == '1' → each row = 1 min
    Jacquard Machine Downtime  : rows where machine_status != '1' → each row = 1 min
    """
    run_min  = 0
    down_min = 0

    for row in uptime_data:
        if row.get('machine_status') == '1':
            run_min += 1
        else:
            down_min += 1

    return {
        'machine_run_time': fmt_duration(timedelta(minutes=run_min)),
        'machine_downtime':  fmt_duration(timedelta(minutes=down_min)),
    }


def calculate_error_logs(uptime_data: list, active_cameras: list) -> dict:
    """
    Calculate Software Errors Duration, Camera Off Duration, and Camera Off Cycles.

    Software Errors Duration:
        For each row, if ANY of the software columns != '1' → add 1 minute.

    Camera Off Duration:
        Derive camera column names from active_cameras (cam_name + '_status').
        For each row, if ANY camera column != '1' → add 1 minute.

    Camera Off Cycles (per-camera breakdown):
        For each active camera, count total minutes where its column != '1'.
    """
    cam_names = [c['cam_name'] for c in active_cameras]
    cam_cols  = [name + '_status' for name in cam_names]

    sw_error_min = 0
    cam_off_min  = 0

    # Sort records by timestamp to ensure correct consecutive order
    sorted_data = sorted(uptime_data, key=lambda r: r["formatted_timestamp"])

    # Software Errors Duration and Camera Off Duration — every row counts
    for row in sorted_data:
        if any(row.get(col) != '1' for col in SOFTWARE_COLS):
            sw_error_min += 1
        if cam_cols and any(row.get(col) != '1' for col in cam_cols):
            cam_off_min += 1

    # Camera Off Cycles — only count continuous off streaks > 1 minute per camera
    per_cam_off = {col: 0 for col in cam_cols}

    for col in cam_cols:
        streak = 0
        for row in sorted_data:
            if row.get(col) != '1':
                streak += 1
            else:
                if streak > 1:          # continuous off > 1 min → count it
                    per_cam_off[col] += streak
                streak = 0
        if streak > 1:                  # handle streak running to end of data
            per_cam_off[col] += streak

    return {
        'software_errors_duration': fmt_duration(timedelta(minutes=sw_error_min)),
        'camera_off_duration':      fmt_duration(timedelta(minutes=cam_off_min)),
    }


def calculate_camera_cycles(uptime_data: list, active_cameras: list) -> list:
    """
    For each active camera, find continuous off cycles (>= 2 consecutive rows
    where cam_status != '1'). Each cycle records the cam name, cycle number,
    from/to timestamps, and duration.

    Returns a flat list of cycle dicts:
      [{"cam_name": "cam1", "cycle": 1, "from": "...", "to": "...", "duration": "HH:MM"}, ...]
    """
    sorted_data = sorted(uptime_data, key=lambda r: r["formatted_timestamp"])

    result = []
    for cam in active_cameras:
        cam_name = cam['cam_name']
        col      = cam_name + '_status'
        cycle_no = 0
        streak   = []

        for row in sorted_data:
            if row.get(col) != '1':
                streak.append(row)
            else:
                if len(streak) >= 2:
                    cycle_no += 1
                    result.append({
                        "cam_name": cam_name,
                        "cycle":    cycle_no,
                        "from":     streak[0]["formatted_timestamp"],
                        "to":       streak[-1]["formatted_timestamp"],
                        "duration": fmt_duration(timedelta(minutes=len(streak))),
                    })
                streak = []

        if len(streak) >= 2:
            cycle_no += 1
            result.append({
                "cam_name": cam_name,
                "cycle":    cycle_no,
                "from":     streak[0]["formatted_timestamp"],
                "to":       streak[-1]["formatted_timestamp"],
                "duration": fmt_duration(timedelta(minutes=len(streak))),
            })

    return result


def calculate_downtime_periods(uptime_data: list, start_str: str, end_str: str) -> list:
    """
    Walk every minute in the shift range. Consecutive minutes with no record
    are grouped into a downtime period with from/to timestamps and duration.
    Returns list of {"from": "...", "to": "...", "duration": "HH:MM"}.
    """
    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
    end_dt   = datetime.strptime(end_str,   "%Y-%m-%d %H:%M")

    recorded_minutes = {
        datetime.strptime(r["formatted_timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        for r in uptime_data
    }

    periods  = []
    streak   = []
    current  = start_dt

    while current < end_dt:
        if current.strftime("%Y-%m-%d %H:%M") not in recorded_minutes:
            streak.append(current)
        else:
            if streak:
                periods.append({
                    "from":     streak[0].strftime("%Y-%m-%d %H:%M"),
                    "to":       streak[-1].strftime("%Y-%m-%d %H:%M"),
                    "duration": fmt_duration(timedelta(minutes=len(streak))),
                })
                streak = []
        current += timedelta(minutes=1)

    if streak:
        periods.append({
            "from":     streak[0].strftime("%Y-%m-%d %H:%M"),
            "to":       streak[-1].strftime("%Y-%m-%d %H:%M"),
            "duration": fmt_duration(timedelta(minutes=len(streak))),
        })

    return periods
