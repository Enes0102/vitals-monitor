import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from rich.console import Console
from rich.live import Live

from vitals.keyboard import KeyReader
from vitals.logger import export_snapshot
from vitals.monitor import Monitor
from vitals.security import file_sha256
from vitals.stats import get_process_details, kill_process, open_location
from vitals.ui import TABS, render

SORTS = [
    ("cpu", "CPU", True),
    ("memory", "memory", True),
    ("io", "I/O", True),
    ("threads", "threads", True),
    ("started", "newest", True),
    ("pid", "PID", False),
    ("name", "name", False),
]

TAB_KEYS = [key for key, _ in TABS]
FLAGGED_LIMIT = 5


class App:
    def __init__(self, monitor):
        self.monitor = monitor
        self.history = monitor.history
        self.snapshot = None
        self.running = True
        self.tab = "overview"
        self.selected = {}
        self.offset = {}
        self.capacity = {}
        self.sort_index = 0
        self.sort_reverse = SORTS[0][2]
        self.filter = ""
        self.search_mode = False
        self.search_buffer = ""
        self.paused = False
        self.show_help = False
        self.detail_pid = None
        self.details = None
        self.confirm = None
        self.message = None
        self.hashes = {}
        self.details_due = 0.0

    def notify(self, text, style="green", seconds=4):
        self.message = (text, style, time.time() + seconds)

    def sort_label(self):
        arrow = "▼" if self.sort_reverse else "▲"
        return f"{SORTS[self.sort_index][1]} {arrow}"

    def resolve(self, ip):
        return self.monitor.resolver.lookup(ip)

    def matches(self, *values):
        if not self.filter:
            return True
        needle = self.filter.lower()
        return any(needle in str(value).lower() for value in values if value is not None)

    def sorted_processes(self):
        key = SORTS[self.sort_index][0]
        processes = [
            p for p in self.snapshot["processes"]
            if self.matches(p["name"], p["pid"], p["user"])
        ]
        if key == "name":
            return sorted(processes, key=lambda p: p["name"].lower(), reverse=self.sort_reverse)
        return sorted(processes, key=lambda p: p[key] or 0, reverse=self.sort_reverse)

    def rows(self, tab):
        security = self.snapshot["security"]
        if tab in ("overview", "processes"):
            return self.sorted_processes()
        if tab == "network":
            return [
                c for c in security["connections"]
                if self.matches(c["name"], c["pid"], c["remote_ip"], c["remote_port"], c["status"],
                                self.monitor.resolver.cache.get(c["remote_ip"]))
            ]
        if tab == "security":
            flagged = [p for p in security["flagged"] if self.matches(p["name"], p["pid"], p["exe"])]
            listeners = [
                item for item in security["listeners"]
                if self.matches(item["name"], item["pid"], item["port"], item["risk"], item["service"])
            ]
            return (
                [{"kind": "flagged", "pid": p["pid"], "item": p} for p in flagged[:FLAGGED_LIMIT]]
                + [{"kind": "listener", "pid": item["pid"], "item": item} for item in listeners]
            )
        entries = list(reversed(self.monitor.log.entries))
        return [entry for entry in entries if self.matches(*entry)]

    def clamp(self, tab, count):
        value = self.selected.get(tab, 0)
        value = max(0, min(value, count - 1)) if count else 0
        self.selected[tab] = value
        return value

    def selected_pid(self):
        tab = self.tab
        rows = self.rows(tab)
        if not rows or tab == "log":
            return None
        row = rows[self.clamp(tab, len(rows))]
        return row.get("pid")

    def move(self, delta):
        tab = self.tab
        count = len(self.rows(tab))
        self.selected[tab] = self.selected.get(tab, 0) + delta
        self.clamp(tab, count)

    def switch_tab(self, tab):
        self.tab = tab
        self.detail_pid = None
        self.show_help = False

    def open_details(self, pid):
        if pid is None:
            return
        self.detail_pid = pid
        self.details = get_process_details(pid, slow=False)
        self.details_due = 0.0

    def ask_kill(self, pid):
        if pid is None:
            return
        if pid == os.getpid():
            self.notify("Vitals can't end itself. Press q to quit.", "yellow")
            return
        name = next((p["name"] for p in self.snapshot["processes"] if p["pid"] == pid), str(pid))
        self.confirm = (pid, name)

    def kill(self, pid, name):
        try:
            kill_process(pid)
        except Exception as error:
            reason = "access denied, try running as administrator" if "denied" in str(error).lower() \
                else "the process is already gone" if "no process" in str(error).lower() \
                else str(error)
            self.notify(f"Couldn't end {name}: {reason}", "bold red", 6)
            self.monitor.log.add("WARN", f"Failed to end {name} ({pid}): {reason}")
            return
        self.notify(f"Ended {name} (PID {pid})", "green")
        self.monitor.log.add("PROC", f"Ended {name} ({pid}) from Vitals")
        if self.detail_pid == pid:
            self.detail_pid = None

    def export(self):
        try:
            path = export_snapshot(self.snapshot, self.monitor.alert_items, "exports")
        except OSError as error:
            self.notify(f"Export failed: {error}", "bold red", 6)
            return
        self.notify(f"Snapshot saved to {path}", "green", 6)
        self.monitor.log.add("INFO", f"Exported snapshot to {path}")

    def start_hash(self, path):
        if not path:
            self.notify("The program path isn't readable, so it can't be hashed.", "yellow")
            return
        if path in self.hashes:
            return

        def worker():
            result = file_sha256(path)
            self.hashes[path] = result if result else None
            if not result:
                self.notify("Couldn't read the file (too large or access denied).", "yellow")

        self.hashes[path] = ""
        threading.Thread(target=worker, daemon=True).start()

    def virustotal(self):
        path = self.details["exe"] if self.details else ""
        sha = self.hashes.get(path)
        if sha:
            webbrowser.open(f"https://www.virustotal.com/gui/file/{sha}")
            self.notify("Opened VirusTotal in your browser", "green")
        elif sha == "":
            self.notify("Still calculating the hash…", "yellow")
        else:
            self.start_hash(path)
            self.notify("Calculating the hash, press v again in a moment", "yellow")

    def copy_path(self):
        path = self.details["exe"] if self.details else ""
        if not path:
            self.notify("No readable path to copy.", "yellow")
            return
        if copy_to_clipboard(path):
            self.notify("Path copied to clipboard", "green")
        else:
            self.notify("No clipboard tool found on this system.", "yellow")

    def handle(self, key):
        if key is None:
            return
        if self.search_mode:
            self.handle_search(key)
            return
        if self.confirm:
            pid, name = self.confirm
            self.confirm = None
            if key == "y":
                self.kill(pid, name)
            else:
                self.notify("Cancelled", "grey62", 2)
            return
        if key == "q":
            self.running = False
            return
        if key == "?":
            self.show_help = not self.show_help
            return
        if self.show_help:
            if key in ("esc", "enter", "backspace"):
                self.show_help = False
                return
        if self.detail_pid is not None:
            if self.handle_details(key):
                return

        if key in "12345" and len(key) == 1:
            self.switch_tab(TAB_KEYS[int(key) - 1])
        elif key in ("tab", "right"):
            self.switch_tab(TAB_KEYS[(TAB_KEYS.index(self.tab) + 1) % len(TAB_KEYS)])
        elif key == "left":
            self.switch_tab(TAB_KEYS[(TAB_KEYS.index(self.tab) - 1) % len(TAB_KEYS)])
        elif key == "up":
            self.move(-1)
        elif key == "down":
            self.move(1)
        elif key == "pageup":
            self.move(-self.capacity.get(self.tab, 10))
        elif key == "pagedown":
            self.move(self.capacity.get(self.tab, 10))
        elif key == "home":
            self.selected[self.tab] = 0
        elif key == "end":
            self.selected[self.tab] = len(self.rows(self.tab)) - 1
            self.clamp(self.tab, len(self.rows(self.tab)))
        elif key == "enter":
            self.open_details(self.selected_pid())
        elif key == "esc":
            if self.filter:
                self.filter = ""
                self.notify("Filter cleared", "grey62", 2)
        elif key == "/":
            self.search_mode = True
            self.search_buffer = self.filter
        elif key == "s":
            self.sort_index = (self.sort_index + 1) % len(SORTS)
            self.sort_reverse = SORTS[self.sort_index][2]
            self.notify(f"Sorting by {self.sort_label()}", "cyan", 2)
        elif key == "r":
            self.sort_reverse = not self.sort_reverse
            self.notify(f"Sorting by {self.sort_label()}", "cyan", 2)
        elif key == "k":
            self.ask_kill(self.selected_pid())
        elif key == "p":
            self.paused = not self.paused
            self.notify("Paused" if self.paused else "Resumed", "yellow" if self.paused else "green", 2)
        elif key == "e":
            self.export()

    def handle_details(self, key):
        if key in ("esc", "backspace", "enter"):
            self.detail_pid = None
            return True
        if key == "k":
            self.ask_kill(self.detail_pid)
            return True
        if key == "o":
            path = self.details["exe"] if self.details else ""
            try:
                opened = open_location(path)
            except OSError:
                opened = False
            if opened:
                self.notify("Opened the program's folder", "green")
            else:
                self.notify("The program's folder isn't accessible.", "yellow")
            return True
        if key == "c":
            self.copy_path()
            return True
        if key == "h":
            self.start_hash(self.details["exe"] if self.details else "")
            return True
        if key == "v":
            self.virustotal()
            return True
        return key in ("up", "down", "pageup", "pagedown", "home", "end", "/", "s", "r")

    def handle_search(self, key):
        if key == "enter":
            self.filter = self.search_buffer.strip()
            self.search_mode = False
            for tab in TAB_KEYS:
                self.selected[tab] = 0
                self.offset[tab] = 0
        elif key == "esc":
            self.search_mode = False
        elif key == "backspace":
            self.search_buffer = self.search_buffer[:-1]
        elif len(key) == 1:
            self.search_buffer += key


