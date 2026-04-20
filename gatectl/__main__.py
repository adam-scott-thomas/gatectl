"""Entry point: python -m gatectl [command] [args...]

Two modes:
  - No args: starts interactive REPL
  - With args: runs one-shot command and exits
"""

import argparse
import sys

from gatectl.client import GateClient
from gatectl.shell import GateShell


def oneshot(args):
    """Execute a single command and exit."""
    client = GateClient(args.server)
    cmd = args.command

    if cmd == "health":
        status, data = client.health()
        if status == 200:
            print(f"OK — {data.get('status', '?')}")
        else:
            print(f"FAILED (status {status})", file=sys.stderr)
            sys.exit(1)

    elif cmd == "filter":
        mode = float(args.args[0]) if args.args else 0.1
        status, data = client.filter(mode)
        if status == 200:
            for t in data.get("visible", []):
                print(f"VISIBLE    {t['name']:24s} {t.get('execution_class', '?')}")
            for t in data.get("suppressed", []):
                print(f"SUPPRESSED {t['name']:24s} {t.get('execution_class', '?')}")
        else:
            print(f"Error {status}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "validate":
        if len(args.args) < 1:
            print("Usage: gatectl validate <tool> [mode]", file=sys.stderr)
            sys.exit(1)
        tool = args.args[0]
        mode = float(args.args[1]) if len(args.args) > 1 else 0.1
        status, data = client.validate(tool, mode)
        if status == 200:
            print("ACCEPTED")
        elif status == 403:
            print(f"DENIED: {data.get('reason', 'suppressed')}")
            sys.exit(1)
        elif status == 404:
            print(f"NOT FOUND: {tool}")
            sys.exit(1)

    elif cmd == "tools":
        status, data = client.list_tools()
        if status == 200:
            for t in data.get("tools", []):
                print(f"{t['name']:24s} {t.get('execution_class', '?')}")
        else:
            print(f"Error {status}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Commands: health, filter, validate, tools", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="gatectl",
        description="Interactive Gate CLI — zero dependencies",
    )
    parser.add_argument(
        "--server", "-s",
        default="http://localhost:8090",
        help="Gate server URL (default: http://localhost:8090)",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="gatectl 0.1.0",
    )
    parser.add_argument("command", nargs="?", help="Command (omit for REPL)")
    parser.add_argument("args", nargs="*", help="Command arguments")

    args = parser.parse_args()

    if args.command:
        oneshot(args)
    elif not sys.stdin.isatty():
        # Pipe mode: read commands from stdin
        shell = GateShell(server_url=args.server)
        shell.use_rawinput = False
        shell.prompt = ""
        shell.intro = ""
        shell.cmdloop()
    else:
        shell = GateShell(server_url=args.server)
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            shell._save_history()
            print("\nBye.")


if __name__ == "__main__":
    sys.exit(main())
