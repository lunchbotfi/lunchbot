#!/usr/bin/env node
/**
 * lunchbot — CLI wrapper
 * Installed globally via: npm install -g @lunchbot/lunchbot-cli
 *
 * Usage:
 *   lunchbot                               # today, English, pretty
 *   lunchbot today / list                  # today, English, pretty
 *   lunchbot week                          # full week Mon-Fri, English, pretty
 *   lunchbot --finnish                     # today, Finnish, pretty
 *   lunchbot week --finnish                # full week, Finnish, pretty
 *   lunchbot --restaurant "Roihu"         # filter, today
 *   lunchbot week --restaurant "Factory"  # filter, week
 *   lunchbot --json                        # today, raw JSON
 *   lunchbot week --json                   # week, raw JSON
 *   lunchbot week --restaurant "Roihu" --finnish --json
 */

const { execFileSync, execSync } = require("child_process");
const path = require("path");

const SKILL_DIR = path.resolve(__dirname, "..");
const SCRIPT    = path.join(SKILL_DIR, "scripts", "scrape.py");

// ── Ensure Python deps ───────────────────────────────────────────────────────
function ensureDeps() {
  try {
    execSync("python3 -c \"import requests, bs4, lxml\"", { stdio: "ignore" });
  } catch {
    console.error("📦 Installing Python dependencies...");
    execSync(`bash "${path.join(SKILL_DIR, "scripts", "install_deps.sh")}"`, {
      stdio: "inherit",
    });
  }
}

// ── Parse CLI args ───────────────────────────────────────────────────────────
const COMMANDS  = new Set(["today", "list", "week"]);
const rawArgs   = process.argv.slice(2);

let   cmd     = "today";   // default
const restArgs = [];

for (const a of rawArgs) {
  if (COMMANDS.has(a) && cmd === "today") {
    cmd = a;
  } else {
    restArgs.push(a);
  }
}

const jsonOut = restArgs.includes("--json");
const finnish = restArgs.includes("--finnish");
const rIdx    = restArgs.findIndex(a => a === "-r" || a === "--restaurant");
const rName   = rIdx !== -1 ? restArgs[rIdx + 1] : null;
const dIdx    = restArgs.findIndex(a => a === "-d" || a === "--date");
const dVal    = dIdx !== -1 ? restArgs[dIdx + 1] : null;

ensureDeps();

// ── Build python call ────────────────────────────────────────────────────────
const pyArgs = [cmd];
if (jsonOut) pyArgs.push("--json");
if (finnish) pyArgs.push("--finnish");
if (rName)   pyArgs.push("--restaurant", rName);
if (dVal)    pyArgs.push("--date", dVal);

try {
  const result = execFileSync("python3", [SCRIPT, ...pyArgs], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  });
  process.stdout.write(result);
} catch (err) {
  console.error("❌ LunchBot scraper failed:", err.message);
  process.exit(1);
}
