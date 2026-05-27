import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UPSTREAM_RPC_URL = os.getenv("UPSTREAM_RPC_URL", "http://anvil:8545")
PORT = int(os.getenv("RPC_PROXY_PORT", "8545"))

BLOCKED_PREFIXES = (
    "admin_",
    "anvil_",
    "debug_",
    "engine_",
    "evm_",
    "hardhat_",
    "miner_",
    "personal_",
    "txpool_",
)
BLOCKED_METHODS = {
    "eth_sendTransaction",
    "eth_sendUnsignedTransaction",
}


def jsonrpc_error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def is_blocked_method(method):
    if method in BLOCKED_METHODS:
        return True
    return any(method.startswith(prefix) for prefix in BLOCKED_PREFIXES)


def normalize_requests(payload):
    if isinstance(payload, list):
        return payload
    return [payload]


class RpcProxyHandler(BaseHTTPRequestHandler):
    server_version = "nxbc-rpc-proxy/0.1"

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True})
            return
        self.send_json(405, {"error": "POST JSON-RPC requests only"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body)
        except Exception:
            self.send_json(400, jsonrpc_error(None, -32700, "Parse error"))
            return

        requests = normalize_requests(payload)
        for item in requests:
            method = item.get("method") if isinstance(item, dict) else None
            if not method:
                self.send_json(400, jsonrpc_error(None, -32600, "Invalid request"))
                return
            if is_blocked_method(method):
                response = jsonrpc_error(item.get("id"), -32601, "Method not allowed")
                self.send_json(200, [response] if isinstance(payload, list) else response)
                return

        upstream_request = Request(
            UPSTREAM_RPC_URL,
            data=raw_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(upstream_request, timeout=10) as upstream_response:
                body = upstream_response.read()
                self.send_response(upstream_response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as exc:
            self.send_json(exc.code, {"error": exc.reason})
        except URLError:
            self.send_json(502, jsonrpc_error(None, -32000, "Upstream RPC unavailable"))

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Starting RPC proxy on 0.0.0.0:{PORT}, upstream={UPSTREAM_RPC_URL}")
    ThreadingHTTPServer(("0.0.0.0", PORT), RpcProxyHandler).serve_forever()
