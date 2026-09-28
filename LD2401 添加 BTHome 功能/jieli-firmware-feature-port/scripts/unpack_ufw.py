"""Safely unpack inspectable UFW artifacts using only the Python standard library.

The default output contains raw non-flash entries and decrypted app files. It
does not write the upgrade key record or VM bytes, which may contain secrets
such as a BTHome key and counter.
"""
import argparse
import json
import re
from pathlib import Path

from ufw_format import audit_image, file_bytes, read_ufw


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return name or "unnamed"


def unpack(source, out_dir):
    data = source.read_bytes()
    header, entries = read_ufw(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out_dir}")
    manifest = {
        "source": str(source.resolve()),
        "size": len(data),
        "entries": [],
        "omitted_sensitive": ["isd_config.ini", "VM"],
        "omitted_entries": [],
    }
    for entry in entries:
        item = {k: entry[k] for k in (
            "type", "index", "name", "offset", "size", "size2", "crc_valid"
        )}
        if entry["name"] == "isd_config.ini":
            manifest["omitted_entries"].append({
                "type": entry["type"], "index": entry["index"], "name": entry["name"]
            })
            continue
        if entry["type"] in (0, 32):
            image = audit_image(data, entry["type"])
            directory = out_dir / f"type_{entry['type']}"
            directory.mkdir()
            written = []
            for appfile in image["appfiles"]:
                name = appfile["name"]
                if name in ("isd_config.ini", "VM") or appfile.get("is_reserved_area"):
                    continue
                target = directory / safe_name(name)
                target.write_bytes(file_bytes(image, name))
                written.append({"name": name, "path": str(target.name), "size": appfile["size"]})
            item["decrypted_app_files"] = written
        else:
            target = out_dir / f"type_{entry['type']}_{entry['index']}_{safe_name(entry['name'])}.bin"
            target.write_bytes(data[entry["offset"]:entry["offset"] + entry["size2"]])
            item["raw_path"] = target.name
        manifest["entries"].append(item)
    with (out_dir / "manifest.json").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ufw", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = unpack(args.ufw.resolve(), args.out.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
