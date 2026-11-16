#!/usr/bin/env bash
# چار علاقائی نقشے: Protomaps بیس میپ + GEBCO گہرائی کی لکیریں (اگر قابلِ اعتماد ذریعہ ملے)
set -euo pipefail
cd "$(dirname "$0")/.."
WORK=work; DIST=dist
rm -rf "$WORK" "$DIST"; mkdir -p "$WORK" "$DIST"
MAXZOOM=$(jq -r .maxzoom packs.json)

# بیس میپ کا تازہ ترین روزانہ بلڈ
SRC=""
for i in $(seq 1 40); do
  d=$(date -u -d "$i days ago" +%Y%m%d)
  if curl -sfI "https://build.protomaps.com/$d.pmtiles" > /dev/null; then
    SRC="https://build.protomaps.com/$d.pmtiles"; break
  fi
done
test -n "$SRC"
echo "Basemap: $SRC"

DEPTH=0
if python3 scripts/fetch_bathy.py "$WORK/bathy.tif" "$WORK/bathy.json"; then
  LEVELS=$(jq -r '.depths | map(-.) | map(tostring) | join(" ")' packs.json)
  gdal_contour -q -a elev -fl $LEVELS "$WORK/bathy.tif" "$WORK/contours.gpkg"
  ogr2ogr -f GeoJSONSeq "$WORK/contours.geojsons" "$WORK/contours.gpkg" -dialect sqlite \
    -sql "SELECT geom, CAST(ROUND(-elev) AS INTEGER) AS depth FROM contour"
  echo "Contours: $(wc -l < "$WORK/contours.geojsons") lines"
  test "$(wc -l < "$WORK/contours.geojsons")" -gt 10
  DEPTH=1
fi

while IFS= read -r row; do
  id=$(jq -r .id <<< "$row")
  bbox=$(jq -r '.bbox | map(tostring) | join(",")' <<< "$row")
  read -r W S E N <<< "$(jq -r '.bbox | map(tostring) | join(" ")' <<< "$row")"
  echo "== $id ($bbox)"
  pmtiles extract "$SRC" "$WORK/base-$id.pmtiles" --bbox="$bbox" --maxzoom="$MAXZOOM"
  if [ "$DEPTH" = 1 ]; then
    ogr2ogr -f GeoJSONSeq "$WORK/depth-$id.geojsons" "$WORK/contours.geojsons" -clipsrc "$W" "$S" "$E" "$N"
    tippecanoe -q -o "$WORK/depth-$id.pmtiles" -l depth -Z6 -z"$MAXZOOM" -y depth \
      --no-feature-limit --no-tile-size-limit --simplification=4 --force "$WORK/depth-$id.geojsons"
    tile-join -q -f --no-tile-size-limit -o "$DIST/$id.pmtiles" "$WORK/base-$id.pmtiles" "$WORK/depth-$id.pmtiles"
  else
    cp "$WORK/base-$id.pmtiles" "$DIST/$id.pmtiles"
  fi
  pmtiles show "$DIST/$id.pmtiles" > "$WORK/show-$id.txt"; head -20 "$WORK/show-$id.txt"
  # گہرائی کی تہہ واقعی موجود ہو
  if [ "$DEPTH" = 1 ]; then pmtiles show "$DIST/$id.pmtiles" --metadata | jq -e '.vector_layers | map(.id) | index("depth") != null'; fi
  ls -la "$DIST/$id.pmtiles"
done < <(jq -c '.packs[]' packs.json)
