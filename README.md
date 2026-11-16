# fishnmap-maps

Offline map packs for the **Fish N Map** app, published as GitHub Release assets.

- `packs.json` — the four regional packs (id, name, bbox) and the depth levels.
- `scripts/build.sh` — extracts each region from the latest Protomaps daily basemap and adds
  depth contours (5, 10, 20, 30, 50, 100, 200 m) made from the GEBCO Grid.
- `scripts/fetch_bathy.py` — gets only our area of the GEBCO Grid (official CEDA archive first,
  Ifremer ERDDAP GEBCO_2021 as fallback). If no source passes the checks, packs are built without depth.
- `scripts/make_catalog.py` — writes `catalog.json` (id, name, bbox, size, sha256, version, url).
- `.github/workflows/build-packs.yml` — runs on demand (Actions → Build map packs → Run workflow)
  and publishes a new release. The app reads `releases/latest/download/catalog.json`.

Licences: map data © OpenStreetMap contributors (ODbL). Depth lines derived from the GEBCO Grid
(public domain; GEBCO Compilation Group) — **not for navigation**. Basemap build by Protomaps.
