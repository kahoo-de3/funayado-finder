# -*- coding: utf-8 -*-
"""
釣割(chowari.jp)から関東(area=92)の全船宿をスクレイプして docs/data/boats.json を生成する。

出力: 各船宿について id/船名/県/市/漁港/評価/レビュー数/URL/対象魚(セット) を収集。
「魚種→漁港→船宿」の絞り込みはクライアント側(index.html)で行う。

使い方:
    python tools/fetch_chowari.py
再実行するとスナップショットを最新化できる（スナップショット運用）。
"""
import datetime
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

AREA = 92  # 関東
BASE = "https://www.chowari.jp/search/?area={area}&page={page}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) funayado-finder/1.0 (personal fishing app)"
SLEEP = 1.0  # サーバ負荷に配慮（1req/秒）
OUT = Path(__file__).resolve().parents[1] / "docs" / "data" / "boats.json"

# 船宿1件分のブロックに含まれる各項目の正規表現
RE_UNIT_SPLIT = re.compile(r'<section class="search__shiplist_unit">')
RE_SHIP_ID = re.compile(r'/ship/(\d+)/')
RE_NAME = re.compile(r'search__shiplist_unit_key_info_name_txt">([^<]+)</h2>')
RE_ADDR = re.compile(
    r'search__shiplist_unit_key_info_address">\s*((?:<li>[^<]*</li>\s*)+)'
)
RE_LI = re.compile(r'<li>([^<]*)</li>')
RE_RATING = re.compile(r'<strong>([\d.]+)</strong>\s*<svg')
RE_REVIEWS = re.compile(r'<span>\((\d+)件\)</span>')
RE_FISH = re.compile(
    r'search__shiplist_unit_plan_list_item_info_sup_fishlist_item">([^<]+)</li>'
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def normalize_fish(raw: str) -> str:
    """'ハナダイ（チダイ）' → 'ハナダイ' のように括弧以降を落として主名を返す。"""
    s = raw.strip()
    s = re.sub(r"[（(].*", "", s)  # 全角/半角括弧以降を除去
    return s.strip()


def parse_page(html: str) -> list[dict]:
    ships = []
    blocks = RE_UNIT_SPLIT.split(html)[1:]  # 先頭はヘッダ部
    for b in blocks:
        mid = RE_SHIP_ID.search(b)
        mname = RE_NAME.search(b)
        maddr = RE_ADDR.search(b)
        if not (mid and mname and maddr):
            continue
        lis = RE_LI.findall(maddr.group(1))
        lis = [x.strip() for x in lis if x.strip()]
        pref = lis[0] if len(lis) >= 1 else ""
        city = lis[1] if len(lis) >= 3 else ""
        port = lis[-1] if len(lis) >= 2 else ""

        mrat = RE_RATING.search(b)
        mrev = RE_REVIEWS.search(b)

        fishes_raw = RE_FISH.findall(b)
        fishes = sorted({normalize_fish(f) for f in fishes_raw if normalize_fish(f)})

        ships.append({
            "id": mid.group(1),
            "name": mname.group(1).strip(),
            "pref": pref,
            "city": city,
            "port": port,
            "rating": float(mrat.group(1)) if mrat else None,
            "reviews": int(mrev.group(1)) if mrev else 0,
            "url": f"https://www.chowari.jp/ship/{mid.group(1)}/",
            "fish": fishes,
        })
    return ships


def main():
    all_ships = {}
    page = 1
    while True:
        url = BASE.format(area=AREA, page=page)
        print(f"[fetch] page {page}: {url}", file=sys.stderr)
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  ! error: {e}", file=sys.stderr)
            break
        ships = parse_page(html)
        print(f"  -> {len(ships)} ships", file=sys.stderr)
        if not ships:
            break
        new = 0
        for s in ships:
            if s["id"] not in all_ships:
                all_ships[s["id"]] = s
                new += 1
        # 新規が0（同じページの繰り返し=最終ページ超過）なら終了
        if new == 0:
            break
        page += 1
        time.sleep(SLEEP)
        if page > 40:  # 安全弁
            break

    ships_list = sorted(all_ships.values(), key=lambda s: (s["pref"], s["port"], s["name"]))
    # 集計
    all_fish = sorted({f for s in ships_list for f in s["fish"]})
    all_ports = sorted({s["port"] for s in ships_list if s["port"]})
    payload = {
        "source": "chowari.jp (area=92 関東)",
        "generated": datetime.date.today().isoformat(),
        "area": AREA,
        "ship_count": len(ships_list),
        "port_count": len(all_ports),
        "fish_count": len(all_fish),
        "fish_names": all_fish,
        "ports": all_ports,
        "ships": ships_list,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {len(ships_list)} ships, {len(all_ports)} ports, {len(all_fish)} fish -> {OUT}", file=sys.stderr)
    # 上位魚種の出現数を表示（確認用）
    from collections import Counter
    cnt = Counter(f for s in ships_list for f in s["fish"])
    print("[top fish] " + ", ".join(f"{k}:{v}" for k, v in cnt.most_common(20)), file=sys.stderr)


if __name__ == "__main__":
    main()
