"""意見の方針の検討用：各駅域（ボロノイ）で、区立小中学校が駅徒歩10分（直線800m）以内にあるかを調べ、
徒歩10分超の学校には、同じ駅域の区有地（他の区施設の敷地）から移転先の候補を挙げる。
実行：python3 src/07_school_access.py（pyproj使用・-I なし）
入力：facilities.json（区立小中学校＝名称に「小学校」「中学校」・区有地）・voronoi.json（駅域）・school_districts.geojson（学区R3）
出力：data/interim/school_access.json、docs の md は手で書かず、この出力を元にする（数字は手で写さない）
方針：距離は直線（駅圏の円と同じ前提）。駅＝その学校が属する駅域の駅（統合した駅域は、統合元の駅も含めて最も近い駅）。
"""
import json, math
from pathlib import Path
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
TO = Transformer.from_crs(4326, 6677, always_xy=True)
WALK = 800  # 徒歩10分（80m/分）
N02 = ROOT.parent / "office-location-sim/data/raw/n02/UTF-8/N02-23_Station.geojson"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def pip(pt, ring):
    x, y = pt
    ins = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            ins = not ins
    return ins


def in_geom(pt, g):
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    return any(pip(pt, p[0]) for p in polys)


def main():
    vor = load(ROOT / "data/interim/voronoi.json")
    members = {}  # 駅 → 駅域（統合先）
    for r in vor["rows"]:
        for m in r["members"]:
            members[m] = r["name"]
    # 駅（同名は1点）
    by = {}
    for f in load(N02)["features"]:
        cs = f["geometry"]["coordinates"]
        x, y = sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs)
        by.setdefault(f["properties"]["N02_005"], []).append(TO.transform(x, y))
    st = {n: (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for n, ps in by.items() if n in members}

    fac = load(ROOT / "data/interim/facilities.json")
    dist = {f["properties"]["name"]: f for f in load(ROOT / "data/interim/school_districts.geojson")["features"]}
    schools, others = [], []
    for f in fac:
        if f["lon"] is None:
            continue
        xy = TO.transform(f["lon"], f["lat"])
        nm = f["name"]
        near = min(st, key=lambda n: math.hypot(xy[0] - st[n][0], xy[1] - st[n][1]))
        d = math.hypot(xy[0] - st[near][0], xy[1] - st[near][1])
        rec = {"name": nm, "kind": f["kind"], "site_m2": f["site_m2"], "floor_m2": f["floor_m2"], "built": f["built"],
               "owner_land": f["owner_land"], "precision": f["precision"], "lon": f["lon"], "lat": f["lat"], "xy": xy,
               "station": near, "area": members[near], "dist_m": round(d), "walk_min": math.ceil(d / 80)}
        if (nm.endswith("小学校") or nm.endswith("中学校")) and "内" not in nm:
            rec["school"] = "小" if nm.endswith("小学校") else "中"
            schools.append(rec)
        else:
            others.append(rec)
    # 学区（令和3年度の学区）。校名は「緑ヶ丘小学校」と学区データの表記がずれる場合があるため、点が入る学区で判定
    for s in schools:
        s["district"] = next((k for k, g in dist.items() if g["properties"]["kind"] == s["school"] and in_geom(s["xy"], g["geometry"]) ), None)
    # 目安の校地面積＝現在の区立学校の最小値（小・中別）
    minsite = {k: min(s["site_m2"] for s in schools if s["school"] == k and s["site_m2"]) for k in ("小", "中")}
    far = [s for s in schools if s["dist_m"] > WALK]
    print(f"区立小中学校 {len(schools)}校（座標あり）。駅から直線{WALK}m超 {len(far)}校")
    print("校地面積の最小（目安）：小", round(minsite["小"]), "㎡／中", round(minsite["中"]), "㎡")
    for s in sorted(schools, key=lambda s: -s["dist_m"]):
        print(f"  {s['name']:10s} {s['school']} 最寄り{s['station']:6s} 駅域={s['area']:10s} {s['dist_m']:5d}m(徒歩約{s['walk_min']}分) 校地{round(s['site_m2'] or 0):6,}㎡ 築{s['built']:.0f}")

    # 移転先の候補：同じ駅域の区有地（区施設の敷地）で、駅から800m以内、学校以外、敷地が目安以上
    cand = []
    for o in others:
        if not (o["owner_land"] or "").startswith("目黒区") or not o["site_m2"]:
            continue
        cand.append(o)
    out_rows = []
    print("\n徒歩10分超の学校 → 同じ駅域で駅から800m以内の区有地（敷地が現校地の最小以上）")
    for s in sorted(far, key=lambda s: -s["dist_m"]):
        need = minsite[s["school"]]
        cs = [c for c in cand if c["area"] == s["area"] and c["dist_m"] <= WALK and c["site_m2"] >= need]
        # 近い駅域でも候補になりうる（学区をまたがない移転）ため、同じ学区内の候補を優先
        cs.sort(key=lambda c: c["dist_m"])
        # 第2候補：駅域にかかわらず、駅から800m以内・現校から1,000m以内（通学圏をおおむね保つ）・敷地が目安以上の区有地
        c2 = []
        for c in cand:
            if c in cs or c["dist_m"] > WALK or c["site_m2"] < need:
                continue
            dd = math.hypot(c["xy"][0] - s["xy"][0], c["xy"][1] - s["xy"][1])
            if dd <= 1000:
                c2.append((dd, c))
        c2.sort(key=lambda t: t[0])
        out_rows.append({"school": s["name"], "kind": s["school"], "station": s["station"], "area": s["area"], "dist_m": s["dist_m"],
                         "site_m2": s["site_m2"], "need_m2": need, "cands": [{k: c[k] for k in ("name", "site_m2", "built", "dist_m", "owner_land", "precision", "station")} for c in cs],
                         "cands2": [dict({k: c[k] for k in ("name", "site_m2", "built", "dist_m", "station", "area")}, from_school_m=round(dd)) for dd, c in c2]})
        print(f"- {s['name']}（{s['area']}域・{s['dist_m']}m・校地{round(s['site_m2']):,}㎡）：" + ("、".join(f"{c['name']}（{round(c['site_m2']):,}㎡・{c['dist_m']}m・築{c['built']:.0f}）" for c in cs[:6]) or "候補なし（同じ駅域・800m以内に該当する区有地がない）") + ("\n    ［他の駅域・現校から1km以内］" + "、".join(f"{c['name']}（{round(c['site_m2']):,}㎡・{c['area']}域{c['dist_m']}m・現校から{round(dd)}m）" for dd, c in c2[:6]) if c2 else ""))
    # 駅域ごとの集計
    print("\n駅域ごとの区立小中学校")
    rows = []
    for r in vor["rows"]:
        ss = [s for s in schools if s["area"] == r["name"]]
        ok = [s for s in ss if s["dist_m"] <= WALK]
        rows.append({"area": r["name"], "n": len(ss), "within": len(ok), "beyond": len(ss) - len(ok),
                     "schools": [f"{s['name']}({s['dist_m']}m)" for s in ss], "pop2020": r["pop"]["2020"], "u15": r["u15_2020"]})
        print(f"  {r['name']:8s} 校{len(ss)} 徒歩10分以内{len(ok)} 超{len(ss) - len(ok)}  0〜14歳2020 {r['u15_2020']:,}人  " + "、".join(rows[-1]["schools"]))
    Path(ROOT / "data/interim/school_access.json").write_text(json.dumps(
        {"walk_m": WALK, "min_site": minsite, "schools": [{k: v for k, v in s.items() if k != "xy"} for s in schools],
         "far": out_rows, "areas": rows}, ensure_ascii=False), encoding="utf-8")


main()
