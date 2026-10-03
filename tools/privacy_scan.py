#!/usr/bin/env python3
"""Checks a HouseOS tree, a ZIP or a git history before it is shared: nothing that names a
household, a computer, a network or an account, and no secrets.

    python3 tools/privacy_scan.py PATH [--git] [--terms FILE] [--secrets DIR]

PATH is a folder, a .zip, or (with --git) a git checkout whose whole history is scanned
(commits with author and committer, annotated tags, notes).
--terms is a private word list kept OUTSIDE the repository (names, host names, addresses,
disk ids), one per line; it is read, never printed. With --terms, this computer's own
identity (host name, machine id, network card addresses, Tailscale addresses and name, disk
ids) is added to the list automatically. --secrets is a folder of credential files (KEY=value
env files, keys) whose values must not appear anywhere. Exit status 1 when anything is found.
Only standard library; findings name the file and the rule, never the matched value."""

import argparse
import gzip
import ipaddress
import json
import re
import socket
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

SKIP_PARTS = {"node_modules", "npm-cache", "wheelhouse", "__pycache__", ".pytest_cache", ".venv", ".git"}
FORBIDDEN_FILES = re.compile(
    r"(^|[/:])(\.env(\.(?!example$)[^/]*)?|\.npmrc|\.pypirc|id_(rsa|dsa|ecdsa|ed25519)[^/]*|cookies[^/]*\.txt"
    r"|[^/]*\.(sqlite[^/]*|db|sql|pem|key|log|p12|pfx|kdbx|dump|har|orig|zip|tar(\.[^/]*)?|tgz|bak[^/]*))$"
)
CERTIFICATE = re.compile(r"[^/]*\.crt$")  # a certificate outside third-party code
RULES = {
    # A person's own folders (API paths like "/home/favorites" are fine).
    "home-folder": rb"/home/[a-z_][a-z0-9_-]{0,31}/(?:\.[a-z]|[A-Z]|projects/|src/|code/|git/)"
    rb"|/Users/[A-Za-z][^/\s]{1,31}/|C:\\\\Users\\\\[A-Za-z]",
    # Someone's own disks and sessions; the neutral install paths are allowed.
    "author-path": rb"(?<![\w.~/-])(?<!== \")(?:/storage(?=[/\s\"'`),:;]|$)|/mnt/(?!house-storage\b|wslg\b|c\b|user/appdata\b)[\w.-]+"
    rb"|/srv/(?!houseos\b)[\w.-]+|/run/user/\d+|/root(?=/))",
    "tailnet-name": rb"[a-z0-9-]+\.[a-z0-9-]+\.ts\.net",
    "provider-key": rb"sk-(?:or-v1|ant|proj)-[A-Za-z0-9_-]{20,}|(?<![\w-])sk-[A-Za-z0-9]{32,}"
    rb"|-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY"
    rb"|AGE-SECRET-KEY-1[0-9A-Z]{20,}|eyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}"
    rb"|github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|hf_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}"
    rb"|ya29\.[\w-]{20,}|xox[abepr]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{35}|(?<!\d)\d{8,10}:AA[\w-]{33}",
    "resolver-url": rb"/resolve/realdebrid/[A-Za-z0-9]{20,}|realdebrid=[A-Za-z0-9]{20,}",
    "email": rb"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b",
    "mac-address": rb"(?<![\w:-])(?:[0-9A-Fa-f]{2}([:-]))(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}(?![\w:-])",
}
SAFE_EMAIL = re.compile(
    rb"@(([a-z0-9-]+\.)*example\.(com|org|net|test|invalid)|[a-z0-9-]*\.?example|users\.noreply\.github\.com"
    rb"|localhost|fcm\.googleapis\.com|anthropic\.com|houseos\.local|house\.test|x\.y)$"
    rb"|^(noreply|no-reply|git|user|name|you|someone|admin|person|resident)@",
    re.I,
)
# Made-up, broadcast, multicast and container (02:42) card addresses.
SAFE_MAC = re.compile(
    rb"^(00[:-]){5}00|^(ff[:-]){5}ff|^02[:-]42|^01[:-]00[:-]5e|^33[:-]33|^aa[:-]bb[:-]cc", re.I
)
IP = re.compile(rb"(?<![\d.])(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?![\d.])")
# IPv6 literals; a network written with a prefix ("fc00::/7") is a rule, not an address.
IPV6 = re.compile(rb"(?<![\w:.])((?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4})(?![\w:/.])")
# Addresses meant as examples or defaults, not anyone's network.
SAFE_NETS = [
    ipaddress.ip_network(n)
    for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "127.0.0.0/8", "0.0.0.0/8",
              "172.16.0.0/12", "10.0.0.0/8", "224.0.0.0/4", "255.255.255.255/32", "169.254.0.0/16")
]  # fmt: skip
PRIVATE_V6 = [
    ipaddress.ip_network(n) for n in ("fc00::/7", "fe80::/10")
]  # incl. Tailscale's fd7a:115c:a1e0::/48
HOME_LAN = "192.168." + "1."  # built, so no export rewrite of these example addresses can touch it
EXAMPLE_LAN = {HOME_LAN + n for n in ("1", "20", "50", "250")} | {"192.168.0.1"}
# Obviously made-up keys in tests: "not-a-…", repeated letters, "fake", "example".
FAKE = re.compile(rb"not-a-|fake|example|test|(.)\1{7}", re.I)
TEXT_ONLY = {
    "email",
    "home-folder",
    "tailnet-name",
    "author-path",
    "mac-address",
}  # binary data matches by chance
# A test that must hold fake private values says so: the address, folder and e-mail rules skip
# it; keys, forbidden files, private words and secrets still count.
FIXTURES = b"privacy-scan: test fixtures"
FIXTURE_EXEMPT = {"email", "home-folder", "tailnet-name", "author-path", "mac-address"}
# Public datasets shipped with HouseOS (film titles and cast from Wikidata): common first names in
# them are other people's, so the private word list does not apply there; every other rule does.
DATASETS = re.compile(r"(^|[/:])backend/houseos/data/")
# Bundled third-party code and licence texts carry their own authors' public addresses.
# Upstream files kept as published: vendored code, dependencies, and a theme's fonts (woff2 files and
# their OFL licence, which names the font's authors and their contact).
THIRD_PARTY = re.compile(r"(^|[/:])(vendor/|dependencies/|THIRD-PARTY|themes/[a-z0-9-]+/fonts/)")
SECRET_KEYS = ("TOKEN", "PASSWORD", "PASS", "SECRET", "KEY", "AUTH", "COOKIE", "CREDENTIAL", "PRIVATE")


