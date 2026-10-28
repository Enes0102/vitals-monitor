# Vitals

**English** | [Türkçe](README.tr.md)

A terminal system monitor that goes beyond the task manager. Vitals shows CPU, memory, disks and network with live history graphs, lists every network connection and open port, flags suspicious processes, raises alerts, records everything to disk and turns a day of data into an HTML report.

![Vitals screenshot](assets/screenshot.png)

## Features

### Monitoring
- **CPU:** total and per-core usage, frequency, temperature (Linux) and a 60-second history graph
- **Memory:** RAM and swap usage, free memory, the process using the most RAM
- **Disks:** usage of every drive plus live read/write speed and the process doing the most disk I/O
- **Network:** live upload/download speed with history, active interface and IP address
- **System:** uptime, process and thread count, battery level

### Network and security
- **Connections:** every TCP/UDP connection with its process, remote address and state; public IPs are resolved to host names in the background
- **Listening ports:** every program waiting for incoming connections, labeled by risk:
  `suspicious` (flagged process or backdoor port), `exposed` (database or remote access open to the network), `open` (reachable from the network), `system` and `local` (this PC only)
- **Suspicious process detection:** flags programs that
  - run from a temp or downloads folder
  - use a Windows system name (like `svchost.exe`) outside the Windows folder
  - started recently and listen on all network interfaces
  - listen on ports often used by backdoors (4444, 1337, 31337…)

### Alerts and logging
- Alert banner when CPU or RAM stays above a limit, a disk fills up, a new port opens or a suspicious process appears
- Optional terminal bell on new alerts
- Event log of alerts, security events and processes starting or exiting
- Metrics saved to a daily CSV file, events to a daily log file
- JSON snapshot export of the current state
- **HTML report** with charts, peaks and alerts for any recorded day

### Interactive
- Five tabs: Overview, Network, Security, Processes, Log
- Search, sort and select with the keyboard
- Process details: path, command line, parent, open files, connections and why it was flagged
- End a process (with confirmation), open its folder, copy its path
- SHA-256 hash of the program file and a one-key VirusTotal lookup

![HTML report](assets/report.png)

## Installation

Requires Python 3.11 or newer.

```bash
git clone https://github.com/Enes0102/vitals-monitor.git
cd vitals-monitor
pip install -r requirements.txt
```

## Usage

```bash
python -m vitals
```

| Option | Description |
|---|---|
| `-i`, `--interval SECONDS` | Refresh interval (default: 1.0) |
| `-c`, `--config PATH` | Use a specific settings file |
| `--no-log` | Don't write anything to disk |
| `--report [DATE]` | Build an HTML report for a day (`YYYY-MM-DD`, default: today) |
| `--no-open` | With `--report`, don't open the browser |
| `--version` | Show the version |

Examples:

```bash
python -m vitals -i 2
python -m vitals --report
python -m vitals --report 2026-10-27
```

### Tabs

| Tab | What you see |
|---|---|
| **1 Overview** | CPU (total and per core), memory, disks, network and the busiest processes. The `60s` rows are mini graphs of the last minute. `busiest` in the Disks panel is the process doing the most I/O (on Windows this also counts network traffic). |
| **2 Network** | Every connection: which program, which remote IP and port, and its state. The Host column shows the domain behind a public IP, filled in a moment after it appears. |
| **3 Security** | Suspicious processes with the reasons they were flagged, and every listening port with its risk level. |
| **4 Processes** | A detailed task manager: PID, parent, user, threads, status, CPU, memory, I/O and age. |
| **5 Log** | Everything that happened, newest first: alerts, security events, programs starting and exiting. |

### Keyboard shortcuts

| Key | Action |
|---|---|
| `1`-`5`, `Tab`, `←` `→` | Switch tabs |
| `↑` `↓`, `PgUp` `PgDn`, `Home` `End` | Move the selection |
| `Enter` | Open process details |
| `Esc` | Go back / clear the filter |
| `/` | Search by name, PID, user, IP or host |
| `s` / `r` | Change sort column / reverse order |
| `k` | End the selected process (asks first) |
| `p` | Pause / resume updates |
| `e` | Export a JSON snapshot |
| `?` | Help |
| `q` | Quit |

### Permissions

Some information needs more rights. On Windows, run the terminal as administrator to see the paths and connections of system processes. On macOS and Linux, connections of other users' processes need `sudo`.

