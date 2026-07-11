# Stock.AI Demo — Transfer & Integration Guide

Handoff package for embedding the Stock.AI product demo into another site.
Read this file plus the sibling `stockai-demo.html` (same folder) — the demo is
one fully self-contained file: no external CSS, JS, fonts, images, or network calls.

- Source of truth: `c:\Code_Git\stock-analysis\docs\demo\stockai-demo.html`
- Live artifact preview: https://claude.ai/code/artifact/10679e96-5f75-495c-8656-f0b1cf80256c
- Snapshot date shown in the demo: **July 10, 2026** (real data from the app)

---

## 1. What the demo contains

One page, four blocks, all data hardcoded (no backend needed):

1. **Header + intro + stat strip** — product one-liner and 5 headline stats
   (689-ticker scan, 20-name AI shortlist, ~20 Gemini calls/day, 4 stop layers, 5 morning sell checks).
2. **Interactive tabbed tour** (`.tabbar` + 4 `.panel` divs) mimicking the app's tabs:
   - `#p-account` — TradeAI holdings table (6 tickers) with a **working "↻ REFRESH PRICES" simulation**
     (jitters prices ±0.4%, flashes cells, shows a toast).
   - `#p-sched` — market-day schedule timeline (9:40 sell checks → 3:00 PM pipeline chain).
   - `#p-dream` — dream-scan strategy buckets (Momentum / Reversal / SmartMoney).
   - `#p-admin` — mock of editable scheduler times + per-file purge rows.
3. **Risk engine cards** (`.rules`) — the four stop-losses; "daily-drop −8%" is tagged NEW.
4. **Pipeline strip** (`.pipe`) — measured stage timings (Dream ~75 min, Analyze ~13 min, etc.)
   and a compliance footer.

JavaScript (bottom of file, ~50 lines, vanilla, no libraries):
- Tab switching via `data-panel` attributes.
- `HOLD` array = the six holdings; `renderHoldings()` computes Today %, G/L, portfolio totals.
- Refresh button simulation with 700 ms fake latency + `#toast`.

## 2. Design tokens (match or map to your site's system)

Defined as CSS custom properties on `:root`:

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0a0a0f` | page ground (committed dark theme) |
| `--surface` / `--surface2` | `#111118` / `#1a1a24` | cards / inputs |
| `--border` | `#2a2a3a` | all hairlines |
| `--accent` | `#c8f135` | brand acid-green (CTAs, active tab, highlights) |
| `--accent2` | `#7c6af7` | secondary violet (sell-only pills) |
| `--text` / `--muted` | `#e8e8f0` / `#6b6b80` | copy |
| `--up` / `--down` / `--warn` | `#4ade80` / `#f87171` / `#fbbf24` | semantic P&L colors — keep these even if you rebrand |

Typography: the real app uses **Syne** (display, weights 700/800) and **DM Mono** (body/data).
The demo ships fallback stacks (`--display`, `--mono` tokens) because the artifact host blocks
font CDNs — **on your site, load the real fonts** for full fidelity:

```html
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
```

The demo is intentionally **single-theme dark** (it's a terminal-style trading product). If your
product page is light, wrap the demo in its own dark container rather than restyling it.

## 3. Integration options (pick one)

**A. Iframe (fastest, zero-collision — recommended).**
Copy `stockai-demo.html` into your site's static assets and embed:
```html
<iframe src="/assets/stockai-demo.html" title="Stock.AI interactive demo"
        style="width:100%;height:900px;border:1px solid #2a2a3a;border-radius:12px;background:#0a0a0f"
        loading="lazy"></iframe>
```

**B. Inline section (single visual flow, needs namespacing).**
The demo uses generic class names (`.card`, `.tab`, `.panel`, `.btn`, `.stat`, `.pill`, `.slot`,
`.rule`, `.stage`, `.header`, `.wrap`) and element-level `table/th/td` styles that WILL collide
with a host page. Before inlining:
1. Wrap everything in `<section id="stockai-demo">…</section>`.
2. Prefix every selector in the `<style>` block with `#stockai-demo ` (including `:root` vars →
   move them onto `#stockai-demo { … }`).
3. The JS queries are already scoped by IDs (`holdTable`, `refreshBtn`, `pv`, `pl`, `asOf`,
   `toast`) — those IDs must stay unique on the host page. Tab code uses
   `document.querySelectorAll('.tab')` — scope it to `#stockai-demo .tab` when inlining.
4. `body { background/font }` rules in the demo must be dropped when inlining.

**C. Rebuild as a component (React/Vue/etc.).**
All content is in three data structures worth porting as-is: the `HOLD` array (holdings),
the schedule slots (4 rows), and the stop-rule cards (4 items). Everything else is markup.

## 4. Product facts (for accurate marketing copy)

Use these numbers verbatim; they're measured, not invented:

- Paper-trading simulation of a **$100k account** — no real orders, and the page MUST keep a
  "not investment advice / simulation" disclaimer (footer text in the demo is pre-written).
- Daily **Dream Scan** scores **689 tickers** (~75 min, Yahoo Finance, rate-limit-paced).
- **Identify** shortlists **20 names** into 3 strategy buckets: Momentum 7 / Reversal 7 / SmartMoney 6.
- **Google Gemini** (`gemini-2.5-flash`) scores the shortlist: ~20 calls/day, throttled 1 per 20 s (~13 min).
- **Four layered stops**: hard −8% vs purchase · **daily-drop −8% vs yesterday's close (newest)** ·
  soft −6% + composite <50 · trailing −10% from peak once in profit. Fills modeled with
  liquidity-aware slippage (0.2–0.6% by market cap).
- **Built-in scheduler** (US-Eastern, market days only, NYSE holidays/early closes skipped):
  sell-only stop checks 9:40/10:20/10:40/11:20/11:40 · full Recommend 10:00 & 11:00 ·
  price refresh + Dream 1:30 PM · Identify→Fetch→Analyze→Recommend 3:00 PM (Recommend ~3:15,
  before the 4:00 close). Times editable in-app; duplicate Dream/Analyze runs auto-skipped.
- Account view shows **yesterday's close and live Today %** per holding; on-demand price refresh
  is ~6 API calls / ~2 s.
- Data sources: Yahoo Finance (prices/fundamentals), Google Gemini (assessments), FRED (macro).

## 5. Gotchas

- Holdings prices/shares in `HOLD` are a **July 10, 2026 snapshot** — fine for a demo, but the
  "DEMO" badge and snapshot date in the header should stay so it never reads as live data.
- The refresh button is a **simulation** (random ±0.4% jitter). Don't wire it to anything real
  on a marketing page; if you later want live data, the real endpoint is `POST /tradeai/refresh_prices`.
- `color-mix()` is used throughout — supported in all evergreen browsers (2023+); no IE fallback.
- Respect `prefers-reduced-motion`: the cell-flash animation already disables itself.
- Ticker symbols shown (BMNR, NBIS, CDE, IRWD, ANGX, ONDS) are real small-caps from the
  simulation; swap for neutral placeholders if that's a concern for your audience.
