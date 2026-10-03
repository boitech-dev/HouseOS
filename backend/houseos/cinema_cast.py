"""Narrow Cast transport. HouseOS must preflight and confirm before calling execute."""

from __future__ import annotations
import hashlib
import json
import secrets
import time
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5
from cryptography.fernet import Fernet
from .config import settings
from .db import utcnow
from .integrations import integration_config
from .playback import MediaError


def connect(address):
    """`address` is the receiver's IP, or "IP:port" for a speaker group (it answers on its own
    port on one of its speakers)."""
    import pychromecast

    host, _, port = address.partition(":")
    try:
        cast = pychromecast.get_chromecast_from_host(
            (host, int(port or 8009), uuid5(NAMESPACE_URL, "houseos-cast:" + address), None, None),
            tries=1,
            retry_wait=1,
            timeout=5,
        )
        cast.wait(timeout=6)
        return cast
    except Exception:
        raise MediaError(
            "TARGET_OFFLINE", "The configured Cast receiver did not respond.", "destination", True
        ) from None


def fresh_media_status(cast):
    """GET_STATUS without pychromecast's implicit receiver-app launch."""
    from pychromecast.response_handler import WaitResponse
    from pychromecast.controllers.media import MediaStatus

    status = MediaStatus()
    controller = cast.media_controller
    if not controller.is_active:
        status.player_state = "IDLE"
        return status
    reply = WaitResponse(5, "media status")
    controller.send_message_nocheck({"type": "GET_STATUS"}, callback_function=reply.callback)
    reply.wait_response()
    if not reply.response or reply.response.get("type") != "MEDIA_STATUS":
        raise MediaError(
            "PLAYBACK_NOT_OBSERVED", "The receiver did not supply fresh media status.", "observe", True
        )
    status.update(reply.response)
    return status


def cast_observe(address):
    cast = connect(address)
    try:
        status = fresh_media_status(cast)
        content = status.content_id or ""
        return {
            "app_id": cast.status.app_id,
            "volume": round(cast.status.volume_level * 100),
            "volume_supported": cast.status.volume_control_type != "fixed",
            "state": {"PLAYING": "active", "PAUSED": "paused", "BUFFERING": "buffering", "IDLE": "idle"}.get(
                status.player_state, "unknown"
            ),
            "item_id": hashlib.sha256(content.encode()).hexdigest() if content else None,
            "position": status.current_time or 0,
            "session_id": status.media_session_id,
            "active_track_ids": status.current_subtitle_tracks,
            "subtitle_tracks": [
                {"id": t.get("trackId"), "language": t.get("language")}
                for t in getattr(status, "subtitle_tracks", [])
                if isinstance(t, dict)
            ],
            "duration": status.duration,
            "idle_reason": status.idle_reason,
            "check_in": utcnow().isoformat() if status.last_updated else None,
        }
    except Exception:
        raise MediaError(
            "PLAYBACK_NOT_OBSERVED", "The Cast receiver did not provide usable media status.", "observe", True
        ) from None
    finally:
        cast.disconnect()


def cast_config(db):
    """Casting works as soon as the media relay is running and knows its LAN address (it
    reports it itself); the old "cast" settings row only overrides that address."""
    from .music_outputs import relay_base_url

    config = integration_config(db, "cast", include_disabled=True)
    base = config.get("receiver_base_url") or relay_base_url(db)
    return {**config, "receiver_base_url": base, "enabled": bool(base)}


