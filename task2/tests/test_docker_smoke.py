from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_DOCKERFILE_DIR = _REPO_ROOT / "task2"
_IMAGE_TAG = "vici-task2:smoke"

_DONE_TOOL_RESPONSE = {
    "id": "chatcmpl-mock",
    "object": "chat.completion",
    "model": "mock",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {
                            "name": "done",
                            "arguments": json.dumps(
                                {
                                    "result": {"title": "Mock heading"},
                                    "evidence": {
                                        "url": "http://fixture/",
                                        "text_snippet": "Mock heading",
                                    },
                                }
                            ),
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _start_mock_llm() -> tuple[ThreadingHTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps(_DONE_TOOL_RESPONSE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _, port = server.server_address[:2]
    return server, port


def _host_bridge_ip() -> str:
    try:
        result = subprocess.run(
            [
                "docker",
                "network",
                "inspect",
                "bridge",
                "--format",
                "{{range .IPAM.Config}}{{.Gateway}}{{end}}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        ip = result.stdout.strip()
        if ip:
            return ip
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "172.17.0.1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.mark.docker
def test_post_tasks_returns_id():
    mock_server, mock_port = _start_mock_llm()
    host_ip = _host_bridge_ip()
    host_port = _free_port()
    container_name = f"vici-smoke-{host_port}"

    try:
        build = subprocess.run(
            ["docker", "build", "-t", _IMAGE_TAG, str(_DOCKERFILE_DIR)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert build.returncode == 0, f"docker build failed:\n{build.stdout}\n{build.stderr}"

        run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "--add-host",
                f"host.docker.internal:{host_ip}",
                "-e",
                f"LLM_BASE_URL=http://host.docker.internal:{mock_port}",
                "-e",
                "LLM_MODEL=mock",
                "-e",
                "DB_PATH=/tmp/smoke.db",
                "-p",
                f"{host_port}:8000",
                _IMAGE_TAG,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert run.returncode == 0, f"docker run failed:\n{run.stdout}\n{run.stderr}"

        base_url = f"http://localhost:{host_port}"
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                r = httpx.get(f"{base_url}/", timeout=2)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            logs = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True,
            )
            pytest.fail(f"Container never became ready.\n{logs.stdout}\n{logs.stderr}")

        resp = httpx.post(
            f"{base_url}/tasks",
            json={"task": "Read the page heading and return it as title"},
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["id"]

    finally:
        subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", container_name], capture_output=True, timeout=30)
        mock_server.shutdown()
