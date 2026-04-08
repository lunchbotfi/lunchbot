#!/usr/bin/env python3
"""
LunchBot scraper — bilingual Helsinki lunch menus.

LANGUAGE BEHAVIOUR PER SOURCE:
  Compass   → JSON API natively supports en/fi via ?language= param
  Luncher   → REST API natively supports en/fi via ?language= param
  Factory   → Single page with BOTH Finnish + English sections; we read
              the correct section directly — no translation needed
  Oikeus    → Finnish HTML only; EN mode auto-translates via MyMemory API
              (no English version available for Oikeus)

CLI USAGE:
  lunchbot                                              # today, English, pretty
  lunchbot today / list                                 # same as above
  lunchbot week                                         # Mon–Fri this week, pretty
  lunchbot --date tomorrow                              # specific day
  lunchbot --date friday                                # this or next Friday
  lunchbot --date yesterday                             # previous working day
  lunchbot --date 2026-04-10                            # exact ISO date
  lunchbot week --date next monday                      # week containing that date
  lunchbot --finnish                                    # today, Finnish, pretty
  lunchbot --restaurant "Roihu" --date tomorrow        # combine freely
  lunchbot --json                                       # raw JSON (any combo)
"""

import argparse
import json
import re
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")


# ── Translation (Finnish → English via MyMemory free API) ────────────────────

_ASCII_SAFE = re.compile(r'^[\x00-\x7F\s\(\)\.,\-\/\%\d:;\'\"!?&+*]+$')

_SKIP = frozenset({"No menu found", "Day section not found", "Not available"})


def _needs_translation(text: str) -> bool:
    """Return True if the text contains non-ASCII characters (likely Finnish)."""
    if not text or text in _SKIP or text.startswith("Error"):
        return False
    return not _ASCII_SAFE.match(text)


def translate_to_english(texts: list) -> list:
    """
    Batch-translate a list of Finnish strings to English using MyMemory (free, no key).
    - Already-English strings (ASCII-safe) pass through unchanged.
    - Falls back silently to the original on any network or parse error.
    - Runs translation requests in parallel for speed.
    """
    if not texts:
        return texts

    to_do   = [(i, t) for i, t in enumerate(texts) if _needs_translation(t)]
    results = list(texts)

    if not to_do:
        return results

    def _translate_one(idx_text):
        idx, text = idx_text
        try:
            r = requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text[:500], "langpair": "fi|en"},
                timeout=6,
            )
            data = r.json()
            tr   = data.get("responseData", {}).get("translatedText", "")
            if tr and tr.upper() != text.upper() and "INVALID" not in tr.upper():
                return idx, tr
        except Exception:
            pass
        return idx, text  # fallback: original

    with ThreadPoolExecutor(max_workers=10) as exe:
        futs = {exe.submit(_translate_one, item): item for item in to_do}
        for f in as_completed(futs):
            idx, tr = f.result()
            results[idx] = tr

    return results



# ── Date resolver ─────────────────────────────────────────────────────────────

