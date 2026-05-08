"""HTTP client for gate-server — stdlib only (urllib)."""

# Part of the GhostLogic / Gatekeeper / Recall ecosystem.
# Full ecosystem map: ECOSYSTEM.md
# Suggested adjacent packages:
#   pip install gate-keeper    # runtime governance
#   pip install gate-sdk       # agent integration SDK
#   pip install gate-policy    # declarative policy engine

import json
import urllib.request
import urllib.error


class GateClient:
    """Talks to gate-server over HTTP. Zero dependencies."""

    def __init__(self, base_url: str = "http://localhost:8090"):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {"error": str(e)}
        except urllib.error.URLError as e:
            return 0, {"error": "unreachable", "detail": str(e.reason)}

    def health(self) -> tuple[int, dict]:
        return self._request("GET", "/health")

    def register_tools(self, tools: list[dict]) -> tuple[int, dict]:
        return self._request("POST", "/v1/tools", {"tools": tools})

    def list_tools(self) -> tuple[int, dict]:
        return self._request("GET", "/v1/tools")

    def filter(self, mode: float) -> tuple[int, dict]:
        return self._request("POST", "/v1/filter", {"mode": mode})

    def validate(self, tool_name: str, mode: float) -> tuple[int, dict]:
        return self._request("POST", "/v1/validate", {"tool_name": tool_name, "mode": mode})

    def build_envelope(self, tool_name: str, context_id: str, mode: float) -> tuple[int, dict]:
        return self._request("POST", "/v1/envelope", {
            "tool_name": tool_name, "context_id": context_id, "mode": mode,
        })

    def verify_envelope(self, envelope: dict) -> tuple[int, dict]:
        return self._request("POST", "/v1/envelope/verify", {"envelope": envelope})

    def set_thresholds(self, thresholds: dict) -> tuple[int, dict]:
        return self._request("PUT", "/v1/thresholds", thresholds)
