"""One-time local copy from the verified snapshot; refuses an existing workspace.

No imports from vehicle source, no network, no Git or hardware access.
Build/launch amendments are recorded separately in CHANGES.patch.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "vehicle_snapshot_20261013_readonly"
UPSTREAM = SNAPSHOT / "source/home/deepbot/catkin_ws/src"
CORE = {"riki_msgs", "deepbot_driver", "uvc_camera", "imu_calib", "deepbot", "robot_localization"}


def main():
    workspace = ROOT / "vehicle_ws"
    workspace.mkdir(exist_ok=False)
    (workspace / "src").mkdir()
    (workspace / "reference").mkdir()
    (workspace / "reference/CATKIN_IGNORE").write_text("", encoding="utf-8")
    packages = {}
    for path in sorted(UPSTREAM.rglob("package.xml")):
        tree = ET.parse(path).getroot()
        name = tree.findtext("name")
        if name in packages:
            raise ValueError("Duplicate package in snapshot: " + name)
        packages[name] = {
            "source_root": path.parent.relative_to(SNAPSHOT).as_posix(),
            "version": tree.findtext("version"),
            "license_declarations": [x.text for x in tree.findall("license")],
            "original_dependencies": [{"kind": x.tag, "name": x.text} for x in tree if "depend" in x.tag],
            "category": "core" if name in CORE else "reference_only",
        }
    inventory = []
    for row in json.loads((SNAPSHOT / "FILE_MANIFEST.json").read_text(encoding="utf-8-sig")):
        record = {"source": row.get("local_path", row["path"].lstrip("/")),
                  "source_sha256": row["sha256"], "source_bytes": row["bytes"],
                  "destination": None, "package": None, "decision": "excluded",
                  "reason": "outside source packages: generated wrappers, platform files, binary or model hash only"}
        if row["copy"]:
            source = SNAPSHOT / row["local_path"]
            candidates = [(n, v) for n, v in packages.items() if source.is_relative_to(SNAPSHOT / v["source_root"])]
            if candidates:
                name, info = max(candidates, key=lambda v: len(v[1]["source_root"]))
                rel = source.relative_to(SNAPSHOT / info["source_root"])
                record["package"] = name
                active = name in CORE
                if name == "deepbot" and rel.parts[0] in {"launch", "maps", "script", "param"}:
                    active = rel.as_posix() in {"param/ekf/robot_localization.yaml", "param/imu/imu_calib.yaml"}
                if name == "deepbot_driver" and rel.as_posix() == "setup.py":
                    active = False
                if name == "uvc_camera" and rel.parts[0] == "launch":
                    active = False
                # Reference code is preserved for review, outside src and CATKIN_IGNORE.
                category = "src" if active else "reference"
                destination = workspace / category / name / rel
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != row["sha256"]:
                    raise ValueError("Source hash mismatch: " + str(rel))
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as out:
                    out.write(data)
                record.update(destination=destination.relative_to(ROOT).as_posix(), decision=category,
                              reason="active core source" if active else "historical/optional or unavailable resource dependency; not in catkin src")
        inventory.append(record)
    docs = ROOT / "competition/docs/vehicle_source"
    (docs / "SOURCE_INVENTORY.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (docs / "PACKAGES.json").write_text(json.dumps(packages, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"packages": len(packages), "core": sorted(CORE),
                      "copied": sum(x["destination"] is not None for x in inventory)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
