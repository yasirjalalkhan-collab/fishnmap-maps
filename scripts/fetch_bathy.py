#!/usr/bin/env python3
"""
GEBCO گہرائی کا گرڈ صرف ہمارے علاقے کیلئے لاتا ہے۔
1) سرکاری GEBCO آرکائیو (CEDA) سے تازہ ترین سال — صرف درکار حصہ (HTTP range)۔
2) نہ ملے تو Ifremer ERDDAP پر GEBCO_2021 کا ٹکڑا۔
ہر نتیجہ جانچا جاتا ہے؛ کچھ بھی قابلِ اعتماد نہ ملے تو exit 2 (نقشے بغیر گہرائی بنیں گے)۔
"""
import datetime, json, os, re, subprocess, sys, time, urllib.request

W, S, E, N = 61.4, 23.5, 68.1, 26.0
OUT_TIF, OUT_META = sys.argv[1], sys.argv[2]
CEDA = "https://dap.ceda.ac.uk/bodc/gebco/global"
ERDDAP = ("https://erddap.ifremer.fr/erddap/griddap/gebco2021.nc?"
          f"elevation%5B({S}):1:({N})%5D%5B({W}):1:({E})%5D")
ENV = dict(os.environ, GDAL_HTTP_MAX_RETRY="10", GDAL_HTTP_RETRY_DELAY="3",
           GDAL_HTTP_TIMEOUT="120", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".nc,.tif")


def log(*a):
    print(*a, flush=True)


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def valid(tif):
    """گرڈ میں سمندر اور زمین دونوں ہوں، اور 200 میٹر سے گہرا پانی بھی (بحیرہ عرب)"""
    try:
        info = json.loads(subprocess.run(["gdalinfo", "-json", "-stats", tif], capture_output=True,
                                         text=True, check=True).stdout)
        band = info["bands"][0]
        w, h = info["size"]
        mn, mx = band["minimum"], band["maximum"]
        log(f"  grid {w}x{h} min={mn} max={mx}")
        return w >= 1500 and h >= 550 and mn < -1000 and mx > 100
    except Exception as e:  # noqa
        log("  validation error:", e)
        return False


def translate(src, budget_s):
    """صرف ہمارا علاقہ کاٹ کر GeoTIFF؛ وقت کی حد کے اندر"""
    if os.path.exists(OUT_TIF):
        os.remove(OUT_TIF)
    cmd = ["timeout", str(budget_s), "gdal_translate", "-q", "-projwin", str(W), str(N), str(E), str(S),
           "-co", "COMPRESS=DEFLATE", src, OUT_TIF]
    t = time.time()
    ok = subprocess.run(cmd, env=ENV).returncode == 0
    log(f"  gdal_translate {'ok' if ok else 'failed'} in {int(time.time() - t)} s")
    return ok and valid(OUT_TIF)


def listing(url):
    try:
        return sorted(set(re.findall(r'href="([^"?]+)"', get(url))))
    except Exception as e:  # noqa
        log(f"  no listing {url} ({e})")
        return []


def try_ceda():
    year = datetime.date.today().year
    for y in range(year, 2022, -1):
        base = f"{CEDA}/gebco_{y}/ice_surface_elevation/"
        subdirs = [d for d in listing(base) if d.endswith("/") and not d.startswith("/") and ".." not in d]
        log(f"CEDA {y}: {subdirs}")
        if not subdirs:
            continue
        meta = {"name": f"GEBCO_{y} Grid", "year": y,
                "attribution": f"GEBCO Compilation Group ({y}) GEBCO {y} Grid"}
        # 1) GeoTIFF ٹکڑا جو ہمارے علاقے (0-90 مشرق، 0-90 شمال) کو ڈھانپتا ہے
        for d in [d for d in subdirs if "tif" in d.lower()]:
            for name in listing(base + d):
                low = name.lower()
                if re.search(r"n90(\.0)?_s0(\.0)?_w0(\.0)?_e90(\.0)?", low) and low.endswith((".tif", ".tiff")):
                    url = base + d + name
                    log(f"  try {url}")
                    if translate("/vsicurl/" + url, 900):
                        return dict(meta, url=url)
        # 2) پورا عالمی netCDF، صرف درکار حصہ
        for d in [d for d in subdirs if "netcdf" in d.lower()]:
            for name in [n for n in listing(base + d) if n.endswith(".nc")]:
                url = base + d + name
                log(f"  try {url}")
                if translate("/vsicurl/" + url, 900):
                    return dict(meta, url=url)
        # صرف تازہ ترین دستیاب سال آزمائیں؛ ناکامی پر ERDDAP
        return None
    return None


def try_erddap():
    nc = OUT_TIF + ".nc"
    for attempt in range(3):
        log(f"ERDDAP gebco2021 attempt {attempt + 1}")
        try:
            with urllib.request.urlopen(ERDDAP, timeout=300) as r, open(nc, "wb") as f:
                f.write(r.read())
        except Exception as e:  # noqa
            log("  download failed:", e)
            continue
        if os.path.exists(OUT_TIF):
            os.remove(OUT_TIF)
        r = subprocess.run(["gdal_translate", "-q", "-a_srs", "EPSG:4326", "-co", "COMPRESS=DEFLATE",
                            f'NETCDF:"{nc}":elevation', OUT_TIF])
        if r.returncode == 0 and valid(OUT_TIF):
            return {"name": "GEBCO_2021 Grid", "year": 2021, "url": ERDDAP,
                    "attribution": "GEBCO Compilation Group (2021) GEBCO 2021 Grid"}
    return None


meta = try_ceda() or try_erddap()
if meta is None:
    log("No reliable bathymetry source. Packs will be built WITHOUT depth.")
    sys.exit(2)
meta["note"] = "Not for navigation. Derived from the GEBCO Grid (public domain)."
with open(OUT_META, "w") as f:
    json.dump(meta, f, indent=2)
log("Bathymetry:", json.dumps(meta))
