"""A local stand-in that speaks the Anthropic Messages and OpenAI chat-completions wire formats.

Used to exercise the real HTTP path (headers, retries, usage accounting, consent gating) without a network or key.
It never pretends to be a model: replies are fixed JSON chosen by the test.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLM:
    def __init__(self, host: str = "127.0.0.1"):
        self.requests: list[dict] = []
        self.fail_next: list[int] = []          # status codes to return before succeeding
        self.reply = '{"edits": []}'
        self.usage = (120, 30)
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                if outer.fail_next:
                    code = outer.fail_next.pop(0)
                    self.send_response(code)
                    self.send_header("retry-after", "0")
                    self.end_headers()
                    self.wfile.write(b'{"error":"fake"}')
                    return
                i, o = outer.usage
                if self.path.endswith("/v1/messages"):
                    out = {"model": body.get("model"), "content": [{"type": "text", "text": outer.reply}],
                           "usage": {"input_tokens": i, "output_tokens": o}}
                else:
                    out = {"model": body.get("model"), "choices": [{"message": {"content": outer.reply}}],
                           "usage": {"prompt_tokens": i, "completion_tokens": o}}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer((host, 0), H)
        self.url = f"http://{host}:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