def preflight_cast(config, source, plan):
    if not config.get("enabled") or not config.get("receiver_base_url"):
        raise MediaError(
            "RELAY_UNCONFIGURED",
            "The media relay isn't running, so the TV can't fetch the film. Restart it in Control Room → Services.",
            "setup",
        )
    if not settings.encryption_key:
        raise MediaError(
            "RELAY_UNCONFIGURED", "The media relay needs the configured server encryption key.", "setup"
        )
    if plan["subtitle_mode"] == "embedded":
        raise MediaError(
            "SUBTITLE_PREPARATION_REQUIRED",
            "Configure external WebVTT capability for this Cast route.",
            "prepare",
        )
    if (
        plan["mode"] == "direct"
        and plan["audio"].get("default")
        and (plan.get("subtitle") or {}).get("external")
        and plan["subtitle_mode"] == "webvtt"
    ):
        plan["preparation_strategy"] = "external_sidecar"
        plan["temporary_bytes"] = 5 * 1024**2
        return
    needs_preparation = (
        plan["mode"] != "direct" or not plan["audio"].get("default") or plan["subtitle_mode"] != "off"
    )
    if needs_preparation:
        import shutil

        size = source.get("size")
        if not size or size > 80 * 1024**3:
            raise MediaError(
                "RESOURCE_LIMIT", "Prepared playback requires a known source size at most 80 GiB.", "prepare"
            )
        from .cinema_progressive import supported

        incremental = supported(source, plan)
        budget = int(size * (1.3 if incremental else 2.2))
        if shutil.disk_usage(settings.runtime_root).free < budget + 20 * 1024**3:
            raise MediaError(
                "RESOURCE_LIMIT",
                "Insufficient NVMe space for temporary media with 20 GiB safety headroom.",
                "prepare",
            )
        plan["temporary_bytes"] = budget
        plan["preparation_strategy"] = "progressive_hls" if incremental else "bounded_complete_spool"
        warning = (
            "Playback starts after a short buffer; video is copied while audio and subtitles are prepared as needed."
            if incremental
            else "This route prepares a complete temporary copy before playback; startup may take several minutes. Temporary files are not a saved library download."
        )
        if warning not in plan["warnings"]:
            plan["warnings"].append(warning)


def wake_screen(db, device):
    """The TV on, and on the Chromecast's input, before the film is sent (tv_remote)."""
    from . import activity, tv_remote

    try:
        done = tv_remote.wake_for_film(db, device)
    except Exception:  # never blocks a film: the resident can still switch by hand
        return
    if done:
        activity.note("TV ready for the film: {what}", what=", ".join(done))


