import tomllib
from copy import deepcopy
from pathlib import Path

DEFAULTS = {
    "refresh": {
        "interval": 1.0,
        "process_interval": 2.0,
    },
    "alerts": {
        "cpu_percent": 90.0,
        "cpu_seconds": 10,
        "ram_percent": 85.0,
        "ram_seconds": 5,
        "disk_percent": 90.0,
        "new_listener": True,
        "suspicious_process": True,
        "bell": False,
        "banner_seconds": 30,
    },
    "logging": {
        "enabled": True,
        "directory": "logs",
        "record_interval": 5,
        "process_events": True,
    },
    "network": {
        "resolve_hosts": True,
    },
    "security": {
        "suspicious_ports": [4444, 1337, 31337, 6667],
        "trusted_processes": [],
    },
}


def merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path=None):
    config = deepcopy(DEFAULTS)
    config["source"] = None
    candidate = Path(path) if path else Path("config.toml")
    if path and not candidate.is_file():
        raise FileNotFoundError(f"Config file not found: {candidate}")
    if candidate.is_file():
        with open(candidate, "rb") as file:
            merge(config, tomllib.load(file))
        config["source"] = str(candidate)
    return config
