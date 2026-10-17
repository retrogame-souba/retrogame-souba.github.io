"""
fetch_raw.py
============
【ステップ1：集める】
softs.json のソフトを楽天市場APIで検索し、ふるいにかける前の
「生のデータ」を全部 raw_rakuten.json に保存する。

  ・1本につき最大 PAGES ページ（30件×PAGES）を取得
  ・ここでは何も捨てない（判定は build_prices.py でやる）

使い方:
    source ~/.rakuten_env && python3 fetch_raw.py                  … 全ソフト
    source ~/.rakuten_env && python3 fetch_raw.py ps1-ff7 ps1-gt   … 指定したソフトだけ取り直す（ほかは前回のまま）
"""

import os, sys, json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
SOFTS_PATH = HERE / "softs.json"
RAW_PATH = HERE / "raw_rakuten.json"

SITE = "https://retrogame-souba.github.io"
API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
WAIT_SEC = 1.5  # 楽天APIへの間隔（1秒1回まで）
PAGES = 3       # 1本につき何ページ取るか（1ページ30件）


def build_ng_keyword(soft: dict, pf: dict) -> str:
    """楽天のNGKeywordは128バイト未満。ソフト用→機種用の順に、入るぶんだけ使う"""
    words = (soft.get("api_ng", "") + " " + pf.get("api_ng", "")).split()
    ng = ""
    for w in words:
        cand = (ng + " " + w).strip()
        if len(cand.encode("utf-8")) >= 128:
            break
        ng = cand
    return ng


def search(keyword: str, ng_keyword: str, page: int) -> list[dict]:
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "affiliateId": os.environ.get("RAKUTEN_AFFILIATE_ID", ""),
        "keyword": keyword,
        "hits": 30,
        "page": page,
        "sort": "+itemPrice",
        "availability": 1,
        "format": "json",
        "formatVersion": 2,
    }
    if ng_keyword:
        params["NGKeyword"] = ng_keyword
    req = urllib.request.Request(
        API_URL + "?" + urllib.parse.urlencode(params),
        headers={"Referer": SITE + "/", "Origin": SITE, "User-Agent": "retrogame-souba/0.1"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("Items", [])


def main(only_ids=None):
    conf = json.loads(SOFTS_PATH.read_text(encoding="utf-8"))
    targets = conf["softs"]
    if only_ids:
        targets = [s for s in targets if s["id"] in only_ids]
        unknown = set(only_ids) - {s["id"] for s in targets}
        if unknown:
            print(f"softs.json にないID: {' '.join(sorted(unknown))}")
            sys.exit(2)
    raw = []
    for i, soft in enumerate(targets, 1):
        pf = conf["platforms"][soft["platform"]]
        keyword = " ".join(x for x in [pf["keyword"], soft["keyword"], "中古"] if x)
        ng_keyword = build_ng_keyword(soft, pf)
        print(f"[{i}/{len(targets)}] {soft['title']}（{pf['label']}）… ", end="", flush=True)

        items, error = [], None
        for page in range(1, PAGES + 1):
            try:
                got = search(keyword, ng_keyword, page)
            except urllib.error.HTTPError as e:
                error = f"{e.code} {e.read().decode()[:200]}"
                break
            except Exception as e:
                error = str(e)
                break
            finally:
                time.sleep(WAIT_SEC)
            for x in got:
                items.append({
                    "name": x["itemName"],
                    "price": x["itemPrice"],
                    "shop": x["shopName"],
                    "url": x["itemUrl"],
                    "aff_url": x.get("affiliateUrl", ""),
                    "postage_included": x.get("postageFlag") == 0,
                })
            if len(got) < 30:
                break

        print(f"エラー {error}" if error else f"{len(items)}件")
        raw.append({
            "id": soft["id"],
            "keyword": keyword,
            "ng_keyword": ng_keyword,
            "error": error,
            "items": items,
        })

    if only_ids and RAW_PATH.exists():
        # 指定したソフトだけ入れ替えて、ほかのソフトの生データは残す
        new = {r["id"]: r for r in raw}
        old = json.loads(RAW_PATH.read_text(encoding="utf-8"))["softs"]
        raw = [new.pop(r["id"], r) for r in old] + list(new.values())

    RAW_PATH.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "softs": raw,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✅ {RAW_PATH.name} に保存しました（{sum(len(r['items']) for r in raw)}件）")


if __name__ == "__main__":
    main(sys.argv[1:])
