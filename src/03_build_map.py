"""目黒区 公共施設マップ（HTML 1ファイル）を生成する。
入力：data/interim/cho.geojson（町丁目）・facilities.json（施設・座標つき）
      data/interim/school_districts.geojson（04_school_districts.py）
      data/raw/roads_osm.json（OSM道路・表示用）・p29/（国土数値情報 学校P29-21）
      ../office-location-sim/data/raw/n02（駅・路線）・n03（区界）
出力：out/meguro_shisetsu_map.html
駅＝区界ポリゴンから900m以内（区内を含む）。駅圏＝駅からの直線距離の円（80m/分：5分＝400m、10分＝800m）。
施設の築年区分（era）：old＝旧耐震（〜1980年度＋1981年度で耐震診断を実施したもの）／r2037＝新耐震で2037年に
RC法定耐用年数47年に達する（〜1990年度）／new＝1991年度〜／na＝不明。1981年度は「耐震診断」列で判定：
「新耐震以降」→新耐震、診断年度あり→旧耐震（新耐震なら診断不要のため）、「未」等→判定不能＝新耐震扱い（注記）。
"""
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N02 = ROOT.parent.parent / "office-location-sim/data/raw/n02/UTF-8"
N03 = ROOT.parent.parent / "office-location-sim/data/raw/n03/N03-23_13_230101.geojson"
P29 = ROOT / "data/raw/p29/P29-21_13.geojson"
BBOX = (139.640, 35.600, 139.720, 35.670)  # 道路・路線の表示範囲（道路取得範囲と同じ）
STATION_BUF_M = 900
RAIL_BBOX = (139.630, 35.580, 139.740, 35.680)  # 区界＋900m の駅を覆う路線の表示範囲（余裕あり）
LAT0 = 35.635
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110950


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def mdist(a, b):
    return math.hypot((a[0] - b[0]) * KX, (a[1] - b[1]) * KY)


def pip(pt, ring):
    x, y = pt
    ins = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            ins = not ins
    return ins


def ward():
    fs = [f for f in load(N03)["features"] if f["properties"]["N03_004"] == "目黒区"]
    rings, polys = [], []
    for f in fs:
        g = f["geometry"]
        ps = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for p in ps:
            polys.append(p)
            rings.append(p[0])
    return rings, {"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": polys}}


def inward(pt, rings):
    return any(pip(pt, r) for r in rings)


def stations(rings):
    byname = {}
    for f in load(N02 / "N02-23_Station.geojson")["features"]:
        cs = f["geometry"]["coordinates"]
        x = sum(c[0] for c in cs) / len(cs)
        y = sum(c[1] for c in cs) / len(cs)
        if not (139.60 <= x <= 139.80 and 35.57 <= y <= 35.70):
            continue  # 粗い前処理。採否は下で区界からの距離で決める
        p = f["properties"]
        s = byname.setdefault(p["N02_005"], {"name": p["N02_005"], "pts": [], "lines": set()})
        s["pts"].append((x, y))
        s["lines"].add(f'{p["N02_003"]}（{p["N02_004"]}）')
    out = []
    for s in byname.values():
        x = sum(p[0] for p in s["pts"]) / len(s["pts"])
        y = sum(p[1] for p in s["pts"]) / len(s["pts"])
        inn = inward((x, y), rings)
        d = 0.0 if inn else dist_to_rings((x, y), rings)
        if d > STATION_BUF_M:
            continue
        out.append({"name": s["name"], "lon": round(x, 6), "lat": round(y, 6), "lines": sorted(s["lines"]),
                    "in": inn, "d_ward_m": round(d)})
    out.sort(key=lambda s: (not s["in"], s["d_ward_m"], s["name"]))
    return out


def dist_to_rings(pt, rings):
    """点から区界（外周リング）までの最短距離 m（局所平面近似）。"""
    px, py = pt
    best = 1e18
    for r in rings:
        for (x0, y0), (x1, y1) in zip(r, r[1:]):
            ax, ay = (x0 - px) * KX, (y0 - py) * KY
            bx, by = (x1 - px) * KX, (y1 - py) * KY
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = 0 if L == 0 else max(0, min(1, -(ax * dx + ay * dy) / L))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def rail():
    feats = []
    for f in load(N02 / "N02-23_RailroadSection.geojson")["features"]:
        if any(RAIL_BBOX[0] <= c[0] <= RAIL_BBOX[2] and RAIL_BBOX[1] <= c[1] <= RAIL_BBOX[3] for c in f["geometry"]["coordinates"]):
            p = f["properties"]
            feats.append({"type": "Feature", "properties": {"line": p["N02_003"], "op": p["N02_004"]},
                          "geometry": {"type": "LineString",
                                       "coordinates": [[round(x, 6), round(y, 6)] for x, y in f["geometry"]["coordinates"]]}})
    return {"type": "FeatureCollection", "features": feats}


