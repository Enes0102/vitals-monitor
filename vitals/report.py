import csv
import html
import time
from datetime import datetime
from pathlib import Path

from vitals import __version__
from vitals.stats import format_bytes

CHARTS = [
    ("CPU usage", [("cpu", "CPU", "#22d3ee")], "percent"),
    ("Memory usage", [("ram", "RAM", "#e879f9"), ("swap", "Swap", "#a78bfa")], "percent"),
    ("Network", [("download", "Download", "#38bdf8"), ("upload", "Upload", "#4ade80")], "rate"),
    ("Disk I/O", [("disk_read", "Read", "#facc15"), ("disk_write", "Write", "#fb923c")], "rate"),
]

LEVEL_COLORS = {
    "ALERT": "#f87171",
    "SEC": "#f87171",
    "WARN": "#facc15",
    "PROC": "#94a3b8",
    "INFO": "#4ade80",
}


def load_metrics(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                parsed = {"time": datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")}
                for key, value in row.items():
                    if key != "time":
                        parsed[key] = float(value)
            except (KeyError, ValueError):
                continue
            rows.append(parsed)
    return rows


def load_events(path):
    events = []
    if not path.exists():
        return events
    with open(path, encoding="utf-8") as file:
        for line in file:
            parts = line.rstrip("\n").split(None, 3)
            if len(parts) == 4:
                events.append((parts[1], parts[2], parts[3]))
    return events


def format_value(value, kind):
    if kind == "percent":
        return f"{value:.0f}%"
    return f"{format_bytes(value)}/s"


def downsample(rows, limit=450):
    if len(rows) <= limit:
        return rows
    size = len(rows) / limit
    result = []
    for index in range(limit):
        bucket = rows[int(index * size):int((index + 1) * size)] or [rows[-1]]
        merged = {"time": bucket[len(bucket) // 2]["time"]}
        for key in bucket[0]:
            if key != "time":
                merged[key] = sum(row[key] for row in bucket) / len(bucket)
        result.append(merged)
    return result


def chart(rows, series, kind, width=900, height=220):
    left, right, top, bottom = 84, 16, 16, 28
    rows = downsample(rows)
    plot_w = width - left - right
    plot_h = height - top - bottom
    start = rows[0]["time"].timestamp()
    end = rows[-1]["time"].timestamp()
    span = max(end - start, 1)

    if kind == "percent":
        peak = 100.0
    else:
        peak = max(max(row[key] for row in rows) for key, _, _ in series) or 1.0

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" preserveAspectRatio="none">']
    for step in range(5):
        y = top + plot_h * step / 4
        value = peak * (1 - step / 4)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.1f}" class="axis" text-anchor="end">'
                     f'{html.escape(format_value(value, kind))}</text>')
    for step in range(5):
        x = left + plot_w * step / 4
        moment = time.strftime("%H:%M", time.localtime(start + span * step / 4))
        parts.append(f'<text x="{x:.1f}" y="{height - 8}" class="axis" text-anchor="middle">{moment}</text>')

    for key, _, color in series:
        points = []
        for row in rows:
            x = left + (row["time"].timestamp() - start) / span * plot_w
            y = top + plot_h - min(row[key] / peak, 1.0) * plot_h
            points.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
                     f'stroke-width="1.6" stroke-linejoin="round"/>')
    parts.append("</svg>")
    return "".join(parts)


def summary_cards(rows):
    def stat(key):
        values = [row[key] for row in rows]
        return sum(values) / len(values), max(values)

    cpu_avg, cpu_max = stat("cpu")
    ram_avg, ram_max = stat("ram")
    down_avg, down_max = stat("download")
    up_avg, up_max = stat("upload")
    first, last = rows[0]["time"], rows[-1]["time"]
    duration = last - first
    hours, remainder = divmod(int(duration.total_seconds()), 3600)

    cards = [
        ("Recorded", f"{hours}h {remainder // 60}m", f"{first:%H:%M} – {last:%H:%M} · {len(rows)} samples"),
        ("CPU", f"{cpu_avg:.0f}% avg", f"peak {cpu_max:.0f}%"),
        ("Memory", f"{ram_avg:.0f}% avg", f"peak {ram_max:.0f}%"),
        ("Download", f"{format_bytes(down_avg)}/s avg", f"peak {format_bytes(down_max)}/s"),
        ("Upload", f"{format_bytes(up_avg)}/s avg", f"peak {format_bytes(up_max)}/s"),
    ]
    return "".join(
        f'<div class="card"><div class="label">{label}</div><div class="value">{html.escape(value)}</div>'
        f'<div class="note">{html.escape(note)}</div></div>'
        for label, value, note in cards
    )


def peak_moments(rows, limit=5, gap_minutes=10):
    busiest = []
    for row in sorted(rows, key=lambda row: row["cpu"], reverse=True):
        if all(abs((row["time"] - other["time"]).total_seconds()) >= gap_minutes * 60 for other in busiest):
            busiest.append(row)
        if len(busiest) == limit:
            break
    items = "".join(
        f"<li><b>{row['time']:%H:%M:%S}</b> CPU {row['cpu']:.0f}% · RAM {row['ram']:.0f}% · "
        f"down {html.escape(format_bytes(row['download']))}/s</li>"
        for row in sorted(busiest, key=lambda row: row["time"])
    )
    return f"<ul class='peaks'>{items}</ul>"


def events_table(events):
    important = [event for event in events if event[1] in ("ALERT", "SEC", "WARN")]
    if not important:
        return "<p class='muted'>No alerts or security events were recorded on this day.</p>"
    rows = "".join(
        f"<tr><td>{html.escape(stamp)}</td>"
        f"<td style='color:{LEVEL_COLORS.get(level, '#e2e8f0')}'>{html.escape(level)}</td>"
        f"<td>{html.escape(message)}</td></tr>"
        for stamp, level, message in important[-200:]
    )
    return f"<table><thead><tr><th>Time</th><th>Level</th><th>Event</th></tr></thead><tbody>{rows}</tbody></table>"


STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0b1120; color: #e2e8f0;
       font: 15px/1.6 ui-monospace, "Cascadia Code", Consolas, monospace; }
