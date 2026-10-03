"""The release privacy scan catches what must never be shared and lets examples through.
(privacy-scan: test fixtures — the fake private values below are the point.)"""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "privacy_scan", Path(__file__).resolve().parents[2] / "tools/privacy_scan.py"
)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def test_rules_catch_private_things_and_pass_examples(tmp_path):
    bad = {
        "a.md": "my server is 192.168.7.23",
        "b.md": "open https://box.tail0000" + ".ts.net",
        "c.py": 'KEY = "sk-or-v1-' + "Ab3" * 12 + '"',
        "d.md": "mail jane.doe@gmail.com",
        "e.sh": "cd /home/jane/Projects/app",
        ".env": "HOUSEOS_DB_PASSWORD=x",
        "f.md": "the owner is Zorblax",
    }
    good = {
        "ok.md": "use 192.0.2.10, 192.168.1.50, 10.0.0.1, 100.64.0.0/10, noreply@anthropic.com",
        "ok.py": 'token = "sk-ant-oat01-' + "f" * 40 + '"  # fake',
        "api.ts": 'await api("/home/favorites")',
        ".env.example": "HOUSEOS_DB_PASSWORD=",
    }
    marked = tmp_path / "marked_test.py"
    marked.write_text("# privacy-scan: test fixtures\nip = '192.168.7.23'\nwho = 'Zorblax'\n")
    for name, text in {**bad, **good}.items():
        (tmp_path / name).write_text(text)
    terms = tmp_path.parent / "terms.txt"
    terms.write_text("# private\nzorblax\n")
    found = {name for name, data in scan.entries(tmp_path, False)
             if scan.scan_bytes(name, data, scan.load_terms(terms), [])}  # fmt: skip
    assert found == set(bad) | {"marked_test.py"}  # fixtures skip the rules, not private words
    marked.write_text("# privacy-scan: test fixtures\nip = '192.168.7.23'\n")
    assert not scan.scan_bytes("marked_test.py", marked.read_bytes(), [], [])
    assert scan.main([str(tmp_path), "--terms", str(terms)]) == 1


def test_history_reads_binary_files_by_content_not_their_encoded_patch(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    (repo / "picture.png").write_bytes(bytes(range(256)) * 40)
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "image")
    found = dict(scan.entries(repo, True))
    image = next(data for name, data in found.items() if name.endswith(":picture.png"))
    assert b"GIT binary patch" not in image and bytes(range(256)) in image


def png(*chunks):
    import struct
    import zlib

    body = b"".join(
        struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d)) for k, d in chunks
    )
    return b"\x89PNG\r\n\x1a\n" + body


def test_new_rules_catch_devices_paths_keys_metadata_and_pass_examples(tmp_path):
    ihdr = (b"IHDR", bytes(13))
    bad = {
        "mac.md": "the TV is 3c:5a:b4:12:9e:07",
        "v6.md": "tailnet fd7a:115c:a1e0:ab12:4843:cd96:6245:9a2f and fe80::1c2b:3aff:fe4d:9e01",
        "disk.service": "RequiresMountsFor=/storage/backups",
        "mnt.sh": "cp x /mnt/bigdisk/films",
        "run.service": "Environment=XDG_RUNTIME_DIR=/run/user/1000",
        "root.sh": "cat /root/.bashrc",
        "age.txt": "AGE-SECRET-KEY-1" + "QZ7" * 20,
        "jwt.md": "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N",
        "gh.md": "github_pat_" + "11ABCDEFG0" * 4,
        "hf.md": "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123",
        "aws.md": "AKIA" + "IOSFODNN7ABCDEFG",
        "sk.md": "sk-" + "Qw3rTy8Zx" * 4,
        "key.md": "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
        "notes.bak-1": "x",
        "id_ed25519": "x",
        ".npmrc": "x",
        "photo.png": png(ihdr, (b"tEXt", b"Author\0someone"), (b"IEND", b"")),
    }
    good = {
        "ok6.md": "fe80::1, fd00::10, fc00::/7, fe80::/10, 2001:db8::1c2b:3aff:fe4d:9e01, 10:30:00",
        "okmac.md": "aa:bb:cc:dd:ee:ff 02:42:ac:11:00:02 00:00:00:00:00:00",
        "okpath.md": "/srv/houseos/data /mnt/house-storage/houseos /opt/houseos /mnt/c/Users /admin/storage/x",
        "api.cjs": 'if (path === "/storage") data = {};',
        "clean.png": png(ihdr, (b"IEND", b"")),
    }
    for name, value in {**bad, **good}.items():
        (tmp_path / name).write_bytes(value if isinstance(value, bytes) else value.encode())
    found = {name for name, data in scan.entries(tmp_path, False) if scan.scan_bytes(name, data, [], [])}
    assert found == set(bad)
    # A fixtures file may hold fake addresses, never keys.
    marked = (
        b"# privacy-scan: test fixtures\nip = 'fd7a:115c:a1e0::1234:5678'\nkey = '"
        + b"hf_"
        + b"Ab1" * 12
        + b"'\n"
    )
    assert scan.scan_bytes("marked_test.py", marked, [], []) == {"provider-key"}


def test_secrets_from_every_file_and_host_identity(tmp_path):
    folder = tmp_path / "store"
    folder.mkdir()
    (folder / "app.env").write_text("DB_PASS=Zq8#kL2p\nMODE=password\nDB_HOST=http://127.0.0.1:3306\n")
    (folder / "old.env.bak-1").write_text("API_TOKEN=Tk7!old-token-9\n")
    (folder / "identity.agekey").write_text("# public key: age1abc\nAGE-SECRET-KEY-1ZZZ\n")
    values = set(scan.load_secrets(folder))
    assert values == {b"Zq8#kL2p", b"Tk7!old-token-9", b"AGE-SECRET-KEY-1ZZZ"}
    import socket

    host = socket.gethostname().lower().encode()
    assert len(host) < 6 or host in scan.host_terms()


def test_history_names_the_committer_too(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    (repo / "a.txt").write_text("x")
    git("add", ".")
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    env = {
        "GIT_COMMITTER_EMAIL": "jane.doe@" + "gmail.com",
        "GIT_COMMITTER_NAME": "Jane",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "-C", str(repo), *identity, "commit", "-qm", "x"], check=True, env=env)
    git(*identity, "tag", "-a", "v1", "-m", "release")
    names = dict(scan.entries(repo, True))
    message = next(v for k, v in names.items() if k.endswith(":message"))
    assert "email" in scan.scan_bytes("m", message, [], []) and "git:tag:v1" in names