def resolve_date(expr: str, today: "datetime.date | None" = None) -> "datetime.date":
    """
    Resolve a natural-language date expression to a concrete date.

    Accepted forms (case-insensitive):
      today, tomorrow, yesterday
      monday … friday          → nearest occurrence (today or future first,
                                  then look back up to 6 days)
      next monday … next friday → the occurrence in the NEXT calendar week
      last monday … last friday → the occurrence in the PREVIOUS calendar week
      YYYY-MM-DD               → parsed directly

    Raises ValueError for unrecognised input.
    """
    from datetime import date as _date, timedelta as _td
    if today is None:
        today = _date.today()

    expr = expr.strip().lower()

    # Exact ISO date
    try:
        return datetime.strptime(expr, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Named relative days
    if expr == "today":
        return today
    if expr in ("tomorrow", "tmr", "tmrw"):
        return today + _td(days=1)
    if expr == "yesterday":
        return today - _td(days=1)

    # Weekday names with optional "next" / "last" prefix
    DAY_NAMES = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        # Finnish shortcuts in case agent passes them
        "maanantai": 0, "tiistai": 1, "keskiviikko": 2,
        "torstai": 3, "perjantai": 4,
    }

    prefix = None
    name   = expr
    if expr.startswith("next "):
        prefix = "next"
        name   = expr[5:].strip()
    elif expr.startswith("last "):
        prefix = "last"
        name   = expr[5:].strip()

    if name in DAY_NAMES:
        target_wd = DAY_NAMES[name]
        today_wd  = today.weekday()

        if prefix == "next":
            # Always the occurrence in the next calendar week
            days_to_monday = (7 - today_wd) % 7 or 7
            next_monday    = today + _td(days=days_to_monday)
            return next_monday + _td(days=target_wd)

        if prefix == "last":
            # Always the occurrence in the previous calendar week
            this_monday = today - _td(days=today_wd)
            last_monday = this_monday - _td(days=7)
            return last_monday + _td(days=target_wd)

        # No prefix → nearest occurrence: today/future first, then look back
        diff = (target_wd - today_wd) % 7
        candidate = today + _td(days=diff)
        if diff == 0:
            return candidate          # it IS today
        # If it would be in the future, check if it was more recently in the past
        past = candidate - _td(days=7)
        # Prefer future over past (natural "Friday" = this coming Friday)
        return candidate

    raise ValueError(
        f"Unrecognised date expression: {expr!r}\n"
        "Try: today, tomorrow, yesterday, monday…friday, "
        "next friday, last monday, YYYY-MM-DD"
    )

# ── LunchScraper ──────────────────────────────────────────────────────────────

