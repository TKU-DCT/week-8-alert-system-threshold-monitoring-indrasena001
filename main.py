import psutil
from datetime import datetime
import sqlite3
import os
import time
import subprocess
import platform
from typing import Tuple

DB_NAME = "log.db"

# Define threshold values
CPU_THRESHOLD = 80.0
MEM_THRESHOLD = 85.0
DISK_THRESHOLD = 90.0


def get_system_info() -> Tuple[str, float, float, float, str, float]:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cpu_percent = psutil.cpu_percent(interval=1.0)
    mem_percent = psutil.virtual_memory().percent

    # Choose disk root based on platform
    if platform.system().lower().startswith("win"):
        current_drive = os.path.splitdrive(os.getcwd())[0] or "C:"
        disk_path = f"{current_drive}\\\\"
    else:
        disk_path = "/"
    disk_percent = psutil.disk_usage(disk_path).percent

    status, latency_ms = ping_host("8.8.8.8")
    return timestamp, cpu_percent, mem_percent, disk_percent, status, latency_ms


def ping_host(host: str) -> Tuple[str, float]:
    is_windows = platform.system().lower().startswith("win")
    try:
        if is_windows:
            # -n 1: one echo; -w 1000: timeout 1000 ms
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", host],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            # -c 1: one echo; -W 1: timeout 1 second
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", host],
                capture_output=True,
                text=True,
                check=False,
            )
        latency = parse_ping_time(result.stdout)
        if latency >= 0:
            return "UP", latency
        return "DOWN", -1.0
    except Exception:
        return "DOWN", -1.0


def parse_ping_time(output: str) -> float:
    """
    Extract latency in milliseconds from ping output.
    Supports common Windows and Unix ping formats.
    Returns -1 if not found.
    """
    text = output.replace("\r", "")

    # Windows examples: "time=23ms" or "Average = 23ms"
    for token in text.split():
        if token.lower().startswith("time=") and token.lower().endswith("ms"):
            value = token.split("=", 1)[1].lower().replace("ms", "").strip()
            try:
                return float(value)
            except ValueError:
                pass

    if "average" in text.lower():
        # Parse the trailing "Average = Xms" in summary
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for ln in reversed(lines):
            if "average" in ln.lower():
                # pick last number ending with ms
                parts = ln.replace("=", " ").replace(",", " ").split()
                for part in reversed(parts):
                    if part.lower().endswith("ms"):
                        try:
                            return float(part.lower().replace("ms", ""))
                        except ValueError:
                            break

    # Unix example: "time=23.1 ms"
    for token in text.replace("=", " = ").split():
        if token.lower().startswith("time"):
            # find the next token that looks like a number or ends with ms
            # e.g., ["time", "=", "23.1", "ms"]
            tokens = text.replace("=", " = ").split()
            for i, t in enumerate(tokens):
                if t.lower() == "time":
                    if i + 2 < len(tokens):
                        val = tokens[i + 2]
                        unit = tokens[i + 3] if i + 3 < len(tokens) else ""
                        if unit.lower().startswith("ms"):
                            try:
                                return float(val)
                            except ValueError:
                                pass
    return -1.0


def ensure_db():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS system_log (
                timestamp TEXT NOT NULL,
                cpu REAL NOT NULL,
                memory REAL NOT NULL,
                disk REAL NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL NOT NULL
            )
            """
        )
        conn.commit()


def insert_log(data: Tuple[str, float, float, float, str, float]) -> None:
    ensure_db()
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO system_log (timestamp, cpu, memory, disk, status, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            data,
        )
        conn.commit()


def check_alerts(cpu: float, memory: float, disk: float) -> None:
    if cpu > CPU_THRESHOLD:
        print(f"⚠️ ALERT: High CPU usage! ({cpu:.1f}%)")
    if memory > MEM_THRESHOLD:
        print(f"⚠️ ALERT: High Memory usage! ({memory:.1f}%)")
    if disk > DISK_THRESHOLD:
        print(f"⚠️ ALERT: Low Disk Space! ({disk:.1f}%)")


if __name__ == "__main__":
    ensure_db()
    iterations = 5
    interval_seconds = 10

    for i in range(iterations):
        ts, cpu, mem, disk, status, latency = get_system_info()
        row = (ts, cpu, mem, disk, status, latency)
        insert_log(row)
        print(f"Logged: {row}")
        check_alerts(cpu, mem, disk)
        if i < iterations - 1:
            time.sleep(interval_seconds)
