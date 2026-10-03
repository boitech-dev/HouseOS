"""Real sandboxed packaging; no RD or physical destinations."""

import json
import re
import subprocess
import time
import pytest
from houseos.cinema_progressive import (
    ffmpeg_args,
    ready,
    write_master,
    supported,
    position_offset,
    prepare_timeline,
)
from houseos.cinema_stream_input import input_broker, streaming_media_command
from houseos.cinema_delivery import local_stream
from houseos.playback import MEDIA_ENV, probe_file
from houseos.cinema_prepare import process_one_preparation


@pytest.fixture
def clip(tmp_path):
    sub = tmp_path / "subtitle.srt"
    sub.write_text("1\n00:00:12,000 --> 00:00:15,000\nBonjour maison\n")
    source = tmp_path / "source.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=160x90:r=24,drawbox=color=white:t=fill:enable='between(t,12,13)'",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc=if(between(t\,12\,13)\,0.5*sin(2*PI*1000*t)\,0):s=48000",
            "-i",
            str(sub),
            "-t",
            "16",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "pools=1:frame-threads=1:keyint=48:min-keyint=48:scenecut=0:log-level=error",
            "-c:a",
            "aac",
            "-ac",
            "6",
            "-c:s",
            "srt",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    media = probe_file(source)
    plan = {
        "video": media["video"],
        "audio": media["audio"][0],
        "subtitle": media["subtitles"][0],
        "video_copied": True,
        "audio_conversion": True,
        "output_audio_codec": "aac",
        "output_channels": 2,
        "subtitle_mode": "webvtt",
        "duration": 16,
        "position": 0,
    }
    return source, plan


def test_stream_ready_before_conversion_finishes_and_subtitles_linked(clip, tmp_path):
    source, plan = clip
    output = tmp_path / "ready"
    output.mkdir()
    with input_broker(tmp_path, lambda r, h: local_stream(source, r, head=h)) as sock:
        plan, _ = prepare_timeline(sock, output, plan)
        args = ffmpeg_args(output, plan)
        args[args.index("-i") : args.index("-i")] = ["-re"]
        with subprocess.Popen(
            streaming_media_command(args, sock, output),
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            env=MEDIA_ENV,
        ) as proc:
            start = time.monotonic()
            while not ready(output, plan) and proc.poll() is None and time.monotonic() - start < 12:
                time.sleep(0.1)
            assert ready(output, plan) and proc.poll() is None
            write_master(output, plan, source.stat().st_size)
            assert 'SUBTITLES="subs"' in (output / "master.m3u8").read_text()
            assert "video_vtt.m3u8" in (output / "master.m3u8").read_text()
            _, error = proc.communicate(timeout=25)
            assert proc.returncode == 0, error.decode()
    assert "Bonjour maison" in "".join(p.read_text() for p in output.glob("*.vtt"))
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,crypto,data",
            "-show_streams",
            "-of",
            "json",
            str(output / "video.m3u8"),
        ],
        capture_output=True,
        check=True,
    )
    streams = json.loads(result.stdout)["streams"]
    assert next(s for s in streams if s["codec_type"] == "video")["codec_name"] == "hevc"
    assert next(s for s in streams if s["codec_type"] == "audio")["channels"] == 2
    assert not list(tmp_path.glob("source.bin"))


