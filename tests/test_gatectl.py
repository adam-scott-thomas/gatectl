"""Tests for gatectl — REPL commands + one-shot mode + client."""

import io
import json
import os
import threading
import time
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

from gatectl.client import GateClient
from gatectl.shell import GateShell

# --- Mock gate-server ---

_mock_tools = []
_mock_thresholds = {"external_action": 0.65, "state_mutation": 0.65, "high_impact": 0.35}


class MockGateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/v1/tools":
            self._json(200, {"tools": _mock_tools})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_body()
        if self.path == "/v1/tools":
            tools = body.get("tools", [])
            if not tools:
                self._json(400, {"error": "no tools"})
                return
            _mock_tools.extend(tools)
            self._json(200, {"registered": len(tools)})
        elif self.path == "/v1/filter":
            mode = body.get("mode", 0.0)
            zone = "normal" if mode <= 0.35 else "elevated" if mode <= 0.65 else "crisis"
            visible, suppressed = [], []
            for t in _mock_tools:
                cls = t.get("execution_class", "read_only")
                th = _mock_thresholds.get(cls)
                if th is not None and mode > th:
                    suppressed.append(t)
                else:
                    visible.append(t)
            self._json(200, {"visible": visible, "suppressed": suppressed, "mode": mode, "mode_zone": zone})
        elif self.path == "/v1/validate":
            name = body.get("tool_name", "")
            mode = body.get("mode", 0.0)
            tool = next((t for t in _mock_tools if t["name"] == name), None)
            if not tool:
                self._json(404, {"error": "tool_not_found"})
                return
            cls = tool.get("execution_class", "read_only")
            th = _mock_thresholds.get(cls)
            if th is not None and mode > th:
                self._json(403, {"reason": "execution_class_suppressed"})
            else:
                self._json(200, {"accepted": True})
        elif self.path == "/v1/envelope":
            mode = body.get("mode", 0.0)
            zone = "normal" if mode <= 0.35 else "elevated" if mode <= 0.65 else "crisis"
            exec_mode = {"normal": "standard", "elevated": "cautious", "crisis": "minimal"}[zone]
            max_calls = {"normal": 20, "elevated": 10, "crisis": 5}[zone]
            self._json(200, {
                "tool_name": body.get("tool_name"), "context_id": body.get("context_id"),
                "mode": mode, "execution_mode": exec_mode,
                "max_tool_calls": max_calls, "signature": "mock-sig",
            })
        elif self.path == "/v1/envelope/verify":
            env = body.get("envelope", {})
            valid = env.get("signature") == "mock-sig" and env.get("max_tool_calls") != 9999
            self._json(200, {"valid": valid, "reason": "" if valid else "tampered"})
        else:
            self._json(404, {"error": "not found"})

    def do_PUT(self):
        body = self._read_body()
        if self.path == "/v1/thresholds":
            _mock_thresholds.update(body)
            self._json(200, {"updated": True})
        else:
            self._json(404, {"error": "not found"})

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length > 0 else {}

    def _json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


MOCK_PORT = 18092
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"


def setUpModule():
    _mock_tools.clear()
    _mock_thresholds.update({"external_action": 0.65, "state_mutation": 0.65, "high_impact": 0.35})
    global _mock_server
    _mock_server = HTTPServer(("127.0.0.1", MOCK_PORT), MockGateHandler)
    threading.Thread(target=_mock_server.serve_forever, daemon=True).start()
    time.sleep(0.2)


def tearDownModule():
    _mock_server.shutdown()


# --- Client Tests ---

class TestClient(unittest.TestCase):
    def setUp(self):
        self.client = GateClient(MOCK_URL)

    def test_health(self):
        status, data = self.client.health()
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_register_and_list(self):
        _mock_tools.clear()
        status, data = self.client.register_tools([
            {"name": "test_tool", "execution_class": "read_only"},
        ])
        self.assertEqual(status, 200)
        self.assertEqual(data["registered"], 1)

        status, data = self.client.list_tools()
        self.assertEqual(status, 200)
        self.assertTrue(any(t["name"] == "test_tool" for t in data["tools"]))

    def test_filter(self):
        _mock_tools.clear()
        _mock_tools.extend([
            {"name": "safe", "execution_class": "read_only"},
            {"name": "danger", "execution_class": "high_impact"},
        ])
        status, data = self.client.filter(0.5)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["visible"]), 1)
        self.assertEqual(len(data["suppressed"]), 1)

    def test_validate_accepted(self):
        _mock_tools.clear()
        _mock_tools.append({"name": "safe", "execution_class": "read_only"})
        status, _ = self.client.validate("safe", 0.9)
        self.assertEqual(status, 200)

    def test_validate_denied(self):
        _mock_tools.clear()
        _mock_tools.append({"name": "danger", "execution_class": "high_impact"})
        status, data = self.client.validate("danger", 0.5)
        self.assertEqual(status, 403)

    def test_validate_not_found(self):
        status, _ = self.client.validate("nonexistent", 0.1)
        self.assertEqual(status, 404)

    def test_envelope_build_and_verify(self):
        status, env = self.client.build_envelope("safe", "ctx", 0.1)
        self.assertEqual(status, 200)
        self.assertEqual(env["execution_mode"], "standard")

        status, result = self.client.verify_envelope(env)
        self.assertEqual(status, 200)
        self.assertTrue(result["valid"])

    def test_envelope_tamper_detected(self):
        _, env = self.client.build_envelope("safe", "ctx", 0.1)
        env["max_tool_calls"] = 9999
        status, result = self.client.verify_envelope(env)
        self.assertEqual(status, 200)
        self.assertFalse(result["valid"])

    def test_set_thresholds(self):
        status, data = self.client.set_thresholds({"high_impact": 0.20})
        self.assertEqual(status, 200)

    def test_unreachable_server(self):
        bad = GateClient("http://127.0.0.1:19999")
        status, data = bad.health()
        self.assertEqual(status, 0)
        self.assertEqual(data["error"], "unreachable")


