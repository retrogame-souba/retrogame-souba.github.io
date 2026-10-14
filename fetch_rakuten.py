"""
fetch_rakuten.py
================
softs.json に書いたソフトを、楽天市場APIで1本ずつ調べて
「版（通常版／廉価版）× 状態（良／説明書なし等）」ごとの相場を出す。

使い方:
    source ~/.rakuten_env && python3 fetch_rakuten.py
出力:
    rakuten_prices.json（このファイルと同じフォルダ）
"""

import os, re, json, time, statistics, unicodedata, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
SOFTS_PATH = HERE / "softs.json"
OUTPUT_PATH = HERE / "rakuten_prices.json"

SITE = "https://retrogame-souba.github.io"
API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
WAIT_SEC = 1.5  # 楽天APIへの間隔（1秒1回まで）
MAX_PAGES = 3   # 1本のソフトにつき、最大何ページ（30件ずつ）見るか
ENOUGH = 10     # 採用がこの件数に届いたら、次のページは見ない

BUDGET = re.compile(r"アルティメット\s*ヒッツ|MEGA\s*HITS|メガヒッツ|ベスト|BEST|廉価版|PlayStation\s*the\s*Best|PS\s*one\s*Books|コレクション", re.I)
DAMAGED = re.compile(r"説明書なし|説明書無|表紙なし|箱なし|箱無|ディスクのみ|ソフトのみ|カセットのみ|ROMのみ|本体のみ|ジャンク|難あり")


def norm(s: str) -> str:
    """全角→半角、いろいろな「−」を「-」にそろえる"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[‐‑‒–—―−]", "-", s)


def search(keyword: str, ng_keyword: str = "", page: int = 1) -> list[dict]:
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "affiliateId": os.environ.get("RAKUTEN_AFFILIATE_ID", ""),
        "keyword": keyword,
        "hits": 30,
        "page": page,
        "sort": "+itemPrice",
        "availability": 1,  # 在庫ありのみ
        "format": "json",
        "formatVersion": 2,
    }
    if ng_keyword:
        params["NGKeyword"] = ng_keyword  # 検索の時点で外す言葉
    req = urllib.request.Request(
        API_URL + "?" + urllib.parse.urlencode(params),
        headers={"Referer": SITE + "/", "Origin": SITE, "User-Agent": "retrogame-souba/0.1"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("Items", [])


def summarize(items: list[dict]) -> dict:
    prices = [x["itemPrice"] for x in items]
    return {
        "count": len(prices),
        "min": min(prices),
        "median": int(statistics.median(prices)),
        "items": [
            {
                "price": x["itemPrice"],
                "shop": x["shopName"],
                "name": x["itemName"],
                "url": x.get("affiliateUrl") or x["itemUrl"],
                "postage_included": x.get("postageFlag") == 0,
            }
            for x in items[:3]  # 安い順に3件だけ保存
        ],
    }


def main():
    conf = json.loads(SOFTS_PATH.read_text(encoding="utf-8"))
    platforms = conf["platforms"]
    common_ng = re.compile(conf["common_ng"], re.I)

    results = []
    for i, soft in enumerate(conf["softs"], 1):
        pf = platforms[soft["platform"]]
        keyword = " ".join(x for x in [pf["keyword"], soft["keyword"], "中古"] if x)
        must = re.compile(soft["must"], re.I)
        ngs = [common_ng, re.compile(pf["ng"], re.I)]
        if soft.get("ng"):
            ngs.append(re.compile(soft["ng"], re.I))

        print(f"[{i}/{len(conf['softs'])}] {soft['title']}（{pf['label']}）… ", end="", flush=True)
        # 楽天のNGKeywordは128文字（バイト）未満まで。ソフト用→機種用の順に、入るぶんだけ使う
        ng_words = (soft.get("api_ng", "") + " " + pf.get("api_ng", "")).split()
        ng_keyword = ""
        for w in ng_words:
            cand = (ng_keyword + " " + w).strip()
            if len(cand.encode("utf-8")) >= 128:
                break
            ng_keyword = cand
        groups = {"normal_good": [], "normal_damaged": [], "budget_good": [], "budget_damaged": []}
        fetched, total, failed = 0, 0, False
        # 採用が少ないときは、次のページ（31件目〜）も見に行く（最大MAX_PAGESページ）
        for page in range(1, MAX_PAGES + 1):
            try:
                items = search(keyword, ng_keyword, page)
            except urllib.error.HTTPError as e:
                print("エラー", e.code, e.read().decode()[:200])
                failed = True
                break
            except Exception as e:
                print("エラー", e)
                failed = True
                break
            finally:
                time.sleep(WAIT_SEC)

            fetched += len(items)
            for it in items:
                name = norm(it["itemName"])
                if "中古" not in name:
                    continue
                if not must.search(name) or any(ng.search(name) for ng in ngs):
                    continue
                edition = "budget" if BUDGET.search(name) else "normal"
                cond = "damaged" if DAMAGED.search(name) else "good"
                groups[f"{edition}_{cond}"].append(it)
                total += 1

            if total >= ENOUGH or len(items) < 30:
                break
        if failed:
            continue

        for v in groups.values():
            v.sort(key=lambda x: x["itemPrice"])
        print(f"{fetched}件中 {total}件採用")

        results.append({
            "id": soft["id"],
            "title": soft["title"],
            "platform": soft["platform"],
            "platform_label": pf["label"],
            "groups": {k: summarize(v) for k, v in groups.items() if v},
            "sample_count": total,
        })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "rakuten",
        "total": len(results),
        "items": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {OUTPUT_PATH} に {len(results)} 本分を書き出しました")


if __name__ == "__main__":
    main()
