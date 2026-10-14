"""
build_prices.py
===============
【ステップ2：ふるいにかけて相場を出す】
raw_rakuten.json（生のデータ）を softs.json のルールで判定し、
rakuten_prices.json（サイトに表示する相場）を作る。

楽天APIは使わないので、ルールを直したら何回でもすぐ試せる。

使い方:
    python3 build_prices.py              … 相場を作って一覧を表示
    python3 build_prices.py fc-dq3       … そのソフトの全商品の判定結果を表示（調査用）
"""

import re, sys, json, statistics, unicodedata
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
SOFTS_PATH = HERE / "softs.json"
RAW_PATH = HERE / "raw_rakuten.json"
OUTPUT_PATH = HERE / "rakuten_prices.json"

LIMITED = re.compile(r"限定版|限定生産|初回限定|特装版|プレミアム\s*(BOX|ボックス|エディション)|コレクターズ|スペシャル\s*(BOX|ボックス|エディション)|同梱版|ツインパック", re.I)
BUDGET = re.compile(r"アルティメット\s*ヒッツ|MEGA\s*HITS|メガヒッツ|ベスト|BEST|廉価版|PlayStation\s*the\s*Best|PS\s*one\s*Books|コレクション", re.I)
DAMAGED = re.compile(r"説明書なし|説明書無|表紙なし|箱なし|箱無|ディスクのみ|ソフトのみ|カセットのみ|ROMのみ|本体のみ|ジャンク|難あり")

GROUP_LABEL = {
    "normal_good": "通常・良", "normal_damaged": "通常・難",
    "budget_good": "廉価・良", "budget_damaged": "廉価・難",
    "limited_good": "限定・良", "limited_damaged": "限定・難",
}


def norm(s: str) -> str:
    """全角→半角、いろいろな「−」を「-」にそろえる"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[‐‑‒–—―−]", "-", s)


def judge(name: str, must, ngs) -> str:
    """商品名を判定して、グループ名か「除外理由」を返す"""
    n = norm(name)
    if "中古" not in n:
        return "×中古じゃない"
    if not must.search(n):
        return "×タイトル不一致"
    for label, ng in ngs:
        m = ng.search(n)
        if m:
            return f"×除外({label}:{m.group(0)})"
    edition = "limited" if LIMITED.search(n) else "budget" if BUDGET.search(n) else "normal"
    cond = "damaged" if DAMAGED.search(n) else "good"
    return f"{edition}_{cond}"


def summarize(items: list[dict]) -> dict:
    items = sorted(items, key=lambda x: x["price"])
    prices = [x["price"] for x in items]
    return {
        "count": len(prices),
        "min": prices[0],
        "median": int(statistics.median(prices)),
        "items": [
            {"price": x["price"], "shop": x["shop"], "name": x["name"],
             "url": x["aff_url"] or x["url"], "postage_included": x["postage_included"]}
            for x in items[:3]
        ],
    }


def main(debug_ids=None):
    conf = json.loads(SOFTS_PATH.read_text(encoding="utf-8"))
    raw = {r["id"]: r for r in json.loads(RAW_PATH.read_text(encoding="utf-8"))["softs"]}
    common_ng = re.compile(conf["common_ng"], re.I)

    results = []
    for soft in conf["softs"]:
        if debug_ids and soft["id"] not in debug_ids:
            continue
        pf = conf["platforms"][soft["platform"]]
        r = raw.get(soft["id"])
        if not r:
            print(f"!! {soft['title']}: 生データがありません（fetch_raw.py を実行してください）")
            continue

        must = re.compile(soft["must"], re.I)
        ngs = [("共通", common_ng), ("機種", re.compile(pf["ng"], re.I))]
        if soft.get("ng"):
            ngs.append(("ソフト", re.compile(soft["ng"], re.I)))

        groups = {k: [] for k in GROUP_LABEL}
        if debug_ids:
            print(f"\n■ {soft['title']}（{pf['label']}） 検索語「{r['keyword']}」 {len(r['items'])}件")
        for x in r["items"]:
            g = judge(x["name"], must, ngs)
            if g in groups:
                groups[g].append(x)
            if debug_ids:
                label = GROUP_LABEL.get(g, g)
                print(f"  {label:<20} {x['price']:>6}円 | {x['name'][:60]}")

        results.append({
            "id": soft["id"],
            "title": soft["title"],
            "platform": soft["platform"],
            "platform_label": pf["label"],
            "groups": {k: summarize(v) for k, v in groups.items() if v},
            "sample_count": sum(len(v) for v in groups.values()),
        })

    if debug_ids:
        return

    # 一覧表示
    for it in results:
        s = "  ".join(f"{GROUP_LABEL[k]} {v['median']}円({v['count']})" for k, v in it["groups"].items())
        print(f"{it['title'][:16]:<16} | {s or '該当なし'}")

    OUTPUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "rakuten",
        "total": len(results),
        "items": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {OUTPUT_PATH.name} に {len(results)} 本分を書き出しました")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
