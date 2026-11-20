"""目黒区を最寄り駅（直線距離）でボロノイ分割し、駅ごとの領域・人口・施設を集計する。
実行：python3 src/06_voronoi.py（pyproj を使うため -I は付けない）
入力：N02-23（駅）・N03-23（区界）・data/interim/cho.geojson・population_cho.json・facilities.json
出力：data/interim/voronoi.json
方針
- 距離＝直線距離（EPSG:6677・平面直角IX系）。駅は同名を1点にまとめる（各路線の駅点の平均）。重みなし。
- 対象駅＝区界から2.5km以内（区の縁の地点が、遠い駅と取り違えられないように。表示用の900mより広い）。
- 領域＝区界ポリゴンを、駅の組ごとの垂直二等分線の半平面で順に切って作る（Sutherland–Hodgman法・scipy不要）。
- 町丁目の人口＝町丁目ポリゴンを同じ半平面で切った面積比で配分（面積按分）。
- 検算＝領域の面積の合計＝区界の面積、無作為の点が最寄り駅の領域に入ること。
- 駅圏から外れる面積・人口＝25m格子で最寄り駅までの距離を測り、町丁目ごとの割合で人口を配分（概算）。
"""
import json, math, random
from pathlib import Path
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
N02 = ROOT.parent / "office-location-sim/data/raw/n02/UTF-8/N02-23_Station.geojson"
N03 = ROOT.parent / "office-location-sim/data/raw/n03/N03-23_13_230101.geojson"
TO = Transformer.from_crs(4326, 6677, always_xy=True)
BACK = Transformer.from_crs(6677, 4326, always_xy=True)
BUF_M = 2500
# 統合する駅（本人指示 2026-11-18）：統合元 → 統合先。領域は和集合、人口・施設・面積は合算。距離は実際の駅で測る。
MERGE = {"池ノ上": "駒場東大前", "代々木上原": "駒場東大前", "代官山": "中目黒", "九品仏": "自由が丘",
         "東北沢": "駒場東大前", "白金台": "恵比寿", "石川台": "緑が丘", "北千束": "洗足"}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def proj(ring):
    return [TO.transform(x, y) for x, y in ring]


def area(r):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1])) / 2


def pip(pt, ring):
    x, y = pt
    ins = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            ins = not ins
    return ins


def clip(poly, a, b, c):
    """半平面 a*x+b*y <= c で多角形を切る。"""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def cell_clip(poly, i, S):
    """多角形を、駅 i が最も近い領域（半平面の共通部分）で切る。"""
    si = S[i]["xy"]
    for j, sj in enumerate(S):
        if j == i or not poly:
            continue
        a, b = sj["xy"][0] - si[0], sj["xy"][1] - si[1]
        c = (sj["xy"][0] ** 2 + sj["xy"][1] ** 2 - si[0] ** 2 - si[1] ** 2) / 2
        poly = clip(poly, a, b, c)
    return poly


def dist_to_ring(pt, ring):
    best = 1e18
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((pt[0] - x0) * dx + (pt[1] - y0) * dy) / L))
        best = min(best, math.hypot(pt[0] - x0 - t * dx, pt[1] - y0 - t * dy))
    return best


