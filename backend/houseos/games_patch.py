"""Romhacks: apply an .ips or .bps patch to a game the house already has. The patch is a
list of changes, not a game; the result is saved as a new game linked to the original."""

import zlib


def ips(source, patch):
    if not patch.startswith(b"PATCH"):
        raise ValueError("GAME_PATCH_INVALID")
    out, i = bytearray(source), 5
    while patch[i : i + 3] != b"EOF":
        if i + 5 > len(patch):
            raise ValueError("GAME_PATCH_INVALID")
        offset = int.from_bytes(patch[i : i + 3], "big")
        size = int.from_bytes(patch[i + 3 : i + 5], "big")
        i += 5
        if size:
            data = patch[i : i + size]
            i += size
        else:  # run of one byte
            size = int.from_bytes(patch[i : i + 2], "big")
            data = patch[i + 2 : i + 3] * size
            i += 3
        if offset + size > len(out):
            out.extend(bytes(offset + size - len(out)))
        out[offset : offset + size] = data
    if len(patch) >= i + 6:  # the optional "cut the file here"
        del out[int.from_bytes(patch[i + 3 : i + 6], "big") :]
    return bytes(out)


def bps(source, patch):
    if not patch.startswith(b"BPS1") or zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise ValueError("GAME_PATCH_INVALID")
    i = 4

    def number():
        nonlocal i
        data, shift = 0, 1
        while True:
            x = patch[i]
            i += 1
            data += (x & 0x7F) * shift
            if x & 0x80:
                return data
            shift <<= 7
            data += shift

    def signed():
        n = number()
        return -(n >> 1) if n & 1 else n >> 1

    if number() != len(source) or zlib.crc32(source) != int.from_bytes(patch[-12:-8], "little"):
        raise ValueError("GAME_PATCH_OTHER_VERSION")
    target = bytearray(number())
    metadata = number()  # (read first: number() moves i)
    i += metadata
    out = source_at = target_at = 0
    while i < len(patch) - 12:
        data = number()
        command, length = data & 3, (data >> 2) + 1
        if command == 0:
            target[out : out + length] = source[out : out + length]
        elif command == 1:
            target[out : out + length] = patch[i : i + length]
            i += length
        elif command == 2:
            source_at += signed()
            target[out : out + length] = source[source_at : source_at + length]
            source_at += length
        else:  # byte by byte: it may copy what it is writing
            target_at += signed()
            for k in range(length):
                target[out + k] = target[target_at + k]
            target_at += length
        out += length
    if zlib.crc32(target) != int.from_bytes(patch[-8:-4], "little"):
        raise ValueError("GAME_PATCH_OTHER_VERSION")
    return bytes(target)


def apply(source, patch):
    """The patched game. A SNES game dumped with a copier header gets a second try without it."""
    kind = ips if patch.startswith(b"PATCH") else bps if patch.startswith(b"BPS1") else None
    if kind is None:
        raise ValueError("GAME_PATCH_INVALID")
    try:
        return kind(source, patch)
    except ValueError as error:
        if str(error) != "GAME_PATCH_OTHER_VERSION" or len(source) % 1024 != 512:
            raise
        return kind(source[512:], patch)


if __name__ == "__main__":  # self-check: python -m houseos.games_patch
    game = bytes(range(256)) * 4
    assert ips(game, b"PATCH" + b"\x00\x00\x10\x00\x02AB" + b"\x00\x00\x20\x00\x00\x00\x03Z" + b"EOF") == (
        game[:16] + b"AB" + game[18:32] + b"ZZZ" + game[35:]
    )

    def varint(n):
        out = bytearray()
        while True:
            x = n & 0x7F
            n >>= 7
            if not n:
                return bytes(out + bytes([x | 0x80]))
            out.append(x)
            n -= 1

    target = game[:100] + b"HELLO" + game[105:]
    body = b"BPS1" + varint(len(game)) + varint(len(target)) + varint(0)
    body += varint((99 << 2) | 0) + varint((4 << 2) | 1) + b"HELLO" + varint(((len(game) - 106) << 2) | 0)
    body += zlib.crc32(game).to_bytes(4, "little") + zlib.crc32(target).to_bytes(4, "little")
    body += zlib.crc32(body).to_bytes(4, "little")
    assert apply(game, body) == target
    assert apply(b"\0" * 512 + game, body) == target  # a copier header is tolerated
    print("games_patch ok")