## Process details and VirusTotal

Select a process and press `Enter` to see its path, command line, parent, start time, open files, connections, listening ports and, if flagged, why. In this view:

| Key | Action |
|---|---|
| `o` | Open the program's folder |
| `c` | Copy the program path |
| `h` | Calculate the SHA-256 hash of the program file |
| `v` | Look the hash up on VirusTotal |

A SHA-256 hash works like a fingerprint: change a single byte of a file and the hash changes completely. [VirusTotal](https://www.virustotal.com) checks files with more than 70 antivirus engines. Vitals never uploads the file itself; it only opens the VirusTotal page for its hash, where you can see whether the file has been scanned before and how many engines flag it.

To try it: press `4`, search `/chrome`, press `Enter` twice, then `h` and a moment later `v`.

## Daily report

While Vitals runs it saves CPU, RAM, network and disk values every 5 seconds, plus every alert. Turn that into a report with charts:

```bash
python -m vitals --report              # today
python -m vitals --report 2026-10-27   # a specific day
```

The report shows how long Vitals recorded, averages and peaks, charts for the whole day, the five busiest moments and every alert and security event of that day.

- The report only covers the time Vitals was running. The longer you leave it open, the more complete the report.
- The `logs` folder is created in the folder you run Vitals from. Always start it from the same folder to keep all days in one place.


## Configuration

Copy `config.example.toml` to `config.toml` in the folder you run Vitals from and change what you need:

```toml
[alerts]
cpu_percent = 90.0
cpu_seconds = 10
ram_percent = 85.0
bell = true

[security]
trusted_processes = ["myserver.exe"]
```

| Section | Setting | Default | Meaning |
|---|---|---|---|
| `refresh` | `interval` | `1.0` | Seconds between updates |
| `refresh` | `process_interval` | `2.0` | Seconds between process list updates |
| `alerts` | `cpu_percent`, `cpu_seconds` | `90`, `10` | Alert when CPU stays above the limit this long |
| `alerts` | `ram_percent`, `ram_seconds` | `85`, `5` | Same for RAM |
| `alerts` | `disk_percent` | `90` | Alert when a disk is fuller than this |
| `alerts` | `new_listener`, `suspicious_process` | `true` | Security alerts |
| `alerts` | `bell` | `false` | Ring the terminal bell on new alerts |
| `alerts` | `banner_seconds` | `30` | How long one-time alerts stay on screen |
| `logging` | `enabled`, `directory` | `true`, `logs` | Where events and metrics are saved |
| `logging` | `record_interval` | `5` | Seconds between CSV rows |
| `logging` | `process_events` | `true` | Log processes starting and exiting |
| `network` | `resolve_hosts` | `true` | Look up host names of public IPs |
| `security` | `suspicious_ports` | `[4444, 1337, 31337, 6667]` | Ports treated as backdoors |
| `security` | `trusted_processes` | `[]` | Process names never flagged |

## Files Vitals creates

```
logs/
├── events-2026-10-27.log    # alerts, security and process events
├── metrics-2026-10-27.csv   # CPU, RAM, network and disk every 5 seconds
└── report-2026-10-27.html   # created by --report
exports/
└── snapshot-20261027-210512.json   # created with the e key
```

## Project structure

```
vitals/
├── __main__.py   # command-line options
├── app.py        # main loop, keyboard handling and actions
├── ui.py         # draws every tab with rich
├── monitor.py    # collects one snapshot per tick
├── stats.py      # CPU, memory, disk, network and process data from psutil
├── security.py   # port risk levels and suspicious process rules
├── alerts.py     # alert rules
├── history.py    # rolling history and sparklines
├── logger.py     # event log, CSV recorder and JSON export
├── report.py     # HTML report
├── resolver.py   # background reverse DNS lookups
├── keyboard.py   # non-blocking key input on Windows, macOS and Linux
└── config.py     # settings and defaults
```

## Built with

- [psutil](https://github.com/giampaolo/psutil): cross-platform system information
- [rich](https://github.com/Textualize/rich): terminal rendering

## Disclaimer

The security checks are simple rules meant to point at things worth a closer look. A flagged process is not proof of malware and an unflagged one is not proof of safety.

## License

This project is licensed under the [MIT License](LICENSE).
