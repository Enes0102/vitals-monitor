import hashlib
import os
import time

from vitals.stats import ip_scope

KNOWN_PORTS = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    135: "Windows RPC",
    139: "NetBIOS",
    443: "HTTPS",
    445: "SMB file sharing",
    1433: "SQL Server",
    1900: "UPnP",
    3000: "Dev server",
    3306: "MySQL",
    3389: "Remote Desktop",
    5000: "Dev server",
    5040: "Windows service",
    5173: "Dev server",
    5357: "Network discovery",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    7680: "Windows Update sharing",
    8000: "Dev server",
    8080: "HTTP alt",
    27017: "MongoDB",
}

SENSITIVE_PORTS = {21, 23, 1433, 3306, 3389, 5432, 5900, 6379, 27017}
SYSTEM_PORTS = {135, 139, 445, 1900, 5040, 5357, 7680}

SYSTEM_NAMES = {
    "svchost.exe",
    "lsass.exe",
    "csrss.exe",
    "winlogon.exe",
    "services.exe",
    "smss.exe",
    "wininit.exe",
    "spoolsv.exe",
    "taskhostw.exe",
}

RISKY_FOLDERS = ("/temp/", "/tmp/", "/downloads/", "/var/tmp/", "/dev/shm/")

NEW_PROCESS_SECONDS = 300


def normalize_path(path):
    return path.replace("\\", "/").lower()


def process_reasons(proc, listeners, now, settings):
    if proc["name"].lower() in settings["trusted"]:
        return []

    reasons = []
    path = normalize_path(proc["exe"])

    if path and any(folder in path for folder in RISKY_FOLDERS):
        reasons.append("runs from a temp or downloads folder")

    if proc["name"].lower() in SYSTEM_NAMES and path and not path.startswith("c:/windows/"):
        reasons.append("uses a Windows system name outside the Windows folder")

    young = proc["started"] and now - proc["started"] < NEW_PROCESS_SECONDS
    if young and any(item["scope"] == "any" for item in listeners):
        reasons.append("started recently and listens on all interfaces")

    if any(item["port"] in settings["suspicious_ports"] for item in listeners):
        reasons.append("listens on a port often used by backdoors")

    return reasons


def listener_risk(listener, flagged_pids, suspicious_ports):
    port = listener["port"]
    if listener["pid"] in flagged_pids or port in suspicious_ports:
        return "suspicious"
    if listener["scope"] == "loopback":
        return "local"
    if port in SYSTEM_PORTS:
        return "system"
    if port in SENSITIVE_PORTS:
        return "exposed"
    if listener["scope"] in ("any", "private", "public"):
        return "open"
    return "local"


def analyze(processes, connections, config):
    settings = {
        "trusted": {name.lower() for name in config.get("trusted_processes", [])},
        "suspicious_ports": set(config.get("suspicious_ports", [])),
    }
    names = {p["pid"]: p["name"] for p in processes}
    now = time.time()

    listeners = []
    established = []
    seen = set()
    for conn in connections:
        name = names.get(conn["pid"], "?" if conn["pid"] else "System")
        if conn["proto"] == "TCP" and conn["status"] == "LISTEN":
            key = (conn["pid"], conn["local_ip"], conn["local_port"])
            if key in seen:
                continue
            seen.add(key)
            listeners.append({
                "pid": conn["pid"],
                "name": name,
                "ip": conn["local_ip"],
                "port": conn["local_port"],
                "scope": ip_scope(conn["local_ip"]),
                "service": KNOWN_PORTS.get(conn["local_port"], ""),
            })
        elif conn["remote_ip"]:
            established.append({
                **conn,
                "name": name,
                "scope": ip_scope(conn["remote_ip"]),
            })

    by_pid = {}
    for listener in listeners:
        by_pid.setdefault(listener["pid"], []).append(listener)

    flagged = []
    for proc in processes:
        reasons = process_reasons(proc, by_pid.get(proc["pid"], []), now, settings)
        if reasons:
            flagged.append({**proc, "reasons": reasons})

    flagged_pids = {p["pid"] for p in flagged}
    for listener in listeners:
        listener["risk"] = listener_risk(listener, flagged_pids, settings["suspicious_ports"])

    risk_order = {"suspicious": 0, "exposed": 1, "open": 2, "system": 3, "local": 4}
    listeners.sort(key=lambda item: (risk_order[item["risk"]], item["port"]))

    scope_order = {"public": 0, "private": 1}
    established.sort(key=lambda item: (
        item["status"] != "ESTABLISHED",
        scope_order.get(item["scope"], 2),
        item["name"].lower(),
    ))

    return {"listeners": listeners, "connections": established, "flagged": flagged}


def file_sha256(path, limit=200 * 1024 * 1024):
    try:
        if not path or os.path.getsize(path) > limit:
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None
