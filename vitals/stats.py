import ipaddress
import os
import platform
import socket
import subprocess
import time

import psutil

FAST_ATTRS = ["cpu_times", "memory_info", "io_counters"]
SLOW_ATTRS = ["num_threads", "status"]
SLOW_EVERY = 5
STATIC_ATTRS = ["name", "ppid", "username", "exe", "create_time"]

GONE = (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess)


def format_bytes(value):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value = value / 1024
    return f"{value:.1f} PB"


def format_duration(seconds):
    seconds = int(max(seconds, 0))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def get_cpu():
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    try:
        freq = psutil.cpu_freq()
        freq_mhz = freq.current if freq else None
    except (OSError, NotImplementedError, AttributeError):
        freq_mhz = None
    return {
        "total": sum(per_core) / len(per_core) if per_core else 0.0,
        "per_core": per_core,
        "cores": len(per_core),
        "freq": freq_mhz,
    }


def get_memory():
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "percent": ram.percent,
        "used": ram.used,
        "total": ram.total,
        "available": ram.available,
        "swap_percent": swap.percent,
        "swap_used": swap.used,
        "swap_total": swap.total,
    }


PARTITIONS = {"list": [], "time": 0.0}
INTERFACE = {"value": None, "time": 0.0}


def get_partitions():
    if time.time() - PARTITIONS["time"] > 30:
        try:
            PARTITIONS["list"] = psutil.disk_partitions()
        except OSError:
            PARTITIONS["list"] = []
        PARTITIONS["time"] = time.time()
    return PARTITIONS["list"]


def get_disks():
    disks = []
    for part in get_partitions():
        if "cdrom" in part.opts or part.fstype == "":
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append({
            "name": part.mountpoint,
            "percent": usage.percent,
            "used": usage.used,
            "total": usage.total,
        })
    return disks


def get_system_info():
    battery = None
    try:
        info = psutil.sensors_battery()
        if info is not None:
            battery = {"percent": info.percent, "plugged": info.power_plugged}
    except (AttributeError, NotImplementedError, OSError):
        pass
    return {
        "host": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "uptime": time.time() - psutil.boot_time(),
        "battery": battery,
        "temperature": get_cpu_temperature(),
    }


def get_cpu_temperature():
    reader = getattr(psutil, "sensors_temperatures", None)
    if reader is None:
        return None
    try:
        sensors = reader()
    except (OSError, NotImplementedError, AttributeError):
        return None
    for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
        for entry in sensors.get(name, []):
            if entry.current:
                return entry.current
    return None


def get_primary_interface():
    if INTERFACE["value"] is None or time.time() - INTERFACE["time"] > 30:
        INTERFACE["value"] = find_primary_interface()
        INTERFACE["time"] = time.time()
    return INTERFACE["value"]


def find_primary_interface():
    try:
        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
    except OSError:
        return {"name": "-", "ip": "-"}
    for name, addrs in addresses.items():
        if name in stats and not stats[name].isup:
            continue
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith(("127.", "169.254.")):
                return {"name": name, "ip": addr.address}
    return {"name": "-", "ip": "-"}


class NetworkMeter:
    def __init__(self):
        self.last = psutil.net_io_counters()
        self.last_time = time.time()

    def read(self):
        now = time.time()
        current = psutil.net_io_counters()
        elapsed = max(now - self.last_time, 1e-6)

        upload = max(current.bytes_sent - self.last.bytes_sent, 0) / elapsed
        download = max(current.bytes_recv - self.last.bytes_recv, 0) / elapsed

        self.last = current
        self.last_time = now

        return {
            "upload": upload,
            "download": download,
            "total_sent": current.bytes_sent,
            "total_received": current.bytes_recv,
            "interface": get_primary_interface(),
        }


class DiskIOMeter:
    def __init__(self):
        self.last = self._counters()
        self.last_time = time.time()

    def _counters(self):
        try:
            return psutil.disk_io_counters()
        except (OSError, RuntimeError):
            return None

    def read(self):
        now = time.time()
        current = self._counters()
        elapsed = max(now - self.last_time, 1e-6)

        if current is None or self.last is None:
            self.last = current
            self.last_time = now
            return {"read": 0.0, "write": 0.0, "available": False}

        read = max(current.read_bytes - self.last.read_bytes, 0) / elapsed
        write = max(current.write_bytes - self.last.write_bytes, 0) / elapsed

        self.last = current
        self.last_time = now
        return {"read": read, "write": write, "available": True}


def short_user(username):
    if not username:
        return "-"
    return username.replace("/", "\\").split("\\")[-1]


