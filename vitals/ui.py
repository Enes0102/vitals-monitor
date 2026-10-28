import math
import time

from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vitals import __version__
from vitals.history import sparkline
from vitals.stats import format_bytes, format_duration

TABS = [
    ("overview", "Overview"),
    ("network", "Network"),
    ("security", "Security"),
    ("processes", "Processes"),
    ("log", "Log"),
]

SELECTED = "bold on grey27"

RISK_STYLES = {
    "suspicious": "bold red",
    "exposed": "yellow",
    "open": "dark_orange",
    "system": "grey62",
    "local": "green",
}

LEVEL_STYLES = {
    "ALERT": "bold red",
    "SEC": "bold red",
    "WARN": "yellow",
    "PROC": "grey62",
    "INFO": "green",
}

SCOPE_STYLES = {
    "public": "cyan",
    "private": "green",
    "loopback": "grey62",
}


def usage_color(percent):
    if percent < 50:
        return "green"
    if percent < 80:
        return "yellow"
    return "red"


def bar(percent, width=20):
    width = max(width, 3)
    percent = max(0.0, min(percent, 100.0))
    filled = round(width * percent / 100)
    color = usage_color(percent)

    text = Text()
    text.append("█" * filled, style=color)
    text.append("░" * (width - filled), style="grey37")
    text.append(f" {percent:5.1f}%", style=f"bold {color}")
    return text


RATE_FLOOR = 10 * 1024


def spark(values, width, style, maximum=None):
    return Text(sparkline(values, max(width, 1), maximum), style=style)


def rate_spark(values, width, style):
    return spark(values, width, style, max(values + [RATE_FLOOR]))


def rate(value):
    return f"{format_bytes(value)}/s"


def short(text, width):
    text = str(text)
    if width <= 1:
        return text[:max(width, 0)]
    return text if len(text) <= width else text[: width - 1] + "…"


def age(started):
    if not started:
        return "-"
    return format_duration(time.time() - started)


def header(app, snapshot, width):
    system = snapshot["system"]
    processes = snapshot["processes"]
    threads = sum(p["threads"] for p in processes)

    top = Text(no_wrap=True, overflow="ellipsis")
    top.append(f" VITALS {__version__} ", style="bold black on cyan")
    top.append(f"  {system['host']}", style="bold")
    top.append(f"  ·  {system['os']}", style="grey62")
    top.append(f"  ·  up {format_duration(system['uptime'])}", style="grey62")
    top.append(f"  ·  {len(processes)} procs · {threads:,} threads", style="grey62")

    right = Text(no_wrap=True)
    if app.paused:
        right.append(" PAUSED ", style="bold black on yellow")
        right.append(" ")
    right.append(time.strftime("%H:%M:%S"), style="grey62")

    tabs = Text(no_wrap=True, overflow="ellipsis")
    for index, (key, label) in enumerate(TABS, start=1):
        if key == app.tab:
            tabs.append(f" {index} {label} ", style="bold black on cyan")
        else:
            tabs.append(f" {index} {label} ", style="grey62")
        tabs.append(" ")

    extras = Text(no_wrap=True)
    battery = system["battery"]
    if battery:
        plug = " ⚡" if battery["plugged"] else ""
        extras.append(f"battery {battery['percent']:.0f}%{plug}", style=usage_color(100 - battery["percent"]))
    if system["temperature"]:
        if extras:
            extras.append("  ·  ", style="grey37")
        extras.append(f"CPU {system['temperature']:.0f}°C", style=usage_color(system["temperature"]))

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1, no_wrap=True)
    grid.add_column(justify="right", no_wrap=True)
    grid.add_row(top, right)
    grid.add_row(tabs, extras)
    return grid


def alert_banner(alerts, limit=3):
    lines = []
    for message, level in alerts[:limit]:
        style = "bold red" if level == "SEC" else "red"
        lines.append(Text(f"▲ {message}", style=style, no_wrap=True, overflow="ellipsis"))
    if len(alerts) > limit:
        lines.append(Text(f"  +{len(alerts) - limit} more · see the Log tab", style="grey62"))
    count = len(alerts)
    title = f"[bold red]{count} active alert{'s' if count != 1 else ''}"
    return Panel(Group(*lines), title=title, title_align="left", border_style="red")