def test_resume_uses_seekable_input_and_resets_subtitle_timeline(clip, tmp_path):
    source, plan = clip
    plan["position"] = 10
    output = tmp_path / "resume"
    output.mkdir()
    with input_broker(tmp_path, lambda r, h: local_stream(source, r, head=h)) as sock:
        plan, _ = prepare_timeline(sock, output, plan)
        result = subprocess.run(
            streaming_media_command(ffmpeg_args(output, plan), sock, output),
            capture_output=True,
            env=MEDIA_ENV,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr.decode()
        offset = position_offset(sock, output, plan)
    text = "".join(p.read_text() for p in output.glob("*.vtt"))
    assert "Bonjour maison" in text
    cue = float(re.search(r"00:([0-9.]+) -->", text)[1])
    assert abs(cue + offset - 12) < 0.1
    assert 0 <= 10 - offset < 4
    assert supported({}, plan)
    assert not supported({"jellyfin_item": "item"}, plan)


def test_hls_delivery_and_seek_are_scoped_and_cancellable(tmp_path, monkeypatch):
    import hashlib
    from datetime import timedelta
    from unittest.mock import patch
    from sqlalchemy.orm import Session
    from starlette.requests import Request
    from fastapi import HTTPException
    import test_cinema
    from houseos import cinema

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    output = tmp_path / "cinema" / "ready"
    output.mkdir(parents=True)
    (output / "master.m3u8").write_text("#EXTM3U\nvideo.m3u8\n")
    (output / "video.m3u8").write_text("#EXTM3U\n#EXTINF:12.0,\nvideo0.m4s\n")
    (output / "video0.m4s").write_bytes(b"0123456789")
    token = "fixture"
    digest = hashlib.sha256(token.encode()).hexdigest()
    try:
        with Session(f.engine, expire_on_commit=False) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            row.state = "playing_observed"
            row.data = {
                **row.data,
                "_prepared": {
                    "streaming": True,
                    "timeline_version": 2,
                    "path": str(output / "master.m3u8"),
                    "position_offset": 0,
                },
                "plan": {"duration": 100, "expected_item": "ours"},
            }
            db.get(cinema.CinemaDevice, f.device_id).owner_workflow = row.id
            db.get(cinema.CinemaDevice, f.device_id).adapter = "cast"
            db.add(
                cinema.CinemaRelay(
                    token_hash=digest,
                    workflow_id=row.id,
                    device_address="192.0.2.17",
                    path=str(output / "master.m3u8"),
                    mime="application/vnd.apple.mpegurl",
                    expires_at=cinema.utcnow() + timedelta(hours=1),
                )
            )
            db.commit()
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "headers": [(b"range", b"bytes=2-5")],
                    "client": ("192.0.2.17", 123),
                }
            )
            response = cinema.receiver_media(token, "video0.m4s", request, db)
            assert response.status_code == 206 and response.headers["content-type"] == "video/mp4"
            import asyncio

            async def read():
                return b"".join([chunk async for chunk in response.body_iterator])

            assert asyncio.run(read()) == b"2345"
            for name in ["../secret", "source.bin", "video0.m4s.tmp"]:
                with pytest.raises(HTTPException):
                    cinema.receiver_media(token, name, request, db)
            request.scope["client"] = ("192.0.2.23", 123)
            with pytest.raises(HTTPException):
                cinema.receiver_media(token, "master.m3u8", request, db)
        with Session(f.engine) as db:
            current = db.get(cinema.CinemaWorkflow, "workflow-one")
            current.data = {**current.data, "_observation_deadline": "2020-01-01T00:00:00"}
            db.commit()
        with (
            patch("houseos.cinema_cast.cast_control") as command,
            patch(
                "houseos.cinema.inspect_destination",
                return_value={"item_id": "ours", "state": "buffering", "session_id": 1},
            ),
        ):
            sought = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control",
                json={"version": 1, "action": "seek", "position": 0.5},
            )
            assert sought.status_code == 200, sought.text
            assert sought.json()["state"] == "command_sent"
            observed = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/observe", json={"version": sought.json()["version"]}
            )
            assert observed.status_code == 200, observed.text
            assert observed.json()["state"] == "command_sent"
        with Session(f.engine) as db:
            current = db.get(cinema.CinemaWorkflow, "workflow-one")
            current.state, current.version = "playing_observed", 1
            db.commit()
        with (
            patch("houseos.cinema.inspect_destination", return_value={"item_id": "ours", "session_id": 1}),
            patch("houseos.cinema_cast.cast_control") as command,
        ):
            result = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control",
                json={"version": 1, "action": "seek", "position": 50},
            )
            assert result.status_code == 200, result.text
            assert result.json()["state"] == "preparing"
            assert (
                f.client.post(
                    "/api/v1/cinema/workflows/workflow-one/observe",
                    json={"version": result.json()["version"]},
                ).json()["state"]
                == "preparing"
            )
            command.assert_called_once_with("192.0.2.17", "pause", None)
            with Session(f.engine) as db:
                current = db.get(cinema.CinemaWorkflow, "workflow-one")
                assert current.data["_seek_previous"]["prepared"]["path"] == str(output / "master.m3u8")
                assert current.data["_seek_previous"]["plan"]["expected_item"] == "ours"
                from houseos.cinema_progressive import retained_seek_buffer

                assert retained_seek_buffer(current, output.parent)
                assert not retained_seek_buffer(current, tmp_path / "different-job")
                from houseos.cinema_delivery import grant_authorized

                assert grant_authorized(db.get_bind(), digest)
                from houseos.cinema_progressive import cleanup_stream_directory

                cleanup_stream_directory(db.get_bind(), current.id, output.parent)
                assert (output / "video0.m4s").read_bytes() == b"0123456789"
            cancelled = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/cancel", json={"version": result.json()["version"]}
            )
            assert cancelled.status_code == 200
            cleanup_stream_directory(f.engine, "workflow-one", output.parent)
            assert not output.exists()
        with Session(f.engine) as db, patch("houseos.cinema_cast.execute_cast") as play:
            assert not process_one_preparation(db)
            play.assert_not_called()
            assert db.get(cinema.CinemaWorkflow, "workflow-one").state == "cancelled"
    finally:
        f.tearDown()