def roads(rings):
    """表示用の道路（区内に1点でもかかる way）。徒歩圏の計算には使わない。"""
    major = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
             "primary_link", "secondary_link", "tertiary_link"}
    out = {"major": [], "minor": []}
    for w in load(ROOT / "data/raw/roads_osm.json")["elements"]:
        ks = [[round(p["lon"], 6), round(p["lat"], 6)] for p in w["geometry"]]
        if any(inward(k, rings) for k in ks):
            hw = w["tags"]["highway"]
            out["major" if hw in major else "minor"].append({"type": "Feature",
                "properties": {"hw": hw, "name": w["tags"].get("name", "")},
                "geometry": {"type": "LineString", "coordinates": ks}})
    return out


def schools():
    pub_no = ("学園", "星美", "日本大学", "日本工業大学", "多摩大学", "目黒学院", "八雲学園", "トキワ松", "自由ヶ丘学園")
    out = []
    for f in load(P29)["features"]:
        p = f["properties"]
        if "目黒区" not in p["P29_005"] or p["P29_003"] not in (16001, 16002, 16003):
            continue
        kind = {16001: "小学校", 16002: "中学校", 16003: "中等教育学校"}[p["P29_003"]]
        x, y = f["geometry"]["coordinates"][:2]
        name = p["P29_004"]
        pub = not any(k in name for k in pub_no)
        out.append({"name": name, "kind": kind, "addr": p["P29_005"], "lon": round(x, 6), "lat": round(y, 6), "public": pub})
    return out


def classify(fac):
    """築年区分を付け、区分別の棟数・延床合計を返す（凡例はこの値をそのまま使う）。"""
    import re
    for f in fac:
        y, f["era_note"] = f["built"], ""
        if y is None:
            f["era"] = "na"
        elif y <= 1980:
            f["era"] = "old"
        elif y == 1981:
            d = f.get("seismic_diag") or ""
            if "新耐震" in d:
                f["era"] = "r2037"; f["era_note"] = "1981年度：耐震診断列＝新耐震以降"
            elif re.search(r"[HS]\d+年度", d):
                f["era"] = "old"; f["era_note"] = f"1981年度：耐震診断を実施（{d}）→旧耐震と判定"
            else:
                f["era"] = "r2037"; f["era_note"] = f"1981年度：耐震診断＝{d or '記載なし'}で判定不能→新耐震扱い"
        elif y <= 1990:
            f["era"] = "r2037"
        else:
            f["era"] = "new"
    stats = {}
    for k in ("old", "r2037", "new", "na"):
        g = [f for f in fac if f["era"] == k]
        stats[k] = {"n": len(g), "floor_m2": round(sum(f["floor_m2"] or 0 for f in g)),
                    "n_mapped": sum(1 for f in g if f["lon"] is not None)}
    return stats


def polys_of(g):
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]


def in_geom(pt, g):
    return any(pip(pt, poly[0]) and not any(pip(pt, h) for h in poly[1:]) for poly in polys_of(g))


