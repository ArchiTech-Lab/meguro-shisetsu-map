"""施設（施設データ集R6・198棟）に住所を付け、国土地理院の住所検索（GETのみ）で座標化する。
住所＝固定資産台帳R7の所在地を、名称の完全一致→部分一致で突き合わせる。公共施設の所在地であり個人情報ではない。
出力：data/interim/facilities.json（座標なしは lon/lat=null・precision="none"）、data/raw/gsi_cache.json
"""
import csv, json, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "meguro-pubcome-shisetsu"
CACHE = ROOT / "data/raw/gsi_cache.json"
OUT = ROOT / "data/interim/facilities.json"


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def gsi(q, cache):
    if q in cache:
        return cache[q]
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(q)
    for _ in range(3):
        try:
            r = json.load(urllib.request.urlopen(url, timeout=20))
            break
        except Exception:
            time.sleep(2)
    else:
        return None
    time.sleep(0.3)
    cache[q] = r[0]["geometry"]["coordinates"] if r else None
    return cache[q]


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return None


def main():
    fac = rd(SRC / "facilities_ownership_R6.csv")
    led = [r for r in rd(SRC / "owned_land_buildings_R7.csv") if r["勘定科目名称"].startswith("事業用")]
    byname = {}
    for r in led:
        byname.setdefault(r["資産名称"], []).append(r)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    out = []
    for r in fac:
        nm = r["名称"]
        rows, how = byname.get(nm), "exact"
        if not rows:
            base = nm.split("（")[0]
            cand = [k for k in byname if base and (base in k or k in base) and len(k) >= 4]
            rows, how = (byname[cand[0]], "partial:" + cand[0]) if cand else (None, "none")
        addr = rows[0]["所在地"] if rows else None
        book = sum(num(x["簿価"]) or 0 for x in rows) if rows else None
        xy = gsi("東京都目黒区" + addr, cache) if addr else None
        out.append({
            "id": r["建物番号"], "name": nm, "dept": r["所管課"], "parts": r["構成施設"],
            "kind": r["施設形態"], "owner": r["所有者"], "owner_land": r["所有者2"],
            "structure": r["構造"], "seismic_diag": r["耐震診断"], "seismic_retrofit": r["耐震補強"],
            "built": num(r["建築年度(西暦）"]), "floor_m2": num(r["延床面積"]), "site_m2": num(r["面積"]),
            "zone": r["用途地域"], "far": num(r["容積率１"]), "bcr": num(r["建ぺい率１"]),
            "depr": num(r["有形固定資産減価償却率"]), "address": addr, "match": how,
            "lon": xy[0] if xy else None, "lat": xy[1] if xy else None,
            "precision": "banchi" if xy else "none", "book_value_yen": book,
        })
    # 住所なし・座標なしの施設は OSM の名称で照合（公園名・施設名の部分一致）。精度＝"osm"（建物でなく公園・施設の代表点）
    import re
    osm = json.loads((ROOT / "data/raw/names_osm.json").read_text())
    for o in out:
        if o["lon"]:
            continue
        base = re.sub(r"（.*?）", "", o["name"])
        key = re.sub(r"(備蓄倉庫|管理棟|管理事務所|詰所|和館|動物舎|自然観察舎|児童交通施設|庭球場|古民家|本館|別館|質)$", "", base)
        keys = [base, key] if len(key) >= 3 else [base]
        for k in keys:
            hit = [x for x in osm if k in x["name"]]
            if hit:
                hit.sort(key=lambda x: len(x["name"]))
                o["lon"], o["lat"], o["precision"], o["match"] = hit[0]["lon"], hit[0]["lat"], "osm", "osm:" + hit[0]["name"]
                break
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    ok = sum(1 for o in out if o["lon"])
    print("osm照合:", [(o["name"], o["match"]) for o in out if o["precision"] == "osm"])
    print(f"{ok}/{len(out)} 件を座標化。未配置：", [o["name"] for o in out if not o["lon"]])


main()
