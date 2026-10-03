"""
Mock LLM server exposing an OpenAI-compatible /v1/chat/completions endpoint.

Key properties:
- Deterministic token counts (configurable per response)
- Request ledger (ground truth for what tokens were actually consumed)
- Scripted responses (loaded from scenario YAML)
- Supports tool_calls in responses for multi-turn scenarios
"""

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import dataclass, field, asdict
from typing import Optional

LEDGER: list[dict] = []
LEDGER_LOCK = threading.Lock()
SCRIPT: list[dict] = []
SCRIPT_INDEX = 0


# The token-details block the server emits on every response. These are
# constants, not simulated cache behaviour: the mock holds no prompt cache, so
# there is nothing to vary and nothing here infers a cache hit. They are named
# once so the wire response and the ledger read from the same source, which is
# what makes the ledger a record of what was emitted rather than a second,
# separately maintained guess at it. Changing a value here changes both.
EMITTED_CACHED_TOKENS = 0
EMITTED_CACHE_WRITE_TOKENS = 0
EMITTED_REASONING_TOKENS = 0


def emitted_prompt_tokens_details() -> dict:
    return {
        "cached_tokens": EMITTED_CACHED_TOKENS,
        "cache_write_tokens": EMITTED_CACHE_WRITE_TOKENS,
    }


def emitted_completion_tokens_details() -> dict:
    return {"reasoning_tokens": EMITTED_REASONING_TOKENS}


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LedgerEntry:
    request_id: str
    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tool_calls_requested: int
    finish_reason: str
    streamed: bool = False
    # Recorded, not simulated. The server emits a token-details block on every
    # response and the ledger dropped it entirely, so the ledger could not
    # answer what cache figures a framework had been told. A framework that
    # reads prompt_tokens_details and reports a cache-adjusted cost is making a
    # claim the ground truth had no basis on which to check it. These fields
    # carry the emitted values through so that check becomes possible; they do
    # not model a cache, and they are zero because zero is what is emitted.
    cached_tokens: int = EMITTED_CACHED_TOKENS
    cache_write_tokens: int = EMITTED_CACHE_WRITE_TOKENS
    reasoning_tokens: int = EMITTED_REASONING_TOKENS


def load_script(script_entries: list[dict]):
    global SCRIPT, SCRIPT_INDEX
    SCRIPT = script_entries
    SCRIPT_INDEX = 0


def get_next_response() -> dict:
    global SCRIPT_INDEX
    if SCRIPT_INDEX >= len(SCRIPT):
        return {
            "content": "Script exhausted.",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "tool_calls": None,
            "finish_reason": "stop",
        }
    entry = SCRIPT[SCRIPT_INDEX]
    SCRIPT_INDEX += 1
    return entry


def reset():
    global LEDGER, SCRIPT_INDEX
    with LEDGER_LOCK:
        LEDGER = []
    SCRIPT_INDEX = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle_completions()
        elif self.path == "/reset":
            reset()
            self._respond(200, {"status": "reset"})
        elif self.path == "/ledger":
            with LEDGER_LOCK:
                self._respond(200, {"entries": LEDGER})
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/ledger":
            with LEDGER_LOCK:
                self._respond(200, {"entries": LEDGER})
        elif self.path == "/v1/models":
            self._respond(200, {"data": [{"id": "mock-budget-llm", "object": "model"}]})
        elif self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def _handle_completions(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))

        model = body.get("model", "mock-budget-llm")
        stream = bool(body.get("stream", False))
        scripted = get_next_response()

        prompt_tokens = scripted.get("prompt_tokens", 100)
        completion_tokens = scripted.get("completion_tokens", 50)
        total_tokens = prompt_tokens + completion_tokens
        finish_reason = scripted.get("finish_reason", "stop")
        tool_calls = scripted.get("tool_calls", None)

        request_id = f"mock-{int(time.time()*1000)}-{SCRIPT_INDEX}"

        # Built through LedgerEntry rather than as a free-standing dict so the
        # dataclass is the schema instead of documentation of one. It was
        # previously neither used nor kept in step: it had no `streamed` field
        # while the appended dict did, and no cache fields while every response
        # carried them.
        #
        # `finish_reason` here is the scripted value, deliberately captured
        # before the `tool_calls` override below rewrites it for the wire. The
        # ledger records what the script asked for; the response records what
        # the client was told. Preserved as-is.
        entry = asdict(LedgerEntry(
            request_id=request_id,
            timestamp=time.time(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            tool_calls_requested=len(tool_calls) if tool_calls else 0,
            finish_reason=finish_reason,
            streamed=stream,
        ))
        with LEDGER_LOCK:
            LEDGER.append(entry)

        if stream:
            self._respond_stream(
                request_id=request_id,
                model=model,
                content=scripted.get("content", "") or "",
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else finish_reason,
                stream_chunks=int(scripted.get("stream_chunks", 1) or 1),
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            )
            return

        message = {"role": "assistant"}
        if tool_calls:
            message["content"] = None
            message["tool_calls"] = tool_calls
            finish_reason = "tool_calls"
        else:
            message["content"] = scripted.get("content", "")

        response = {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "prompt_tokens_details": emitted_prompt_tokens_details(),
                "completion_tokens_details": emitted_completion_tokens_details(),
            },
        }
        self._respond(200, response)

    def _respond_stream(
        self,
        request_id: str,
        model: str,
        content: str,
        tool_calls: Optional[list],
        finish_reason: str,
        stream_chunks: int,
        usage: dict,
    ):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        created = int(time.time())

        def frame(delta: dict, finish: Optional[str] = None) -> bytes:
            chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {"index": 0, "delta": delta, "finish_reason": finish},
                ],
            }
            return b"data: " + json.dumps(chunk).encode() + b"\n\n"

        try:
            self.wfile.write(frame({"role": "assistant", "content": ""}))

            if tool_calls:
                for i, tc in enumerate(tool_calls):
                    self.wfile.write(frame({"tool_calls": [{
                        "index": i,
                        "id": tc.get("id"),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": tc.get("function", {}).get("name"),
                            "arguments": tc.get("function", {}).get("arguments", ""),
                        },
                    }]}))
            elif content:
                n = max(1, stream_chunks)
                step = max(1, len(content) // n)
                for i in range(n):
                    start = i * step
                    end = len(content) if i == n - 1 else start + step
                    piece = content[start:end]
                    if piece:
                        self.wfile.write(frame({"content": piece}))

            usage_frame = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                "usage": {
                    **usage,
                    "prompt_tokens_details": emitted_prompt_tokens_details(),
                    "completion_tokens_details": emitted_completion_tokens_details(),
                },
            }
            self.wfile.write(b"data: " + json.dumps(usage_frame).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _respond(self, code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run(port: int = 9111, script: Optional[list[dict]] = None):
    if script:
        load_script(script)
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Mock LLM running on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser(description="Mock LLM for budget differential testing")
    parser.add_argument("--port", type=int, default=9111)
    parser.add_argument("--script", help="Path to scenario YAML file")
    args = parser.parse_args()

    if args.script:
        with open(args.script) as f:
            scenario = yaml.safe_load(f)
        load_script(scenario.get("script", []))
        print(f"Loaded scenario: {scenario.get('name', args.script)}")
        print(f"  Turns: {len(scenario.get('script', []))}")

    run(port=args.port)