# --- Shell Tests ---

class TestShell(unittest.TestCase):
    def _run_cmd(self, shell, cmd_str):
        """Capture stdout from a shell command."""
        out = io.StringIO()
        with patch("sys.stdout", out):
            shell.onecmd(cmd_str)
        return out.getvalue()

    def test_mode_display(self):
        shell = GateShell(MOCK_URL)
        output = self._run_cmd(shell, "mode")
        self.assertIn("0.10", output)
        self.assertIn("normal", output)

    def test_mode_set(self):
        shell = GateShell(MOCK_URL)
        self._run_cmd(shell, "mode 0.7")
        self.assertAlmostEqual(shell.mode, 0.7)
        self.assertIn("crisis", shell.prompt)

    def test_mode_clamp(self):
        shell = GateShell(MOCK_URL)
        self._run_cmd(shell, "mode 5.0")
        self.assertAlmostEqual(shell.mode, 1.0)

    def test_health_command(self):
        shell = GateShell(MOCK_URL)
        output = self._run_cmd(shell, "health")
        self.assertIn("OK", output)

    def test_demo_and_filter(self):
        _mock_tools.clear()
        shell = GateShell(MOCK_URL)
        self._run_cmd(shell, "demo")
        output = self._run_cmd(shell, "filter 0.5")
        self.assertIn("VISIBLE", output)
        self.assertIn("SUPPRESSED", output)

    def test_validate_in_shell(self):
        _mock_tools.clear()
        _mock_tools.append({"name": "x", "execution_class": "high_impact"})
        shell = GateShell(MOCK_URL)
        out = self._run_cmd(shell, "validate x 0.5")
        self.assertIn("DENIED", out)

    def test_envelope_workflow(self):
        shell = GateShell(MOCK_URL)
        self._run_cmd(shell, "envelope read_file ctx1")
        self.assertIsNotNone(shell.last_envelope)
        out = self._run_cmd(shell, "verify")
        self.assertIn("VALID", out)
        out = self._run_cmd(shell, "tamper")
        self.assertIn("TAMPER DETECTED", out)

    def test_quit(self):
        shell = GateShell(MOCK_URL)
        result = shell.onecmd("quit")
        self.assertTrue(result)

    def test_prompt_updates(self):
        shell = GateShell(MOCK_URL)
        self.assertIn("normal", shell.prompt)
        self._run_cmd(shell, "mode 0.8")
        self.assertIn("crisis", shell.prompt)

    def test_script_mode(self):
        """Script command reads and executes a file of commands."""
        import tempfile
        _mock_tools.clear()
        shell = GateShell(MOCK_URL)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# comment\n")
            f.write("demo\n")
            f.write("mode 0.5\n")
            f.name
            script_path = f.name

        try:
            self._run_cmd(shell, f"script {script_path}")
            self.assertAlmostEqual(shell.mode, 0.5)
        finally:
            os.unlink(script_path)

    def test_script_file_not_found(self):
        shell = GateShell(MOCK_URL)
        out = self._run_cmd(shell, "script /nonexistent/file.txt")
        self.assertIn("not found", out)

    def test_server_command(self):
        shell = GateShell(MOCK_URL)
        out = self._run_cmd(shell, "server")
        self.assertIn(MOCK_URL, out)

    def test_server_change(self):
        shell = GateShell(MOCK_URL)
        self._run_cmd(shell, "server http://other:9090")
        self.assertEqual(shell.client.base_url, "http://other:9090")

    def test_register_single_tool(self):
        _mock_tools.clear()
        shell = GateShell(MOCK_URL)
        out = self._run_cmd(shell, "register my_tool advisory")
        self.assertIn("Registered", out)

    def test_register_bad_class(self):
        shell = GateShell(MOCK_URL)
        out = self._run_cmd(shell, "register my_tool bogus_class")
        self.assertIn("Unknown class", out)

    def test_json_no_envelope(self):
        shell = GateShell(MOCK_URL)
        out = self._run_cmd(shell, "json")
        self.assertIn("No envelope", out)

    def test_json_with_envelope(self):
        shell = GateShell(MOCK_URL)
        self._run_cmd(shell, "envelope read_file ctx1")
        out = self._run_cmd(shell, "json")
        self.assertIn("execution_mode", out)


if __name__ == "__main__":
    unittest.main()
