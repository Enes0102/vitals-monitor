import platform
import time

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vitals.stats import (
    NetworkMeter,
    format_bytes,
    get_cpu,
    get_disks,
    get_memory,
    get_processes,
)


def usage_color(percent):
    if percent < 50:
        return "green"
    if percent < 80:
        return "yellow"
    return "red"


def bar(percent, width=20):
    filled = round(width * percent / 100)
    color = usage_color(percent)

    text = Text()
    text.append("█" * filled, style=color)
    text.append("░" * (width - filled), style="grey37")
    text.append(f" {percent:5.1f}%", style=f"bold {color}")
    return text


def header():
    text = Text()
    text.append(" VITALS ", style="bold black on cyan")
    text.append(f"  {platform.node()}", style="bold")
    text.append(f"  ·  {platform.system()} {platform.release()}", style="dim")
    text.append(f"  ·  {time.strftime('%H:%M:%S')}", style="dim")
    text.append("     Ctrl+C to quit", style="italic grey50")
    return text


def cpu_panel(cpu):
    lines = [Text.assemble(("Total  ", "bold"), bar(cpu["total"])), Text("")]

    for i, percent in enumerate(cpu["per_core"]):
        lines.append(Text.assemble((f"Core {i:<3}", "dim"), bar(percent, 10)))

    lines.append(Text(""))
    lines.append(Text(f"{cpu['cores']} logical cores", style="dim"))

    return Panel(Group(*lines), title="[bold cyan]CPU", border_style="cyan")


def memory_panel(mem):
    return Panel(
        Group(
            Text.assemble(("RAM  ", "bold"), bar(mem["percent"])),
            Text(f"     {format_bytes(mem['used'])} / {format_bytes(mem['total'])}", style="dim"),
        ),
        title="[bold magenta]Memory",
        border_style="magenta",
    )


def disk_panel(disks):
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_column(style="dim")

    for disk in disks:
        table.add_row(
            disk["name"],
            bar(disk["percent"], 15),
            f"{format_bytes(disk['used'])} / {format_bytes(disk['total'])}",
        )

    return Panel(table, title="[bold yellow]Disks", border_style="yellow")


def network_panel(net):
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column(justify="right")

    table.add_row("▲ Upload", Text(f"{format_bytes(net['upload'])}/s", style="green"))
    table.add_row("▼ Download", Text(f"{format_bytes(net['download'])}/s", style="cyan"))
    table.add_row("", "")
    table.add_row(Text("Total sent", style="dim"),
                  Text(format_bytes(net["total_sent"]), style="dim"))
    table.add_row(Text("Total received", style="dim"),
                  Text(format_bytes(net["total_received"]), style="dim"))

    return Panel(table, title="[bold green]Network", border_style="green")


def process_panel(processes):
    table = Table(expand=True, box=None, header_style="bold blue")
    table.add_column("PID", justify="right", style="dim", width=8)
    table.add_column("Name", ratio=1, no_wrap=True, overflow="ellipsis")
    table.add_column("CPU %", justify="right", width=8)
    table.add_column("MEM %", justify="right", width=8)

    for p in processes:
        table.add_row(
            str(p["pid"]),
            p["name"],
            Text(f"{p['cpu']:.1f}", style=usage_color(p["cpu"])),
            Text(f"{p['memory']:.1f}", style=usage_color(p["memory"])),
        )

    return Panel(table, title="[bold blue]Processes", border_style="blue")


def render(network, top):
    cpu = get_cpu()
    disks = get_disks()

    layout = Layout()
    layout.split_column(
        Layout(header(), size=1),
        Layout(name="top", size=cpu["cores"] + 6),
        Layout(name="middle", size=max(7, len(disks) + 2)),
        Layout(process_panel(get_processes(top))),
    )
    layout["top"].split_row(
        Layout(cpu_panel(cpu), ratio=3),
        Layout(memory_panel(get_memory()), ratio=2),
    )
    layout["middle"].split_row(
        Layout(disk_panel(disks), ratio=3),
        Layout(network_panel(network.read()), ratio=2),
    )
    return layout


def run(interval=1.0, top=20):
    console = Console()
    network = NetworkMeter()

    try:
        with Live(render(network, top), console=console, screen=True) as live:
            while True:
                time.sleep(interval)
                live.update(render(network, top))
    except KeyboardInterrupt:
        pass
