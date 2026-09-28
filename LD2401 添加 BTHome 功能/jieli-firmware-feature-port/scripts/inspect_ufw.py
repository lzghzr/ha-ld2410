"""Inspect a UFW/JLFS package without writing or flashing firmware."""
import argparse
import hashlib
import json
from pathlib import Path

from ufw_format import audit_image, read_ufw


def digest(data):
    return hashlib.sha256(data).hexdigest()


def summary(path):
    data = path.read_bytes()
    header, entries = read_ufw(data)
    result = {
        "path": str(path.resolve()),
        "sha256": digest(data),
        "size": len(data),
        "chip": header[16:64].split(b"\0", 1)[0].decode("ascii", "replace"),
        "entries": [],
    }
    for entry in entries:
        item = {k: entry[k] for k in (
            "type", "index", "name", "offset", "size", "size2", "crc_valid"
        )}
        if entry["type"] in (0, 32):
            try:
                image = audit_image(data, entry["type"])
                files = []
                for f in image["appfiles"]:
                    files.append({
                        "name": f["name"], "offset": f["offset"],
                        "size": f["size"], "crc_valid": f["crc_valid"],
                        "reserved": bool(f.get("is_reserved_area", False)),
                    })
                vm = next((f for f in image["appfiles"] if f["name"] == "VM"), None)
                prct = next((f for f in image["appfiles"] if f["name"] == "PRCT"), None)
                item["flash"] = {
                    "app_base": image["base"],
                    "decoded_end": image["end"],
                    "app": {"offset": image["app"]["offset"], "size": image["app"]["size"]},
                    "vm": None if vm is None else {
                        "offset": vm["offset"], "size": vm["size"],
                        "end": vm["offset"] + vm["size"],
                    },
                    "prct": None if prct is None else {
                        "offset": prct["offset"], "size": prct["size"],
                    },
                    "files": files,
                    "all_area_crc_valid": all(a["crc_valid"] for a in image["areas"]),
                    "all_file_crc_valid": all(f["crc_valid"] for f in image["appfiles"]),
                    "key_record_present": any(f["name"] == "isd_config.ini" for f in image["top"]),
                }
            except (AssertionError, KeyError, StopIteration, ValueError) as exc:
                item["flash_error"] = str(exc)
        result["entries"].append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ufw", type=Path)
    parser.add_argument("--json", type=Path, help="also write the summary to this file")
    args = parser.parse_args()
    report = summary(args.ufw.resolve())
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        with args.json.resolve().open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