class LunchScraper:

    WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    # All weekday names recognised in page content (EN + FI + SV)
    WEEKDAY_MAP = {
        "Monday":    ["MONDAY",    "MAANANTAI",   "MÅNDAG"],
        "Tuesday":   ["TUESDAY",   "TIISTAI",     "TISDAG"],
        "Wednesday": ["WEDNESDAY", "KESKIVIIKKO", "ONSDAG"],
        "Thursday":  ["THURSDAY",  "TORSTAI",     "TORSDAG"],
        "Friday":    ["FRIDAY",    "PERJANTAI",   "FREDAG"],
    }

    # ── Restaurant configurations ─────────────────────────────────────────────
    #
    # COMPASS  – JSON API, natively bilingual
    #   EN: https://www.compass-group.fi/menuapi/feed/json?costNumber=<N>&language=en
    #   FI: https://www.compass-group.fi/menuapi/feed/json?costNumber=<N>&language=fi
    #
    # LUNCHER  – REST API, natively bilingual
    #   EN: https://.../api/v1/week/<uuid>/active?language=en
    #   FI: https://.../api/v1/week/<uuid>/active?language=fi
    #
    # FACTORY  – same URL for both languages; page contains Finnish section
    #            first, then English section below. We select the correct
    #            section by matching the language-specific day heading.
    #            No translation needed.
    #
    # OIKEUS   – Finnish HTML only (no EN version)
    #   EN mode: auto-translate via MyMemory
    #   FI mode: return raw text

    COMPASS = {
        "Roihu":                3060,
        "Food & Co Ruoholahti": 3130,
    }

    FACTORY = {
        "Factory Ruoholahti": (
            "https://ravintolafactory.com/lounasravintolat/"
            "ravintolat/factory-ruoholahti/"
        ),
        "Factory Salmisaari": (
            "https://ravintolafactory.com/lounasravintolat/"
            "ravintolat/helsinki-salmisaari/"
        ),
    }

    LUNCHER = {
        "Dylan Milk":      "3d9b2545-87e6-479b-9306-813ac4451b65",
        "Dylan Raspberry": "f1f5f748-1e90-4e13-9463-aefeeb211f6d",
        "Hima & Sali":     "085d7829-8bd1-4dae-bf0e-30f63c40e265",
    }

    LUNCHER_BASE = "https://europe-west1-luncher-7cf76.cloudfunctions.net"

    # Nordrest Oikeus – Finnish HTML only
    OIKEUS_URL = "https://nordrest.fi/restaurang/oikeus/"

    # Words that signal end-of-menu in Oikeus / Factory pages
    _STOP_WORDS = frozenset({"HINNAT", "PRICES", "NORDREST", "AU KIOLO"})

    def __init__(self, lang: str = "en", target_date=None):
        """
        lang:        "en" (default) or "fi"
        target_date: a datetime.date to anchor the week on (default: today).
                     The scraper always fetches the full Mon–Fri week that
                     contains target_date, then slices to that date for
                     single-day views.
        """
        assert lang in ("en", "fi"), "lang must be 'en' or 'fi'"
        self.lang = lang

        self.now       = datetime.now()
        real_today     = self.now.date()
        anchor         = target_date if target_date is not None else real_today

        self.today_iso = anchor.isoformat()          # the "day of interest"
        self.day_en    = anchor.strftime("%A")
        self.real_today_iso = real_today.isoformat() # actual today for ◀ TODAY marker

        # ISO dates for Mon–Fri of the week containing anchor
        monday = anchor - timedelta(days=anchor.weekday())
        self.week_dates     = {
            day: (monday + timedelta(days=i)).isoformat()
            for i, day in enumerate(self.WEEKDAYS)
        }
        self._week_date_set = set(self.week_dates.values())

        # Compile a single pattern matching any weekday name in any language
        self._day_re = re.compile(
            "|".join(d for days in self.WEEKDAY_MAP.values() for d in days),
            re.IGNORECASE,
        )
        # Reverse-lookup: "MAANANTAI" → "Monday"
        self._variant_to_day = {
            v: day
            for day, variants in self.WEEKDAY_MAP.items()
            for v in variants
        }

        self._headers = {"User-Agent": "Mozilla/5.0 (LunchBot/1.0)"}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _variants(self, day_en: str) -> list:
        """Return all uppercase header strings for a given English day name."""
        return [v.upper() for v in self.WEEKDAY_MAP.get(day_en, [])]

    def _maybe_translate(self, dishes: list) -> list:
        """
        Translate dishes to English if lang=="en".
        In Finnish mode dishes are already Finnish — return unchanged.
        """
        if self.lang == "en":
            return translate_to_english(dishes)
        return dishes

    def _fill_missing(self, out: dict) -> dict:
        """Ensure every week date has an entry."""
        for date in self._week_date_set:
            out.setdefault(date, ["No menu found"])
        return out

    # ── Compass ───────────────────────────────────────────────────────────────
    # JSON API — natively bilingual, no translation needed.
    # EN: ?language=en  |  FI: ?language=fi

    def fetch_compass(self, name: str, cost: int) -> dict:
        """Returns {date_iso: [dishes]} for the full week."""
        out = {}
        try:
            url  = (
                "https://www.compass-group.fi/menuapi/feed/json"
                f"?costNumber={cost}&language={self.lang}"
            )
            data = requests.get(url, timeout=8).json()
            for day_data in data.get("MenusForDays", []):
                date = day_data.get("Date", "")[:10]
                if date not in self._week_date_set:
                    continue
                dishes = [
                    c.strip()
                    for menu in day_data.get("SetMenus", [])
                    for c in menu.get("Components", [])
                    if c.strip()
                ]
                out[date] = dishes or ["No menu found"]
        except Exception as e:
            for date in self._week_date_set:
                out[date] = [f"Error: {e}"]
        return self._fill_missing(out)

    # ── Luncher ───────────────────────────────────────────────────────────────
    # REST API — natively bilingual, no translation needed.
    # EN: ?language=en  |  FI: ?language=fi

    def fetch_luncher(self, name: str, uuid: str) -> dict:
        """Returns {date_iso: [dishes]} for the full week."""
        out = {}
        try:
            url  = f"{self.LUNCHER_BASE}/api/v1/week/{uuid}/active?language={self.lang}"
            res  = requests.get(url, timeout=8).json()
            days = res.get("data", {}).get("week", {}).get("days", [])
            for day in days:
                date = str(day.get("dateString", ""))[:10]
                if date not in self._week_date_set:
                    continue
                items = []
                for lunch in day.get("lunches", []):
                    # Both "en" and "fi" keys exist in the response
                    title = lunch.get("title", {}).get(self.lang, "").strip()
                    desc  = lunch.get("description", {}).get(self.lang, "").strip()
                    if title:
                        items.append(f"{title} ({desc})" if desc else title)
                out[date] = items or ["No menu found"]
        except Exception as e:
            for date in self._week_date_set:
                out[date] = [f"Error: {e}"]
        return self._fill_missing(out)

    # ── Factory ───────────────────────────────────────────────────────────────
    # The Factory page has BOTH language sections on the same URL:
    #   Finnish section first:  "### Maanantai 7.4.2026"
    #   English section below:  "### Monday 7.4.2026"
    #
    # We target ONLY the heading variant for the requested language,
    # reading the native text directly — no translation needed.
    #
    # WEEKDAY_MAP variant index: 0 = English, 1 = Finnish, 2 = Swedish
    _FACTORY_LANG_IDX = {"en": 0, "fi": 1}

    def fetch_factory(self, name: str, url: str) -> dict:
        """
        Returns {date_iso: [dishes]} in the requested language.

        Page structure (both Ruoholahti and Salmisaari):
          <h3>Maanantai 6.4.2026</h3>   Finnish day headings first
          <p>dish line 1\ndish line 2</p>
          <h3>Tiistai 7.4.2026</h3>
          ...
          <h3>Monday 6.4.2026</h3>       English day headings below
          <p>dish line 1\ndish line 2</p>
          <h3>Tuesday 7.4.2026</h3>

        Strategy: find ALL h3 tags, locate the one for the target day/language,
        then collect text from every sibling until the next h3. Avoids the
        fragile find_next() tree-walk entirely.
        """
        out = {}
        try:
            res  = requests.get(url, headers=self._headers, timeout=10)
            soup = BeautifulSoup(res.text, "lxml")

            all_h3 = soup.find_all("h3")
            vi = self._FACTORY_LANG_IDX.get(self.lang, 0)

            for day_en, date_iso in self.week_dates.items():
                target = self.WEEKDAY_MAP[day_en][vi].upper()

                # Find the h3 whose text contains this language's day name
                header = None
                header_idx = None
                for i, h3 in enumerate(all_h3):
                    if target in h3.get_text().upper():
                        header = h3
                        header_idx = i
                        break

                if not header:
                    out[date_iso] = ["Day section not found"]
                    continue

                # Next NON-EMPTY h3 is the boundary — skip empty <h3></h3> tags
                # (the page has empty h3s between the day heading and its dishes
                # e.g. ### Tiistai 7.4.2026 / ### / dish lines...)
                next_h3 = None
                for j in range(header_idx + 1, len(all_h3)):
                    if all_h3[j].get_text(strip=True):  # skip empty h3s
                        next_h3 = all_h3[j]
                        break

                # Allergen legend lines that appear after the last day's dishes
                _ALLERGEN = frozenset({
                    "LAKTOOSITON", "VÄHÄLAKTOOSINEN", "GLUTEENITON",
                    "VEGAANINEN", "MAIDOTON", "SIS. VALKOSIPULIA",
                    "HENKILÖKUNTAMME", "TILAA LOUNASLISTA",
                })

                # Collect text from all siblings between header h3 and next_h3
                dishes = []
                for sibling in header.next_siblings:
                    if sibling == next_h3:
                        break
                    if hasattr(sibling, "name") and sibling.name == "h3":
                        # Only stop on non-empty h3s (same guard as above)
                        if sibling.get_text(strip=True):
                            break

                    if hasattr(sibling, "get_text"):
                        txt = sibling.get_text("\n", strip=True)
                    else:
                        txt = str(sibling).strip()

                    if not txt:
                        continue

                    for line in txt.split("\n"):
                        line = line.strip()
                        if (len(line) > 5
                                and target not in line.upper()
                                and "SÄHKÖPOSTI" not in line.upper()
                                and "DOCUMENT." not in line.upper()
                                and line.upper() not in _ALLERGEN
                                and not any(a in line.upper() for a in _ALLERGEN)):
                            dishes.append(line)

                out[date_iso] = dishes if dishes else ["No menu found"]

        except Exception as e:
            for date in self._week_date_set:
                out[date] = [f"Error: {e}"]

        return self._fill_missing(out)

    # ── Oikeus ────────────────────────────────────────────────────────────────
    # Finnish HTML only — no English URL exists.
    # EN mode → auto-translate scraped Finnish text via MyMemory.
    # FI mode → return raw Finnish text.

    def fetch_oikeus(self) -> dict:
        """Returns {date_iso: [dishes]} for the full week."""
        out = {}
        try:
            res  = requests.get(self.OIKEUS_URL, headers=self._headers, timeout=10)
            soup = BeautifulSoup(res.text, "lxml")
            lines = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]

            current_day: str | None = None
            buffer: list            = []

            def flush():
                """Persist the buffered lines for current_day into out."""
                if current_day and current_day in self.week_dates:
                    date = self.week_dates[current_day]
                    out[date] = self._maybe_translate(buffer) if buffer else ["No menu found"]

            for line in lines:
                # Is this line a weekday header? (exact match against known variants)
                matched_day = self._variant_to_day.get(line.upper())

                if matched_day:
                    flush()
                    current_day = matched_day
                    buffer      = []
                    continue

                if current_day:
                    # Stop collecting if we hit a footer/price section
                    if any(s in line.upper() for s in self._STOP_WORDS):
                        flush()
                        current_day = None
                        buffer      = []
                        continue
                    if len(line) > 5:
                        buffer.append(line)

            flush()  # persist the last day

        except Exception as e:
            for date in self._week_date_set:
                out[date] = [f"Error: {e}"]

        return self._fill_missing(out)

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def scrape_all(self, filter_name: str = None) -> dict:
        """
        Fetch all restaurants in parallel.
        Returns: {restaurant_name: {date_iso: [dishes]}}
        """
        def matches(n: str) -> bool:
            return not filter_name or filter_name.lower() in n.lower()

        results = {}
        with ThreadPoolExecutor(max_workers=15) as exe:
            futures: dict = {}

            for name, cost in self.COMPASS.items():
                if matches(name):
                    futures[exe.submit(self.fetch_compass, name, cost)] = name

            for name, url in self.FACTORY.items():
                if matches(name):
                    futures[exe.submit(self.fetch_factory, name, url)] = name

            for name, uuid in self.LUNCHER.items():
                if matches(name):
                    futures[exe.submit(self.fetch_luncher, name, uuid)] = name

            if matches("Oikeus"):
                futures[exe.submit(self.fetch_oikeus)] = "Oikeus"

            for f in as_completed(futures):
                name = futures[f]
                try:
                    results[name] = f.result()
                except Exception as e:
                    results[name] = {d: [f"Thread Error: {e}"] for d in self._week_date_set}

        return results

    # ── View helpers ──────────────────────────────────────────────────────────

    def today_view(self, all_data: dict) -> dict:
        """Slice to today: {restaurant_name: [dishes]}"""
        return {
            name: days.get(self.today_iso, ["No menu found"])
            for name, days in all_data.items()
        }

    def week_view(self, all_data: dict) -> dict:
        """
        Full week structure (Mon→Fri order):
        {day_name: {date: str, restaurants: {name: [dishes]}}}
        """
        week = {}
        for day_en in self.WEEKDAYS:
            date_iso = self.week_dates[day_en]
            week[day_en] = {
                "date": date_iso,
                "restaurants": {
                    name: days.get(date_iso, ["No menu found"])
                    for name, days in all_data.items()
                },
            }
        return week


