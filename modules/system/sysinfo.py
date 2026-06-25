"""System information via psutil + stdlib."""

from __future__ import annotations

import os
import platform
import shutil
from datetime import datetime

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a phase-1 dependency
    psutil = None  # type: ignore


def _require_psutil() -> None:
    if psutil is None:
        raise RuntimeError("psutil is not installed (pip install psutil).")


def get_system_info(info_type: str = "all") -> dict:
    info_type = (info_type or "all").lower()
    handlers = {
        "cpu": _cpu,
        "ram": _ram,
        "disk": _disk,
        "processes": _processes,
        "network": _network,
        "battery": _battery,
        "datetime": _datetime,
        "env_vars": _env_vars,
    }
    if info_type == "all":
        out = {}
        for name, fn in handlers.items():
            try:
                out[name] = fn()
            except Exception as e:
                out[name] = {"error": str(e)}
        return out
    if info_type in handlers:
        return {info_type: handlers[info_type]()}
    return {"error": f"Unknown info_type: {info_type}"}


def _cpu() -> dict:
    _require_psutil()
    return {
        "percent": psutil.cpu_percent(interval=0.5),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
    }


def _ram() -> dict:
    _require_psutil()
    m = psutil.virtual_memory()
    return {
        "total_gb": round(m.total / 1e9, 2),
        "available_gb": round(m.available / 1e9, 2),
        "used_percent": m.percent,
    }


def _disk() -> dict:
    out = {}
    if psutil is not None:
        parts = psutil.disk_partitions(all=False)
    else:  # fallback to a single root usage
        parts = []
    if parts:
        for p in parts:
            try:
                u = shutil.disk_usage(p.mountpoint)
                out[p.device] = {
                    "total_gb": round(u.total / 1e9, 2),
                    "free_gb": round(u.free / 1e9, 2),
                    "used_percent": round(u.used / u.total * 100, 1) if u.total else 0,
                }
            except Exception as e:
                out[p.device] = {"error": str(e)}
    else:
        u = shutil.disk_usage(os.getcwd())
        out["."] = {
            "total_gb": round(u.total / 1e9, 2),
            "free_gb": round(u.free / 1e9, 2),
        }
    return out


def _processes() -> list[dict]:
    _require_psutil()
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except Exception:
            continue
    procs.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
    return procs[:15]


def _network() -> dict:
    _require_psutil()
    io = psutil.net_io_counters()
    return {
        "bytes_sent_mb": round(io.bytes_sent / 1e6, 1),
        "bytes_recv_mb": round(io.bytes_recv / 1e6, 1),
    }


def _battery() -> dict:
    _require_psutil()
    b = psutil.sensors_battery()
    if b is None:
        return {"present": False}
    return {"present": True, "percent": b.percent, "plugged_in": b.power_plugged}


def _datetime() -> dict:
    now = datetime.now()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "human": now.strftime("%A, %d %B %Y, %I:%M %p"),
    }


def _env_vars() -> dict:
    # Only a safe subset; never dump secrets wholesale.
    keys = ["USERNAME", "COMPUTERNAME", "OS", "PROCESSOR_ARCHITECTURE",
            "NUMBER_OF_PROCESSORS", "USERPROFILE", "SystemRoot"]
    return {k: os.environ.get(k, "") for k in keys}


def platform_summary() -> str:
    return f"{platform.system()} {platform.release()} ({platform.version()})"