def cpu_panel(snapshot, history, width):
    cpu = snapshot["cpu"]
    inner = width - 4
    columns = 2 if cpu["cores"] <= 16 else 4
    lines = [
        Text.assemble(("Total  ", "bold"), bar(cpu["total"], min(30, inner - 14))),
        Text.assemble(("60s    ", "grey50"), spark(history.get("cpu"), inner - 7, "cyan", 100),
                      no_wrap=True, overflow="crop"),
        Text(""),
    ]

    cell = max(inner // columns, 12)
    grid = Table.grid(padding=(0, 0))
    for _ in range(columns):
        grid.add_column(width=cell, no_wrap=True)
    cells = [
        Text.assemble((f"C{i:<3}", "grey50"), bar(value, max(cell - 12, 3)))
        for i, value in enumerate(cpu["per_core"])
    ]
    for start in range(0, len(cells), columns):
        row = cells[start:start + columns]
        row += [Text("")] * (columns - len(row))
        grid.add_row(*row)
    lines.append(grid)

    details = [f"{cpu['cores']} logical cores"]
    if cpu["freq"]:
        details.append(f"{cpu['freq'] / 1000:.2f} GHz")
    if snapshot["system"]["temperature"]:
        details.append(f"{snapshot['system']['temperature']:.0f}°C")
    return Panel(
        Group(*lines),
        title="[bold cyan]CPU",
        subtitle=f"[grey62]{' · '.join(details)}",
        border_style="cyan",
    )


def cpu_height(snapshot):
    cores = snapshot["cpu"]["cores"]
    columns = 2 if cores <= 16 else 4
    return math.ceil(cores / columns) + 5


def memory_panel(snapshot, history, width):
    memory = snapshot["memory"]
    inner = width - 4
    size = min(30, inner - 13)

    lines = [
        Text.assemble(("RAM   ", "bold"), bar(memory["percent"], size)),
        Text(
            f"      {format_bytes(memory['used'])} / {format_bytes(memory['total'])}"
            f" · {format_bytes(memory['available'])} free",
            style="grey62", no_wrap=True, overflow="ellipsis",
        ),
        Text.assemble(("60s   ", "grey50"), spark(history.get("ram"), inner - 6, "magenta", 100)),
    ]
    if memory["swap_total"]:
        lines += [
            Text.assemble(("Swap  ", "bold"), bar(memory["swap_percent"], size)),
            Text(f"      {format_bytes(memory['swap_used'])} / {format_bytes(memory['swap_total'])}",
                 style="grey62"),
        ]
    else:
        lines += [Text("Swap  not configured", style="grey50"), Text("")]

    top = max(snapshot["processes"], key=lambda p: p["rss"], default=None)
    if top:
        lines.append(Text.assemble(
            ("top   ", "grey50"),
            (short(top["name"], inner - 16), "bold"),
            (f"  {format_bytes(top['rss'])}", "magenta"),
        ))
    return Panel(Group(*lines), title="[bold magenta]Memory", border_style="magenta")


def disk_panel(snapshot, history, width):
    inner = width - 4
    disks = snapshot["disks"][:4]
    label = max([len(short(d["name"], 12)) for d in disks] + [4])
    room = inner - label - 1

    lines = []
    for disk in disks:
        size_text = f" {format_bytes(disk['used'])} / {format_bytes(disk['total'])}"
        show_size = room >= 40
        bar_width = min(24, room - 8 - (len(size_text) if show_size else 0))
        line = Text.assemble((f"{short(disk['name'], 12):<{label}} ", "bold"), bar(disk["percent"], bar_width))
        if show_size:
            line.append(size_text, style="grey62")
        lines.append(line)
    if not disks:
        lines.append(Text("No readable disks", style="grey50"))

    lines.append(Text(""))
    io = snapshot["disk_io"]
    if io["available"]:
        for key, title, style in (("read", "read ", "cyan"), ("write", "write", "yellow")):
            value = f"{rate(io[key]):>12}"
            lines.append(Text.assemble(
                (f"{title} ", "grey50"), (value, style), "  ",
                rate_spark(history.get(f"disk_{key}"), inner - 20, style),
                no_wrap=True, overflow="crop",
            ))
        top = max(snapshot["processes"], key=lambda p: p["io"], default=None)
        if top and top["io"] > 0:
            lines.append(Text.assemble(
                ("busiest  ", "grey50"), (short(top["name"], inner - 24), "bold"), (f"  {rate(top['io'])}", "yellow"),
            ))
        else:
            lines.append(Text("busiest  -", style="grey50"))
    else:
        lines.append(Text("Disk I/O counters unavailable", style="grey50"))
    return Panel(Group(*lines), title="[bold yellow]Disks", border_style="yellow")


def disk_height(snapshot):
    return min(len(snapshot["disks"]), 4) + 6


def network_panel(snapshot, history, width):
    inner = width - 4
    net = snapshot["network"]
    security = snapshot["security"]
    graph = inner - 24

    established = sum(1 for c in security["connections"] if c["status"] == "ESTABLISHED")
    lines = [
        Text.assemble(("▲ Up    ", "bold"), (f"{rate(net['upload']):>12}", "green"), "  ",
                      rate_spark(history.get("up"), graph, "green"), no_wrap=True, overflow="crop"),
        Text.assemble(("▼ Down  ", "bold"), (f"{rate(net['download']):>12}", "cyan"), "  ",
                      rate_spark(history.get("down"), graph, "cyan"), no_wrap=True, overflow="crop"),
        Text(""),
        Text.assemble((f"{short(net['interface']['name'], 16)}  ", "grey50"), (net["interface"]["ip"], "bold")),
    ]
    if security["available"]:
        lines.append(Text(
            f"{established} established · {len(security['listeners'])} listening",
            style="grey62",
        ))
    else:
        lines.append(Text("connections need admin rights", style="grey50"))
    lines.append(Text(
        f"sent {format_bytes(net['total_sent'])} · received {format_bytes(net['total_received'])}",
        style="grey62", no_wrap=True, overflow="ellipsis",
    ))
    return Panel(Group(*lines), title="[bold green]Network", border_style="green")


def process_rows(app):
    return app.rows("processes")


def window(app, tab, rows, capacity):
    capacity = max(capacity, 1)
    app.capacity[tab] = capacity
    selected = app.clamp(tab, len(rows))
    offset = app.offset.get(tab, 0)
    if selected < offset:
        offset = selected
    if selected >= offset + capacity:
        offset = selected - capacity + 1
    offset = max(0, min(offset, max(len(rows) - capacity, 0)))
    app.offset[tab] = offset
    return offset, rows[offset:offset + capacity], selected


def list_title(base, app, count, extra=""):
    parts = [f"[bold]{base}[/] [grey62]{count}"]
    if extra:
        parts.append(f"[grey62]{extra}")
    if app.filter:
        parts.append(f"[cyan]filter: {app.filter}")
    return " · ".join(parts)


def scroll_hint(offset, shown, total):
    if total <= shown:
        return ""
    return f"[grey62]{offset + 1}-{offset + shown} of {total}"


def process_table(app, tab, height, full):
    rows = app.rows(tab)
    offset, visible, selected = window(app, tab, rows, height - 3)

    table = Table(expand=True, box=None, header_style="bold blue", pad_edge=False)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("PID", justify="right", style="grey62", width=7, no_wrap=True)
    if full:
        table.add_column("PPID", justify="right", style="grey50", width=7, no_wrap=True)
    table.add_column("Name", ratio=2, no_wrap=True, overflow="ellipsis", min_width=10)
    table.add_column("User", ratio=1, style="grey62", no_wrap=True, overflow="ellipsis", min_width=4)
    if full:
        table.add_column("Thr", justify="right", width=4, no_wrap=True)
        table.add_column("Status", width=9, no_wrap=True, overflow="ellipsis")
    table.add_column("CPU%", justify="right", width=6, no_wrap=True)
    table.add_column("MEM%", justify="right", width=6, no_wrap=True)
    table.add_column("Memory", justify="right", width=9, no_wrap=True)
    if full:
        table.add_column("I/O", justify="right", width=11, no_wrap=True)
        table.add_column("Age", justify="right", width=9, no_wrap=True)

    flagged = {p["pid"] for p in app.snapshot["security"]["flagged"]}
    for index, proc in enumerate(visible, start=offset):
        is_selected = index == selected
        name_style = "bold red" if proc["pid"] in flagged else ""
        cells = [
            Text("›" if is_selected else " ", style="cyan"),
            str(proc["pid"]),
        ]
        if full:
            cells.append(str(proc["ppid"] or "-"))
        cells += [Text(proc["name"], style=name_style), proc["user"]]
        if full:
            cells += [str(proc["threads"]), proc["status"]]
        cells += [
            Text(f"{proc['cpu']:.1f}", style=usage_color(proc["cpu"] * 2)),
            Text(f"{proc['memory']:.1f}", style=usage_color(proc["memory"] * 4)),
            format_bytes(proc["rss"]),
        ]
        if full:
            cells += [rate(proc["io"]) if proc["io"] else "-", age(proc["started"])]
        table.add_row(*cells, style=SELECTED if is_selected else None)

    if not rows:
        table.add_row("", "", *([""] * (2 if full else 0)), Text("No matching processes", style="grey50"))

    sort = f"sort: {app.sort_label()}"
    return Panel(
        table,
        title=list_title("Processes", app, len(rows), sort),
        title_align="left",
        subtitle=scroll_hint(offset, len(visible), len(rows)),
        subtitle_align="right",
        border_style="blue",
    )


def overview(app, width, height):
    snapshot = app.snapshot
    history = app.history
    left = int(width * 0.58)
    right = width - left

    top = max(cpu_height(snapshot), 8)
    middle = max(disk_height(snapshot), 8)
    show_middle = height - top - middle >= 6
    show_top = height - top >= 6
    bottom = height - (top if show_top else 0) - (middle if show_middle else 0)

    rows = []
    if show_top:
        rows.append(Layout(name="top", size=top))
    if show_middle:
        rows.append(Layout(name="middle", size=middle))
    rows.append(Layout(process_table(app, "overview", bottom, False), name="bottom"))

    layout = Layout()
    layout.split_column(*rows)
    if show_top:
        layout["top"].split_row(
            Layout(cpu_panel(snapshot, history, left), size=left),
            Layout(memory_panel(snapshot, history, right)),
        )
    if show_middle:
        layout["middle"].split_row(
            Layout(disk_panel(snapshot, history, left), size=left),
            Layout(network_panel(snapshot, history, right)),
        )
    return layout


def traffic_panel(app, width):
    history = app.history
    net = app.snapshot["network"]
    graph = width - 4 - 26
    peak_up = max(history.get("up") or [0])
    peak_down = max(history.get("down") or [0])
    lines = [
        Text.assemble(("▲ Upload    ", "bold"), (f"{rate(net['upload']):>12}", "green"), "  ",
                      rate_spark(history.get("up"), graph, "green"), no_wrap=True, overflow="crop"),
        Text.assemble(("▼ Download  ", "bold"), (f"{rate(net['download']):>12}", "cyan"), "  ",
                      rate_spark(history.get("down"), graph, "cyan"), no_wrap=True, overflow="crop"),
        Text(
            f"peak (5 min)  up {rate(peak_up)} · down {rate(peak_down)}"
            f"   ·   {net['interface']['name']} {net['interface']['ip']}",
            style="grey62", no_wrap=True, overflow="ellipsis",
        ),
    ]
    return Panel(Group(*lines), title="[bold green]Traffic", title_align="left", border_style="green")


def connections_panel(app, height):
    security = app.snapshot["security"]
    tab = "network"
    if not security["available"]:
        message = Text(
            "Reading connections needs more permissions on this system.\n"
            "Run the terminal as administrator (Windows) or with sudo (macOS/Linux).",
            style="yellow",
        )
        return Panel(message, title="[bold green]Connections", title_align="left", border_style="green")

    rows = app.rows(tab)
    offset, visible, selected = window(app, tab, rows, height - 3)

    table = Table(expand=True, box=None, header_style="bold green", pad_edge=False)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("Process", ratio=2, no_wrap=True, overflow="ellipsis", min_width=8)
    table.add_column("PID", justify="right", style="grey62", width=7, no_wrap=True)
    table.add_column("Proto", width=5, no_wrap=True)
    table.add_column("Local", ratio=2, style="grey62", no_wrap=True, overflow="ellipsis", min_width=8)
    table.add_column("Remote", ratio=2, no_wrap=True, overflow="ellipsis", min_width=8)
    table.add_column("Host", ratio=3, style="grey62", no_wrap=True, overflow="ellipsis", min_width=6)
    table.add_column("State", width=12, no_wrap=True, overflow="ellipsis")

    for index, conn in enumerate(visible, start=offset):
        is_selected = index == selected
        host = app.resolve(conn["remote_ip"]) if conn["scope"] == "public" else conn["scope"]
        if host is None:
            host = "…"
        state_style = "green" if conn["status"] == "ESTABLISHED" else "grey62"
        table.add_row(
            Text("›" if is_selected else " ", style="cyan"),
            conn["name"],
            str(conn["pid"] or "-"),
            conn["proto"],
            f"{conn['local_ip']}:{conn['local_port']}",
            Text(f"{conn['remote_ip']}:{conn['remote_port']}", style=SCOPE_STYLES.get(conn["scope"], "")),
            host or "-",
            Text(conn["status"] if conn["status"] != "NONE" else "-", style=state_style),
            style=SELECTED if is_selected else None,
        )
    if not rows:
        table.add_row("", Text("No connections", style="grey50"))

    established = sum(1 for c in security["connections"] if c["status"] == "ESTABLISHED")
    return Panel(
        table,
        title=list_title("Connections", app, len(rows), f"{established} established"),
        title_align="left",
        subtitle=scroll_hint(offset, len(visible), len(rows)),
        subtitle_align="right",
        border_style="green",
    )


def network_view(app, width, height):
    layout = Layout()
    layout.split_column(
        Layout(traffic_panel(app, width), size=5),
        Layout(connections_panel(app, max(height - 5, 4))),
    )
    return layout


def flagged_panel(rows, selected, total):
    flagged = [row for row in rows if row["kind"] == "flagged"]
    if not flagged:
        body = Text("✓ No suspicious processes found", style="green")
        return Panel(body, title="[bold red]Suspicious processes", title_align="left", border_style="green")

    table = Table(expand=True, box=None, header_style="bold red", pad_edge=False)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("Process", ratio=1, no_wrap=True, overflow="ellipsis", min_width=10)
    table.add_column("PID", justify="right", width=7, style="grey62", no_wrap=True)
    table.add_column("Why", ratio=3, no_wrap=True, overflow="ellipsis")
    for index, row in enumerate(flagged):
        proc = row["item"]
        is_selected = index == selected
        table.add_row(
            Text("›" if is_selected else " ", style="cyan"),
            Text(proc["name"], style="bold red"),
            str(proc["pid"]),
            "; ".join(proc["reasons"]),
            style=SELECTED if is_selected else None,
        )
    extra = f"+{total - len(flagged)} more · use / to filter" if total > len(flagged) else ""
    return Panel(
        table,
        title=f"[bold red]Suspicious processes [grey62]{total}",
        title_align="left",
        subtitle=f"[grey62]{extra}" if extra else "",
        border_style="red",
    )


def listeners_panel(app, rows, selected, height, shift):
    listeners = [row for row in rows if row["kind"] == "listener"]
    capacity = max(height - 3, 1)
    local_selected = selected - shift
    offset = app.offset.get("security", 0)
    if 0 <= local_selected < offset:
        offset = local_selected
    if local_selected >= offset + capacity:
        offset = local_selected - capacity + 1
    offset = max(0, min(offset, max(len(listeners) - capacity, 0)))
    app.offset["security"] = offset
    app.capacity["security"] = capacity

    table = Table(expand=True, box=None, header_style="bold yellow", pad_edge=False)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("Risk", width=10, no_wrap=True)
    table.add_column("Process", ratio=2, no_wrap=True, overflow="ellipsis", min_width=8)
    table.add_column("PID", justify="right", width=7, style="grey62", no_wrap=True)
    table.add_column("Address", ratio=2, no_wrap=True, overflow="ellipsis", min_width=10)
    table.add_column("Service", ratio=2, style="grey62", no_wrap=True, overflow="ellipsis", min_width=6)

    visible = listeners[offset:offset + capacity]
    for index, row in enumerate(visible, start=offset):
        item = row["item"]
        is_selected = index == local_selected
        table.add_row(
            Text("›" if is_selected else " ", style="cyan"),
            Text(item["risk"], style=RISK_STYLES[item["risk"]]),
            item["name"],
            str(item["pid"] or "-"),
            f"{item['ip']}:{item['port']}",
            item["service"] or "-",
            style=SELECTED if is_selected else None,
        )
    if not listeners:
        table.add_row("", "", Text("No listening ports", style="grey50"))

    counts = {}
    for row in listeners:
        counts[row["item"]["risk"]] = counts.get(row["item"]["risk"], 0) + 1
    summary = " ".join(
        f"[{RISK_STYLES[risk]}]{counts[risk]} {risk}[/]"
        for risk in ("suspicious", "exposed", "open", "system", "local")
        if counts.get(risk)
    )
    title = f"[bold yellow]Listening ports [grey62]{len(listeners)}"
    if app.filter:
        title += f" · [cyan]filter: {app.filter}"
    return Panel(
        table,
        title=title,
        title_align="left",
        subtitle=summary,
        subtitle_align="right",
        border_style="yellow",
    )


def security_view(app, width, height):
    security = app.snapshot["security"]
    if not security["available"]:
        message = Text(
            "Listening ports and connections need more permissions on this system.\n"
            "Run the terminal as administrator (Windows) or with sudo (macOS/Linux).",
            style="yellow",
        )
        return Panel(message, title="[bold red]Security", border_style="red")

    rows = app.rows("security")
    selected = app.clamp("security", len(rows))
    flagged_count = sum(1 for row in rows if row["kind"] == "flagged")
    total_flagged = len(security["flagged"])
    top = flagged_count + 3 if flagged_count else 3

    legend = Text.assemble(
        (" suspicious", RISK_STYLES["suspicious"]), (" flagged/backdoor  ·  ", "grey50"),
        ("exposed", RISK_STYLES["exposed"]), (" database or remote access  ·  ", "grey50"),
        ("open", RISK_STYLES["open"]), (" reachable from network  ·  ", "grey50"),
        ("local", RISK_STYLES["local"]), (" this PC only", "grey50"),
        no_wrap=True, overflow="ellipsis",
    )

    layout = Layout()
    layout.split_column(
        Layout(flagged_panel(rows, selected, total_flagged), size=top),
        Layout(listeners_panel(app, rows, selected, max(height - top - 1, 4), flagged_count)),
        Layout(legend, size=1),
    )
    return layout


def log_view(app, width, height):
    rows = app.rows("log")
    offset, visible, selected = window(app, "log", rows, height - 3)

    table = Table(expand=True, box=None, header_style="bold", pad_edge=False)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("Time", width=8, style="grey62", no_wrap=True)
    table.add_column("Level", width=6, no_wrap=True)
    table.add_column("Event", ratio=1, no_wrap=True, overflow="ellipsis")
    for index, (stamp, level, message) in enumerate(visible, start=offset):
        is_selected = index == selected
        style = LEVEL_STYLES.get(level, "")
        table.add_row(
            Text("›" if is_selected else " ", style="cyan"),
            stamp,
            Text(level, style=style),
            Text(message, style=style if level in ("ALERT", "SEC") else ""),
            style=SELECTED if is_selected else None,
        )
    if not rows:
        table.add_row("", "", "", Text("No events yet", style="grey50"))

    directory = app.monitor.log_directory
    saved = f"saved to {directory}" if directory else "not saved to disk"
    return Panel(
        table,
        title=list_title("Events", app, len(rows), "newest first · " + saved),
        title_align="left",
        subtitle=scroll_hint(offset, len(visible), len(rows)),
        subtitle_align="right",
        border_style="white",
    )


def detail_row(table, label, value, style=""):
    table.add_row(Text(label, style="grey62"), Text(str(value), style=style))


def details_view(app, width, height):
    pid = app.detail_pid
    info = app.details
    proc = next((p for p in app.snapshot["processes"] if p["pid"] == pid), None)
    security = app.snapshot["security"]
    flagged = next((p for p in security["flagged"] if p["pid"] == pid), None)

    if info is None:
        body = Text(f"Process {pid} is no longer running.", style="yellow")
        return Panel(body, title=f"[bold]PID {pid}", border_style="grey50")

    table = Table.grid(padding=(0, 2))
    table.add_column(width=12, no_wrap=True)
    table.add_column(ratio=1, overflow="fold")
    path_style = "bold red" if flagged else "bold"
    detail_row(table, "path", info["exe"] or "access denied", path_style)
    detail_row(table, "command", info["cmdline"])
    detail_row(table, "folder", info["cwd"])
    detail_row(table, "parent", info["parent"])
    detail_row(table, "user", info["user"])
    if isinstance(info["started"], float):
        started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info["started"]))
        detail_row(table, "started", f"{started} · running {age(info['started'])}")
    if proc:
        detail_row(
            table, "usage",
            f"CPU {proc['cpu']:.1f}% · RAM {proc['memory']:.1f}% ({format_bytes(proc['rss'])})"
            f" · {proc['threads']} threads · I/O {rate(proc['io'])}",
        )
    detail_row(
        table, "resources",
        f"{info['open_files']} open files · {info['connections']} connections · {info['children']} child processes",
    )
    sha = app.hashes.get(info["exe"])
    if sha == "":
        detail_row(table, "sha256", "calculating…", "grey62")
    elif sha:
        detail_row(table, "sha256", sha, "cyan")
    else:
        detail_row(table, "sha256", "press h to calculate", "grey50")

    parts = [table]
    listeners = [item for item in security["listeners"] if item["pid"] == pid]
    connections = [item for item in security["connections"] if item["pid"] == pid]
    if listeners or connections:
        net = Table(expand=True, box=None, header_style="bold green", pad_edge=False)
        net.add_column("Type", width=9)
        net.add_column("Address", ratio=1, no_wrap=True, overflow="ellipsis")
        net.add_column("Info", ratio=1, no_wrap=True, overflow="ellipsis", style="grey62")
        for item in listeners[:6]:
            net.add_row(
                Text("listen", style=RISK_STYLES[item["risk"]]),
                f"{item['ip']}:{item['port']}",
                f"{item['risk']} · {item['service'] or 'unknown service'}",
            )
        room = max(height - 20 - len(listeners[:6]), 2)
        for item in connections[:room]:
            host = app.resolve(item["remote_ip"]) if item["scope"] == "public" else item["scope"]
            net.add_row(
                Text(item["proto"].lower(), style="green"),
                f"{item['remote_ip']}:{item['remote_port']}",
                f"{item['status']} · {host or '…'}",
            )
        parts += [Text(""), net]

    if flagged:
        parts += [Text(""), Text("Why flagged:", style="bold red")]
        parts += [Text(f"  • {reason}", style="red") for reason in flagged["reasons"]]

    title = f"[bold]{info['name']}[/] [grey62]· PID {pid}"
    border = "red" if flagged else "cyan"
    actions = "[grey62]k kill · o open folder · c copy path · h hash · v VirusTotal · esc back"
    return Panel(Group(*parts), title=title, title_align="left", subtitle=actions,
                 subtitle_align="left", border_style=border)