@pytest.mark.parametrize("seek", [0, 10])
def test_external_srt_uses_small_sidecar_and_streaming_movie(clip, tmp_path, seek):
    from houseos.cinema_subtitles import normalize_text

    source, plan = clip
    plan["position"] = seek
    output = tmp_path / "external"
    output.mkdir()
    plan["subtitle"] = {**plan["subtitle"], "external": True, "id": "uploaded-subtitle"}
    plan["_external_subtitle_path"] = normalize_text(
        b"1\n00:00:12,000 --> 00:00:15,000\nExternal French line\n", output
    )
    assert supported({}, plan)
    assert not (output / "external.srt").exists()
    with input_broker(tmp_path, lambda r, h: local_stream(source, r, head=h)) as sock:
        plan, _ = prepare_timeline(sock, output, plan)
        result = subprocess.run(
            streaming_media_command(ffmpeg_args(output, plan), sock, output),
            capture_output=True,
            env=MEDIA_ENV,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr.decode()
        offset = position_offset(sock, output, plan)
    assert ready(output, plan)
    text = "".join(p.read_text() for p in output.glob("video*.vtt"))
    assert "External French line" in text
    cue = float(re.search(r"00:([0-9.]+) -->", text)[1])
    assert abs(cue + offset - 12) < 0.03
    assert not (output / "source.bin").exists()


def test_direct_sidecar_plan_does_not_reserve_or_spool_movie(monkeypatch):
    from houseos.cinema_cast import preflight_cast
    from houseos.config import settings

    monkeypatch.setattr(settings, "encryption_key", "fixture-configured")
    plan = {
        "mode": "direct",
        "audio": {"default": True},
        "subtitle": {"external": True},
        "subtitle_mode": "webvtt",
    }
    preflight_cast(
        {"enabled": True, "receiver_base_url": "http://fixture.invalid"}, {"size": 30 * 1024**3}, plan
    )
    assert plan["preparation_strategy"] == "external_sidecar"
    assert plan["temporary_bytes"] == 5 * 1024**2


def test_readiness_needs_published_subtitle_segments(tmp_path):
    (tmp_path / "video.m3u8").write_text('#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4,\nvideo0.m4s\n')
    (tmp_path / "video0.m4s").write_bytes(b"video")
    (tmp_path / "init.mp4").write_bytes(b"init")
    (tmp_path / "video_vtt.m3u8").write_text("#EXTM3U\n#EXTINF:4,\nvideo0.vtt\n")
    assert not ready(tmp_path, {"subtitle_mode": "webvtt"})
    (tmp_path / "video0.vtt").write_text("WEBVTT\n\n")
    assert ready(tmp_path, {"subtitle_mode": "webvtt"})


def test_range_probe_reads_tail_metadata_without_movie_spool(clip, tmp_path, monkeypatch):
    from houseos.cinema_sources import probe_media
    import struct

    source, _ = clip
    mp4 = tmp_path / "tail.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-c",
            "copy",
            str(mp4),
        ],
        capture_output=True,
        check=True,
    )
    raw = mp4.read_bytes()
    offset = 0
    while raw[offset + 4 : offset + 8] != b"moov":
        offset += struct.unpack(">I", raw[offset : offset + 4])[0]
    with mp4.open("wb") as out:
        out.write(raw[:offset])
        out.write(struct.pack(">I4s", 40 * 1024**2, b"free"))
        out.seek(40 * 1024**2 - 8, 1)
        out.write(raw[offset:])
    ranges = []

    def stream(_url, byte_range, head=False):
        ranges.append(byte_range)
        return local_stream(mp4, byte_range, head=head)

    monkeypatch.setattr("houseos.cinema_adapters.public_stream", stream)
    work = tmp_path / "probe"
    result = probe_media("https://fixture.invalid/never-contacted", work)
    assert result["video"]["codec"] == "hevc" and result["audio"]
    assert any(r and int(r.split("=")[1].split("-")[0] or 0) > 32 * 1024**2 for r in ranges)
    assert not list(work.iterdir())