def execute_cast(db, row, device, source, plan):
    from .cinema import CinemaRelay, authorize_workflow
    from .cinema_sources import resolve_media

    config = cast_config(db)
    preflight_cast(config, source, plan)
    prepared = row.data.get("_prepared")
    if plan.get("preparation_strategy") and not prepared:
        from .cinema import CinemaPreparation
        from .db import new_id

        db.add(
            CinemaPreparation(
                id=new_id(),
                workflow_id=row.id,
                owner_id=row.owner_id,
                workflow_version=row.version,
                state="queued",
            )
        )
        db.commit()
        return False
    url = None
    if not prepared or prepared.get("sidecar_only"):
        if source.get("jellyfin_item"):
            from .cinema_adapters import Jellyfin, jellyfin_inspection
            from .playback import compatibility

            jf = Jellyfin(integration_config(db, "jellyfin"))
            current = next(
                (
                    media
                    for media in jf.playback_info(source["jellyfin_item"]).get("MediaSources", [])
                    if media["Id"] == source["jellyfin_source"]
                ),
                None,
            )
            if not current:
                raise MediaError(
                    "SOURCE_EXPIRED", "The exact Jellyfin release is no longer available.", "prepare"
                )
            checked = compatibility(jellyfin_inspection(current), device.capabilities, row.data["request"])
            if any(checked[key] != plan[key] for key in ["video", "audio", "subtitle", "mode"]):
                raise MediaError("PLAN_STALE", "Jellyfin media tracks changed after approval.", "prepare")
            url, size = (
                "jellyfin:"
                + json.dumps({"item_id": source["jellyfin_item"], "source_id": source["jellyfin_source"]}),
                current.get("Size"),
            )
        else:
            url, size = resolve_media(db, source)
        if size and source.get("size") and size != source["size"]:
            raise MediaError("PLAN_STALE", "The selected source size changed after preflight.", "prepare")
    token = secrets.token_urlsafe(32)
    streaming = bool(prepared and prepared.get("streaming"))
    relay_url = (
        config["receiver_base_url"] + "/receiver/" + token + ("/master.m3u8" if streaming else "/media.mp4")
    )
    native_media = not prepared or prepared.get("sidecar_only")
    mime = (
        "video/webm"
        if native_media and "webm" in source["inspection"]["container"]
        else "video/mp2t"
        if native_media and "mpegts" in source["inspection"]["container"]
        else "video/mp4"
    )
    if streaming:
        mime = "application/vnd.apple.mpegurl"
    relay = CinemaRelay(
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        workflow_id=row.id,
        device_address=device.address,
        path=prepared["path"] if prepared else "",
        encrypted_url=Fernet(settings.encryption_key.encode()).encrypt(url.encode()).decode()
        if url
        else None,
        mime=mime,
        expires_at=utcnow() + timedelta(seconds=max(3600, int(plan.get("duration") or 0) + 3600)),
    )
    db.add(relay)
    row.data = {**row.data, "plan": {**plan, "expected_item": hashlib.sha256(relay_url.encode()).hexdigest()}}
    db.commit()
    # Only when a film starts: not on a seek (re-cast of the same film) nor on autoplay's next
    # episode (a TV someone switched off stays off).
    if not row.data.get("_seek_previous") and not row.data.get("_autoplay_parent"):
        wake_screen(db, device)
    cast = connect(device.address)
    try:
        authorize_workflow(db, row)
        # Other apps (including Spotify) share the media namespace. Explicitly
        # select the Cast media receiver before sending a HouseOS LOAD.
        cast.start_app("CC1AD845", timeout=10)
        cast.media_controller.play_media(
            relay_url,
            mime,
            current_time=max(0, plan.get("position", 0) - prepared.get("position_offset", 0))
            if streaming
            else plan.get("position", 0),
            stream_type="BUFFERED",
            autoplay=(row.data.get("_seek_previous") or {}).get("state") != "paused",
            subtitles=relay_url.replace("/media.mp4", "/subtitle.vtt")
            if prepared and prepared.get("subtitle_path")
            else None,
            subtitles_lang=(plan.get("subtitle") or {}).get("language") or "und",
            media_info={"hlsSegmentFormat": "FMP4", "hlsVideoSegmentFormat": "FMP4"} if streaming else None,
        )
        deadline = time.monotonic() + 15
        subtitle_attempts, next_subtitle_attempt = 0, 0.0
        while time.monotonic() < deadline:
            status = cast.media_controller.status
            if getattr(status, "idle_reason", None) == "ERROR" and status.content_id == relay_url:
                raise MediaError(
                    "PLAYBACK_REJECTED",
                    "The receiver rejected this stream before playback started. No picture or subtitles were confirmed.",
                    "play",
                    True,
                )
            if (
                status.content_id == relay_url
                and status.media_session_id is not None
                and status.player_state in {"PLAYING", "PAUSED", "BUFFERING"}
            ):
                if plan.get("subtitle") and plan.get("subtitle_mode") == "webvtt":
                    tracks = [
                        t
                        for t in getattr(status, "subtitle_tracks", [])
                        if isinstance(t, dict)
                        and t.get("type") == "TEXT"
                        and t.get("language") == (plan["subtitle"].get("language") or "und")
                    ]
                    if len(tracks) == 1 and tracks[0].get("trackId") not in status.current_subtitle_tracks:
                        if subtitle_attempts < 3 and time.monotonic() >= next_subtitle_attempt:
                            cast.media_controller.enable_subtitle(tracks[0]["trackId"])
                            subtitle_attempts += 1
                            next_subtitle_attempt = time.monotonic() + 1
                        cast.media_controller.update_status()
                        time.sleep(0.25)
                        continue
                    if len(tracks) != 1:
                        cast.media_controller.update_status()
                        time.sleep(0.25)
                        continue
                break
            cast.media_controller.update_status()
            time.sleep(0.25)
        else:
            if (
                status.content_id == relay_url
                and status.player_state in {"PLAYING", "PAUSED"}
                and plan.get("subtitle")
            ):
                raise MediaError(
                    "SUBTITLE_NOT_OBSERVED",
                    "The receiver reports playback, but has not confirmed the requested subtitles. Picture and subtitle display remain unverified.",
                    "play",
                    True,
                )
            raise MediaError(
                "PLAYBACK_NOT_OBSERVED",
                "The receiver did not start the requested video. Picture, audio and subtitles were not confirmed.",
                "play",
                True,
            )
    except MediaError:
        raise
    except Exception:
        raise MediaError(
            "PLAYBACK_NOT_OBSERVED",
            "The command outcome is unknown. Inspect the receiver before retrying.",
            "play",
            True,
        ) from None
    finally:
        cast.disconnect()
    return True