HELP = [
    ("Navigation", [
        ("1-5, tab, ←/→", "switch tabs"),
        ("↑/↓", "move selection"),
        ("PgUp/PgDn, Home/End", "jump"),
        ("enter", "process details"),
        ("esc", "back / clear filter"),
    ]),
    ("Processes", [
        ("/", "search by name, PID, user, IP or host"),
        ("s", "change sort column"),
        ("r", "reverse sort order"),
        ("k", "kill selected process (asks first)"),
    ]),
    ("Details view", [
        ("o", "open the program's folder"),
        ("c", "copy the program path"),
        ("h", "calculate the SHA-256 hash"),
        ("v", "look the hash up on VirusTotal"),
    ]),
    ("General", [
        ("p", "pause / resume updates"),
        ("e", "export a JSON snapshot"),
        ("?", "show / hide this help"),
        ("q, ctrl+c", "quit"),
    ]),
]


def help_view(app, width, height):
    columns = Table.grid(padding=(0, 4), expand=True)
    columns.add_column(ratio=1)
    columns.add_column(ratio=1)
    blocks = []
    for title, items in HELP:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(style="")
        table.add_row(Text(title, style="bold"), "")
        for key, description in items:
            table.add_row(key, description)
        blocks.append(table)
    columns.add_row(blocks[0], blocks[1])
    columns.add_row(Text(""), Text(""))
    columns.add_row(blocks[2], blocks[3])

    notes = Text.assemble(
        ("\nSettings are read from ", "grey50"), ("config.toml", "cyan"),
        (" in the current folder. Logs and CSV metrics go to ", "grey50"),
        (str(app.monitor.log_directory or "nowhere (logging is off)"), "cyan"), (".", "grey50"),
    )
    return Panel(Group(columns, notes), title="[bold]Keyboard shortcuts", border_style="cyan", padding=(1, 2))


