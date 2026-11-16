#!/usr/bin/env python3
"""
One-off survey: what depth data exists for the Sindh/Balochistan coast?
1) NOAA/IHO crowdsourced bathymetry (CSB): counts, platforms, and the soundings themselves.
2) GEBCO 2026 TID grid: how much of the grid is measured vs. interpolated.
Writes a text report and PNG maps to the output folder. Never fails hard; each part reports its own errors.
"""
import json, os, re, subprocess, sys, time, urllib.request, urllib.parse

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
REGIONS = {
    "all":          (61.4, 23.5, 68.1, 26.0),
    "karachi":      (66.30, 24.40, 67.60, 25.20),
    "sindh-east":   (66.90, 23.65, 68.10, 24.95),
    "hub-ormara":   (64.40, 24.60, 66.85, 25.75),
    "pasni-jiwani": (61.55, 24.70, 63.75, 25.55),
}
CSB = "https://q81rej0j12.execute-api.us-east-1.amazonaws.com"
CEDA = "https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2026"
ELEV_TIF = CEDA + "/ice_surface_elevation/geotiff/gebco_2026_n90.0_s0.0_w0.0_e90.0_geotiff.tif"
ENV = dict(os.environ, GDAL_HTTP_MAX_RETRY="10", GDAL_HTTP_RETRY_DELAY="3", GDAL_HTTP_TIMEOUT="120",
           CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.nc")
report = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    report.append(line)


def get(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def bbox_s(b):
    return ",".join(str(v) for v in b)


# ---------------- 1) Crowdsourced bathymetry ----------------
def csb():
    say("== NOAA/IHO crowdsourced bathymetry (CSB) ==")
    counts = {}
    for name, b in REGIONS.items():
        try:
            c = json.loads(get(f"{CSB}/count?bbox={bbox_s(b)}"))["count"]
            counts[name] = int(c)
            say(f"  {name:13s} soundings: {c}")
        except Exception as e:  # noqa
            say(f"  {name:13s} count error: {e}")
    try:
        p = json.loads(get(f"{CSB}/platforms?bbox={bbox_s(REGIONS['all'])}"))
        say(f"  platforms in area: {p.get('count')}")
        for row in p.get("data", [])[:40]:
            say(f"    - {row.get('provider')}: {row.get('platform')}")
    except Exception as e:  # noqa
        say(f"  platforms error: {e}")

    total = counts.get("all", 0)
    if total == 0:
        say("  no soundings to download")
        return None
    if total > 3_000_000:
        say("  too many soundings for this check; skipping download")
        return None
    try:
        body = json.dumps({"bbox": bbox_s(REGIONS["all"]), "datasets": [{"label": "csb"}]}).encode()
        resp = json.loads(get(f"{CSB}/order", data=body))
        url = resp["url"]
        say("  order:", resp.get("message"))
        for _ in range(60):
            time.sleep(30)
            st = json.loads(get(url))
            if st.get("status") == "complete":
                loc = st["output_location"]
                m = re.match(r"s3://([^/]+)/(.+)", loc)
                http = f"https://{m.group(1)}.s3.amazonaws.com/{m.group(2)}"
                path = os.path.join(OUT, "csb_points.csv")
                urllib.request.urlretrieve(http, path)
                say(f"  downloaded {os.path.getsize(path)} bytes")
                return path
            if st.get("status") in ("error", "failed"):
                say("  order failed:", st)
                return None
        say("  order not finished in 30 min")
    except Exception as e:  # noqa
        say(f"  order error: {e}")
    return None


def csb_stats(path):
    import csv
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((float(r["LON"]), float(r["LAT"]), float(r["DEPTH"]), r.get("PLATFORM_NAME", ""),
                             r.get("TIME", "")[:4]))
            except (KeyError, ValueError):
                pass
    say(f"  valid soundings: {len(rows)}")
    if not rows:
        return rows
    bands = [(0, 10), (10, 20), (20, 30), (30, 50), (50, 100), (100, 200), (200, 1e9)]
    for lo, hi in bands:
        n = sum(1 for r in rows if lo <= r[2] < hi)
        say(f"    depth {lo:>4}-{hi if hi < 1e9 else 'more':>4} m: {n}")
    for name, (w, s, e, n_) in REGIONS.items():
        if name == "all":
            continue
        k = sum(1 for r in rows if w <= r[0] <= e and s <= r[1] <= n_)
        shelf = sum(1 for r in rows if w <= r[0] <= e and s <= r[1] <= n_ and r[2] < 50)
        say(f"    {name:13s} soundings {k}, shallower than 50 m {shelf}")
    years = {}
    for r in rows:
        years[r[4]] = years.get(r[4], 0) + 1
    say("    by year: " + ", ".join(f"{y}:{c}" for y, c in sorted(years.items())))
    return rows


# ---------------- 2) GEBCO TID ----------------
def listing(url):
    try:
        html = get(url + "/").decode("utf-8", "replace")
        return sorted(set(re.findall(r'href="([^"?#]+)"', html)))
    except Exception as e:  # noqa
        say(f"  no listing {url}: {e}")
        return []


def find_tid_tif():
    for d in listing(CEDA):
        name = d.rstrip("/").split("/")[-1]
        if re.search(r"tid|type", name, re.I):
            base = CEDA + "/" + name
            for sub in [""] + [x.rstrip("/").split("/")[-1] for x in listing(base)]:
                folder = base + ("/" + sub if sub else "")
                for f in listing(folder):
                    fn = f.split("/")[-1]
                    if fn.endswith(".tif") and "n90.0_s0.0_w0.0_e90.0" in fn:
                        return folder + "/" + fn
    return None


def crop(url, out):
    w, s, e, n = REGIONS["all"]
    cmd = ["gdal_translate", "-q", "-projwin", str(w), str(n), str(e), str(s), "/vsicurl/" + url, out]
    return subprocess.run(cmd, env=ENV, timeout=1800).returncode == 0


def tid():
    say("== GEBCO 2026 TID (source type per grid cell) ==")
    url = find_tid_tif()
    say("  TID file:", url)
    if not url:
        return None, None
    t, z = os.path.join(OUT, "tid.tif"), os.path.join(OUT, "elev.tif")
    if not (crop(url, t) and crop(ELEV_TIF, z)):
        say("  crop failed")
        return None, None
    return t, z


def tid_stats(t, z):
    import numpy as np
    from osgeo import gdal
    T = gdal.Open(t).ReadAsArray().astype(int)
    Z = gdal.Open(z).ReadAsArray().astype(float)
    gt = gdal.Open(t).GetGeoTransform()
    names = {0: "land", 10: "singlebeam", 11: "multibeam", 12: "seismic", 13: "isolated sounding",
             14: "ENC sounding", 15: "lidar", 16: "optical", 17: "combined direct",
             40: "predicted (satellite gravity)", 41: "interpolated", 42: "chart contours",
             43: "ENC contours", 44: "bathymetric sounding", 45: "predicted (other)",
             46: "combined indirect", 70: "pre-generated grid", 71: "unknown", 72: "steering points"}
    h, w = T.shape
    lons = gt[0] + (np.arange(w) + 0.5) * gt[1]
    lats = gt[3] + (np.arange(h) + 0.5) * gt[5]
    LON, LAT = np.meshgrid(lons, lats)
    for name, (x0, y0, x1, y1) in REGIONS.items():
        m = (LON >= x0) & (LON <= x1) & (LAT >= y0) & (LAT <= y1) & (Z < 0)
        for label, mm in (("all sea", m), ("shelf <50 m", m & (Z > -50))):
            tot = int(mm.sum())
            if tot == 0:
                continue
            vals, cnt = np.unique(T[mm], return_counts=True)
            parts = [f"{names.get(int(v), str(int(v)))} {100 * c / tot:.1f}%" for v, c in zip(vals, cnt)]
            direct = sum(c for v, c in zip(vals, cnt) if 10 <= v < 40)
            say(f"  {name:13s} {label:12s} cells {tot}: direct {100 * direct / tot:.1f}% | " + "; ".join(parts))
    return T, Z, LON, LAT


def plots(rows, tidres):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    w, s, e, n = REGIONS["all"]
    if tidres:
        T, Z, LON, LAT = tidres
        cls = np.full(T.shape, 0)
        cls[(T >= 10) & (T < 40)] = 3
        cls[(T >= 40) & (T < 70)] = 2
        cls[T >= 70] = 1
        cls[Z >= 0] = -1
        fig, ax = plt.subplots(figsize=(14, 6))
        from matplotlib.colors import ListedColormap
        ax.imshow(cls, extent=(w, e, s, n), cmap=ListedColormap(["#e8dcc0", "#cccccc", "#9ecae1", "#f4a582", "#1a9850"]),
                  vmin=-1.5, vmax=3.5, interpolation="nearest")
        ax.contour(LON, LAT, -Z, levels=[10, 20, 30, 50, 100, 200], colors="k", linewidths=0.4)
        ax.set_title("GEBCO 2026 source: green = measured, orange = interpolated/predicted, grey = pre-generated/unknown")
        fig.savefig(os.path.join(OUT, "gebco_source.png"), dpi=110, bbox_inches="tight")
    if rows:
        a = np.array([(r[0], r[1], r[2]) for r in rows])
        fig, ax = plt.subplots(figsize=(14, 6))
        if tidres:
            ax.contourf(tidres[2], tidres[3], tidres[1] >= 0, levels=[0.5, 1.5], colors=["#e8dcc0"])
        sc = ax.scatter(a[:, 0], a[:, 1], c=np.clip(a[:, 2], 0, 200), s=1, cmap="viridis_r")
        fig.colorbar(sc, label="depth m")
        ax.set_xlim(w, e); ax.set_ylim(s, n)
        ax.set_title("Crowdsourced soundings (NOAA/IHO DCDB)")
        fig.savefig(os.path.join(OUT, "csb_points.png"), dpi=110, bbox_inches="tight")


rows = []
try:
    p = csb()
    if p:
        rows = csb_stats(p)
except Exception as e:  # noqa
    say("CSB part error:", e)
tidres = None
try:
    t, z = tid()
    if t:
        tidres = tid_stats(t, z)
except Exception as e:  # noqa
    say("TID part error:", e)
try:
    plots(rows, tidres)
except Exception as e:  # noqa
    say("plot error:", e)
open(os.path.join(OUT, "report.txt"), "w").write("\n".join(report) + "\n")
