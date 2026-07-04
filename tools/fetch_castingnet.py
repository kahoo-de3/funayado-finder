# -*- coding: utf-8 -*-
"""
キャスティング船釣り予約(reserve.castingnet.jp)から関東の船宿を取得し、
boats.json に未掲載の船宿を追記する。

背景:
- castingnet と釣割(chowari.jp)は同系列で **船IDが共通**。
- 釣割の area=92 検索は「予約プランあり」の船のみ。castingnet の地図には
  プラン非掲載の船宿も載っているため、そこが「記載漏れ」になる。

データ取得:
- 船一覧: POST ajax_mapmarker.php (bbox: s/w/n/e) → cd_ship + 船名 + 緯度経度
- 港・県 : POST ajax_mapship.php (id)            → dt_s_pref / dt_s_port
- 市・魚 : GET  chowari /ship/{id}/catch/         → <title>から市、FAQ「よく釣れる魚」から対象魚

使い方:
    python tools/fetch_castingnet.py         # 差分を boats.json に追記
    python tools/fetch_castingnet.py --dry   # 追記せず差分表示のみ
追記された船は "via": "castingnet" フラグ付き。予約URLは castingnet の船ページ。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) funayado-finder/1.0 (personal fishing app)"
SLEEP = 0.8
# 関東広域: 南伊豆〜茨城北部(平潟)・銚子沖まで
BBOX = {"s": "34.4", "w": "138.7", "n": "37.0", "e": "141.2"}
BOATS = Path(__file__).resolve().parents[1] / "docs" / "data" / "boats.json"
# アプリの対象県（これ以外は追記しない）
PREFS_OK = {"茨城県", "千葉県", "東京都", "神奈川県", "埼玉県", "静岡県"}


def post(endpoint, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"https://reserve.castingnet.jp/{endpoint}", data=data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Referer": "https://reserve.castingnet.jp/scroll_map/map_search.php"})
    raw = urllib.request.urlopen(req, timeout=30).read()
    return json.loads(urllib.parse.unquote(raw.decode("euc-jp", "replace")))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def full_pref(p):
    """castingnetの県名(短縮形あり)を正式名に"""
    if p in ("東京", "東京都"):
        return "東京都"
    if p.endswith(("都", "道", "府", "県")):
        return p
    return p + "県"


def fetch_chowari_extra(sid):
    """釣割の釣果ページから (市, 対象魚リスト) を取る。ページ無しは ('', [])"""
    try:
        h = get(f"https://www.chowari.jp/ship/{sid}/catch/")
    except Exception:
        return "", []
    # <title>釣果｜〇〇丸 ... - 神奈川県横浜市金沢八景洲崎</title> 形式から住所文字列
    city = ""
    mt = re.search(r"<title>[^<]*-\s*([^<|]+?)</title>", h)
    addr = mt.group(1).strip() if mt else ""
    # FAQ: 例年、<a...>魚</a>、... がよく釣れます
    fish = []
    mi = h.find("よく釣れるのはどんな魚")
    if mi > 0:
        seg = h[mi:mi + 1500]
        fish = re.findall(r"fish=\d+>([^<]+)</a>", seg)
    return addr, sorted(set(f.strip() for f in fish if f.strip()))


def parse_city(addr, pref, port):
    """'神奈川県横浜市金沢八景洲崎' → pref/portを剥がして市区町村部分を返す"""
    s = addr
    if s.startswith(pref):
        s = s[len(pref):]
    if port and s.endswith(port):
        s = s[: -len(port)]
    m = re.match(r"(.+?[市区町村])", s)
    return m.group(1) if m else s


def main():
    dry = "--dry" in sys.argv
    boats = json.loads(BOATS.read_text(encoding="utf-8"))
    our_ids = {s["id"] for s in boats["ships"]}

    print(f"[markers] bbox={BBOX}", file=sys.stderr)
    mk = post("ajax_mapmarker.php", BBOX)
    markers = list(mk["ship"].values())
    print(f"  castingnet: {len(markers)}隻 / boats.json: {len(our_ids)}隻", file=sys.stderr)

    missing = [m for m in markers if m["cd_ship"] not in our_ids]
    print(f"  未掲載: {len(missing)}隻", file=sys.stderr)

    added, skipped = [], []
    for i, m in enumerate(missing, 1):
        sid, name = m["cd_ship"], m["dt_ship"].strip()
        # 港・県
        try:
            det = post("ajax_mapship.php", {"id": sid}).get("ship", {})
        except Exception as e:
            print(f"  ! {sid} {name}: detail error {e}", file=sys.stderr)
            det = {}
        pref = full_pref(det.get("dt_s_pref", "").strip())
        port = det.get("dt_s_port", "").strip()
        time.sleep(SLEEP)
        # 市・対象魚（釣割）
        addr, fish = fetch_chowari_extra(sid)
        city = parse_city(addr, pref, port) if addr else ""
        time.sleep(SLEEP)

        if pref and pref not in PREFS_OK:
            skipped.append((sid, name, pref))
            print(f"  [{i}/{len(missing)}] skip(県外) {name} ({pref})", file=sys.stderr)
            continue

        added.append({
            "id": sid, "name": name,
            "pref": pref, "city": city, "port": port,
            "rating": None, "reviews": 0,
            "url": f"https://reserve.castingnet.jp/ship{sid}.html",
            "fish": fish,
            "via": "castingnet",
        })
        print(f"  [{i}/{len(missing)}] + {name} ({pref}/{port}) fish={len(fish)}", file=sys.stderr)

    print(f"\n[result] 追記対象 {len(added)}隻 / 県外スキップ {len(skipped)}隻", file=sys.stderr)
    if dry:
        for a in added:
            print(json.dumps(a, ensure_ascii=False))
        return

    boats["ships"].extend(added)
    boats["ships"].sort(key=lambda s: (s["pref"], s["port"], s["name"]))
    all_fish = sorted({f for s in boats["ships"] for f in s["fish"]})
    all_ports = sorted({s["port"] for s in boats["ships"] if s["port"]})
    boats["ship_count"] = len(boats["ships"])
    boats["port_count"] = len(all_ports)
    boats["fish_count"] = len(all_fish)
    boats["fish_names"] = all_fish
    boats["ports"] = all_ports
    boats["source"] = "chowari.jp (area=92 関東) + reserve.castingnet.jp"
    BOATS.write_text(json.dumps(boats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] boats.json: {boats['ship_count']}隻 / {boats['port_count']}港 / {boats['fish_count']}魚種", file=sys.stderr)

    # seasons.json の alias 漏れチェック
    seasons = json.loads((BOATS.parent / "seasons.json").read_text(encoding="utf-8"))
    covered = {a for sp in seasons["species"] for a in sp["aliases"]}
    uncovered = sorted(set(all_fish) - covered)
    if uncovered:
        print(f"[WARN] seasons.json に未マッピングの魚種: {uncovered}", file=sys.stderr)


if __name__ == "__main__":
    main()
