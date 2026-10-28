import time
from pathlib import Path

from vitals.alerts import AlertManager
from vitals.history import History
from vitals.logger import EventLog, MetricsRecorder
from vitals.resolver import HostResolver
from vitals.security import analyze
from vitals.stats import (
    DiskIOMeter,
    NetworkMeter,
    ProcessTracker,
    get_connections,
    get_cpu,
    get_disks,
    get_memory,
    get_system_info,
)


class Monitor:
    def __init__(self, config):
        self.config = config
        self.interval = config["refresh"]["interval"]
        self.process_interval = max(config["refresh"]["process_interval"], self.interval)
        self.processes = None
        self.processes_time = 0.0
        log_directory = None
        self.recorder = None
        if config["logging"]["enabled"]:
            log_directory = Path(config["logging"]["directory"])
            try:
                log_directory.mkdir(parents=True, exist_ok=True)
                self.recorder = MetricsRecorder(log_directory, config["logging"]["record_interval"])
            except OSError:
                log_directory = None

        self.log = EventLog(log_directory)
        self.history = History(size=300)
        self.network = NetworkMeter()
        self.disk_io = DiskIOMeter()
        self.tracker = ProcessTracker()
        self.alerts = AlertManager(config, self.log)
        self.alert_items = []
        self.resolver = HostResolver(config["network"]["resolve_hosts"])
        self.log_directory = log_directory

        get_cpu()
        self.tracker.read()
        self.log.add("INFO", "Vitals started")
        if config["source"]:
            self.log.add("INFO", f"Loaded settings from {config['source']}")
        if log_directory:
            self.log.add("INFO", f"Recording to {log_directory}")

    def gather(self):
        now = time.monotonic()
        if self.processes is None or now - self.processes_time >= self.process_interval:
            processes, started, exited = self.tracker.read()
            self.processes = processes
            self.processes_time = now
        else:
            processes, started, exited = self.processes, [], []
        connections = get_connections()
        security = analyze(processes, connections or [], self.config["security"])
        security["available"] = connections is not None

        return {
            "system": get_system_info(),
            "cpu": get_cpu(),
            "memory": get_memory(),
            "disks": get_disks(),
            "disk_io": self.disk_io.read(),
            "network": self.network.read(),
            "processes": processes,
            "started": started,
            "exited": exited,
            "security": security,
        }

    def apply(self, snapshot):
        history = self.history
        history.add("cpu", snapshot["cpu"]["total"])
        history.add("ram", snapshot["memory"]["percent"])
        history.add("swap", snapshot["memory"]["swap_percent"])
        history.add("up", snapshot["network"]["upload"])
        history.add("down", snapshot["network"]["download"])
        history.add("disk_read", snapshot["disk_io"]["read"])
        history.add("disk_write", snapshot["disk_io"]["write"])

        self.alert_items = self.alerts.check(snapshot, history)
        if self.recorder:
            self.recorder.record(snapshot)

    def collect(self):
        snapshot = self.gather()
        self.apply(snapshot)
        return snapshot

    def take_new_alert(self):
        fresh = self.alerts.fresh
        self.alerts.fresh = False
        return fresh

    def close(self):
        self.resolver.close()
        self.log.add("INFO", "Vitals stopped")