main { max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h1 span { background: #22d3ee; color: #0b1120; padding: 0 8px; margin-right: 8px; }
h2 { font-size: 16px; margin: 32px 0 12px; color: #94a3b8; font-weight: 500; }
.muted { color: #64748b; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-top: 24px; }
.card { border: 1px solid #1e293b; border-radius: 8px; padding: 12px 14px; background: #0f172a; }
.label { color: #64748b; font-size: 12px; }
.value { font-size: 18px; margin: 2px 0; }
.note { color: #94a3b8; font-size: 12px; }
.chart { border: 1px solid #1e293b; border-radius: 8px; padding: 12px; background: #0f172a; margin-bottom: 16px; }
.chart h3 { margin: 0 0 6px; font-size: 14px; font-weight: 500; }
.legend span { margin-right: 16px; font-size: 12px; }
.legend i { display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 2px; }
svg { width: 100%; height: 220px; display: block; }
.grid { stroke: #1e293b; stroke-width: 1; }
.axis { fill: #64748b; font-size: 11px; font-family: inherit; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #1e293b; vertical-align: top; }
th { color: #64748b; font-weight: 500; }
.peaks { margin: 0; padding-left: 20px; color: #cbd5e1; }
footer { margin-top: 40px; color: #475569; font-size: 12px; }
"""


def build_report(directory="logs", date=None, output=None):
    folder = Path(directory)
    day = date or time.strftime("%Y-%m-%d")
    metrics_path = folder / f"metrics-{day}.csv"
    if not metrics_path.exists():
        available = sorted(path.stem.removeprefix("metrics-") for path in folder.glob("metrics-*.csv"))
        hint = f" Available days: {', '.join(available)}" if available else " Run Vitals for a while first."
        raise FileNotFoundError(f"No recorded data for {day} in {folder}.{hint}")

    rows = load_metrics(metrics_path)
    if len(rows) < 2:
        raise ValueError(f"Not enough samples in {metrics_path} yet. Let Vitals run a little longer.")
    events = load_events(folder / f"events-{day}.log")

    charts = []
    for title, series, kind in CHARTS:
        legend = "".join(f'<span><i style="background:{color}"></i>{name}</span>' for _, name, color in series)
        charts.append(
            f'<div class="chart"><h3>{title}</h3><div class="legend">{legend}</div>'
            f"{chart(rows, series, kind)}</div>"
        )

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vitals report · {day}</title>
<style>{STYLE}</style>
</head>
<body>
<main>
<h1><span>VITALS</span>Daily report</h1>
<div class="muted">{day} · generated {time.strftime("%Y-%m-%d %H:%M")}</div>
<div class="cards">{summary_cards(rows)}</div>
<h2>Over the day</h2>
{"".join(charts)}
<h2>Busiest moments</h2>
{peak_moments(rows)}
<h2>Alerts and security events</h2>
{events_table(events)}
<footer>Vitals {__version__} · data from {html.escape(str(metrics_path))}</footer>
</main>
</body>
</html>
"""
    target = Path(output) if output else folder / f"report-{day}.html"
    target.write_text(page, encoding="utf-8")
    return target
