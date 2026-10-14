"""
fetch_bookoff.py
================
ブックオフ楽天市場店（bookoffonline）のレトロゲームの在庫を、機種ごとに全部取得して
raw_bookoff.json に保存する（ミニPCの中だけに置く。GitHubには上げない）。

楽天APIは1つの検索条件につき3,000件までしか取れないので、
件数が多い検索は「価格帯」で自動的に分けて取得する。

使い方:
    source ~/.rakuten_env && python3 fetch_bookoff.py
"""

import os, re, json, time, collections, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
RAW_PATH = HERE / "raw_bookoff.json"

SITE = "https://retrogame-souba.github.io"
API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
SHOP = "bookoffonline"
WAIT_SEC = 1.5
LIMIT = 3000        # 楽天APIの上限（30件×100ページ）
PRICE_MAX = 300000  # 価格帯で分けるときの上限

# 取得する検索条件。ng は楽天の検索の時点で外す言葉（128バイト未満）
QUERIES = [
    {"keyword": "ファミコン", "ng": ""},
    {"keyword": "スーパーファミコン", "ng": ""},
    {"keyword": "PS", "ng": "PS2 PS3 PS4 PS5 PSP PSVITA 編集部 周辺機器 本体 攻略"},  # PS1は「／PS」と書かれている
    {"keyword": "PS2", "ng": ""},
    {"keyword": "PSP", "ng": ""},
    {"keyword": "Vita", "ng": ""},
    {"keyword": "ゲームボーイ", "ng": ""},
]


class Fetcher:
    def __init__(self):
        self.calls = 0

    def search(self, keyword, ng, page, min_price=None, max_price=None) -> dict:
        params = {
            "applicationId": os.environ["RAKUTEN_APP_ID"],
            "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
            "affiliateId": os.environ.get("RAKUTEN_AFFILIATE_ID", ""),
            "shopCode": SHOP,
            "keyword": keyword + " 中古",
            "hits": 30,
            "page": page,
            "sort": "+itemPrice",
            "availability": 1,
            "format": "json",
            "formatVersion": 2,
        }
        if ng:
            params["NGKeyword"] = ng
        if min_price is not None:
            params["minPrice"] = min_price
        if max_price is not None:
            params["maxPrice"] = max_price
        req = urllib.request.Request(
            API_URL + "?" + urllib.parse.urlencode(params),
            headers={"Referer": SITE + "/", "Origin": SITE, "User-Agent": "retrogame-souba/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        finally:
            self.calls += 1
            time.sleep(WAIT_SEC)

    def fetch_range(self, q, lo, hi, out: dict, depth=0):
        """価格帯 lo〜hi 円を取得。3,000件を超えたら半分に分けてやり直す"""
        first = self.search(q["keyword"], q["ng"], 1, lo, hi)
        count = first.get("count", 0)
        indent = "  " * (depth + 1)
        if count > LIMIT and hi - lo > 1:
            mid = (lo + hi) // 2
            print(f"{indent}{lo}〜{hi}円: {count}件 → 分割")
            self.fetch_range(q, lo, mid, out, depth + 1)
            self.fetch_range(q, mid + 1, hi, out, depth + 1)
            return
        got_total = 0
        page, d = 1, first
        while True:
            got = d.get("Items", [])
            for x in got:
                out.setdefault(x["itemUrl"], {
                    "name": x["itemName"],
                    "price": x["itemPrice"],
                    "url": x["itemUrl"],
                    "aff_url": x.get("affiliateUrl", ""),
                    "postage_included": x.get("postageFlag") == 0,
                    "query": q["keyword"],
                })
            got_total += len(got)
            if len(got) < 30 or got_total >= count or page >= LIMIT // 30:
                break
            page += 1
            d = self.search(q["keyword"], q["ng"], page, lo, hi)
        if depth:
            print(f"{indent}{lo}〜{hi}円: {got_total}件")


def main():
    f = Fetcher()
    items = {}  # URLで重複をなくす
    for q in QUERIES:
        before = len(items)
        print(f"■ {q['keyword']}")
        try:
            f.fetch_range(q, 0, PRICE_MAX, items)
        except urllib.error.HTTPError as e:
            print(f"  エラー: {e.code} {e.read().decode()[:150]}")
        except Exception as e:
            print(f"  エラー: {e}")
        print(f"  → 新しく {len(items) - before}件（API {f.calls}回目まで）")

    RAW_PATH.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "shop": SHOP,
        "items": list(items.values()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✅ {RAW_PATH.name} に {len(items)}件（重複なし）を保存しました（API {f.calls}回）")

    tail = collections.Counter()
    for x in items.values():
        m = re.search(r"／\s*([^／]+?)\s*$", x["name"])
        tail[m.group(1) if m else "（／なし）"] += 1
    print("\n商品名の最後の「／○○」ランキング:")
    for k, v in tail.most_common(15):
        print(f"  {v:>5}件  {k}")


if __name__ == "__main__":
    main()
