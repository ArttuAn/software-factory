import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from factory import Factory, FactoryError, ao_request, handler, private_write, safe_id


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class SupervisorSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.factory = Factory("http://127.0.0.1:1", self.temp.name)
        self.factory.save_policy("managed", {"requiredChecks": ["test"]})
        self.calls = []

        def native(path, *args):
            self.calls.append(path)
            if path == "/healthz":
                return {"ok": True}
            if path == "/api/v1/projects":
                return {"projects": [{"id": "managed"}, {"id": "foreign"}]}
            if path == "/api/v1/sessions":
                return {"sessions": [{"id": "ours", "projectId": "managed"}, {"id": "theirs", "projectId": "foreign"}]}
            if path in ("/api/v1/sessions/ours", "/api/v1/sessions/theirs"):
                return {"session": {"projectId": "managed" if path.endswith("ours") else "foreign"}}
            return {"messages": [{"text": "private conversation"}]}

        self.factory.api = native
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        self.server.RequestHandlerClass = handler(self.factory, self.server.server_port)
        self.thread = start_server(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET" if body is None else "POST", path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def token(self):
        status, state = self.request("/api/state", headers={"X-Factory-Client": "supervisor"})
        self.assertEqual(status, 200)
        return state["token"]

    def test_state_filters_unmanaged_projects_and_sessions(self):
        status, state = self.request("/api/state", headers={"X-Factory-Client": "supervisor"})
        self.assertEqual(status, 200)
        self.assertEqual(state["projects"], [{"id": "managed"}])
        self.assertEqual([s["id"] for s in state["sessions"]], ["ours"])

    def test_cross_origin_reads_and_missing_client_header_never_reach_daemon(self):
        for headers in [{}, {"X-Factory-Client": "supervisor", "Origin": "https://evil.test"},
                        {"X-Factory-Client": "supervisor", "Sec-Fetch-Site": "cross-site"},
                        {"X-Factory-Client": "supervisor", "Sec-Fetch-Site": "same-site"}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/state", headers=headers)[0], 403)
        self.assertEqual(self.calls, [])

    def test_unmanaged_session_cannot_be_read_or_controlled(self):
        token = self.token()
        for action in ["conversation", "reviews", "send", "review", "gate", "interrupt", "approval"]:
            self.calls.clear()
            headers = {"X-Factory-Client": "supervisor", "X-Factory-Token": token, "Content-Type": "application/json"}
            status, _ = self.request("/api/sessions/theirs/" + action, None if action in ("conversation", "reviews") else "{}", headers)
            self.assertIn(status, (400, 502))
            self.assertEqual(self.calls, ["/api/v1/sessions/theirs"])
        self.assertEqual(self.request("/api/sessions/ours/conversation", headers={"X-Factory-Client": "supervisor"})[0], 200)

    def test_non_object_and_wrong_content_type_are_rejected(self):
        headers = {"X-Factory-Token": self.token(), "Content-Type": "application/json"}
        self.assertEqual(self.request("/api/spawn", "[]", headers)[0], 400)
        headers["Content-Type"] = "text/plain"
        self.assertEqual(self.request("/api/spawn", "{}", headers)[0], 415)


class TransportAndStorageTests(unittest.TestCase):
    def test_redirect_cannot_forward_prompts_and_proxy_environment_is_ignored(self):
        received = []

        class Native(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(self.path)
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(307)
                self.send_header("Location", "/private-prompt-leak")
                self.end_headers()

            def do_GET(self):
                received.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Native)
        thread = start_server(server)
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1", "no_proxy": "", "NO_PROXY": ""}):
                self.assertEqual(ao_request(base, "/healthz"), {"ok": True})
                with self.assertRaises(FactoryError):
                    ao_request(base, "/sessions", {"prompt": "private"})
            self.assertEqual(received, ["/healthz", "/sessions"])
            with self.assertRaises(FactoryError):
                ao_request("https://example.com", "/sessions", {"prompt": "private"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_state_files_are_private_and_cannot_truncate_a_hardlinked_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path, victim = Path(directory) / "policy.json", Path(directory) / "private.txt"
            victim.write_text("private")
            os.link(victim, path)
            private_write(path, {"safe": True})
            self.assertEqual(victim.read_text(), "private")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_identifiers_cannot_change_proxy_route(self):
        for value in [".", "..", "../projects", "x/y", "", None]:
            with self.assertRaises(FactoryError):
                safe_id(value)


if __name__ == "__main__":
    unittest.main()