def private_ip_hits(data):
    for match in IP.findall(data):
        try:
            address = ipaddress.ip_address(match.decode())
        except ValueError:
            continue
        text = str(address)
        if any(address in net for net in SAFE_NETS) or text in EXAMPLE_LAN or text.endswith(".0"):
            continue
        if address.is_private or address in ipaddress.ip_network("100.64.0.0/10"):
            yield text
    for match in IPV6.findall(data):
        if match.endswith(b"::"):  # a prefix such as "fe80::", not a device
            continue
        try:
            address = ipaddress.IPv6Address(match.decode())
        except ValueError:
            continue
        # Real devices have a random interface id; "fe80::1" or "fd00::10" are examples.
        if int(address) & 0xFFFFFFFFFFFFFFFF <= 0xFFFF and not address.ipv4_mapped:
            continue
        if any(address in net for net in PRIVATE_V6) or (
            address.ipv4_mapped and address.ipv4_mapped in ipaddress.ip_network("100.64.0.0/10")
        ):
            yield str(address)


def image_metadata(data):
    """True when a PNG, JPEG or WebP carries text, EXIF or XMP (camera, place, software, author)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        at = 8
        while at + 8 <= len(data):
            length, kind = struct.unpack(">I4s", data[at : at + 8])
            if kind in {b"tEXt", b"iTXt", b"zTXt", b"eXIf"}:
                return True
            if kind == b"IEND":
                break
            at += 12 + length
        return False
    if data.startswith(b"\xff\xd8"):
        at = 2
        while at + 4 <= len(data) and data[at] == 0xFF and data[at + 1] not in (0xDA, 0xD9):
            length = struct.unpack(">H", data[at + 2 : at + 4])[0]
            body = data[at + 4 : at + 2 + length]
            if data[at + 1] == 0xE1 and (body.startswith(b"Exif\0") or b"ns.adobe.com/xap" in body[:40]):
                return True
            at += 2 + length
        return False
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return b"EXIF" in data[12:] or b"XMP " in data[12:]
    return False


def scan_bytes(name, data, terms, secrets):
    found = set()
    binary = b"\0" in data[:4096] or bool(THIRD_PARTY.search(name))
    fixtures = FIXTURES in data[:2048]
    if FORBIDDEN_FILES.search(name) or (CERTIFICATE.search(name) and not THIRD_PARTY.search(name)):
        found.add("forbidden-file")
    for label, pattern in RULES.items():
        if (binary and label in TEXT_ONLY) or (fixtures and label in FIXTURE_EXEMPT):
            continue
        for match in re.finditer(pattern, data):
            if label == "email" and SAFE_EMAIL.search(match.group(0)):
                continue
            if label == "provider-key" and FAKE.search(match.group(0)):
                continue
            if label == "mac-address" and SAFE_MAC.search(match.group(0)):
                continue
            found.add(label)
            break
    if not binary and not fixtures and any(True for _ in private_ip_hits(data)):
        found.add("private-address")
    if image_metadata(data):
        found.add("image-metadata")
    lowered = data.lower()
    if not DATASETS.search(name) and any(term in lowered for term in terms):
        found.add("private-term")
    if any(value in data for value in secrets):
        found.add("local-secret")
    return found


def unpacked(name, data):
    """Compressed files are read inside too (folders, ZIP members and history alike)."""
    if name.endswith(".gz") and data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except (OSError, EOFError):
            return data
    return data


def entries(path, git):
    if git:
        run = lambda *a: subprocess.run(["git", "-C", str(path), *a], capture_output=True, check=True).stdout  # noqa: E731
        for sha in run("rev-list", "--all").decode().split():
            identity = "%an <%ae>%n%cn <%ce>%n%B"
            yield f"git:{sha[:12]}:message", run("show", "-s", f"--format={identity}", sha)
            # Each file's own changes, so rules that depend on the file name still apply.
            for patch in run("show", "--format=", "--binary", sha).split(b"\ndiff --git ")[0:]:
                name = patch.split(b"\n", 1)[0].rsplit(b" b/", 1)[-1].decode(errors="replace")
                if b"GIT binary patch" in patch:
                    # base85 text can spell a short word by chance: read the file itself instead
                    # (a deleted file has nothing left to check at this commit).
                    try:
                        patch = patch.split(b"GIT binary patch", 1)[0] + unpacked(
                            name, run("show", f"{sha}:{name}")
                        )
                    except subprocess.CalledProcessError:
                        patch = patch.split(b"GIT binary patch", 1)[0]
                yield f"git:{sha[:12]}:{name}", patch
        refs = run("for-each-ref", "--format=%(objecttype) %(objectname) %(refname:short)", "refs/tags")
        for kind, sha, ref in (line.split(" ", 2) for line in refs.decode().splitlines()):
            if kind == "tag":  # an annotated tag has its own tagger and message
                yield f"git:tag:{ref}", run("cat-file", "-p", sha)
        return
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.is_dir() and not SKIP_PARTS & set(Path(info.filename).parts):
                    yield info.filename, unpacked(info.filename, archive.read(info))
        return
    for file in sorted(path.rglob("*")):
        if file.is_file() and not file.is_symlink() and not SKIP_PARTS & set(file.relative_to(path).parts):
            yield str(file.relative_to(path)), unpacked(file.name, file.read_bytes())


def quiet(*command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def host_terms():
    """This computer's own identity, read at scan time (never printed)."""
    found = {socket.gethostname()}
    for file in [Path("/etc/machine-id"), *Path("/sys/class/net").glob("*/address")]:
        try:
            found.add(file.read_text().strip())
        except OSError:
            pass
    found |= set(quiet("tailscale", "ip").split()) | set(quiet("lsblk", "-nro", "UUID").split())
    try:
        found.add(
            json.loads(quiet("tailscale", "status", "--json") or "{}").get("Self", {}).get("DNSName", "")
        )
    except ValueError:
        pass
    found = {f.strip(".").lower() for f in found}
    return [f.encode() for f in found if len(f) >= 6 and f != "localhost" and not f.startswith("00:00:00")]