def test_master_keeps_ffmpeg_codec_declaration(tmp_path):
    from houseos.cinema_progressive import write_master

    (tmp_path / "av_master.m3u8").write_text(
        '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=3840x2160,CODECS="hvc1.2.4.L150.B0,mp4a.40.2"\nvideo.m3u8\n'
    )
    write_master(
        tmp_path, {"duration": 100, "subtitle_mode": "webvtt", "subtitle": {"language": "en"}}, 1000000
    )
    master = (tmp_path / "master.m3u8").read_text()
    assert 'CODECS="hvc1.2.4.L150.B0,mp4a.40.2"' in master
    assert 'SUBTITLES="subs"' in master


@pytest.mark.parametrize("seek,codec", [(0, "aac"), (10.3, "aac"), (10.3, "eac3")])
def test_decoded_flash_tone_and_subtitle_stay_in_sync_without_edit_lists(clip, tmp_path, seek, codec):
    import array

    source, plan = clip
    if codec == "eac3":
        converted = tmp_path / "eac3.mkv"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(source),
                "-map",
                "0",
                "-c",
                "copy",
                "-c:a",
                "eac3",
                str(converted),
            ],
            check=True,
            capture_output=True,
        )
        source = converted
    plan["position"] = seek
    output = tmp_path / "sync"
    output.mkdir()
    with input_broker(tmp_path, lambda r, h: local_stream(source, r, head=h)) as sock:
        plan, _ = prepare_timeline(sock, output, plan)
        result = subprocess.run(
            streaming_media_command(ffmpeg_args(output, plan), sock, output),
            capture_output=True,
            env=MEDIA_ENV,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr.decode()
        offset = position_offset(sock, output, plan)
    assert b"elst" not in (output / "init.mp4").read_bytes()
    inp = ["-protocol_whitelist", "file,crypto,data", "-i", str(output / "video.m3u8")]

    def frames(stream):
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,crypto,data",
                "-select_streams",
                stream,
                "-show_frames",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "json",
                str(output / "video.m3u8"),
            ],
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)["frames"]

    pixels = subprocess.run(
        ["ffmpeg", "-v", "error"]
        + inp
        + [
            "-map",
            "0:v",
            "-vf",
            "scale=1:1,format=gray",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    video = next(
        float(frame["best_effort_timestamp_time"]) for frame, pixel in zip(frames("v"), pixels) if pixel > 200
    )
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error"]
        + inp
        + ["-map", "0:a", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"],
        capture_output=True,
        check=True,
    ).stdout
    samples = array.array("f")
    samples.frombytes(pcm)
    audio = (
        float(frames("a")[0]["best_effort_timestamp_time"])
        + next(i for i, value in enumerate(samples) if abs(value) > 0.1) / 48000
    )
    text = "".join(p.read_text() for p in output.glob("*.vtt"))
    cue = float(re.search(r"00:([0-9.]+) -->", text)[1])
    assert abs(video - audio) < 0.03, (video, audio)
    assert abs(video - cue) < 0.03, (video, cue)
    assert abs(video + offset - 12) < 0.03, (video, offset)