def copy_to_clipboard(text):
    if os.name == "nt":
        commands = [["clip"]]
        data = text.encode("utf-16")
    elif platform.system() == "Darwin":
        commands = [["pbcopy"]]
        data = text.encode()
    else:
        commands = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
        data = text.encode()
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=data, check=True, timeout=2,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def collector(app, monitor, lock, stop, events):
    while not stop.is_set():
        started = time.monotonic()
        if not app.paused:
            snapshot = monitor.gather()
            pid = app.detail_pid
            details = None
            if pid is not None and started >= app.details_due:
                details = get_process_details(pid)
            with lock:
                monitor.apply(snapshot)
                app.snapshot = snapshot
                if details is not None and app.detail_pid == pid:
                    app.details = details
                    app.details_due = time.monotonic() + 3
                if monitor.take_new_alert():
                    events["bell"] = True
                events["fresh"] = True
        elapsed = time.monotonic() - started
        stop.wait(max(monitor.interval - elapsed, 0.1))


def run(config):
    console = Console()
    if not console.is_terminal:
        print("Vitals needs an interactive terminal.", file=sys.stderr)
        return 1

    console.print("[cyan]Starting Vitals…[/] [grey50]reading processes for the first time[/]")
    monitor = Monitor(config)
    app = App(monitor)
    time.sleep(0.4)
    app.snapshot = monitor.collect()

    lock = threading.Lock()
    stop = threading.Event()
    events = {"fresh": False, "bell": False}
    worker = threading.Thread(target=collector, args=(app, monitor, lock, stop, events), daemon=True)
    size = console.size

    try:
        with KeyReader() as keys, Live(
            render(app, console.width, console.height),
            console=console,
            screen=True,
            auto_refresh=False,
        ) as live:
            worker.start()
            while app.running:
                dirty = False

                key = keys.read()
                while key is not None and app.running:
                    with lock:
                        app.handle(key)
                    dirty = True
                    key = keys.read()

                if events["fresh"]:
                    events["fresh"] = False
                    dirty = True
                if events["bell"]:
                    events["bell"] = False
                    if config["alerts"]["bell"]:
                        console.bell()

                if console.size != size:
                    size = console.size
                    dirty = True
                if dirty and app.running:
                    with lock:
                        view = render(app, console.width, console.height)
                    live.update(view, refresh=True)
                time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join(timeout=0.5)
        monitor.close()
    return 0
