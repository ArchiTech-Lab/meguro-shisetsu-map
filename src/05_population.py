"""町丁目別・年齢層別の人口（2020実績／2050・2100の3シナリオ）を計算する。
入力
  data/raw/estat/age/tblT001082C13110.txt   国勢調査2020 小地域 年齢5歳階級別（e-Stat T001082・目黒区13110）
  data/interim/cho.geojson                  町丁目ポリゴン（KEY_CODEで突合）
  ../../shinagawa-map/data/raw/ipss/suikei_kekka.xlsx   社人研 地域別将来推計（令和5年推計）目黒区13110の2020・2050
  ../../shinagawa-map/data/interim/ipss_projection.json  社人研 全国（出生中位・死亡中位）2050・2100の5歳階級別（2100は長期参考推計）
  data/interim/population_official_meguro.md の数字（区の公式推計・国調ベース基本／高位）は下の OFFICIAL に転記
出力  data/interim/population_cho.json

シナリオ（★全国の出生高位・低位の表が取得できなかったため、当初の設計から変更）
  社人研（目黒区・出生中位）／区推計・国調基本／区推計・国調高位 の3つの公式推計を2050年の入口にする。
  low ＝社人研（令和5年推計）目黒区 … 2050年総人口の最小の公式推計
  mid ＝区推計・国勢調査ベース基本推計
  high＝区推計・国勢調査ベース高位推計
  2050年＝町丁目の2020年値 × 年齢層別の伸び率（3区分は各推計の2050/2020。5〜9歳・10〜14歳・75歳以上は社人研の伸び率を
          親の区分（0〜14／65以上）の比で補正）
  2100年＝2050年値 × 全国（出生中位・死亡中位）の年齢層別変化率（2100/2050・長期参考推計）。3シナリオに共通。
  → 2100年のシナリオ差は2050年水準の差が引き継がれたものだけ。出生仮定による差は含まない。予測ではなくシナリオ。
  町丁目ごとの違い（再開発・転出入）は反映されない（全町丁目に同じ伸び率）。年齢不詳は各年齢層へ比例配分して総数に合わせる。
"""
import csv, json, re, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT.parent.parent / "shinagawa-map"
GROUPS = ["total", "u15", "a1564", "a65", "a75", "a5_9", "a10_14"]
# 区の公式推計（国調ベース）。出典＝population_official_meguro.md（区公式PDF jinko_50603.pdf p.12-13）
OFFICIAL = {
    "2020": {"u15": 31959, "a1564": 199560, "a65": 56567, "total": 288086},
    "mid": {"2050": {"u15": 30405, "a1564": 182845, "a65": 100921, "total": 314171}},
    "high": {"2050": {"u15": 52765, "a1564": 198265, "a65": 100921, "total": 351951}},
}
SCEN = {"low": "低位＝社人研（令和5年推計）目黒区", "mid": "中位＝区推計・国勢調査ベース基本", "high": "高位＝区推計・国勢調査ベース高位"}


def xlsx_rows():
    z = zipfile.ZipFile(SH / "data/raw/ipss/suikei_kekka.xlsx")
    ss = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
    sh = z.read("xl/worksheets/sheet1.xml").decode()
    for _, r in re.findall(r'<row [^>]*r="(\d+)"[^>]*>(.*?)</row>', sh, re.S):
        c = {}
        for m in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', r, re.S):
            col, attr, body = m.groups()
            v = re.search(r"<v>(.*?)</v>", body or "")
            if v:
                c[col] = ss[int(v.group(1))] if 't="s"' in attr else v.group(1)
        if c.get("A") == "13110":
            yield c


def ipss_meguro():
    cols = "GHIJKLMNOPQRSTUVWXYZ"  # 0-4 … 90-94, 95+（G..Z）
    out = {}
    for c in xlsx_rows():
        y = c["E"].replace("年", "")
        b = {i * 5: float(c[col]) for i, col in enumerate(cols)}
        out[y] = b
    return out


