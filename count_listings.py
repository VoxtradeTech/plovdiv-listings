"""Daily count of imot.bg listings in Plovdiv; appends to history.csv and rebuilds docs/index.html."""
import csv
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "history.csv"
CHART = ROOT / "docs" / "index.html"
TEMPLATE = ROOT / "chart_template.html"
FIELDS = ["date", "source", "deal", "district", "category", "count"]

DEALS = {"sale": "prodazhbi", "rent": "naemi"}
DISTRICTS = {"Център": "tsentar", "Сточна гара": "stochna-gara"}
CATEGORIES = {"офис": "ofis", "магазин": "magazin",
              "двустаен": "dvustaen", "тристаен": "tristaen", "мезонет": "mezonet"}
# (deal, category) pairs to count, for both districts
COMBOS = [(d, c) for d in ("sale", "rent") for c in ("офис", "магазин")] + \
         [("sale", c) for c in ("двустаен", "тристаен", "мезонет")]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


def url_for(deal, district, category):
    return (f"https://www.imot.bg/obiavi/{DEALS[deal]}/grad-plovdiv/"
            f"{DISTRICTS[district]}/{CATEGORIES[category]}")


def parse_count(html):
    m = re.search(r'class="SearchInfoLine">([^<]+)<', html)
    if not m:
        raise ValueError("SearchInfoLine not found (page layout changed or blocked?)")
    info = m.group(1)
    if "Няма намерени обяви" in info:
        return 0
    m = re.search(r"от общо\s+(\d+)", info) or re.search(r"(\d+)\s+обяв", info)
    if not m:
        raise ValueError(f"cannot parse count from: {info.strip()}")
    return int(m.group(1))


def fetch_count(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html", "Accept-Language": "bg-BG,bg;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.geturl().rstrip("/") != url.rstrip("/"):
            raise ValueError(f"redirected to {resp.geturl()}")
        html = resp.read().decode("cp1251", errors="replace")
    return parse_count(html)


def load_history():
    if not HISTORY.exists():
        return []
    with HISTORY.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def count_today(rows):
    today = dt.datetime.now(ZoneInfo("Europe/Sofia")).date().isoformat()
    done = {(r["deal"], r["district"], r["category"]) for r in rows if r["date"] == today}
    new, errors = [], []
    for deal, category in COMBOS:
        for district in DISTRICTS:
            if (deal, district, category) in done:
                continue
            url = url_for(deal, district, category)
            if new or errors:
                time.sleep(random.uniform(4, 8))
            try:
                n = fetch_count(url)
                new.append({"date": today, "source": "imot.bg", "deal": deal,
                            "district": district, "category": category, "count": n})
                print(f"{deal} {district} {category}: {n}")
            except Exception as e:  # logged, never written as zero
                errors.append(f"{url}: {e}")
                print(f"ERROR {url}: {e}", file=sys.stderr)
    if new:
        exists = HISTORY.exists()
        with HISTORY.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if not exists:
                w.writeheader()
            w.writerows(new)
    return errors


def build_chart():
    rows = load_history()
    for r in rows:
        r["count"] = int(r["count"])
    CHART.parent.mkdir(exist_ok=True)
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*DATA*/[]", json.dumps(rows, ensure_ascii=False))
    CHART.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    if "--probe" in sys.argv:  # check imot.bg answers from this machine; writes nothing
        u = url_for("sale", "Център", "офис")
        print(f"{u}: {fetch_count(u)}")
        sys.exit(0)
    errs = [] if "--chart-only" in sys.argv else count_today(load_history())
    build_chart()
    sys.exit(1 if errs else 0)
