#!/usr/bin/env node
// Explain or list siting-screen results from the shell, using the same
// docs/screens.js the website runs.
//
//   node scripts/screen.js list                     screens and their criteria
//   node scripts/screen.js explain <site-id> [key]  one site, every screen (or one)
//   node scripts/screen.js top <key> [N]            the first N sites in rank order
//   node scripts/screen.js counts                   how many sites meet k criteria, per screen
//
// The site record is built the way the browser builds it: program record
// first, then each enrichment file fills only fields that are still empty,
// then stale geographic fields from evidence-invalidations.json are removed.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const DATA = process.env.SCREEN_DATA_DIR || path.join(ROOT, "docs", "data");  // override for tests
const Screens = require(path.join(ROOT, "docs", "screens.js"));

const PROGRAM_FILES = ["sites.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"];
const ENRICHMENT_FILES = ["infra-proximity.json", "water-proximity.json", "port-proximity.json",
  "nickel-anchor-proximity.json", "parcel-owner.json", "eia-retired-plants.json",
  "planned-retirements-proximity.json", "fema-nri.json",
  "acreage-flags.json", "coord-quality.json"];
const read = f => JSON.parse(fs.readFileSync(path.join(DATA, f), "utf8"));

function loadCorpus() {
  const byId = new Map();
  for (const f of PROGRAM_FILES) for (const s of read(f).sites) if (!byId.has(s.id)) byId.set(s.id, {...s});
  // Every input is required: ranking without one would differ from the
  // browser, which shows a failed-load state instead.
  const missing = ENRICHMENT_FILES.filter(f => !fs.existsSync(path.join(DATA, f)));
  if (missing.length) {
    console.error(`missing screen input(s): ${missing.join(", ")}`);
    process.exit(2);
  }
  for (const f of ENRICHMENT_FILES) {
    for (const rec of read(f).sites) {
      const s = byId.get(rec.id);
      if (!s) continue;
      for (const [k, v] of Object.entries(rec)) if (k !== "id" && k !== "program" && s[k] == null) s[k] = v;
    }
  }
  const inv = read("evidence-invalidations.json").by_id || {};
  for (const [id, x] of Object.entries(inv)) {
    const s = byId.get(id);
    if (!s || !x.invalidate) continue;
    for (const f of x.clear_fields || []) delete s[f];
    Object.assign(s, x.restore_core_fields || {});
  }
  return [...byId.values()];
}

// Each screen ranks one population (screens.js `universe`).
const UNIVERSES = {
  corpus: loadCorpus,
  installations: () => read("ap1000-sites.json").sites,
  civilian: () => read("nuclear-civilian-sites.json").sites,
  coal: () => read("coal-plants.json").plants,
  retired: () => read("retired-industrial.json").sites,
};
const cache = {};
const universe = name => (cache[name] = cache[name] || UNIVERSES[name]());

const mark = {pass: "✓", fail: "✗", unknown: "?"};
function printEval(site, key) {
  const sc = Screens.SCREENS[key];
  if (sc.applies && !sc.applies(site)) { console.log(`  ${sc.label}: not in scope (${sc.scope || "filtered out"})`); return; }
  const ev = Screens.evaluate(site, key);
  console.log(`  ${sc.label}: ${ev.met} of ${ev.total} met, ${ev.unknown} unknown`);
  for (const r of ev.results) {
    const c = sc.criteria.find(x => x.id === r.id);
    console.log(`    ${mark[r.status]} ${r.label.padEnd(26)} ${String(r.value).padEnd(16)} rule: ${c.rule} [${c.kind}] ${c.source.url}`);
  }
}

function main([cmd, a, b]) {
  if (!cmd || cmd === "list") {
    for (const sc of Object.values(Screens.SCREENS)) {
      console.log(`${sc.key}: ${sc.label} — ${sc.method}`);
      for (const c of sc.criteria) console.log(`  - ${c.label}: ${c.rule} [${c.kind}] ${c.source.title} ${c.source.url}`);
      if (sc.tieBreak) console.log(`  tie-breaker: ${sc.tieBreak.label}`);
    }
    return;
  }
  if (cmd === "explain") {
    const keys = b ? [b] : Object.keys(Screens.SCREENS);
    let found = false;
    for (const key of keys) {
      const site = universe(Screens.SCREENS[key].universe).find(s => s.id === a);
      if (!site) continue;
      if (!found) console.log(`${site.id} · ${site.name} · ${site.state || ""} · ${site.program || Screens.SCREENS[key].universe}`);
      found = true;
      printEval(site, key);
    }
    if (!found) throw new Error(`unknown site id ${a}`);
  } else if (cmd === "top" && process.argv.includes("--json")) {
    // Machine-readable: full site record plus the per-criterion results.
    const n = Number(b) || 20;
    const rows = Screens.rank(universe(Screens.SCREENS[a].universe), a).slice(0, n);
    console.log(JSON.stringify(rows.map((r, i) => ({rank: i + 1, ev: r.ev, site: r.site}))));
  } else if (cmd === "top") {
    const n = Number(b) || 20;
    Screens.rank(universe(Screens.SCREENS[a].universe), a).slice(0, n).forEach((r, i) =>
      console.log(`${String(i + 1).padStart(3)}. ${r.ev.met}/${r.ev.total} (${r.ev.unknown}?) ${String(r.site.id).padEnd(18)} ${r.site.state || ""} ${r.site.name}`));
  } else if (cmd === "coverage") {
    // Per criterion: how many in-scope sites pass, fail or are unknown. A
    // criterion that is unknown for most of its universe says what the tab
    // cannot tell the user, however good the ranking looks.
    const out = {};
    for (const [key, sc] of Object.entries(Screens.SCREENS)) {
      const rows = Screens.rank(universe(sc.universe), key);
      out[key] = {scope: rows.length, criteria: {}};
      for (const c of sc.criteria) out[key].criteria[c.id] = {pass: 0, fail: 0, unknown: 0, rule: c.rule, kind: c.kind};
      for (const r of rows) for (const x of r.ev.results) out[key].criteria[x.id][x.status]++;
    }
    console.log(JSON.stringify(out));
  } else if (cmd === "sources") {
    const out = [];
    for (const [key, sc] of Object.entries(Screens.SCREENS))
      for (const c of sc.criteria) out.push({screen: key, criterion: c.id, title: c.source.title, url: c.source.url, kind: c.kind});
    console.log(JSON.stringify(out));
  } else if (cmd === "counts") {
    for (const key of Object.keys(Screens.SCREENS)) {
      const rows = Screens.rank(universe(Screens.SCREENS[key].universe), key);
      const hist = {};
      for (const r of rows) hist[r.ev.met] = (hist[r.ev.met] || 0) + 1;
      console.log(`${key.padEnd(10)} in scope ${String(rows.length).padStart(6)} · met→sites ${JSON.stringify(hist)}`);
    }
  } else throw new Error(`unknown command ${cmd}`);
}

main(process.argv.slice(2));
