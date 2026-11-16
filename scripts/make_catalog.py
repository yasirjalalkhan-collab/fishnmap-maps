#!/usr/bin/env python3
"""catalog.json: ہر نقشے کا id، نام، bbox، سائز، sha256، ورژن اور ڈاؤنلوڈ کا پتہ"""
import datetime, hashlib, json, os, sys

dist, tag, repo = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open("packs.json"))
depth = None
if os.path.exists("work/bathy.json"):
    depth = json.load(open("work/bathy.json"))

packs = []
for p in cfg["packs"]:
    path = os.path.join(dist, p["id"] + ".pmtiles")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    packs.append({
        "id": p["id"],
        "name": p["name"],
        "bbox": p["bbox"],
        "size": os.path.getsize(path),
        "sha256": h.hexdigest(),
        "version": tag,
        "url": f"https://github.com/{repo}/releases/download/{tag}/{p['id']}.pmtiles",
        "depth": depth is not None,
    })

catalog = {
    "format": 1,
    "version": tag,
    "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "attribution": "© OpenStreetMap contributors (ODbL); basemap build by Protomaps",
    "depth": depth,
    "packs": packs,
}
with open(os.path.join(dist, "catalog.json"), "w") as f:
    json.dump(catalog, f, indent=2)
print(json.dumps(catalog, indent=2))
