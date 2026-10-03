import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from houseos.playback import (
    MediaError,
    compatibility,
    effective_request,
    exact_episode_file,
    prepare_local,
    probe_file,
    select_candidate,
    media_command,
    MEDIA_ENV,
    map_library_tracks,
)


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.media = {
            "video": {"index": 0, "codec": "hevc", "height": 2160, "hdr": "hdr10", "dv_profile": None},
            "audio": [{"id": "1", "codec": "truehd", "language": "en", "channels": 6, "default": True}],
            "subtitles": [{"id": "2", "codec": "subrip", "language": "fr"}],
            "duration": 300,
            "container": "matroska",
            "evidence": "ffprobe",
        }
        self.caps = {
            "inspected_at": "now",
            "video_codecs": ["hevc"],
            "audio_codecs": ["aac"],
            "maximum_resolution": 2160,
            "max_audio_channels": 6,
            "hdr_modes": ["hdr10"],
            "containers": ["mov"],
            "external_webvtt": True,
        }

    def test_audio_only_4k_video_and_webvtt(self):
        result = compatibility(
            self.media,
            self.caps,
            {"audio_language": "en", "subtitles_on": True, "subtitle_language": "fr", "quality": "4k"},
        )
        self.assertEqual(result["mode"], "audio_convert")
        self.assertTrue(result["video_copied"])
        self.assertEqual(result["subtitle_mode"], "webvtt")
        self.assertEqual(result["video"]["height"], 2160)

    def test_request_override_does_not_change_defaults(self):
        saved = {"audio_language": "en", "subtitles_on": True, "subtitle_language": "fr"}
        request = effective_request(saved, {"audio_language": "es", "subtitles_on": False})
        self.assertEqual(request["audio_language"], "es")
        self.assertFalse(request["subtitles_on"])
        self.assertTrue(saved["subtitles_on"])
        with self.assertRaisesRegex(MediaError, "AUDIO_INCOMPATIBLE"):
            compatibility(self.media, self.caps, request)

    def test_no_hdr_downgrade_and_bitmap_no_fake_conversion(self):
        caps = {**self.caps, "hdr_modes": ["sdr"]}
        with self.assertRaisesRegex(MediaError, "VIDEO_MODE_UNSUPPORTED"):
            compatibility(self.media, caps, {})
        media = copy.deepcopy(self.media)
        media["subtitles"][0]["codec"] = "hdmv_pgs_subtitle"
        with self.assertRaisesRegex(MediaError, "SUBTITLE_BURN_REQUIRED"):
            compatibility(media, self.caps, {"subtitles_on": True})

    def test_exact_pack_mapping(self):
        files = [
            {"id": 41, "path": "/Show.S02E03.mkv"},
            {"id": 90, "path": "/Show.S02E04.mkv"},
            {"id": 6, "path": "/Sample.S02E03.mkv"},
        ]
        self.assertEqual(exact_episode_file(files, 2, 3)["id"], 41)
        with self.assertRaisesRegex(MediaError, "EPISODE_AMBIGUOUS"):
            exact_episode_file(files + [{"id": 71, "path": "/Other.S02E03.mp4"}], 2, 3)
        with self.assertRaisesRegex(MediaError, "EPISODE_AMBIGUOUS"):
            exact_episode_file([{"id": 1, "path": "Show.S01E01-E02.mkv"}], 1, 1)

    def test_frozen_choices(self):
        choices = [
            {"id": "one", "height": 2160, "size": 220},
            {"id": "two", "height": 2160, "size": 310},
            {"id": "three", "height": 1080, "size": 80},
        ]
        self.assertEqual(select_candidate(choices, "1")["id"], "one")
        self.assertEqual(select_candidate(choices, "the smaller 4K one")["id"], "one")
        self.assertEqual(select_candidate(choices, "1080p")["id"], "three")
        with self.assertRaisesRegex(MediaError, "CHOICE_AMBIGUOUS"):
            select_candidate(choices, "4k")

    def test_parser_sandbox_has_no_home_secrets_or_network(self):
        import json

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "input.bin"
            source.write_bytes(b"HouseOS fixture")
            code = "import os,socket,json; s=socket.socket(); result=s.connect_ex(('127.0.0.1',3306)); print(json.dumps({'home':os.path.exists('/home/YOUR_USER'), 'db_env':'HOUSEOS_DATABASE_URL' in os.environ, 'network_connect':result,'input':open('/input/media.bin','rb').read().decode()}))"
            raw = subprocess.check_output(
                media_command(["python3", "-c", code], source), env=MEDIA_ENV, timeout=10
            )
            result = json.loads(raw)
            self.assertFalse(result["home"])
            self.assertFalse(result["db_env"])
            self.assertNotEqual(result["network_connect"], 0)
            self.assertEqual(result["input"], "HouseOS fixture")

    def test_actual_ffmpeg_audio_conversion_and_subtitles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subtitle = root / "text.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,500\nHouseOS synthetic test\n")
            source = root / "test.mkv"
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x180:rate=10",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000",
                    "-i",
                    str(subtitle),
                    "-t",
                    "2",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "flac",
                    "-c:s",
                    "srt",
                    "-metadata:s:a:0",
                    "language=eng",
                    "-metadata:s:s:0",
                    "language=fra",
                    str(source),
                ],
                check=True,
                timeout=30,
            )
            media = probe_file(source)
            caps = {**self.caps, "video_codecs": ["h264"], "hdr_modes": ["sdr"]}
            plan = compatibility(
                media, caps, {"audio_language": "en", "subtitles_on": True, "subtitle_language": "fr"}
            )
            prepared = prepare_local(source, root / "output", plan)
            self.assertEqual(prepared["inspection"]["audio"][0]["codec"], "aac")
            self.assertEqual(prepared["inspection"]["video"]["codec"], "h264")
            self.assertTrue(Path(prepared["subtitle_path"]).read_text().startswith("WEBVTT"))

            def frame_hash(path):
                return subprocess.check_output(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-i",
                        str(path),
                        "-map",
                        "0:v:0",
                        "-c",
                        "copy",
                        "-f",
                        "hash",
                        "-hash",
                        "sha256",
                        "-",
                    ],
                    timeout=20,
                )

            self.assertEqual(frame_hash(source), frame_hash(prepared["path"]))
            burn_caps = {**caps, "external_webvtt": False}
            burn_plan = compatibility(media, burn_caps, {"subtitles_on": True, "allow_video_transcode": True})
            self.assertEqual(burn_plan["subtitle_mode"], "burn")
            burned = prepare_local(source, root / "burned", burn_plan)
            self.assertNotEqual(frame_hash(source), frame_hash(burned["path"]))
            self.assertFalse(burn_plan["video_copied"])
            external_dir = root / "external-burn"
            external_dir.mkdir()
            external_subtitle = external_dir / "subtitle.vtt"
            external_subtitle.write_bytes(Path(prepared["subtitle_path"]).read_bytes())
            external_plan = copy.deepcopy(burn_plan)
            external_plan["_external_subtitle_path"] = str(external_subtitle)
            external_plan["subtitle"]["id"] = "external-with-no-embedded-index"
            external_burned = prepare_local(source, external_dir, external_plan)
            self.assertNotEqual(frame_hash(source), frame_hash(external_burned["path"]))
            self.assertIsNone(external_burned["subtitle_path"])

    def test_library_sidecar_renumbering_requires_unique_track_mapping(self):
        actual = copy.deepcopy(self.media)
        actual["video"]["index"] = 0
        declared = copy.deepcopy(actual)
        declared["video"]["index"] = 1
        declared["audio"][0]["id"] = "2"
        declared["subtitles"][0]["id"] = "3"
        declared["subtitles"].insert(
            0, {"id": "0", "codec": "subrip", "language": "es", "external_jellyfin": True}
        )
        mapped, indices = map_library_tracks(actual, declared)
        self.assertEqual(mapped["audio"][0]["id"], "2")
        self.assertEqual(indices["2"], actual["audio"][0]["id"])
        self.assertEqual(mapped["video"]["index"], 1)
        actual["audio"].append({**actual["audio"][0], "id": "7"})
        declared["audio"].append({**declared["audio"][0], "id": "8"})
        with self.assertRaisesRegex(MediaError, "TRACK_MAPPING_AMBIGUOUS"):
            map_library_tracks(actual, declared)


if __name__ == "__main__":
    unittest.main()
