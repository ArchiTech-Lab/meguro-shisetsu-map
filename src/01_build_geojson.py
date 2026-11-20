"""e-Stat 小地域（町丁・字等）境界 shapefile → GeoJSON（標準ライブラリのみ）。
入力：data/raw/estat/r2ka13110.{shp,dbf}（国勢調査2020・目黒区・JGD2000経緯度）
出力：data/interim/cho.geojson（町丁目ポリゴン＋重心＋町名）
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/estat/r2ka13110"
OUT = ROOT / "data/interim"
OUT.mkdir(parents=True, exist_ok=True)


def read_dbf(path):
    b = path.read_bytes()
    n, hlen, rlen = struct.unpack("<IHH", b[4:12])
    fields, p = [], 32
    while b[p] != 0x0D:
        name = b[p:p + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, b[p + 16]))
        p += 32
    rows = []
    for i in range(n):
        rec = b[hlen + i * rlen: hlen + (i + 1) * rlen]
        q, row = 1, {}
        for name, ln in fields:
            row[name] = rec[q:q + ln].decode("cp932", "replace").strip()
            q += ln
        rows.append(row)
    return rows


def read_shp(path):
    b = path.read_bytes()
    p, shapes = 100, []
    while p < len(b):
        _, clen = struct.unpack(">ii", b[p:p + 8])
        rec = b[p + 8: p + 8 + clen * 2]
        p += 8 + clen * 2
        if struct.unpack("<i", rec[:4])[0] != 5:
            shapes.append(None)
            continue
        nparts, npts = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts]))
        off = 44 + 4 * nparts
        pts = [struct.unpack("<dd", rec[off + 16 * k: off + 16 * k + 16]) for k in range(npts)]
        parts.append(npts)
        shapes.append([pts[parts[k]:parts[k + 1]] for k in range(nparts)])
    return shapes


def ring_area_centroid(r):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(r, r[1:]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if a == 0:
        return 0.0, r[0][0], r[0][1]
    return a / 2, cx / (6 * (a / 2)), cy / (6 * (a / 2))


def main():
    rows = read_dbf(SRC.with_suffix(".dbf"))
    shapes = read_shp(SRC.with_suffix(".shp"))
    feats = []
    for row, rings in zip(rows, shapes):
        if not rings or not row.get("S_NAME"):
            continue  # 水面調査区など名称なし
        # 最大面積の外周リングの重心をラベル位置にする
        best = max((ring_area_centroid(r) for r in rings), key=lambda t: abs(t[0]))
        name = row["S_NAME"]
        town = name.split("丁目")[0].rstrip("一二三四五六七八九十") or name
        feats.append({
            "type": "Feature",
            "properties": {"name": name, "town": town, "key": row["KEY_CODE"],
                           "label": [round(best[1], 6), round(best[2], 6)]},
            "geometry": {"type": "Polygon" if len(rings) == 1 else "MultiPolygon",
                         "coordinates": [[[round(x, 6), round(y, 6)] for x, y in r] for r in rings]
                         if len(rings) == 1 else
                         [[[[round(x, 6), round(y, 6)] for x, y in r]] for r in rings]},
        })
    (OUT / "cho.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                                ensure_ascii=False), encoding="utf-8")
    print(len(feats), "町丁目", sorted({f["properties"]["town"] for f in feats})[:60])


if __name__ == "__main__":
    main()
