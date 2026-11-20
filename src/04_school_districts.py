"""国土数値情報 A27-21（小学校区）・A32-21（中学校区）の東京都分から目黒区分を取り出し、GeoJSON にする。
校名は学区データの属性（A27_004／A32_004）。学校の点（P29-21）と校名で照合し、照合できない学区を出力する。
入力：data/raw/a27/A27-21_13.geojson・data/raw/a32/A32-21_13.geojson・data/raw/p29/P29-21_13.geojson
出力：data/interim/school_districts.geojson（properties: kind=小|中, name, addr, setter, school_lon/lat）
令和3年度時点のデータ。現行の学区との差は data/interim/school_districts_check.md を参照。
中学校は令和7年4月に2件の統合（第七＋第九→目黒南、第八＋第十一→目黒西）があったため、属性 now に現行校名を付ける
（目黒西＝旧2校区の合算【確】、目黒南＝旧2校区の合算【推測】）。小学校は変更が見つからなかった【未確認】。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def r6(geom):
    def ring(r):
        return [[round(x, 6), round(y, 6)] for x, y, *_ in r]
    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring(r) for r in geom["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[ring(r) for r in p] for p in geom["coordinates"]]}


MERGED_R7 = {"第七中学校": "目黒南中学校", "第九中学校": "目黒南中学校",
             "第八中学校": "目黒西中学校", "第十一中学校": "目黒西中学校"}


def main():
    schools = {}
    for f in load(RAW / "p29/P29-21_13.geojson")["features"]:
        p = f["properties"]
        if "目黒区" in p["P29_005"] and p["P29_003"] in (16001, 16002):
            schools[p["P29_004"]] = f["geometry"]["coordinates"][:2]
    feats, unmatched = [], []
    for kind, pre, path in (("小", "A27", "a27/A27-21_13.geojson"), ("中", "A32", "a32/A32-21_13.geojson")):
        n = 0
        for f in load(RAW / path)["features"]:
            p = f["properties"]
            if p[f"{pre}_001"] != "13110":
                continue
            name = p[f"{pre}_004"]
            pt = schools.get(name)
            if pt is None:
                unmatched.append(f"{kind}:{name}")
            feats.append({"type": "Feature",
                          "properties": {"kind": kind, "name": name, "now": MERGED_R7.get(name, name) if kind == "中" else name,
                                         "addr": p[f"{pre}_005"], "setter": p[f"{pre}_002"],
                                         "school_lon": pt[0] if pt else None, "school_lat": pt[1] if pt else None},
                          "geometry": r6(f["geometry"])})
            n += 1
        print(f"{kind}学校区 {n} 区域")
    out = ROOT / "data/interim/school_districts.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    print("令和7年4月の統合を反映した現行の中学校区：", sorted({f["properties"]["now"] for f in feats if f["properties"]["kind"] == "中"}))
    print("学校の点（P29）と校名を照合できなかった学区：", unmatched or "なし")
    print(out)


main()
