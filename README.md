# Vitals

**English** | [Türkçe](README.tr.md)

A lightweight, colorful system monitor that runs in your terminal. Vitals shows your CPU, memory, disks, network and the busiest processes on a single live-updating dashboard.

![Vitals screenshot](assets/screenshot.png)

## Features

- **CPU:** total usage plus a bar for every logical core
- **Memory:** RAM usage with used / total amounts
- **Disks:** usage of every mounted drive
- **Network:** live upload/download speed and total traffic
- **Processes:** the busiest processes sorted by CPU usage
- Color-coded bars: green under 50%, yellow under 80%, red above
- Full-screen layout that adapts to the terminal size
- Works on Windows, Linux and macOS

## Installation

Requires Python 3.10 or newer.

```bash
git clone https://github.com/Enes0102/vitals-monitor.git
cd vitals-monitor
pip install -r requirements.txt
```

## Usage

```bash
python -m vitals
```

Press `Ctrl+C` to quit.

| Option | Description | Default |
|---|---|---|
| `-i`, `--interval` | Refresh interval in seconds | `1.0` |
| `-n`, `--top` | Number of processes to show | `20` |
| `-h`, `--help` | Show the help message | |

Example: refresh every 2 seconds and show 10 processes:

```bash
python -m vitals -i 2 -n 10
```

## Project Structure

```
vitals-monitor/
├── vitals/
│   ├── __init__.py
│   ├── __main__.py   # command-line entry point
│   ├── stats.py      # collects system data with psutil
│   └── ui.py         # draws the dashboard with rich
├── assets/
│   └── screenshot.png
├── requirements.txt
└── LICENSE
```

Data collection (`stats.py`) and drawing (`ui.py`) are kept separate, so either part can be changed or reused on its own.

## Built With

- [psutil](https://github.com/giampaolo/psutil): cross-platform system information
- [rich](https://github.com/Textualize/rich): terminal formatting and live rendering

## Roadmap

- [ ] Sort processes by memory with a keyboard shortcut
- [ ] CPU and network history graphs
- [ ] Battery and temperature panels
- [ ] Export a snapshot to JSON

## License

This project is licensed under the [MIT License](LICENSE).
