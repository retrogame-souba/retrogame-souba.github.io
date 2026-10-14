"""
fetch_bookoff.py
================
ブックオフ楽天市場店（bookoffonline）のレトロゲームの在庫を、機種ごとに全部取得して
raw_bookoff.json に保存する（ミニPCの中だけに置く。GitHubには上げない）。

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
MAX_PAGES = 100  # 楽天APIの上限（30件×100ページ＝3,000件）

# 取得する機種（検索キーワード）。DSは件数が多すぎるので今回は対象外
QUERIES = ["ファミコン", "スーパーファミコン", "プレイステーション", "PS2", "PSP", "Vita", "ゲームボーイ"]


def search(keyword: str, page: int) -> dict:
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
    req = urllib.request.Request(
        API_URL + "?" + urllib.parse.urlencode(params),
        headers={"Referer": SITE + "/", "Origin": SITE, "User-Agent": "retrogame-souba/0.1"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    items = {}  # URLで重複をなくす（「ファミコン」で検索するとスーパーファミコンも出るため）
    for q in QUERIES:
        print(f"■ {q} … ", end="", flush=True)
        got_total, count = 0, None
        for page in range(1, MAX_PAGES + 1):
            try:
                d = search(q, page)
            except urllib.error.HTTPError as e:
                print(f"\n  エラー page={page}: {e.code} {e.read().decode()[:150]}")
                break
            except Exception as e:
                print(f"\n  エラー page={page}: {e}")
                break
            finally:
                time.sleep(WAIT_SEC)

            count = d.get("count", 0)
            got = d.get("Items", [])
            for x in got:
                url = x["itemUrl"]
                if url not in items:
                    items[url] = {
                        "name": x["itemName"],
                        "price": x["itemPrice"],
                        "url": url,
                        "aff_url": x.get("affiliateUrl", ""),
                        "postage_included": x.get("postageFlag") == 0,
                        "query": q,
                    }
            got_total += len(got)
            if page % 10 == 0:
                print(f"{got_total}/{count} ", end="", flush=True)
            if len(got) < 30 or got_total >= count:
                break
        print(f"→ {got_total}件取得（全{count}件）")

    RAW_PATH.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "shop": SHOP,
        "items": list(items.values()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✅ {RAW_PATH.name} に {len(items)}件（重複なし）を保存しました")

    # おまけ：商品名の最後の「／機種」の集計（名前の付け方を知るため）
    tail = collections.Counter()
    for x in items.values():
        m = re.search(r"／\s*([^／]+?)\s*$", x["name"])
        tail[m.group(1) if m else "（／なし）"] += 1
    print("\n商品名の最後の「／○○」ランキング:")
    for k, v in tail.most_common(15):
        print(f"  {v:>5}件  {k}")


if __name__ == "__main__":
    main()