def footer(app):
    text = Text(no_wrap=True, overflow="ellipsis")
    if app.search_mode:
        text.append(" / ", style="bold black on cyan")
        text.append(f" {app.search_buffer}")
        text.append("█", style="cyan")
        text.append("   enter apply · esc cancel", style="grey50")
        return text
    if app.confirm:
        pid, name = app.confirm
        text.append(" KILL ", style="bold white on red")
        text.append(f" End {name} (PID {pid})? ", style="bold")
        text.append("y", style="bold red")
        text.append(" yes · any other key cancels", style="grey50")
        return text
    if app.message and time.time() < app.message[2]:
        message, style, _ = app.message
        text.append(f" {message}", style=style)
        return text

    hints = [("?", "help"), ("/", "search"), ("s", "sort"), ("enter", "details"), ("k", "kill"),
             ("p", "pause"), ("e", "export"), ("q", "quit")]
    for key, label in hints:
        text.append(f" {key}", style="bold cyan")
        text.append(f" {label} ", style="grey62")
    return text


def render(app, width, height):
    alerts = app.monitor.alert_items
    banner = min(len(alerts), 3) + (1 if len(alerts) > 3 else 0) + 2 if alerts else 0
    body = max(height - 3 - banner, 6)

    if app.show_help:
        content = help_view(app, width, body)
    elif app.detail_pid is not None:
        content = details_view(app, width, body)
    elif app.tab == "overview":
        content = overview(app, width, body)
    elif app.tab == "network":
        content = network_view(app, width, body)
    elif app.tab == "security":
        content = security_view(app, width, body)
    elif app.tab == "processes":
        content = Layout(process_table(app, "processes", body, True))
    else:
        content = log_view(app, width, body)

    parts = [Layout(header(app, app.snapshot, width), size=2)]
    if banner:
        parts.append(Layout(alert_banner(alerts), size=banner))
    parts += [Layout(content), Layout(footer(app), size=1)]

    root = Layout()
    root.split_column(*parts)
    return root
