import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

from houseos.cinema_stream_input import input_broker, streaming_media_command
from houseos.playback import MEDIA_ENV


class StreamInputTests(unittest.TestCase):
    def test_isolated_seekable_input_rejects_other_paths_and_revocation(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            payload = b"0123456789" * 100
            calls = []
            cancelled = [False]

            def opener(byte_range, head):
                calls.append((byte_range, head))
                if byte_range:
                    start, end = byte_range[6:].split("-")
                    start, end = int(start), int(end) if end else len(payload) - 1
                    data = payload[start : end + 1]
                    return (
                        206,
                        {
                            "Content-Length": str(len(data)),
                            "Content-Range": f"bytes {start}-{end}/{len(payload)}",
                        },
                        iter([data]),
                    )
                return 200, {"Content-Length": str(len(payload))}, iter([payload])

            with input_broker(directory, opener, lambda: cancelled[0]) as path:
                code = """import urllib.request,json,socket
u="INPUT_URL"
r=urllib.request.urlopen(urllib.request.Request(u,headers={"Range":"bytes=12-19"}))
assert r.status==206 and r.read()==b"23456789"
assert urllib.request.urlopen(urllib.request.Request(u,method="HEAD")).headers["Content-Length"]=="1000"
try: urllib.request.urlopen(u+"/other")
except urllib.error.HTTPError as e: assert e.code==404
else: raise AssertionError("other path accepted")
s=socket.socket();s.settimeout(.2)
try:s.connect(("192.0.2.17",8990))
except OSError:pass
else:raise AssertionError("host network reachable")
print("OK")"""
                # The bridge substitutes an argv INPUT; the test receives it through argv.
                code = code.replace('u="INPUT_URL"', "import sys;u=sys.argv[1]")
                result = subprocess.run(
                    streaming_media_command(["/usr/bin/python3", "-c", code, "INPUT"], path, directory),
                    capture_output=True,
                    env=MEDIA_ENV,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertIn(b"OK", result.stdout)
                self.assertEqual(calls, [("bytes=12-19", False), (None, True)])
                cancelled[0] = True
                client = socket.socket(socket.AF_UNIX)
                client.connect(str(path))
                client.sendall(b"GET /source HTTP/1.0\r\n\r\n")
                self.assertIn(b"410", client.recv(256))
                client.close()
            self.assertFalse(path.exists())

    def test_ffmpeg_mp4_tail_seek_without_full_copy(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = directory / "tail.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=64x64:rate=10",
                    "-t",
                    "2",
                    "-c:v",
                    "mpeg4",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            payload = source.read_bytes()
            calls = []

            def opener(byte_range, head):
                calls.append(byte_range)
                start = 0
                end = len(payload) - 1
                if byte_range:
                    a, b = byte_range[6:].split("-")
                    start = int(a)
                    end = min(int(b), end) if b else end
                data = payload[start : end + 1]
                return (
                    (206 if byte_range else 200),
                    {
                        "Content-Length": str(len(data)),
                        "Accept-Ranges": "bytes",
                        "Content-Range": f"bytes {start}-{end}/{len(payload)}",
                    },
                    iter([data]),
                )

            with input_broker(directory, opener) as path:
                command = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "http,tcp",
                    "-format_whitelist",
                    "mov",
                    "-show_format",
                    "-of",
                    "json",
                    "INPUT",
                ]
                result = subprocess.run(
                    streaming_media_command(command, path, directory),
                    capture_output=True,
                    env=MEDIA_ENV,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertAlmostEqual(float(json.loads(result.stdout)["format"]["duration"]), 2)
                self.assertTrue(any(c for c in calls))
