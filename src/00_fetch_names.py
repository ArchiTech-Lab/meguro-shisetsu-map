"""OSM（Overpass・GETのみ）から名称つき地物の代表点を取得し、住所のない施設の位置づけに使う。出力：data/raw/names_osm.json"""
import json, urllib.parse, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
q = ('[out:json][timeout:90];nwr["name"~"公園|コミュニティセンター|キャンパス|清掃工場|天空庭園|区民|住区|プラザ|ホーム|アパート|スクエア|ふれあい館|学習館|自転車|駐輪|浄化|川の資料館|アトラス|目黒"]'
     '(35.600,139.640,35.670,139.720);out center tags;')
url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(q)
req = urllib.request.Request(url, headers={"User-Agent": "meguro-shisetsu-map/0.1 (research; read-only)", "Accept": "*/*"})
d = json.load(urllib.request.urlopen(req, timeout=120))
out = []
for e in d["elements"]:
    c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
    if c:
        out.append({"name": e["tags"]["name"], "lon": c["lon"], "lat": c["lat"], "tags": {k: e["tags"].get(k) for k in ("leisure", "amenity", "building")}})
(ROOT / "data/raw/names_osm.json").write_text(json.dumps(out, ensure_ascii=False))
print(len(out))
