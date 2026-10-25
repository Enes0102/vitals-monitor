import argparse

from vitals.ui import run


def main():
    parser = argparse.ArgumentParser(
        prog="vitals",
        description="A lightweight terminal system monitor.",
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=1.0,
        help="refresh interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "-n", "--top", type=int, default=20,
        help="number of processes to show (default: 20)",
    )
    args = parser.parse_args()

    run(interval=max(args.interval, 0.25), top=args.top)


if __name__ == "__main__":
    main()
