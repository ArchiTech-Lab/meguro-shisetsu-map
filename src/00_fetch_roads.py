"""OSM（Overpass API・GETのみ）から目黒区周辺（bbox・描画時に区界で絞る）の道路を取得する。出力：data/raw/roads_osm.json"""
import json, urllib.parse, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
q = ('[out:json][timeout:90];'
     'way(35.600,139.640,35.670,139.720)["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|[a-z]+_link)$"];out geom tags;')
url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(q)
req = urllib.request.Request(url, headers={"User-Agent": "meguro-shisetsu-map/0.1 (research; read-only)", "Accept": "*/*"})
d = json.load(urllib.request.urlopen(req, timeout=120))
(ROOT / "data/raw/roads_osm.json").write_text(json.dumps(d, ensure_ascii=False))
from collections import Counter
print(len(d["elements"]), Counter(e["tags"]["highway"] for e in d["elements"]))
