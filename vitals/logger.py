import csv
import json
import time
from collections import deque
from pathlib import Path


class EventLog:
    def __init__(self, directory=None, size=500):
        self.entries = deque(maxlen=size)
        self.directory = Path(directory) if directory else None

    def add(self, level, message):
        self.entries.append((time.strftime("%H:%M:%S"), level, message))
        if not self.directory:
            return
        path = self.directory / f"events-{time.strftime('%Y-%m-%d')}.log"
        try:
            with open(path, "a", encoding="utf-8") as file:
                file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {level:<6}  {message}\n")
        except OSError:
            pass


class MetricsRecorder:
    FIELDS = ["time", "cpu", "ram", "swap", "upload", "download", "disk_read", "disk_write"]

    def __init__(self, directory, every):
        self.directory = Path(directory)
        self.every = every
        self.last = 0.0

    def record(self, snapshot):
        now = time.time()
        if now - self.last < self.every:
            return
        self.last = now

        path = self.directory / f"metrics-{time.strftime('%Y-%m-%d')}.csv"
        is_new = not path.exists()
        cpu = snapshot["cpu"]
        memory = snapshot["memory"]
        network = snapshot["network"]
        disk_io = snapshot["disk_io"]
        try:
            with open(path, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                if is_new:
                    writer.writerow(self.FIELDS)
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    round(cpu["total"], 1),
                    round(memory["percent"], 1),
                    round(memory["swap_percent"], 1),
                    round(network["upload"]),
                    round(network["download"]),
                    round(disk_io["read"]),
                    round(disk_io["write"]),
                ])
        except OSError:
            pass


def export_snapshot(snapshot, alerts, directory):
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"snapshot-{time.strftime('%Y%m%d-%H%M%S')}.json"

    processes = sorted(snapshot["processes"], key=lambda p: p["cpu"], reverse=True)
    data = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "system": snapshot["system"],
        "cpu": snapshot["cpu"],
        "memory": snapshot["memory"],
        "disks": snapshot["disks"],
        "disk_io": snapshot["disk_io"],
        "network": snapshot["network"],
        "alerts": [message for message, _ in alerts],
        "listening_ports": snapshot["security"]["listeners"],
        "flagged_processes": snapshot["security"]["flagged"],
        "connections": snapshot["security"]["connections"],
        "top_processes": processes[:50],
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, default=str)
    return path
