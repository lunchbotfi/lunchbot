---
name: lunchbot
description: >
  Fetch, display, and query lunch menus from restaurants in the
  Salmisaari/Ruoholahti area of Helsinki (Compass, Factory, Luncher, Oikeus
  networks). Use this skill whenever the user asks what's for lunch, wants to
  see today's or this week's menu, asks about restaurant options nearby, or
  says anything like "what can I eat today", "what's for lunch at Roihu",
  "lunch options", "today's food", "show menus", or "what's on this week".
  Supports English (default) and Finnish (--finnish flag). Also triggers when
  running `lunchbot` CLI commands or when a lunch_menu_scrapper.py file is
  mentioned. Always use this skill — don't try to answer lunch queries from
  memory.
compatibility:
  python: ">=3.8"
  pip: [requests, beautifulsoup4, lxml]
---

# LunchBot Skill

Scrapes and presents lunch menus from restaurants in the **Salmisaari/Ruoholahti
area of Helsinki** in parallel. Works as a Claude Code / AI agent skill, a
standalone CLI tool, or an OpenAI function.

---

## As a Claude Code / AI agent skill

When a user asks about lunch in natural language, run the scraper and answer
conversationally. You do **not** need to show raw CLI commands to the user —
just fetch the data and present it clearly.

> **⚠️ Menu availability:** Restaurants only publish menus for the **current week**.
> Next week's and last week's menus are not available. If a user asks about
> next week or last week, politely explain this and offer to show this week's
> menus instead.

**Example user requests and how to handle them:**

| User says | What to do |
|---|---|
| "What's for lunch today?" | Run scraper for today, all restaurants |
| "What's for lunch tomorrow?" | Run with `--date tomorrow` |
| "What was lunch yesterday?" | Run with `--date yesterday` |
| "What's for lunch on Friday?" | Run with `--date friday` |
| "What's for lunch at Roihu?" | Run with `--restaurant "Roihu"` |
| "Show me this week's menus" | Run with `week` command |
| "What's on at Factory this week in Finnish?" | Run `week --restaurant "Factory" --finnish` |
| "Any vegetarian options today?" | Fetch all, filter dishes containing VE/vegan markers |
| "What's for lunch next week?" | ❌ Explain menus are only available for the current week |
| "What was on the menu last week?" | ❌ Explain menus are only available for the current week |

**Run the scraper:**
```bash
python scripts/scrape.py today                              # today, all restaurants
python scripts/scrape.py today --date tomorrow              # tomorrow
python scripts/scrape.py today --date friday                # this Friday
python scripts/scrape.py today --date yesterday             # yesterday
python scripts/scrape.py today --date 2026-04-10            # exact ISO date
python scripts/scrape.py today --restaurant "Roihu"         # filter restaurant
python scripts/scrape.py week                               # full this week
python scripts/scrape.py today --finnish                    # Finnish
python scripts/scrape.py today --json                       # raw JSON
```

Parse the output and respond naturally — e.g. *"Today at Roihu: grilled salmon,
vegetable curry, and pea soup."* Don't just dump the raw list at the user.

---

## As a CLI tool

```bash
# Install
npm install -g @lunchbot/lunchbot-cli

# Today's menus (all equivalent)
lunchbot
lunchbot today
lunchbot list

# Full week Mon–Fri
lunchbot week

# Filter by restaurant (partial name, case-insensitive)
lunchbot --restaurant "Roihu"
lunchbot week --restaurant "Factory"

# Language (default: English)
lunchbot --finnish
lunchbot week --finnish
lunchbot --restaurant "Roihu" --finnish

# Raw JSON output — add --json to any command
lunchbot --json
lunchbot week --restaurant "Roihu" --json
```

### As an OpenAI function / tool
See `references/openai_function.json` for the full function schema to pass in `tools`.

---

## Language support

| Restaurant           | English              | Finnish              |
|----------------------|----------------------|----------------------|
| Roihu                | ✅ Native API         | ✅ Native API         |
| Food & Co Ruoholahti | ✅ Native API         | ✅ Native API         |
| Factory Ruoholahti   | ✅ Native (page EN section) | ✅ Native (page FI section) |
| Factory Salmisaari   | ✅ Native (page EN section) | ✅ Native (page FI section) |
| Dylan Milk           | ✅ Native API         | ✅ Native API         |
| Dylan Raspberry      | ✅ Native API         | ✅ Native API         |
| Hima & Sali          | ✅ Native API         | ✅ Native API         |
| Oikeus               | 🔄 Auto-translated    | ✅ Native (FI only)   |

English is the default. Use `--finnish` for Finnish menus.
Oikeus has no English version — English output is auto-translated via MyMemory API.

---

## Supported Restaurants

All restaurants are in the **Salmisaari / Ruoholahti area, Helsinki**.

| Restaurant           | Network      | Location        |
|----------------------|--------------|-----------------|
| Roihu                | Compass      | Ruoholahti      |
| Food & Co Ruoholahti | Compass      | Ruoholahti      |
| Factory Ruoholahti   | Factory      | Ruoholahti      |
| Factory Salmisaari   | Factory      | Salmisaari      |
| Dylan Milk           | Luncher      | Ruoholahti      |
| Dylan Raspberry      | Luncher      | Ruoholahti      |
| Hima & Sali          | Luncher      | Ruoholahti      |
| Oikeus               | Nordrest     | Ruoholahti      |

---

## Output Schema (JSON mode)

```json
{
  "meta": {
    "date": "2026-04-07",
    "day": "Tuesday",
    "lang": "en",
    "scraped_at": "2026-04-07 11:30:00"
  },
  "restaurants": {
    "Roihu": ["Dish 1 (allergens)", "Dish 2"],
    "Factory Ruoholahti": ["..."],
    "Dylan Milk": ["..."]
  }
}
```

Week mode wraps this per day:
```json
{
  "meta": { "mode": "week", "week_start": "2026-04-07", ... },
  "week": {
    "Monday": { "date": "2026-04-06", "restaurants": { ... } },
    "Tuesday": { ... }
  }
}
```

---

## Error Handling

Each restaurant fetches independently — one failure never blocks the others.
Errors appear as `["Error: <message>"]` for that restaurant only.
Surface these gracefully: *"Roihu menu unavailable today."*

---

## Files in This Skill

| Path | Purpose |
|------|---------|
| `scripts/scrape.py` | Core scraper — bilingual, parallel, CLI-wrapped |
| `scripts/install_deps.sh` | One-shot pip install for dependencies |
| `bin/lunchbot.js` | Node.js CLI entry point |
| `references/openai_function.json` | OpenAI `tools` schema |
| `references/npm_package.json` | Template package.json for npm publish |
