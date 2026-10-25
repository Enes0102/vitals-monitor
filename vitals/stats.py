import psutil
import time


def format_bytes(value):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value = value / 1024
    return f"{value:.1f} PB"


def get_cpu():
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    return {
        "total": sum(per_core) / len(per_core),
        "per_core": per_core,
        "cores": len(per_core),
    }


def get_memory():
    ram = psutil.virtual_memory()
    return {
        "percent": ram.percent,
        "used": ram.used,
        "total": ram.total,
    }


def get_disks():
    disks = []
    for part in psutil.disk_partitions():
        if "cdrom" in part.opts or part.fstype == "":
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue
        disks.append({
            "name": part.mountpoint,
            "percent": usage.percent,
            "used": usage.used,
            "total": usage.total,
        })
    return disks


class NetworkMeter:
    def __init__(self):
        self.last = psutil.net_io_counters()
        self.last_time = time.time()

    def read(self):
        now = time.time()
        current = psutil.net_io_counters()
        elapsed = now - self.last_time

        upload = (current.bytes_sent - self.last.bytes_sent) / elapsed
        download = (current.bytes_recv - self.last.bytes_recv) / elapsed

        self.last = current
        self.last_time = now

        return {
            "upload": upload,
            "download": download,
            "total_sent": current.bytes_sent,
            "total_received": current.bytes_recv,
        }


def get_processes(top=10):
    cores = psutil.cpu_count()
    result = []

    for proc in psutil.process_iter(["pid", "name", "memory_percent"]):
        if proc.info["pid"] == 0:
            continue
        try:
            result.append({
                "pid": proc.info["pid"],
                "name": proc.info["name"] or "?",
                "cpu": proc.cpu_percent() / cores,
                "memory": proc.info["memory_percent"] or 0.0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    result.sort(key=lambda p: p["cpu"], reverse=True)
    return result[:top]


if __name__ == "__main__":
    get_cpu()
    network = NetworkMeter()
    time.sleep(1)

    cpu = get_cpu()
    mem = get_memory()
    net = network.read()

    print("CPU:", round(cpu["total"], 1), "%", "-", cpu["cores"], "cores")
    print("RAM:", mem["percent"], "%", "-",
          format_bytes(mem["used"]), "/", format_bytes(mem["total"]))

    for disk in get_disks():
        print("Disk", disk["name"], ":", disk["percent"], "%", "-",
              format_bytes(disk["used"]), "/", format_bytes(disk["total"]))

    print("Upload:", format_bytes(net["upload"]) + "/s")
    print("Download:", format_bytes(net["download"]) + "/s")
