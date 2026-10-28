import argparse
import sys
import webbrowser

from vitals import __version__
from vitals.config import load_config


def parse_args():
    parser = argparse.ArgumentParser(
        prog="vitals",
        description="A terminal system monitor with network, security and alert panels.",
    )
    parser.add_argument(
        "-i", "--interval", type=float,
        help="refresh interval in seconds (default: 1.0 or the value in config.toml)",
    )
    parser.add_argument(
        "-c", "--config", metavar="PATH",
        help="settings file to use (default: config.toml in the current folder)",
    )
    parser.add_argument(
        "--no-log", action="store_true",
        help="don't write events and metrics to disk",
    )
    parser.add_argument(
        "--report", nargs="?", const="today", metavar="DATE",
        help="build an HTML report from recorded data (DATE as YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="with --report, don't open the report in the browser",
    )
    parser.add_argument(
        "--version", action="version", version=f"vitals {__version__}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as error:
        print(f"vitals: {error}", file=sys.stderr)
        return 2

    if args.interval is not None:
        config["refresh"]["interval"] = args.interval
    config["refresh"]["interval"] = max(float(config["refresh"]["interval"]), 0.25)
    if args.no_log:
        config["logging"]["enabled"] = False

    if args.report:
        from vitals.report import build_report

        date = None if args.report == "today" else args.report
        try:
            path = build_report(config["logging"]["directory"], date)
        except (FileNotFoundError, ValueError) as error:
            print(f"vitals: {error}", file=sys.stderr)
            return 1
        print(f"Report saved to {path}")
        if not args.no_open:
            webbrowser.open(path.resolve().as_uri())
        return 0

    from vitals.app import run

    return run(config)


if __name__ == "__main__":
    sys.exit(main())