def load_terms(file):
    if not file:
        return []
    lines = Path(file).read_text().splitlines()
    return [line.strip().lower().encode() for line in lines if line.strip() and not line.startswith("#")]


def load_secrets(folder):
    """Credential values from every file in the folder (env files, backups, key files)."""
    values = []
    for file in sorted(p for p in Path(folder).iterdir() if p.is_file()) if folder else []:
        for line in file.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep or not re.fullmatch(r"(export\s+)?[A-Za-z_][A-Za-z0-9_]*", key):
                key, value = "PRIVATE", line  # a bare key file, such as an age identity
            value = value.strip().strip("'\"")
            key = key.upper()
            loopback = value.startswith(
                ("http://127.", "http://localhost", "https://127.", "https://localhost")
            )
            secret_named = any(w in key for w in SECRET_KEYS)
            wordish = value.isalpha() or value.startswith("/")  # a setting such as "password" or a path
            if loopback or wordish:
                continue
            if (secret_named and len(value) >= 8) or ("URL" in key and len(value) >= 16):
                values.append(value.encode())
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--git", action="store_true", help="scan every commit of this checkout")
    parser.add_argument("--terms", help="private word list (outside the repository)")
    parser.add_argument("--secrets", help="folder of credential files")
    parser.add_argument("--allow", action="append", default=[], help="file:rule to accept (repeatable)")
    args = parser.parse_args(argv)
    terms, secrets = load_terms(args.terms), load_secrets(args.secrets)
    own = host_terms() if args.terms else []
    allowed = {tuple(entry.rsplit(":", 1)) for entry in args.allow}
    findings, count = [], 0
    for name, data in entries(args.path, args.git):
        count += 1
        for rule in sorted(scan_bytes(name, data, terms + own, secrets)):
            if (name, rule) not in allowed:
                findings.append((name, rule))
    for name, rule in findings:
        print(f"{rule:18} {name}")
    print(
        f"{'FAIL' if findings else 'PASS'}: {count} {'commit entries' if args.git else 'files'} checked, "
        f"{len(findings)} findings ({len(terms)} private terms, {len(own)} host identifiers, "
        f"{len(secrets)} local secrets compared)."
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
