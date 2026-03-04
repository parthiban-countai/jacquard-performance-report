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
    Calculate Total Uptime, Total Downtime, and Power Off Duration.

    Data is recorded every 1 minute. Logic:
      - Each record present        → 1 minute of Total Uptime
      - Gap between consecutive records:
            missing = gap - 1 min  (subtract the 1 min the current record covers)
            missing >= 2 min       → Power Off Duration
            0 < missing < 2 min    → Total Downtime  (exactly 1 missed minute)
      - Boundary gaps (start → first record, last record → end):
            full gap, same >= 2 / < 2 min classification
    """
    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
    end_dt   = datetime.strptime(end_str,   "%Y-%m-%d %H:%M")

    uptime    = timedelta()
    downtime  = timedelta()
    power_off = timedelta()

    def classify(gap: timedelta):
        nonlocal downtime, power_off
        secs = gap.total_seconds()
        if secs <= 0:
            return
        if secs >= 120:   # >= 2 minutes → Power Off
            power_off += gap
        else:             # < 2 minutes (≈ 1 missed minute) → Downtime
            downtime += gap

    if not uptime_data:
        # No records at all: entire shift is Power Off
        classify(end_dt - start_dt)
    else:
        records = sorted(uptime_data, key=lambda r: r["formatted_timestamp"])
        timestamps = [
            datetime.strptime(r["formatted_timestamp"], "%Y-%m-%d %H:%M:%S")
            for r in records
        ]

        # Each record present = 1 minute of uptime
        uptime = timedelta(minutes=len(records))

        # Gap: shift start → first record
        classify(timestamps[0] - start_dt)

        # Gaps between consecutive records
        for i in range(len(timestamps) - 1):
            gap     = timestamps[i + 1] - timestamps[i]
            missing = gap - timedelta(minutes=1)   # subtract the 1 min the current record covers
            classify(missing)

        # Gap: last record → shift end
        # subtract 1 min because the last record already covers [T, T+1)
        classify(end_dt - timestamps[-1] - timedelta(minutes=1))

    return {
        "total_uptime":       fmt_duration(uptime),
        "total_downtime":     fmt_duration(downtime),
        "power_off_duration": fmt_duration(power_off),
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

    camera_off_cycles = ", ".join(
        f"{col}: {mins}" for col, mins in per_cam_off.items() if mins != 0
    )

    return {
        'software_errors_duration': fmt_duration(timedelta(minutes=sw_error_min)),
        'camera_off_duration':      fmt_duration(timedelta(minutes=cam_off_min)),
        'camera_off_cycles':        camera_off_cycles
    }