def cast_music(address, url, mime, position, paused, live, title):
    """Load one song on the Cast media receiver; the music follower keeps it on the house clock."""
    cast = connect(address)
    try:
        cast.start_app("CC1AD845", timeout=10)
        cast.media_controller.play_media(
            url,
            mime,
            title=title,
            current_time=position,
            autoplay=not paused,
            stream_type="LIVE" if live else "BUFFERED",
        )
        cast.media_controller.block_until_active(timeout=10)
    except Exception:
        raise MediaError(
            "PLAYBACK_NOT_OBSERVED", "The Cast speaker did not accept the song.", "play", True
        ) from None
    finally:
        cast.disconnect()


def cast_control(address, action, position):
    cast = connect(address)
    try:
        controller = cast.media_controller
        if action not in {"volume", "volume_step", "mute"}:
            controller.status = fresh_media_status(cast)
            if controller.status.media_session_id is None:
                raise MediaError(
                    "PLAYBACK_NOT_OBSERVED",
                    "The receiver has no active media session to control.",
                    "control",
                    True,
                )
        if action == "pause":
            controller.pause()
        elif action == "resume":
            controller.play()
        elif action == "stop":
            controller.stop()
        elif action == "seek":
            from pychromecast.response_handler import WaitResponse

            reply = WaitResponse(10, "seek")
            controller.send_message(
                {
                    "type": "SEEK",
                    "mediaSessionId": controller.status.media_session_id,
                    "currentTime": position,
                    "resumeState": "PLAYBACK_PAUSE"
                    if controller.status.player_state == "PAUSED"
                    else "PLAYBACK_START",
                },
                callback_function=reply.callback,
                inc_session_id=True,
            )
            reply.wait_response()
        elif action == "volume":
            cast.set_volume(position / 100)
        # The TV remote: a relative volume step (percent), mute toggle, play/pause toggle.
        elif action == "volume_step":
            cast.set_volume(min(1.0, max(0.0, cast.status.volume_level + position / 100)))
        elif action == "mute":
            cast.set_volume_muted(not cast.status.volume_muted)
        elif action == "toggle":
            controller.pause() if controller.status.player_state == "PLAYING" else controller.play()
    except Exception:
        raise MediaError(
            "PLAYBACK_NOT_OBSERVED", "The receiver did not confirm the control command.", "control", True
        ) from None
    finally:
        cast.disconnect()


def abort_cast(address, expected_items):
    """Close our receiver, including an idle failed load, without stopping another app."""
    cast = connect(address)
    try:
        if cast.status.app_id != "CC1AD845":
            return "already_closed"
        status = fresh_media_status(cast)
        content = status.content_id or ""
        if content and hashlib.sha256(content.encode()).hexdigest() not in expected_items:
            raise MediaError(
                "DESTINATION_CHANGED", "The screen is playing something else; it was left alone.", "control"
            )
        cast.quit_app(timeout=5)
        return "stop_sent"
    except MediaError:
        raise
    except Exception:
        raise MediaError(
            "STOP_UNVERIFIED",
            "Preparation stopped, but the receiver did not acknowledge closing. Try Stop Cinema again.",
            "control",
            True,
        ) from None
    finally:
        cast.disconnect()