# ── Pretty printers ───────────────────────────────────────────────────────────

def _lang_badge(lang: str) -> str:
    return "🇫🇮  Finnish" if lang == "fi" else "🇬🇧  English"


def print_today(meta: dict, restaurants: dict):
    badge = _lang_badge(meta["lang"])
    date_label = meta["date"]
    day_label  = meta["day"].upper()
    today_mark = "  ◀ TODAY" if meta["date"] == meta["real_today"] else ""
    print(f"\n🍽  LUNCH — {day_label}  {date_label}{today_mark}  [{badge}]")
    print("─" * 54)
    for name in sorted(restaurants):
        print(f"\n  📍 {name}")
        for dish in restaurants[name]:
            print(f"     • {dish}")
    print(f"\n{'─' * 54}")
    print(f"  Scraped at {meta['scraped_at']}\n")


def print_week(meta: dict, week: dict):
    badge      = _lang_badge(meta["lang"])
    week_dates = [v["date"] for v in week.values()]
    print(f"\n🗓  LUNCH WEEK  {week_dates[0]} → {week_dates[-1]}  [{badge}]")
    print("═" * 54)
    for day_en, day_data in week.items():
        date     = day_data["date"]
        is_today = date == meta["real_today"]
        marker   = "  ◀ TODAY" if is_today else ""
        print(f"\n  ┌{'─' * 50}┐")
        print(f"  │  {day_en.upper():12}  {date}{marker:<10}│")
        print(f"  └{'─' * 50}┘")
        for name in sorted(day_data["restaurants"]):
            print(f"\n    📍 {name}")
            for dish in day_data["restaurants"][name]:
                print(f"       • {dish}")
    print(f"\n{'═' * 54}")
    print(f"  Scraped at {meta['scraped_at']}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="lunchbot",
        description="LunchBot — Helsinki lunch menus in English or Finnish",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands (optional, default = today):
  today / list   Today's menus
  week           Full week Mon–Fri

options:
  --finnish      Show menus in Finnish (default: English)
  --restaurant   Filter by name, partial match, case-insensitive
  --json         Raw JSON output instead of pretty text

examples:
  lunchbot
  lunchbot today
  lunchbot week
  lunchbot --date tomorrow
  lunchbot --date friday
  lunchbot --date yesterday
  lunchbot --date "next monday"
  lunchbot --date 2026-04-10
  lunchbot week --date "next monday"
  lunchbot --restaurant "Roihu" --date tomorrow
  lunchbot --finnish --date friday
  lunchbot --json
  lunchbot week --date "next monday" --restaurant "Factory" --finnish --json
""",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="today",
        choices=["today", "list", "week"],
        help="today (default), list (alias for today), week",
    )
    parser.add_argument(
        "--restaurant", "-r",
        dest="restaurant",
        metavar="NAME",
        help="Filter to one restaurant (partial name, case-insensitive)",
    )
    parser.add_argument(
        "--finnish",
        action="store_true",
        help="Show menus in Finnish instead of English",
    )
    parser.add_argument(
        "--date", "-d",
        dest="date",
        metavar="DATE",
        default=None,
        help=(
            "Date to query: today, tomorrow, yesterday, "
            "monday…friday, next friday, last monday, YYYY-MM-DD. "
            "Defaults to today."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of pretty text",
    )

    args = parser.parse_args()
    lang = "fi" if args.finnish else "en"

    # Resolve --date expression to a concrete date
    target_date = None
    if args.date:
        try:
            target_date = resolve_date(args.date)
        except ValueError as e:
            print(f"❌ {e}", flush=True)
            raise SystemExit(1)

    scraper    = LunchScraper(lang=lang, target_date=target_date)
    all_data   = scraper.scrape_all(filter_name=args.restaurant)
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    week_dates_list = list(scraper.week_dates.values())
    meta = {
        "today":      scraper.today_iso,       # requested date (may differ from real today)
        "real_today": scraper.real_today_iso,  # actual today, for ◀ TODAY marker
        "day":        scraper.day_en,
        "lang":       lang,
        "week_start": week_dates_list[0],
        "week_end":   week_dates_list[-1],
        "scraped_at": scraped_at,
    }

    if args.command in ("today", "list"):
        restaurants = scraper.today_view(all_data)
        meta_out    = {**meta, "date": scraper.today_iso, "mode": "today"}
        if args.json:
            print(json.dumps({"meta": meta_out, "restaurants": restaurants},
                             ensure_ascii=False, indent=2))
        else:
            print_today(meta_out, restaurants)

    else:  # week
        week     = scraper.week_view(all_data)
        meta_out = {**meta, "mode": "week"}
        if args.json:
            print(json.dumps({"meta": meta_out, "week": week},
                             ensure_ascii=False, indent=2))
        else:
            print_week(meta_out, week)


if __name__ == "__main__":
    main()