class ProcessTracker:
    def __init__(self):
        self.cores = psutil.cpu_count() or 1
        self.total_memory = psutil.virtual_memory().total or 1
        self.static = {}
        self.slow = {}
        self.ticks = 0
        self.last_io = {}
        self.last_cpu = {}
        self.last_time = time.time()
        self.known_pids = None

    def static_info(self, proc):
        info = self.static.get(proc.pid)
        if info is None:
            values = proc.as_dict(STATIC_ATTRS, ad_value=None)
            info = {
                "name": values["name"] or "?",
                "ppid": values["ppid"],
                "user": short_user(values["username"]),
                "exe": values["exe"] or "",
                "started": values["create_time"] or 0.0,
            }
            self.static[proc.pid] = info
        return info

    def read(self):
        now = time.time()
        elapsed = max(now - self.last_time, 1e-6)
        processes = []
        io_now = {}
        cpu_now = {}
        refresh_slow = self.ticks % SLOW_EVERY == 0
        self.ticks += 1
        attrs = FAST_ATTRS + SLOW_ATTRS if refresh_slow else FAST_ATTRS

        for proc in psutil.process_iter(attrs, ad_value=None):
            pid = proc.pid
            if pid == 0:
                continue
            try:
                static = self.static_info(proc)
            except GONE:
                continue

            info = proc.info
            cpu = 0.0
            times = info["cpu_times"]
            if times is not None:
                used = times.user + times.system
                cpu_now[pid] = used
                previous = self.last_cpu.get(pid)
                if previous is not None:
                    cpu = max(used - previous, 0) / elapsed / self.cores * 100
            if refresh_slow or pid not in self.slow:
                if "num_threads" not in info:
                    info.update(proc.as_dict(SLOW_ATTRS, ad_value=None))
                self.slow[pid] = (info["num_threads"] or 0, info["status"] or "?")
            threads, status = self.slow[pid]
            io_rate = 0.0
            io = info["io_counters"]
            if io is not None:
                total = io.read_bytes + io.write_bytes
                io_now[pid] = total
                previous = self.last_io.get(pid)
                if previous is not None:
                    io_rate = max(total - previous, 0) / elapsed

            memory = info["memory_info"]
            rss = memory.rss if memory else 0
            processes.append({
                "pid": pid,
                "ppid": static["ppid"],
                "name": static["name"],
                "user": static["user"],
                "threads": threads,
                "status": status,
                "cpu": cpu,
                "memory": rss / self.total_memory * 100,
                "rss": rss,
                "exe": static["exe"],
                "started": static["started"],
                "io": io_rate,
            })

        current_pids = {p["pid"] for p in processes}
        started = []
        exited = []
        if self.known_pids is not None:
            by_pid = {p["pid"]: p for p in processes}
            started = [by_pid[pid] for pid in current_pids - self.known_pids]
            exited = [
                (pid, self.static.get(pid, {}).get("name", "?"))
                for pid in self.known_pids - current_pids
            ]

        for cache in (self.static, self.slow):
            for pid in list(cache):
                if pid not in current_pids:
                    del cache[pid]
        self.known_pids = current_pids
        self.last_io = io_now
        self.last_cpu = cpu_now
        self.last_time = now
        return processes, started, exited


def ip_scope(ip):
    if not ip:
        return "none"
    try:
        address = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_unspecified:
        return "any"
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link-local"
    if address.is_private:
        return "private"
    if address.is_multicast:
        return "multicast"
    return "public"


def get_connections():
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError, OSError):
        return None

    result = []
    for conn in connections:
        result.append({
            "pid": conn.pid,
            "proto": "TCP" if conn.type == socket.SOCK_STREAM else "UDP",
            "local_ip": conn.laddr.ip if conn.laddr else "",
            "local_port": conn.laddr.port if conn.laddr else 0,
            "remote_ip": conn.raddr.ip if conn.raddr else "",
            "remote_port": conn.raddr.port if conn.raddr else 0,
            "status": conn.status,
        })
    return result


def safe_call(function, default="access denied"):
    try:
        return function()
    except GONE:
        return default
    except (OSError, AttributeError):
        return default


def get_process_details(pid, slow=True):
    try:
        proc = psutil.Process(pid)
    except GONE:
        return None

    def count_connections():
        method = getattr(proc, "net_connections", None) or proc.connections
        return len(method(kind="inet"))

    def parent_text():
        parent = proc.parent()
        return f"{parent.name()} ({parent.pid})" if parent else "-"

    return {
        "pid": pid,
        "name": safe_call(proc.name, "?"),
        "exe": safe_call(proc.exe, ""),
        "cmdline": safe_call(lambda: " ".join(proc.cmdline()) or "-"),
        "cwd": safe_call(proc.cwd),
        "parent": safe_call(parent_text),
        "started": safe_call(proc.create_time, None),
        "user": safe_call(lambda: short_user(proc.username())),
        "open_files": safe_call(lambda: len(proc.open_files()), "?") if slow else "…",
        "connections": safe_call(count_connections, "?"),
        "children": safe_call(lambda: len(proc.children()), "?"),
    }


def kill_process(pid):
    proc = psutil.Process(pid)
    name = proc.name()
    proc.terminate()
    return name


def open_location(path):
    if not path or not os.path.exists(path):
        return False
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", path])
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