def district_table():
    """町丁目の中心点（ラベル位置）がどの学区に入るかで割り当て、学区別の年少人口を集計する。
    小学校区＝5〜9歳、中学校区＝10〜14歳。境界をまたぐ町丁目（外周の頂点が別の学区に入る）を数える。"""
    pop = load(ROOT / "data/interim/population_cho.json")
    cho = load(ROOT / "data/interim/cho.geojson")["features"]
    dists = load(ROOT / "data/interim/school_districts.geojson")["features"]
    rows, un, cross = [], {"小": [], "中": []}, {"小": [], "中": []}
    asg = {"小": {}, "中": {}}
    for f in cho:
        k, nm = f["properties"]["key"], f["properties"]["name"]
        if k not in pop["towns"]:
            continue
        c = f["properties"]["label"]
        for kind in ("小", "中"):
            hit = [d for d in dists if d["properties"]["kind"] == kind and in_geom(c, d["geometry"])]
            if not hit:
                un[kind].append(nm)
                continue
            asg[kind][k] = hit[0]["properties"]["name"]
            ring = polys_of(f["geometry"])[0][0]
            smp = ring[:: max(1, len(ring) // 16)]
            cnt = {}
            for v in smp:
                for d in dists:
                    if d["properties"]["kind"] == kind and in_geom(v, d["geometry"]):
                        cnt[d["properties"]["name"]] = cnt.get(d["properties"]["name"], 0) + 1
            if any(n != hit[0]["properties"]["name"] and c >= max(2, 0.25 * len(smp)) for n, c in cnt.items()):
                cross[kind].append(nm)
    for d in dists:
        kind, name = d["properties"]["kind"], d["properties"]["name"]
        key = "a5_9" if kind == "小" else "a10_14"
        ks = [k for k, v in asg[kind].items() if v == name]
        row = {"kind": kind, "name": name, "now": d["properties"].get("now", name), "towns": len(ks),
               "v2020": round(sum(pop["towns"][k]["2020"][key] for k in ks))}
        for sc in pop["scenarios"]:
            for y in ("2050", "2100"):
                row[f"{sc}_{y}"] = round(sum(pop["towns"][k][sc][y][key] for k in ks))
        rows.append(row)
    print("学区割り当て：割り当てできなかった町丁目 小=", un["小"] or "なし", "／中=", un["中"] or "なし")
    print("境界をまたぐ可能性のある町丁目（中心点の学区に全量を割り当て）：小", len(cross["小"]), "／中", len(cross["中"]))
    for kind in ("小", "中"):
        ts = [r for r in rows if r["kind"] == kind]
        print(f"  {kind}学校区 計 2020={sum(r['v2020'] for r in ts):,}", {sc: (sum(r[f'{sc}_2050'] for r in ts), sum(r[f'{sc}_2100'] for r in ts)) for sc in pop["scenarios"]})
    return pop, {"rows": rows, "unassigned": un, "cross": cross}


def cho_with_area():
    """町丁目に面積（ha・局所平面近似。外周－穴）を付ける。人口密度の表示用。"""
    d = load(ROOT / "data/interim/cho.geojson")
    def ring_a(r):
        return sum((x0 * KX) * (y1 * KY) - (x1 * KX) * (y0 * KY) for (x0, y0), (x1, y1) in zip(r, r[1:])) / 2
    for f in d["features"]:
        a = sum(abs(ring_a(p[0])) - sum(abs(ring_a(h)) for h in p[1:]) for p in polys_of(f["geometry"]))
        f["properties"]["ha"] = round(a / 10000, 2)
    print("町丁目の面積合計", round(sum(f["properties"]["ha"] for f in d["features"]), 1), "ha（目黒区の公表面積 約1,467ha）")
    return d


def main():
    rings, wardf = ward()
    sts = stations(rings)
    fac = load(ROOT / "data/interim/facilities.json")
    # 区外（県・世田谷区）・非公開の住所は、住所検索が同じ代表点（中目黒付近）に落とすため未配置にする
    for f in fac:
        a = f.get("address") or ""
        if f.get("lon") is not None and ("県" in a or "世田谷区" in a or "非公開" in a):
            f["lon"] = f["lat"] = None
            f["precision"] = None
    stats = classify(fac)
    pop, dtable = district_table()
    rd = roads(rings)
    data = {
        "ward": wardf,
        "cho": cho_with_area(),
        "rail": rail(),
        "stations": sts,
        "roads": rd,
        "districts": load(ROOT / "data/interim/school_districts.geojson"),
        "schools": schools(),
        "fac": fac,
        "era_stats": stats,
        "pop": pop,
        "dtable": dtable,
        "vor": load(ROOT / "data/interim/voronoi.json"),
        "redev": load(ROOT / "data/manual/redev_polygons.geojson"),
    }
    tpl = (ROOT / "src/template.html").read_text(encoding="utf-8")
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = ROOT / "out/meguro_shisetsu_map.html"
    html = tpl.replace("/*DATA*/", "const D=" + js + ";")
    html = html.replace("/*REDEV*/", (ROOT / "src/redev.js").read_text(encoding="utf-8"))
    out.write_text(html, encoding="utf-8")
    print(out, round(out.stat().st_size / 1e6, 2), "MB",
          "駅", len(sts), "道路 主/細", len(rd["major"]), len(rd["minor"]),
          "学区", len(data["districts"]["features"]), "学校", len(data["schools"]))
    lab = {"old": "旧耐震（〜1980年度＋1981年度の判定分）", "r2037": "新耐震で2037年に47年（〜1990年度）", "new": "1991年度〜", "na": "不明"}
    for k, v in stats.items():
        print(f"区分 {lab[k]}：{v['n']}棟（うち地図に配置 {v['n_mapped']}）延床 {v['floor_m2']:,}㎡")
    print("1981年度の判定：", [(f["name"], f["era"], f["era_note"]) for f in fac if f["built"] == 1981])
    print("駅一覧（区内→区外は区界からの距離m）：", "、".join(s["name"] + ("" if s["in"] else f"({s['d_ward_m']})") for s in sts))


main()
