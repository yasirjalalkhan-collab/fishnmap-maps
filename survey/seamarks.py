#!/usr/bin/env python3
"""One-off: list OpenSeaMap/OSM nautical objects on the Pakistan coast. Prints a report and JSON lines."""
import json, sys, time, urllib.request, urllib.parse, collections
BBOX = (23.5, 61.4, 26.0, 68.1)  # S, W, N, E
Q = f"""[out:json][timeout:180];
(
  nwr["seamark:type"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["natural"~"^(reef|rock|shoal)$"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["historic"="wreck"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["man_made"="lighthouse"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["depth"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
);
out center tags;"""
EPS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
       "https://overpass.private.coffee/api/interpreter"]
data = None
for ep in EPS * 2:
    try:
        req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": Q}).encode(),
                                     headers={"User-Agent": "fishnmap-survey/1"})
        data = json.loads(urllib.request.urlopen(req, timeout=240).read())
        print("source:", ep); break
    except Exception as e:  # noqa
        print("failed", ep, e); time.sleep(10)
if not data:
    sys.exit("no data")
els = data["elements"]
print("total objects:", len(els))
kinds = collections.Counter()
for e in els:
    t = e.get("tags", {})
    k = t.get("seamark:type") or ("natural=" + t["natural"] if "natural" in t else None) \
        or ("historic=wreck" if t.get("historic") == "wreck" else None) \
        or ("lighthouse" if t.get("man_made") == "lighthouse" else "depth-tag")
    kinds[k] += 1
for k, c in kinds.most_common():
    print(f"  {k}: {c}")
print("---JSON---")
for e in els:
    t = e.get("tags", {})
    lat = e.get("lat") or e.get("center", {}).get("lat")
    lon = e.get("lon") or e.get("center", {}).get("lon")
    keep = {k: v for k, v in t.items() if k.startswith("seamark") or k in
            ("name", "name:en", "natural", "historic", "man_made", "depth", "wreck:type", "source", "note")}
    print("J", json.dumps({"id": f"{e['type'][0]}{e['id']}", "lat": lat, "lon": lon, "t": keep}, ensure_ascii=False))
