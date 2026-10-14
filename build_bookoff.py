"""
build_bookoff.py
================
raw_bookoff.json（ブックオフの生データ）を、商品名の「／機種」で機種を判定し、
ソフトごとにまとめて bookoff_prices.json を作る。楽天APIは使わない。

使い方:
    python3 build_bookoff.py            … まとめて書き出し＋集計を表示
    python3 build_bookoff.py ドラゴンクエスト  … 名前にその言葉を含むソフトの中身を表示（調査用）
"""

import re, sys, json, statistics, unicodedata, collections
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
RAW_PATH = HERE / "raw_bookoff.json"
OUTPUT_PATH = HERE / "bookoff_prices.json"

# 商品名の最後の「／○○」→ サイトでの機種
PLATFORM_MAP = {
    "ファミコン": ("famicom", "ファミコン"),
    "スーパーファミコン": ("sfc", "スーパーファミコン"),
    "PS": ("ps1", "プレイステーション"),
    "PS1": ("ps1", "プレイステーション"),
    "プレイステーション": ("ps1", "プレイステーション"),
    "PS2": ("ps2", "プレイステーション2"),
    "PSP": ("psp", "PSP"),
    "PSVITA": ("vita", "PS Vita"),
    "ゲームボーイ": ("gb", "ゲームボーイ"),
    "GB": ("gb", "ゲームボーイ"),
    "ゲームボーイカラー": ("gbc", "ゲームボーイカラー"),
    "GBC": ("gbc", "ゲームボーイカラー"),
    "GBA": ("gba", "ゲームボーイアドバンス"),
    "ゲームボーイアドバンス": ("gba", "ゲームボーイアドバンス"),
}

# 版の判定（商品名から取り除いて、ソフト名をそろえる）
EDITION_PATTERNS = [
    ("limited", r"\S*同梱版|\S*(CD|DVD|特典)付き?|限定版|限定生産|初回限定(版)?|初回生産(版)?|特装版|プレミアム\s*(BOX|ボックス|エディション)|コレクターズ\s*(BOX|エディション)?|スペシャル\s*(BOX|ボックス|エディション)|同梱版|ツインパック|.{0,6}BOX"),
    ("budget", r"PlayStation\s*Vita\s*the\s*Best|PSP\s*the\s*Best|PlayStation\s*2\s*the\s*Best|PlayStation\s*the\s*Best|PS\s*one\s*Books|the\s*Best|アルティメット\s*ヒッツ|メガ\s*ヒッツ|MEGA\s*HITS!?|ベスト(版|プライス)?|BEST\s*(版|PRICE|SELECTION)?|廉価版|コナミ殿堂セレクション|カプコレ|SEGA\s*THE\s*BEST|バリューセレクション|ザ\s*・?\s*ベスト"),
]
NOISE = r"[（(]\s*(再販|再版|通常版|新価格版|廉価版)\s*[)）]|【.*?】|\[.*?\]"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[‐‑‒–—―−]", "-", s)


def parse(name: str):
    """商品名 → (機種キー, 機種名, 版, 表示用タイトル, まとめ用キー)。ゲームでなければ None"""
    n = norm(name).strip()
    m = re.search(r"/\s*([^/]+?)\s*$", n)  # NFKCで「／」は「/」になる
    if not m:
        return None
    tail = m.group(1).upper().replace(" ", "")
    hit = next((v for k, v in PLATFORM_MAP.items() if k.upper().replace(" ", "") == tail), None)
    if not hit:
        return None
    body = n[: m.start()]
    body = re.sub(NOISE, " ", body)

    edition = "normal"
    for ed, pat in EDITION_PATTERNS:
        if re.search(pat, body, re.I):
            edition = ed
            body = re.sub(pat, " ", body, flags=re.I)
            break
    body = re.sub(r"\s*[（(]\s*[)）]\s*", " ", body)  # 中身が消えた（）を消す
    title = re.sub(r"\s+", " ", body).strip(" -・/")
    key = re.sub(r"[\s・:：~〜\-!！?？.。、,]", "", title).lower()
    return hit[0], hit[1], edition, title, key


def main(debug_word=None):
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    softs = {}
    skipped = collections.Counter()

    for x in raw["items"]:
        p = parse(x["name"])
        if not p:
            m = re.search(r"／\s*([^／]+?)\s*$", x["name"])
            skipped[m.group(1) if m else "（／なし）"] += 1
            continue
        pkey, plabel, edition, title, key = p
        s = softs.setdefault((pkey, key), {
            "platform": pkey, "platform_label": plabel, "title": title, "editions": {}})
        if len(title) < len(s["title"]):  # いちばん短い名前を表示名にする
            s["title"] = title
        s["editions"].setdefault(edition, []).append(x)

    if debug_word:
        w = norm(debug_word)
        for s in sorted(softs.values(), key=lambda s: (s["platform"], s["title"])):
            if w in s["title"]:
                print(f"\n■ {s['title']}（{s['platform_label']}）")
                for ed, lst in s["editions"].items():
                    for x in sorted(lst, key=lambda x: x["price"]):
                        print(f"  {ed:<8} {x['price']:>6}円 | {x['name'][:70]}")
        return

    out = []
    for s in softs.values():
        eds = {}
        for ed, lst in s["editions"].items():
            lst.sort(key=lambda x: x["price"])
            prices = [x["price"] for x in lst]
            eds[ed] = {
                "count": len(prices),
                "min": prices[0],
                "median": int(statistics.median(prices)),
                "items": [{"price": x["price"], "name": x["name"], "url": x["aff_url"] or x["url"],
                           "postage_included": x["postage_included"]} for x in lst[:3]],
            }
        out.append({"platform": s["platform"], "platform_label": s["platform_label"],
                    "title": s["title"], "editions": eds})
    out.sort(key=lambda s: (s["platform"], s["title"]))

    OUTPUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bookoff",
        "fetched_at": raw.get("fetched_at"),
        "total": len(out),
        "items": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 集計表示 ──
    print("■ 機種ごとの集計")
    by_pf = collections.defaultdict(lambda: [0, 0])
    for s in out:
        by_pf[s["platform_label"]][0] += 1
        by_pf[s["platform_label"]][1] += sum(e["count"] for e in s["editions"].values())
    for k, (titles, items) in sorted(by_pf.items(), key=lambda kv: -kv[1][1]):
        print(f"  {k:<14} ソフト {titles:>4}本 / 商品 {items:>5}件")

    print("\n■ 出品数が多いソフト TOP15（まとめ方の確認用）")
    top = sorted(out, key=lambda s: -sum(e["count"] for e in s["editions"].values()))[:15]
    for s in top:
        n = sum(e["count"] for e in s["editions"].values())
        eds = " ".join(f"{k}:{v['count']}" for k, v in s["editions"].items())
        print(f"  {n:>3}件 {s['title'][:30]:<30}（{s['platform_label']}） {eds}")

    print("\n■ ゲームとして扱わなかった商品（／の後ろ）TOP15")
    for k, v in skipped.most_common(15):
        print(f"  {v:>5}件  {k}")

    print(f"\n✅ {OUTPUT_PATH.name} に {len(out)} 本分を書き出しました")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
