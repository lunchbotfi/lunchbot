# 🍽 LunchBot — Helsinki lunch menus for AI agents.

Helsinki Salmisaari/Ruoholahti area lunch menus, straight to your terminal or AI agent — in English or Finnish.

An open-source CLI and AI agent skill that fetches today's or this week's lunch menus from all major restaurants in the Salmisaari/Ruoholahti area of Helsinki. One command gives the full daily spread across 8 restaurants.

[GitHub](https://github.com/lunchbotfi/lunchbot) · [Add Skill to Agent](#quick-start) · [Install CLI](#quick-start)

---

```
$ lunchbot today

🍽  LUNCH — WEDNESDAY  2026-04-08  [🇬🇧  English]
──────────────────────────────────────────────────────

  📍 Factory Ruoholahti
     • Vegan miso soup with tofu (VE+G+VS)
     • Sesame seed breaded chicken breast in chili sauce (M+G+VS)
     • Oven-baked sausages with Dijon mustard and cheese topping (L+G)
     • House spinach pancakes (L) lingonberry mash (VE+G)
     • Banoffee mousse (VL+gluten-free biscuit)

  📍 Roihu
     • Lentil soup with coconut (VE+G)
     • Grilled salmon with lemon butter sauce (L+G)
     • Chicken tikka masala with basmati rice (L+G)
     ...
```

---

## Quick Start

Choose your setup and copy the commands into your terminal.

### Agent (Claude Code, Cursor, Codex, OpenCode…)

```bash
# 1) Install the CLI
npm install -g @lunchbot/lunchbot-cli

# 2) Add the LunchBot skill to your agent
npx skills add lunchbotfi/lunchbot
```

Then just ask your agent naturally:
- *"What's for lunch today?"*
- *"Show me this week's menus in Finnish"*
- *"Any vegetarian options at Factory today?"*

### CLI only

```bash
# Install
npm install -g @lunchbot/lunchbot-cli

# Run
lunchbot
```

---

## What can I do with LunchBot?

Every command works standalone or via your AI agent. Add `--json` to any command for structured output.

### Today's menus

*"What's for lunch today?"*

```bash
lunchbot today
```

### Full week view

*"What's on the menu this week?"*

```bash
lunchbot week
```

### Filter by restaurant

*"What's for lunch at Roihu today?"*

```bash
lunchbot --restaurant "Roihu"
lunchbot week --restaurant "Factory"
```

### Query by date

*"What's for lunch tomorrow?"*
*"What was lunch yesterday?"*
*"What's on Friday?"*

```bash
lunchbot --date tomorrow
lunchbot --date yesterday
lunchbot --date friday          # this coming Friday
lunchbot --date 2026-04-10      # exact date (ISO format)
```

> **Note:** Menus are only published for the current week. Queries for next week
> or last week will return "No menu found" as the restaurants don't publish
> in advance or keep historical menus.

### Finnish menus

*"Näytä tämän viikon lounaslistat suomeksi"*

```bash
lunchbot --finnish
lunchbot week --restaurant "Factory" --finnish
```

### Raw JSON output

For scripting or piping into other tools:

```bash
lunchbot --json
lunchbot week --restaurant "Roihu" --json
```

---

## Restaurants covered

All restaurants are in the **Salmisaari / Ruoholahti area, Helsinki**.

| Restaurant            | Network   | English | Finnish |
|-----------------------|-----------|---------|---------|
| Roihu                 | Compass   | ✅ Native | ✅ Native |
| Food & Co Ruoholahti  | Compass   | ✅ Native | ✅ Native |
| Factory Ruoholahti    | Factory   | ✅ Native | ✅ Native |
| Factory Salmisaari    | Factory   | ✅ Native | ✅ Native |
| Dylan Milk            | Luncher   | ✅ Native | ✅ Native |
| Dylan Raspberry       | Luncher   | ✅ Native | ✅ Native |
| Hima & Sali           | Luncher   | ✅ Native | ✅ Native |
| Oikeus                | Nordrest  | 🔄 Auto-translated | ✅ Native |

---

## How It Works

**1. Fetches menus in parallel**
All 8 restaurants are scraped simultaneously — the whole thing runs in a few seconds.

**2. Native bilingual support**
Most restaurants have native EN/FI APIs or bilingual pages. No translation needed except Oikeus (Finnish-only site), which is auto-translated via MyMemory.

**3. One failure never blocks the rest**
Each restaurant fetches independently. If one is down, the others still show up.

---

## FAQ

### Does it work outside of Helsinki?

No — LunchBot is purpose-built for the Salmisaari/Ruoholahti office area. The restaurant list is hardcoded.

### Do I need an account or API key?

No. LunchBot scrapes public menu pages and free APIs. No login, no key.

### How fresh is the data?

Fetched live every time you run it — always today's actual menu.

### What does the allergen notation mean?

| Code | Meaning (FI) | Meaning (EN) |
|------|-------------|--------------|
| L    | Laktoositon | Lactose-free |
| VL   | Vähälaktoosinen | Low-lactose |
| G    | Gluteeniton | Gluten-free |
| VE   | Vegaaninen | Vegan |
| M    | Maidoton | Dairy-free |
| VS   | Sis. valkosipulia | Contains garlic |

### What if a restaurant shows "No menu found"?

The restaurant may be closed (public holidays, summer break) or their website structure may have changed. Open an issue on GitHub if it persists.

### Can I add more restaurants?

Yes! Pull requests are welcome. See the scraper structure in `scripts/scrape.py` — each network (Compass, Luncher, Factory, Nordrest) has its own fetch method.

---

## Development

```bash
# Clone
git clone https://github.com/lunchbotfi/lunchbot.git
cd lunchbot

# Set up Python env
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 lxml

# Run directly
python3 scripts/scrape.py today
python3 scripts/scrape.py week --finnish
python3 scripts/scrape.py --restaurant "Roihu" --json

# Test CLI locally (no publish needed)
npm link
lunchbot today
```

---

[GitHub](https://github.com/lunchbotfi/lunchbot) · [Issues](https://github.com/lunchbotfi/lunchbot/issues)

MIT Licensed · Not affiliated with any of the listed restaurants.
