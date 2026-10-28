import time


class AlertManager:
    def __init__(self, config, log):
        self.config = config["alerts"]
        self.interval = config["refresh"]["interval"]
        self.log = log
        self.process_events = config["logging"]["process_events"]
        self.fresh = False
        self.active = {}
        self.recent = {}
        self.known_listeners = None
        self.known_flagged = set()

    def samples(self, seconds):
        return max(1, round(seconds / self.interval))

    def set_state(self, key, condition, message, level="ALERT"):
        if condition and key not in self.active:
            self.log.add(level, message)
            self.fresh = True
        if condition:
            self.active[key] = message
        else:
            self.active.pop(key, None)

    def flash(self, key, message, level):
        self.log.add(level, message)
        self.fresh = True
        self.recent[key] = (message, time.time())

    def check(self, snapshot, history):
        cfg = self.config
        cpu = snapshot["cpu"]["total"]
        ram = snapshot["memory"]["percent"]
        top = max(snapshot["processes"], key=lambda p: p["cpu"], default=None)
        top_text = f" (top: {top['name']} {top['cpu']:.1f}%)" if top else ""

        self.set_state(
            "cpu",
            history.sustained("cpu", cfg["cpu_percent"], self.samples(cfg["cpu_seconds"])),
            f"CPU above {cfg['cpu_percent']:.0f}% for {cfg['cpu_seconds']}s{top_text}",
        )
        self.set_state(
            "ram",
            history.sustained("ram", cfg["ram_percent"], self.samples(cfg["ram_seconds"])),
            f"RAM above {cfg['ram_percent']:.0f}% ({ram:.1f}% used)",
        )
        for disk in snapshot["disks"]:
            self.set_state(
                f"disk:{disk['name']}",
                disk["percent"] > cfg["disk_percent"],
                f"Disk {disk['name']} is {disk['percent']:.1f}% full",
                "WARN",
            )

        security = snapshot["security"]
        if security["available"]:
            listeners = {(item["pid"], item["port"]): item for item in security["listeners"]}
            if self.known_listeners is not None and cfg["new_listener"]:
                for key in listeners.keys() - self.known_listeners:
                    item = listeners[key]
                    self.flash(
                        f"listen:{key}",
                        f"New listening port {item['ip']}:{item['port']} by {item['name']}",
                        "SEC",
                    )
            self.known_listeners = set(listeners)

            flagged = {p["pid"]: p for p in security["flagged"]}
            if cfg["suspicious_process"]:
                for pid in flagged.keys() - self.known_flagged:
                    proc = flagged[pid]
                    self.flash(
                        f"flag:{pid}",
                        f"Suspicious process {proc['name']} ({pid}): {proc['reasons'][0]}",
                        "SEC",
                    )
            self.known_flagged = set(flagged)

        if self.process_events:
            for pid, name in snapshot["exited"]:
                self.log.add("PROC", f"{name} ({pid}) exited")
            for proc in snapshot["started"]:
                self.log.add("PROC", f"{proc['name']} ({proc['pid']}) started")

        now = time.time()
        self.recent = {
            key: (message, at)
            for key, (message, at) in self.recent.items()
            if now - at < cfg["banner_seconds"]
        }
        return self.current()

    def current(self):
        items = [(message, "SEC") for message, _ in self.recent.values()]
        items += [(message, "ALERT") for message in self.active.values()]
        return items
