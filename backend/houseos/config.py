from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Neutral defaults for a new install; each deployment sets its own values (HOUSEOS_*)."""

    model_config = SettingsConfigDict(env_prefix="HOUSEOS_", extra="ignore")
    database_url: str = ""
    runtime_root: Path = Path("/var/lib/houseos")
    data_root: Path = Path("/srv/houseos/data")
    # Native installs: the UUID of the disk holding data_root, checked before every write.
    storage_uuid: str = ""
    storage_mount: Path = Path("/srv/houseos")
    # Docker: the data root is a named volume mounted at storage_mount; there is no disk UUID.
    storage_container: bool = False
    tusd_url: str = "http://127.0.0.1:8892"
    file_quota_bytes: int = 20 * 1024**3
    media_quota_bytes: int = 200 * 1024**3
    max_upload_bytes: int = 2 * 1024**3
    # Addresses HouseOS may be opened at; the first admin's address is added automatically
    # and admins manage the rest in Control Room → Access.
    allowed_origins: str = "http://localhost:8990,http://127.0.0.1:8990"
    # Secure cookies are always used over HTTPS; true forces them on plain HTTP too.
    cookie_secure: bool = False
    session_hours: int = 168
    encryption_key: str = ""
    bootstrap_token: str = ""
    frontend_dist: Path = Path(__file__).resolve().parents[2] / "frontend/dist"
    audio_socket: Path | None = None  # default: <runtime_root>/run/audio.sock
    audio_enabled: bool = False
    external_fetch_enabled: bool = False
    # Your network, for films on the TV; empty means "not set up yet".
    receiver_base_url: str = ""
    # This computer's address on the home network, when a VPN takes the default route.
    lan_address: str = ""
    cast_lan_cidr: str = ""
    import_root: Path = Path("/srv/houseos/import")
    # The torrent player (TorrServer, optional, this computer only): plays a stream add-on's versions
    # when the debrid service doesn't have them.
    torrent_engine: str = "http://127.0.0.1:8090"
    torrent_engine_auth: str = ""  # "user:password" when the player asks for one (native setup)
    # The house's own address on the home network (e.g. https://house.lan), announced over
    # mDNS when the built-in HTTPS door is not in use.
    lan_url: str = ""
    # The media relay announces this name on the Wi-Fi (houseos.local); empty turns it off.
    mdns_name: str = "houseos"
    https_port: int = 8443  # the Docker HTTPS door
    private_remote_url: str = ""
    # Subscription AI bridges (ChatGPT via Codex, Claude via Claude Code): private sockets and
    # the official CLIs they run. Docker keeps the sockets in the shared state volume.
    codex_socket: Path = Path("/run/houseos-codex/bridge.sock")
    claude_socket: Path = Path("/run/houseos-claude/bridge.sock")
    codex_bin: str = "/usr/bin/codex"
    claude_bin: str = "/usr/local/lib/houseos/claude"
    # The HouseOS source checkout Nox may read to draft code changes (Control Room → Changes);
    # empty turns code changes off. Docker mounts the clone read-only at /source.
    source_root: Path | None = None
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_subject: str = ""

    @model_validator(mode="after")
    def derived_paths(self):
        if self.audio_socket is None:
            self.audio_socket = self.runtime_root / "run" / "audio.sock"
        return self


settings = Settings()
