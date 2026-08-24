"""Tests for the mock LLM server."""

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

MOCK_PORT = 9222
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"
SCENARIO_PATH = Path(__file__).parent.parent / "scenarios" / "S1-simple-tool-loop.yaml"


@pytest.fixture(scope="module")
def mock_server():
    proc = subprocess.Popen(
        [sys.executable, "mock-llm/server.py", f"--port={MOCK_PORT}", f"--script={SCENARIO_PATH}"],
        cwd=str(Path(__file__).parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(50):
        try:
            r = httpx.get(f"{MOCK_URL}/health", timeout=0.5)
            if r.status_code == 200:
                yield proc
                proc.kill()
                proc.wait()
                return
        except httpx.ConnectError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Mock LLM server failed to start")


def test_health(mock_server):
    r = httpx.get(f"{MOCK_URL}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_endpoint(mock_server):
    r = httpx.get(f"{MOCK_URL}/v1/models")
    assert r.status_code == 200
    assert r.json()["data"][0]["id"] == "mock-budget-llm"


def test_completions_returns_tool_calls(mock_server):
    httpx.post(f"{MOCK_URL}/reset")

    body = {
        "model": "mock-budget-llm",
        "messages": [{"role": "user", "content": "test"}],
    }
    r = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    assert r.status_code == 200
    data = r.json()

    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"] is not None
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "calculate"


def test_completions_scripted_sequence(mock_server):
    httpx.post(f"{MOCK_URL}/reset")

    body = {"model": "mock-budget-llm", "messages": [{"role": "user", "content": "test"}]}

    r1 = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    assert r1.json()["choices"][0]["finish_reason"] == "tool_calls"

    r2 = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    assert r2.json()["choices"][0]["finish_reason"] == "tool_calls"

    r3 = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    assert r3.json()["choices"][0]["finish_reason"] == "tool_calls"

    r4 = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    assert r4.json()["choices"][0]["finish_reason"] == "stop"
    assert r4.json()["choices"][0]["message"]["content"] is not None


def test_ledger_tracks_all_calls(mock_server):
    httpx.post(f"{MOCK_URL}/reset")

    body = {"model": "mock-budget-llm", "messages": [{"role": "user", "content": "test"}]}
    for _ in range(4):
        httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)

    r = httpx.get(f"{MOCK_URL}/ledger")
    ledger = r.json()
    entries = ledger.get("entries", ledger)
    assert len(entries) == 4


def test_token_counts_deterministic(mock_server):
    httpx.post(f"{MOCK_URL}/reset")

    body = {"model": "mock-budget-llm", "messages": [{"role": "user", "content": "test"}]}
    r = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    usage = r.json()["usage"]

    assert usage["prompt_tokens"] == 80
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 100


def test_reset_clears_state(mock_server):
    body = {"model": "mock-budget-llm", "messages": [{"role": "user", "content": "test"}]}
    httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)

    httpx.post(f"{MOCK_URL}/reset")

    ledger = httpx.get(f"{MOCK_URL}/ledger").json()
    entries = ledger.get("entries", ledger)
    assert len(entries) == 0

    r = httpx.post(f"{MOCK_URL}/v1/chat/completions", json=body)
    assert r.json()["choices"][0]["finish_reason"] == "tool_calls"
