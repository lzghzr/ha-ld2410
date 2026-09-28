"""Small, dependency-free UFW/JLFS reader used by the firmware feature skill.

It reads and decrypts metadata in memory. The parser never exposes the local
upgrade key in returned reports and never writes firmware by itself.
"""
import binascii
import struct


def crc(data):
    return binascii.crc_hqx(data, 0)


def cipher(data, key=0xFFFF):
    out = bytearray(data)
    for i in range(len(out)):
        out[i] ^= key & 0xFF
        key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF
    return out


def _entry(data, offset):
    raw = data[offset:offset + 32]
    if len(raw) != 32:
        raise ValueError(f"short JLFS entry at {offset:#x}")
    hcrc, dcrc, off, size, flags, reserved, last, name = struct.unpack(
        "<HHIIBBH16s", raw
    )
    if hcrc != crc(raw[2:]):
        raise ValueError(f"JLFS header CRC at {offset:#x}")
    return {
        "header": offset,
        "data_crc": dcrc,
        "offset": off,
        "size": size,
        "flags": flags,
        "reserved": reserved,
        "last": last,
        "name": name.split(b"\0")[0].decode("ascii", "replace"),
    }


def _key_decode(data):
    score = sum(data[:16]) & 0xFF
    score = 0xAA if score >= 0xE0 else 0x55 if score <= 0x10 else score
    return sum(1 << i for i in range(16) if (data[16 + i] ^ data[15 - i]) < score)


def _sfc(data, start, end, base, key):
    if (start - base) % 32:
        raise ValueError("encrypted JLFS range is not block aligned")
    for off in range(start, end, 32):
        n = min(32, end - off)
        data[off:off + n] = cipher(data[off:off + n], key ^ ((off - base) >> 2))


def read_ufw(data):
    """Return the outer header and UFW entries without changing *data*."""
    header = cipher(data[:64])
    if len(header) != 64:
        raise ValueError("short UFW header")
    hcrc, list_crc, size, count, _, _, chip = struct.unpack(
        "<HHIHHI48s", header
    )
    if hcrc != crc(header[2:]):
        raise ValueError("UFW header CRC")
    if size != len(data):
        raise ValueError(f"UFW size says {size}, file is {len(data)}")
    if list_crc != crc(data[64:64 + count * 80]):
        raise ValueError("UFW entry-list CRC")
    entries = []
    for off in range(64, 64 + count * 80, 80):
        raw = cipher(data[off:off + 80])
        kind, index, dcrc, reserved, pos, length, length2, extra, name = struct.unpack(
            "<HHHHIII44s16s", raw
        )
        if pos + length > len(data):
            raise ValueError(f"UFW payload bounds at {off:#x}")
        payload = data[pos:pos + length]
        entries.append({
            "header": off,
            "type": kind,
            "index": index,
            "data_crc": dcrc,
            "offset": pos,
            "size": length,
            "size2": length2,
            "crc_valid": crc(payload) == dcrc,
            "name": name.split(b"\0")[0].decode("ascii", "replace"),
        })
    return header, entries


def audit_image(data, image_type):
    """Audit one flash entry and return decrypted metadata and app files.

    Key material and the VM bytes stay in memory only; callers should avoid
    serializing ``plain`` or the ``key`` field.
    """
    _, ufw_entries = read_ufw(data)
    flash_ent = next(e for e in ufw_entries if e["type"] == image_type)
    flash = bytearray(data[flash_ent["offset"]:flash_ent["offset"] + flash_ent["size"]])
    fh = cipher(flash[:32])
    if crc(fh[2:]) != int.from_bytes(fh[:2], "little"):
        raise ValueError(f"flash header CRC for type {image_type}")

    top = []
    off = 32
    while True:
        entry = _entry(cipher(flash[off:off + 32]), 0)
        entry["header"] = off
        top.append(entry)
        off += 32
        if entry["last"]:
            break

    key_ent = next(e for e in top if e["name"] == "isd_config.ini")
    keydata = flash[key_ent["offset"]:key_ent["offset"] + 34]
    if crc(keydata[:32]) != int.from_bytes(keydata[32:], "little"):
        raise ValueError(f"key record CRC for type {image_type}")
    key = _key_decode(keydata[:32])
    base = next(e["offset"] for e in top if e["name"] == "app_dir_head")
    plain = bytearray(flash)
    _sfc(plain, base, base + 32, base, key)

    areas = []
    decoded = base + 32
    off = base
    while True:
        entry = _entry(plain, off)
        if entry["size"] < 32 or off + entry["size"] > len(plain):
            raise ValueError(f"bad JLFS area {entry['name']} for type {image_type}")
        end = off + entry["size"]
        decode_end = end if entry["last"] else (end + 63) // 32 * 32
        if decoded < decode_end:
            _sfc(plain, decoded, decode_end, base, key)
            decoded = decode_end
        entry["computed_data_crc"] = crc(plain[off + 32:end])
        entry["crc_valid"] = entry["computed_data_crc"] == entry["data_crc"]
        areas.append(entry)
        if entry["last"]:
            break
        off = end

    app_area = areas[0]
    appfiles = []
    off = base + 32
    while True:
        entry = _entry(plain, off)
        start = base + entry["offset"]
        if entry["flags"] & 0x10:
            entry["crc_valid"] = True
            entry["is_reserved_area"] = True
        else:
            entry["is_reserved_area"] = False
            if start + entry["size"] > base + app_area["size"]:
                raise ValueError(f"file outside app area: {entry['name']}")
            entry["computed_data_crc"] = crc(plain[start:start + entry["size"]])
            entry["crc_valid"] = entry["computed_data_crc"] == entry["data_crc"]
        appfiles.append(entry)
        if entry["last"]:
            break
        off += 32

    app = next(e for e in appfiles if e["name"] == "app.bin")
    return {
        "ufw_entry": flash_ent,
        "top": top,
        "areas": areas,
        "appfiles": appfiles,
        "base": base,
        "end": decoded,
        "key": key,
        "plain": plain,
        "app": app,
    }


def file_bytes(image, name):
    entry = next(e for e in image["appfiles"] if e["name"] == name)
    start = image["base"] + entry["offset"]
    return bytes(image["plain"][start:start + entry["size"]])