def main():
    wf = [f for f in load(N03)["features"] if f["properties"]["N03_004"] == "目黒区"]
    polys = []
    for f in wf:
        g = f["geometry"]
        for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            polys.append([proj(r) for r in p])  # [外周, 穴...]
    outers = [p[0] for p in polys]
    ward_area = sum(area(p[0]) for p in polys)  # 穴は無視（区界に穴はない想定）
    print(f"区界 {len(polys)}ポリゴン 面積 {abs(ward_area) / 1e4:,.1f}ha")
    # 駅（同名を1点に）
    byname = {}
    for f in load(N02)["features"]:
        cs = f["geometry"]["coordinates"]
        x = sum(c[0] for c in cs) / len(cs)
        y = sum(c[1] for c in cs) / len(cs)
        if 139.55 <= x <= 139.85 and 35.52 <= y <= 35.75:
            byname.setdefault(f["properties"]["N02_005"], []).append(TO.transform(x, y))
    S = []
    for name, pts in byname.items():
        xy = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        inside = any(pip(xy, o) for o in outers)
        d = 0.0 if inside else min(dist_to_ring(xy, o) for o in outers)
        if d <= BUF_M:
            lon, lat = BACK.transform(*xy)
            S.append({"name": name, "xy": xy, "lon": lon, "lat": lat, "in": inside, "d_ward": d})
    print(f"駅（区界から{BUF_M}m以内・同名は1点）{len(S)}駅")

    # 領域
    for i, s in enumerate(S):
        rings = []
        for p in polys:
            r = cell_clip(list(p[0]), i, S)
            if len(r) >= 3 and abs(area(r)) > 1:
                rings.append(r)
        s["rings"] = rings
        s["area_m2"] = sum(abs(area(r)) for r in rings)
    cells = [s for s in S if s["area_m2"] > 0]
    tot = sum(s["area_m2"] for s in cells)
    print(f"領域のある駅 {len(cells)}駅。面積の合計 {tot / 1e4:,.2f}ha／区界 {abs(ward_area) / 1e4:,.2f}ha（差 {(tot - abs(ward_area)) / abs(ward_area):+.4%}）")

    # 検算：無作為の点
    random.seed(1)
    xs = [p[0] for o in outers for p in o]
    ys = [p[1] for o in outers for p in o]
    bad, n = 0, 0
    while n < 3000:
        pt = (random.uniform(min(xs), max(xs)), random.uniform(min(ys), max(ys)))
        if not any(pip(pt, o) for o in outers):
            continue
        n += 1
        near = min(range(len(S)), key=lambda i: math.hypot(pt[0] - S[i]["xy"][0], pt[1] - S[i]["xy"][1]))
        if not any(pip(pt, r) for r in S[near]["rings"]):
            bad += 1
    print(f"検算：無作為の点 {n}個のうち、最寄り駅の領域に入らなかったもの {bad}個")

    # 町丁目の人口を面積按分
    pop = load(ROOT / "data/interim/population_cho.json")
    cho = load(ROOT / "data/interim/cho.geojson")["features"]
    keys = {"2020": ("2020", None), "low2050": ("low", "2050"), "mid2050": ("mid", "2050"), "high2050": ("high", "2050"),
            "low2100": ("low", "2100"), "mid2100": ("mid", "2100"), "high2100": ("high", "2100")}
    for s in cells:
        s["pop"] = {k: 0.0 for k in keys}
        s["pop_u15_2020"] = 0.0
        s["pop_a65_2020"] = 0.0
    towns_pts = {}  # 町丁目ごとの外周（格子の割り当て用）
    for f in cho:
        k = f["properties"]["key"]
        t = pop["towns"].get(k)
        if not t:
            continue
        g = f["geometry"]
        tps = [proj(p[0]) for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])]
        towns_pts[k] = tps
        ta = sum(abs(area(r)) for r in tps)
        for i, s in enumerate(S):
            if s["area_m2"] == 0:
                continue
            a = 0.0
            for r in tps:
                cr = cell_clip(list(r), i, S)
                if len(cr) >= 3:
                    a += abs(area(cr))
            if a <= 0:
                continue
            w = a / ta
            for kk, (sc, y) in keys.items():
                v = t["2020"]["total"] if y is None else t[sc][y]["total"]
                s["pop"][kk] += v * w
            s["pop_u15_2020"] += t["2020"]["u15"] * w
            s["pop_a65_2020"] += t["2020"]["a65"] * w
    p20 = sum(s["pop"]["2020"] for s in cells)
    print(f"人口の配分：2020年 領域の合計 {p20:,.0f}人（国勢調査の合計 {pop['ward_2020']:,}人）")

    # 施設
    fac = load(ROOT / "data/interim/facilities.json")
    for s in cells:
        s.update(fac_n=0, fac_old=0, fac_floor=0.0, fac_names=[])
    for f in fac:
        if f["lon"] is None:
            continue
        xy = TO.transform(f["lon"], f["lat"])
        s = min(cells, key=lambda c: math.hypot(xy[0] - c["xy"][0], xy[1] - c["xy"][1]))
        s["fac_n"] += 1
        s["fac_floor"] += f["floor_m2"] or 0
        s["fac_names"].append(f["name"])
        f["_vor"] = s["name"]
    # 旧耐震（03_build_map.py の classify と同じ定義を使うため、era は後段で付く。ここでは築年度のみで判定）
    for f in fac:
        if f["lon"] is None or f["built"] is None:
            continue
        old = f["built"] <= 1980
        if f["built"] == 1981:
            d = f.get("seismic_diag") or ""
            old = ("新耐震" not in d) and any(ch in d for ch in "HS") and "年度" in d
        if old:
            s = next(c for c in cells if c["name"] == f["_vor"])
            s["fac_old"] += 1

    # 格子で最寄り駅までの距離・駅圏から外れる面積と人口
    STEP = 25
    gx = [min(xs) + STEP / 2 + i * STEP for i in range(int((max(xs) - min(xs)) / STEP) + 1)]
    gy = [min(ys) + STEP / 2 + j * STEP for j in range(int((max(ys) - min(ys)) / STEP) + 1)]
    tb = {k: (min(p[0] for r in tp for p in r), max(p[0] for r in tp for p in r),
              min(p[1] for r in tp for p in r), max(p[1] for r in tp for p in r)) for k, tp in towns_pts.items()}
    cnt = {k: [0, 0, 0] for k in towns_pts}  # 全体・400m超・800m超
    far = {s["name"]: 0.0 for s in cells}
    tot_pts = [0, 0, 0]
    for x in gx:
        for y in gy:
            pt = (x, y)
            if not any(pip(pt, o) for o in outers):
                continue
            d, nm = min((math.hypot(x - c["xy"][0], y - c["xy"][1]), c["name"]) for c in cells)
            far[nm] = max(far[nm], d)
            tot_pts[0] += 1; tot_pts[1] += d > 400; tot_pts[2] += d > 800
            for k, tp in tb.items():
                if tp[0] <= x <= tp[1] and tp[2] <= y <= tp[3] and any(pip(pt, r) for r in towns_pts[k]):
                    cnt[k][0] += 1; cnt[k][1] += d > 400; cnt[k][2] += d > 800
                    break
    p_out = [0.0, 0.0]
    for k, (n0, n4, n8) in cnt.items():
        if n0:
            p_out[0] += pop["towns"][k]["2020"]["total"] * n4 / n0
            p_out[1] += pop["towns"][k]["2020"]["total"] * n8 / n0
    ward_ha = tot_pts[0] * STEP * STEP / 1e4
    gap = {"grid_m": STEP, "ward_ha_grid": round(ward_ha, 1),
           "over400_ha": round(tot_pts[1] * STEP * STEP / 1e4, 1), "over800_ha": round(tot_pts[2] * STEP * STEP / 1e4, 1),
           "over400_pop": round(p_out[0]), "over800_pop": round(p_out[1]),
           "over400_area_share": tot_pts[1] / tot_pts[0], "over800_area_share": tot_pts[2] / tot_pts[0],
           "over400_pop_share": p_out[0] / p20, "over800_pop_share": p_out[1] / p20}
    print(f"駅圏から外れる地域（25m格子の概算）：5分圏（400m）の外＝面積 {gap['over400_ha']}ha（{gap['over400_area_share']:.1%}）・人口 約{gap['over400_pop']:,}人（{gap['over400_pop_share']:.1%}）")
    print(f"                                      10分圏（800m）の外＝面積 {gap['over800_ha']}ha（{gap['over800_area_share']:.1%}）・人口 約{gap['over800_pop']:,}人（{gap['over800_pop_share']:.1%}）")

    # 隣接の長さ（統合前・提案用）：共有する辺の長さ（m）
    def shared(a, b):
        L = 0.0
        ea = [(p, q) for r in a["rings"] for p, q in zip(r, r[1:] + r[:1])]
        for r in b["rings"]:
            for p, q in zip(r, r[1:] + r[:1]):
                for u, v in ea:
                    if (math.hypot(p[0] - u[0], p[1] - u[1]) < 1 and math.hypot(q[0] - v[0], q[1] - v[1]) < 1) or \
                       (math.hypot(p[0] - v[0], p[1] - v[1]) < 1 and math.hypot(q[0] - u[0], q[1] - u[1]) < 1):
                        L += math.hypot(p[0] - q[0], p[1] - q[1])
        return L
    print("\n統合前の隣接（共有境界の長さ・長い順に上位3。統合の提案用）")
    for a_ in sorted(cells, key=lambda c: c["area_m2"]):
        if a_["area_m2"] < 400000:
            nb = sorted(((shared(a_, b_), b_["name"]) for b_ in cells if b_ is not a_), reverse=True)[:3]
            print(f"  {a_['name']:6s} {a_['area_m2'] / 1e4:5.1f}ha → " + "、".join(f"{n} {l:.0f}m" for l, n in nb if l > 0))
    # 統合
    byn = {c["name"]: c for c in cells}
    for src, dst in MERGE.items():
        a_, b_ = byn[src], byn[dst]
        b_["rings"] += a_["rings"]
        for k in ("area_m2", "pop_u15_2020", "pop_a65_2020", "fac_n", "fac_old", "fac_floor"):
            b_[k] += a_[k]
        for k in keys:
            b_["pop"][k] += a_["pop"][k]
        b_["fac_names"] += a_["fac_names"]
        b_.setdefault("members", [dst]).append(src)
        far[dst] = max(far[dst], far[src])
        b_["in"] = b_["in"] or a_["in"]
        cells.remove(a_)
    print("統合：", "、".join(f"{k}→{v}" for k, v in MERGE.items()), f"／領域数 {len(cells)}")
    # 隣接（色分け用）：頂点が1m以内で接する領域
    def near(a, b):
        return any(math.hypot(p[0] - q[0], p[1] - q[1]) < 1.0 for r1 in a["rings"] for p in r1 for r2 in b["rings"] for q in r2)
    adj = {c["name"]: set() for c in cells}
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            if near(a, b):
                adj[a["name"]].add(b["name"]); adj[b["name"]].add(a["name"])
    col = {}
    for c in sorted(cells, key=lambda c: -len(adj[c["name"]])):
        used = {col[n] for n in adj[c["name"]] if n in col}
        col[c["name"]] = next(k for k in range(20) if k not in used)
    print("色分けに使った色数（隣り合う領域が同じ色にならない）：", max(col.values()) + 1)

    feats, rows = [], []
    for c in sorted(cells, key=lambda c: -c["area_m2"]):
        ha = c["area_m2"] / 1e4
        geom = {"type": "MultiPolygon", "coordinates": [[[list(BACK.transform(x, y)) for x, y in r + r[:1]]] for r in c["rings"]]}
        row = {"name": c["name"], "in_ward": c["in"], "area_ha": round(ha, 1), "far_m": round(far[c["name"]]),
               "pop": {k: round(v) for k, v in c["pop"].items()}, "dens2020": round(c["pop"]["2020"] / ha, 1),
               "u15_2020": round(c["pop_u15_2020"]), "a65_2020": round(c["pop_a65_2020"]),
               "fac_n": c["fac_n"], "fac_old": c["fac_old"], "fac_floor": round(c["fac_floor"]),
               "lon": c["lon"], "lat": c["lat"], "color": col[c["name"]], "members": c.get("members", [c["name"]])}
        rows.append(row)
        feats.append({"type": "Feature", "properties": {"name": c["name"], "color": col[c["name"]]}, "geometry": geom})
    out = {"cells": {"type": "FeatureCollection", "features": feats}, "rows": rows, "gap": gap,
           "check": {"area_diff": (tot - abs(ward_area)) / abs(ward_area), "random_points": n, "random_bad": bad,
                     "pop2020_sum": round(p20), "n_stations": len(S), "n_cells": len(cells), "buffer_m": BUF_M}}
    (ROOT / "data/interim/voronoi.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("\n駅ごとの領域（面積の大きい順・上位12）")
    for r in rows[:12]:
        print(f"  {r['name']:8s} {r['area_ha']:6.1f}ha  人口2020 {r['pop']['2020']:6,}  2050中位 {r['pop']['mid2050']:6,}  密度{r['dens2020']:5.0f}人/ha  施設{r['fac_n']:2d}（旧耐震{r['fac_old']:2d}）  最遠{r['far_m']}m")
    print(f"\n出力 data/interim/voronoi.json（{len(rows)}領域）")


main()
