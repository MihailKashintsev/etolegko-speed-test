import argparse
import contextlib
import io
import threading
import socket
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import speed_test

BODY = b"0123456789" * 10000


class Handler(BaseHTTPRequestHandler):
    paths = []
    active = 0
    peak = 0

    def do_GET(self):
        type(self).paths.append(self.path)
        type(self).active += 1
        type(self).peak = max(type(self).peak, type(self).active)
        try:
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/file")
                self.end_headers()
                return
            if self.path == "/missing":
                self.send_error(404)
                return
            body = b"" if self.path == "/empty" else BODY
            self.send_response(200)
            if self.path != "/no-length":
                length = len(body) + (100 if self.path == "/truncated" else 0)
                self.send_header("Content-Length", str(length))
            self.end_headers()
            self.wfile.write(body)
        finally:
            type(self).active -= 1

    def log_message(self, *args):
        pass


class SpeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_ten_complete_sequential_downloads(self):
        Handler.paths = []
        Handler.peak = 0
        with contextlib.redirect_stdout(io.StringIO()):
            size, seconds = speed_test.measure(self.base + "/file")
        self.assertEqual(size, 10 * len(BODY))
        self.assertEqual(Handler.paths, ["/file"] * 10)
        self.assertEqual(Handler.peak, 1)
        self.assertGreater(seconds, 0)

    def test_redirect_empty_and_missing_content_length(self):
        for path, expected in [("/redirect", len(BODY)), ("/empty", 0), ("/no-length", len(BODY))]:
            with self.subTest(path=path):
                size, seconds = speed_test.download(self.base + path, 2)
                self.assertEqual(size, expected)
                self.assertGreaterEqual(seconds, 0)

    def test_truncated_response_is_not_success(self):
        with self.assertRaises(OSError):
            speed_test.download(self.base + "/truncated", 2)

    def test_http_error_returns_nonzero_without_summary(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = speed_test.main([self.base + "/missing"])
        self.assertEqual(result, 1)
        self.assertIn("404", errors.getvalue())
        self.assertNotIn("Скорость скачивания:", output.getvalue())

    def test_calculation_uses_total_bytes_over_total_time(self):
        output = io.StringIO()
        with patch("speed_test.measure", return_value=(10 * 1024**2, 5.0)):
            with contextlib.redirect_stdout(output):
                self.assertEqual(speed_test.main([self.base + "/file"]), 0)
        self.assertIn("0.500 с", output.getvalue())
        self.assertIn("2.000 МиБ/с", output.getvalue())
        self.assertIn("16.777 Мбит/с", output.getvalue())

    def test_invalid_arguments(self):
        for url in ["file:///etc/passwd", "ftp://example.com/a", "https://", "http://a:bad", "https://a:b@example.com"]:
            with self.subTest(url=url), self.assertRaises(argparse.ArgumentTypeError):
                speed_test.http_url(url)
        for timeout in ["0", "-1", "nan", "inf", "abc"]:
            with self.subTest(timeout=timeout), self.assertRaises(argparse.ArgumentTypeError):
                speed_test.positive_seconds(timeout)

    def test_timeout_stops_run(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch("speed_test.urlopen", side_effect=socket.timeout("timed out")):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                self.assertEqual(speed_test.main([self.base + "/file"]), 1)
        self.assertNotIn("ЗАМЕР ЗАВЕРШЁН", output.getvalue())
        self.assertIn("timed out", errors.getvalue())

    def test_redirected_output_has_no_ansi(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(speed_test.styled("готово"), "готово")


if __name__ == "__main__":
    unittest.main()
