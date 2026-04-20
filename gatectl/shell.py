"""Interactive REPL shell for Gate — the core of gatectl.

Uses stdlib cmd.Cmd for readline support, history, tab completion.
Maintains session state: current mode, last envelope, connection status.
"""

import cmd
import json
import os
import shlex
import sys
import time

from gatectl.client import GateClient

HISTORY_FILE = os.path.expanduser("~/.gatectl_history")


EXEC_CLASSES = ["read_only", "advisory", "external_action", "state_mutation", "high_impact"]


def _zone(mode: float) -> str:
    if mode <= 0.35:
        return "normal"
    if mode <= 0.65:
        return "elevated"
    return "crisis"


def _fmt_tool(tool: dict, suppressed: bool = False) -> str:
    name = tool.get("name", "?")
    cls = tool.get("execution_class", "?")
    marker = " [SUPPRESSED]" if suppressed else ""
    return f"  {name:24s} {cls}{marker}"


class GateShell(cmd.Cmd):
    """Interactive Gate shell with session state."""

    intro = (
        "gatectl v0.1.0 — interactive Gate shell\n"
        "Type 'help' for commands, 'quit' to exit.\n"
    )
    prompt = "gatectl> "

    def __init__(self, server_url: str = "http://localhost:8090"):
        super().__init__()
        self.client = GateClient(server_url)
        self.mode = 0.1
        self.last_envelope = None
        self._watching = False
        self._update_prompt()
        self._load_history()

    def _update_prompt(self):
        zone = _zone(self.mode)
        self.prompt = f"gatectl [{self.mode:.2f} {zone}]> "

    def _print_json(self, data: dict):
        print(json.dumps(data, indent=2))

    # --- Connection ---

    def do_health(self, arg):
        """Check gate-server health."""
        status, data = self.client.health()
        if status == 200:
            print(f"OK — {data.get('status', '?')}")
        else:
            print(f"FAILED (status {status})")
            self._print_json(data)

    def do_server(self, arg):
        """Show or change the gate-server URL. Usage: server [URL]"""
        if arg.strip():
            self.client = GateClient(arg.strip())
            print(f"Server URL: {self.client.base_url}")
        else:
            print(f"Server URL: {self.client.base_url}")

    # --- Mode ---

    def do_mode(self, arg):
        """Get or set the current mode signal. Usage: mode [0.0-1.0]"""
        if not arg.strip():
            zone = _zone(self.mode)
            print(f"Mode: {self.mode:.2f} ({zone})")
            return
        try:
            m = float(arg.strip())
            self.mode = max(0.0, min(1.0, m))
            self._update_prompt()
            zone = _zone(self.mode)
            print(f"Mode set to {self.mode:.2f} ({zone})")
        except ValueError:
            print("Usage: mode <float 0.0-1.0>")

    # --- Tools ---

    def do_register(self, arg):
        """Register a tool. Usage: register <name> <execution_class>"""
        parts = shlex.split(arg) if arg else []
        if len(parts) < 2:
            print("Usage: register <name> <execution_class>")
            print(f"  Classes: {', '.join(EXEC_CLASSES)}")
            return
        name, cls = parts[0], parts[1]
        if cls not in EXEC_CLASSES:
            print(f"Unknown class '{cls}'. Valid: {', '.join(EXEC_CLASSES)}")
            return
        status, data = self.client.register_tools([{"name": name, "execution_class": cls}])
        if status == 200:
            print(f"Registered: {name} ({cls})")
        else:
            print(f"Failed (status {status})")
            self._print_json(data)

    def complete_register(self, text, line, begidx, endidx):
        # Complete execution class (second arg)
        parts = line.split()
        if len(parts) >= 3 or (len(parts) == 2 and not text):
            return [c for c in EXEC_CLASSES if c.startswith(text)]
        return []

    def do_tools(self, arg):
        """List registered tools."""
        status, data = self.client.list_tools()
        if status == 200:
            tools = data.get("tools", [])
            if not tools:
                print("No tools registered.")
                return
            print(f"{'NAME':24s} CLASS")
            print("-" * 44)
            for t in tools:
                print(f"  {t.get('name', '?'):24s} {t.get('execution_class', '?')}")
            print(f"\n{len(tools)} tool(s)")
        else:
            print(f"Failed (status {status})")
            self._print_json(data)

    def do_demo(self, arg):
        """Load 5 demo tools (read_file, analyze, send_email, write_db, deploy)."""
        tools = [
            {"name": "read_file", "execution_class": "read_only"},
            {"name": "analyze", "execution_class": "advisory"},
            {"name": "send_email", "execution_class": "external_action"},
            {"name": "write_db", "execution_class": "state_mutation"},
            {"name": "deploy", "execution_class": "high_impact"},
        ]
        status, data = self.client.register_tools(tools)
        if status == 200:
            print(f"Registered {data.get('registered', '?')} demo tools.")
        else:
            print(f"Failed (status {status})")

    # --- Filter ---

    def do_filter(self, arg):
        """Filter tools at current mode. Usage: filter [mode]"""
        mode = self.mode
        if arg.strip():
            try:
                mode = float(arg.strip())
            except ValueError:
                print("Usage: filter [mode]")
                return

        status, data = self.client.filter(mode)
        if status != 200:
            print(f"Failed (status {status})")
            self._print_json(data)
            return

        visible = data.get("visible", [])
        suppressed = data.get("suppressed", [])
        zone = data.get("mode_zone", _zone(mode))

        print(f"Mode: {mode:.2f} ({zone})")
        print(f"\nVISIBLE ({len(visible)}):")
        for t in visible:
            print(_fmt_tool(t))
        if suppressed:
            print(f"\nSUPPRESSED ({len(suppressed)}):")
            for t in suppressed:
                print(_fmt_tool(t, suppressed=True))

    # --- Validate ---

    def do_validate(self, arg):
        """Validate a tool at current mode. Usage: validate <tool_name> [mode]"""
        parts = shlex.split(arg) if arg else []
        if not parts:
            print("Usage: validate <tool_name> [mode]")
            return
        tool_name = parts[0]
        mode = float(parts[1]) if len(parts) > 1 else self.mode

        status, data = self.client.validate(tool_name, mode)
        if status == 200:
            print(f"ACCEPTED — {tool_name} allowed at mode {mode:.2f}")
        elif status == 403:
            print(f"DENIED — {data.get('reason', 'suppressed')}")
        elif status == 404:
            print(f"NOT FOUND — {tool_name} is not registered")
        else:
            print(f"Error (status {status})")
            self._print_json(data)

    # --- Envelope ---

    def do_envelope(self, arg):
        """Build an authorization envelope. Usage: envelope <tool_name> [context_id]"""
        parts = shlex.split(arg) if arg else []
        if not parts:
            print("Usage: envelope <tool_name> [context_id]")
            return
        tool_name = parts[0]
        context_id = parts[1] if len(parts) > 1 else "gatectl-session"

        status, data = self.client.build_envelope(tool_name, context_id, self.mode)
        if status == 200:
            self.last_envelope = data
            print(f"Envelope built for {tool_name} at mode {self.mode:.2f}")
            print(f"  execution_mode: {data.get('execution_mode')}")
            print(f"  max_tool_calls: {data.get('max_tool_calls')}")
            print(f"  branching:      {data.get('branching')}")
            print("Use 'verify' to check signature, 'tamper' to test tamper detection.")
        else:
            print(f"Failed (status {status})")
            self._print_json(data)

    def do_verify(self, arg):
        """Verify the last built envelope."""
        if not self.last_envelope:
            print("No envelope to verify. Use 'envelope <tool>' first.")
            return
        status, data = self.client.verify_envelope(self.last_envelope)
        if status == 200:
            if data.get("valid"):
                print("VALID — signature verified")
            else:
                print(f"INVALID — {data.get('reason', 'verification failed')}")
        else:
            print(f"Error (status {status})")

    def do_tamper(self, arg):
        """Tamper with the last envelope and verify (should fail)."""
        if not self.last_envelope:
            print("No envelope to tamper. Use 'envelope <tool>' first.")
            return
        tampered = {**self.last_envelope, "max_tool_calls": 9999}
        status, data = self.client.verify_envelope(tampered)
        if status == 200:
            if not data.get("valid"):
                print("TAMPER DETECTED — signature mismatch (max_tool_calls changed to 9999)")
            else:
                print("WARNING — tampered envelope was accepted!")
        else:
            print(f"Error (status {status})")

    # --- Thresholds ---

    def do_thresholds(self, arg):
        """Set thresholds. Usage: thresholds <class> <value> [class value ...]"""
        parts = shlex.split(arg) if arg else []
        if len(parts) < 2 or len(parts) % 2 != 0:
            print("Usage: thresholds <class> <value> [class value ...]")
            print(f"  Classes: {', '.join(EXEC_CLASSES)}")
            return
        overrides = {}
        for i in range(0, len(parts), 2):
            cls, val = parts[i], parts[i + 1]
            try:
                overrides[cls] = float(val)
            except ValueError:
                print(f"Invalid threshold value: {val}")
                return

        status, data = self.client.set_thresholds(overrides)
        if status == 200:
            print("Thresholds updated:")
            for k, v in overrides.items():
                print(f"  {k}: {v}")
        else:
            print(f"Failed (status {status})")

    def complete_thresholds(self, text, line, begidx, endidx):
        parts = line.split()
        if len(parts) % 2 == 0 or (len(parts) % 2 == 1 and not text):
            return [c for c in EXEC_CLASSES if c.startswith(text)]
        return []

    # --- JSON dump ---

    def do_json(self, arg):
        """Dump last envelope as JSON."""
        if self.last_envelope:
            self._print_json(self.last_envelope)
        else:
            print("No envelope stored.")

    # --- Watch Mode ---

    def do_watch(self, arg):
        """Auto-filter every N seconds. Usage: watch [interval_secs] (default: 2, 0 to stop)"""
        interval = 2.0
        if arg.strip():
            try:
                interval = float(arg.strip())
            except ValueError:
                print("Usage: watch [interval_secs]")
                return

        if interval <= 0:
            print("Watch stopped.")
            return

        print(f"Watching at mode {self.mode:.2f} every {interval}s (Ctrl+C to stop)...")
        prev_zone = None
        try:
            while True:
                status, data = self.client.filter(self.mode)
                if status != 200:
                    print(f"  Error {status}")
                    time.sleep(interval)
                    continue

                zone = data.get("mode_zone", _zone(self.mode))
                vis = len(data.get("visible", []))
                sup = len(data.get("suppressed", []))
                ts = time.strftime("%H:%M:%S")

                if prev_zone and zone != prev_zone:
                    print(f"  [{ts}] ZONE CHANGE: {prev_zone} -> {zone}")

                print(f"  [{ts}] mode={self.mode:.2f} zone={zone} visible={vis} suppressed={sup}")
                prev_zone = zone
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nWatch stopped.")

    # --- Script Mode ---

    def do_script(self, arg):
        """Run commands from a file. Usage: script <filename>"""
        path = arg.strip()
        if not path:
            print("Usage: script <filename>")
            return
        if not os.path.exists(path):
            print(f"File not found: {path}")
            return
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                print(f"gatectl> {line}")
                self.onecmd(line)

    # --- History ---

    def _load_history(self):
        try:
            import readline
            if os.path.exists(HISTORY_FILE):
                readline.read_history_file(HISTORY_FILE)
        except (ImportError, OSError):
            pass

    def _save_history(self):
        try:
            import readline
            readline.set_history_length(500)
            readline.write_history_file(HISTORY_FILE)
        except (ImportError, OSError):
            pass

    # --- Session ---

    def do_quit(self, arg):
        """Exit gatectl."""
        self._save_history()
        print("Bye.")
        return True

    def do_exit(self, arg):
        """Exit gatectl."""
        return self.do_quit(arg)

    do_EOF = do_quit

    def emptyline(self):
        pass  # Don't repeat last command