def groups_from_bands(b):
    s = lambda lo, hi: sum(v for k, v in b.items() if lo <= k < hi)
    u15, a1564, a65, a75 = s(0, 15), s(15, 65), s(65, 999), s(75, 999)
    return {"total": u15 + a1564 + a65, "u15": u15, "a1564": a1564, "a65": a65, "a75": a75,
            "a5_9": b.get(5, 0), "a10_14": b.get(10, 0)}


def parse_nat(d):
    b = {}
    for k, v in d.items():
        m = re.match(r"(\d+)", k)
        if m:
            b[int(m.group(1))] = b.get(int(m.group(1)), 0) + float(v)
    return b


def main():
    # 国勢調査2020 小地域
    rows = list(csv.reader(open(ROOT / "data/raw/estat/age/tblT001082C13110.txt", encoding="cp932")))[2:]
    g = lambda r, i: float(r[7 + i - 1] or 0) if r[7 + i - 1] not in ("", "-", "X") else 0.0
    # 列: 001=総数(不詳含む) 002..016=0-4…70-74 017=15歳未満 018=15-64 019=65+ 020=75+ （品川区マップと同じ）
    ward_row = rows[0]
    towns = {}
    for r in rows[1:]:
        if r[0] and r[3]:
            towns[r[0]] = r
    cho = json.loads((ROOT / "data/interim/cho.geojson").read_text(encoding="utf-8"))
    base = {}
    for f in cho["features"]:
        k = f["properties"]["key"]
        r = towns.get(k)
        if not r:
            continue
        u15, a1564, a65, a75 = g(r, 17), g(r, 18), g(r, 19), g(r, 20)
        known = u15 + a1564 + a65
        tot = g(r, 1)
        kk = tot / known if known else 1.0  # 年齢不詳を比例配分して総数に合わせる
        base[k] = {"total": tot, "u15": u15 * kk, "a1564": a1564 * kk, "a65": a65 * kk, "a75": a75 * kk,
                   "a5_9": g(r, 3) * kk, "a10_14": g(r, 4) * kk}
    S = {x: sum(b[x] for b in base.values()) for x in GROUPS}
    wt = g(ward_row, 1)
    print(f"国勢調査2020 町丁目 {len(base)}件の合計 {S['total']:,.0f}人／区全体の行 {wt:,.0f}人（差 {S['total'] - wt:+,.0f}）")

    ip = ipss_meguro()
    ig = {y: groups_from_bands(b) for y, b in ip.items()}
    print(f"社人研 目黒区 2020={ig['2020']['total']:,.0f} 2050={ig['2050']['total']:,.0f}")
    nat = json.loads((SH / "data/interim/ipss_projection.json").read_text(encoding="utf-8"))["japan"]
    n50, n100 = groups_from_bands(parse_nat(nat["2050"])), groups_from_bands(parse_nat(nat["2100"]))
    r100 = {x: n100[x] / n50[x] for x in GROUPS}
    print("全国 2100/2050 変化率", {x: round(v, 3) for x, v in r100.items()})

    # 2050/2020 伸び率（区分ごと）
    r50 = {}
    base_ip = {x: ig["2050"][x] / ig["2020"][x] for x in GROUPS}
    r50["low"] = dict(base_ip)
    for sc in ("mid", "high"):
        o20, o50 = OFFICIAL["2020"], OFFICIAL[sc]["2050"]
        par = {x: o50[x] / o20[x] for x in ("u15", "a1564", "a65")}
        r = {x: par[x] for x in ("u15", "a1564", "a65")}
        r["a5_9"] = base_ip["a5_9"] * par["u15"] / base_ip["u15"]      # 親＝0〜14歳
        r["a10_14"] = base_ip["a10_14"] * par["u15"] / base_ip["u15"]
        r["a75"] = base_ip["a75"] * par["a65"] / base_ip["a65"]        # 親＝65歳以上
        r["total"] = None
        r50[sc] = r
    towns_out, wardsum = {}, {sc: {"2020": dict(S), "2050": {}, "2100": {}} for sc in SCEN}
    for k, b in base.items():
        towns_out[k] = {"2020": {x: round(b[x], 1) for x in GROUPS}}
        for sc in SCEN:
            v50 = {x: b[x] * r50[sc][x] for x in ("u15", "a1564", "a65", "a75", "a5_9", "a10_14")}
            v50["total"] = v50["u15"] + v50["a1564"] + v50["a65"]
            v100 = {x: v50[x] * r100[x] for x in ("u15", "a1564", "a65", "a75", "a5_9", "a10_14")}
            v100["total"] = v100["u15"] + v100["a1564"] + v100["a65"]
            towns_out[k][sc] = {"2050": {x: round(v, 1) for x, v in v50.items()}, "2100": {x: round(v, 1) for x, v in v100.items()}}
    for sc in SCEN:
        for y in ("2050", "2100"):
            wardsum[sc][y] = {x: sum(t[sc][y][x] for t in towns_out.values()) for x in GROUPS}
    # 検証：町丁目の合計 vs 区全体（区全体＝区の2020実績×同じ伸び率。独立に計算）
    print("\n町丁目の合計と区全体の値の差（総数）")
    worst = 0
    ward_out = {}
    for sc in SCEN:
        ward_out[sc] = {}
        for y, rr in (("2050", r50[sc]), ("2100", None)):
            if y == "2050":
                ward_tot = sum(S[x] * rr[x] for x in ("u15", "a1564", "a65"))
            else:
                ward_tot = sum(S[x] * r50[sc][x] * r100[x] for x in ("u15", "a1564", "a65"))
            diff = wardsum[sc][y]["total"] - ward_tot
            worst = max(worst, abs(diff) / ward_tot)
            ward_out[sc][y] = round(wardsum[sc][y]["total"])
            print(f"  {sc:4s} {y}: 町丁目合計 {wardsum[sc][y]['total']:,.0f}／区全体 {ward_tot:,.0f}／差 {diff:+,.0f}（{diff / ward_tot:+.3%}）")
    d20 = S["total"] - wt
    print(f"  2020: 町丁目合計 {S['total']:,.0f}／区全体 {wt:,.0f}／差 {d20:+,.0f}（{d20 / wt:+.3%}）")
    worst = max(worst, abs(d20) / wt)
    print(f"最大の差 {worst:.3%}（目標1%以内）→ {'OK' if worst <= 0.01 else 'NG'}")
    # 公式推計との突き合わせ（2050年総人口）
    print("\n2050年 総人口の比較（人）")
    ip50 = ig["2050"]["total"]
    for sc, off in (("low", ip50), ("mid", OFFICIAL["mid"]["2050"]["total"]), ("high", OFFICIAL["high"]["2050"]["total"])):
        print(f"  {sc}: 本計算 {wardsum[sc]['2050']['total']:,.0f}／公式 {off:,.0f}／差 {wardsum[sc]['2050']['total'] - off:+,.0f}（{(wardsum[sc]['2050']['total'] - off) / off:+.2%}）")
    gap = OFFICIAL["mid"]["2050"]["total"] - ip50
    print(f"社人研（中位）と区推計（国調基本）の2050年総人口の差：{gap:,}人（{gap / ip50:.1%}）")
    out = {"scenarios": SCEN, "groups": GROUPS, "r50": {k: {x: v for x, v in d.items() if v} for k, d in r50.items()},
           "r100": r100, "ward": ward_out, "ward_2020": round(S["total"]),
           "official_2050": {"ipss_meguro_mid": ip50, "ku_mid": OFFICIAL["mid"]["2050"]["total"], "ku_high": OFFICIAL["high"]["2050"]["total"]},
           "towns": towns_out}
    (ROOT / "data/interim/population_cho.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("\n出力 data/interim/population_cho.json  町丁目", len(towns_out))


main()
