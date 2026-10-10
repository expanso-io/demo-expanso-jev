# Demo design system

The positive half of the quality bar. `lint-demo-ui.py` and `DEMO_REVIEW.md` say what a demo must not do; this file says what to build instead — the tokens, type rails, components, and layouts that good demos share so gates pass by construction.

**The contract: shared skeleton, per-demo palette.** Every mature demo in this corpus is mono-first, radially lit, and topology-first, with its palette tailored to its subject and host per the Theme section of `../AGENTS.md` and recorded in `DESIGN_BRIEF.md`.

Reference implementations, in order of authority:
1. `demo-fleet-telemetry-databricks/dashboard/` — the only `--video-strict` clean dashboard; when this file and that demo disagree, check which one moved last.
2. `demo-space-force-edge-routing/dashboard/` — the visual benchmark fleet was built to (its own CSS says so), providing composition, SVG ground maps, incident cards, and popup inspectors.
3. `demo-airborne-vehicle/dashboard/` (the F-35 demo) — the typographic reference using Barlow Condensed over IBM Plex Mono (vendored), rationed accents with named meanings (ready/T0/down), and declared type-scale rails with `docs/RESEARCH.md`.
4. `demo-modbus-edge-operations/public/` — the most complete build featuring accessibility evidence, contract tests, and scenario vocabulary.

**What to take from a reference, and what never to take.** A reference board is a reference for behaviour (drawing scenarios rather than labelling them, one colour per meaning, outcomes as instruments, click-to-open records, lanes matching source height, and hover-paused shelves), never for its ground, accents, glyphs, vocabulary, or mood.

**The swap test.** Pass the swap test by verifying that covering all words on screen still leaves the subject domain recognizable from graphics, materials, and palette alone without inheriting past demo themes.

**Choose symbols for the story.** Choose imagery from the subject (log slips for logs, pumpjacks for wells, satellites for orbital routes) and reserve dollar signs for when spend is part of the demo's argument.

---

## No internal scrolling

Internal horizontal and vertical scrollbars are forbidden in every demo and shared component, including dialogs, inspectors, log panes, tables, and menus.
Hiding a scrollbar while preserving an internal scroll container does not comply.
Only the document may scroll vertically; the document must never overflow horizontally.
Handle overflowing content using bounded rows, pagination, focused drill-down modals, and copy or download actions for complete records.
Keep log entries on one visual line with concise previews that grant access to full values.
`lint-demo-ui.py` rejects literal nested `overflow: auto` and `scroll` declarations, while browser tests detect computed scroll containers and horizontal overflow across viewports.

---

## Tokens

Name tokens exactly to preserve automated contrast verification with `CONTRAST_PAIRS` in `lint-demo-ui.py` (`--text`/`--text-dim` on `--bg`/`--surface` and `--ink`/`--dim`/`--secondary` on `--bg`).
Custom palette names like `--panel`, `--muted`, or `--quiet` without canonical registration silently evade contrast checking.

```css
:root {
  color-scheme: dark;

  /* ground — three elevations and a line */
  --bg:        #0b1220;   /* page field            */
  --surface:   #121c2b;   /* panel                 */
  --surface-2: #18263a;   /* raised panel, popup   */
  --line:      #2a4058;   /* borders               */

  /* ink — two levels are enough */
  --text:      #edf4ff;
  --text-dim:  #a9bfd8;

  /* accents — rationed, load-bearing only */
  --accent:    #6fc3ff;   /* Expanso orchestrator, the data lane        */
  --ok:        #8ee6a1;   /* value landed, state on                     */
  --warn:      #ffc06e;   /* degraded, raw, pending                     */
  --err:       #ff9d9d;   /* failed, disabled, down                     */
  --kept:      #68707c;   /* retained locally (alias of --text-dim / --quiet) */

  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

The house dark variant (`showcase/tokens.css`) and house light variant (`showcase/tokens-light.css`) share identical token names so `new-demo.py --palette dark|light` derives all palette-specific literals from a single source of truth.
Palettes are per-demo variants that keep the three-elevation ground, two ink levels, and rationed accents while re-huing values to fit the subject and host:

| Demo | Ground | Accent story |
|---|---|---|
| fleet-telemetry-databricks | `#04182e` deep utility blue | blue `#4da3ff` / green `#97d65e` |
| space-force-edge-routing | `#050e17` near-black | cyan `#57dcff` / mint `#a5f3c4` / ctl `#8fb6ff` |
| modbus / feeder | `#071019` | cyan `#58dcff` / mint `#85efbb` / orange `#ff8c67` |
| airborne-vehicle | `#070d13` | ice `#6fd3ff` / ready `#7ff0b0` / T0 amber `#ffb454` |
| kubernetes-worker-cloud | `#061321` | cyan `#54dfff` / violet `#c2b4ff` |
| agriculture-data (light) | `#f2ede2` warm paper, ink `#2c3122` | grain `#3f9d5a` / Expanso violet `#6d3aed` / Postgres `#336791` — subject-led |
| oil-gas-motherduck (light) | `#f4efea` MotherDuck cream, ink `#383838` | duck `#ff9538` / Expanso violet `#7c3aed` / verified teal `#0d8577` — host-led, lives inside a MotherDuck Dive |

The body background must be declared as a literal hex, not `var(--bg)`: `body { background: #0b1220; }` (layered under ambient radials) so the `video-theme` check can verify agreement with `color-scheme: light` or dark.

### The extended ramp — when four accents are not enough

The extended token ramp provides an editorial superset for rich documents, landing pages, and complex tables:

```css
:root {
  --canvas:    #f6f6f3;   /* ground; warm here, cool in building-ops */
  --surface:   #ffffff;   /* panel floating on the canvas            */
  --surface-2: #f0ebff;   /* tinted panel, one per accent family     */
  --surface-dark: #17141c; /* inversion: one dark section mid-page   */

  --ink:   #17141c;       /* body                                    */
  --muted: #554f5e;       /* secondary, captions                     */
  --quiet: #6c6475;       /* table chrome, meta, timestamps          */

  --line:        #d5d0da; /* default border                          */
  --line-strong: #aaa1b2; /* border that has to hold a shape         */

  --violet: #6743cf;  --violet-soft: #f0ebff;
  --green:  #087f5b;  --green-soft:  #e6f5ef;
  --amber:  #9a5a05;  --amber-soft:  #fff3d7;
  --orange: #d94b18;  --orange-soft: #fff0e9;

  --page: 1220px;
}
```

Every accent is a pair where the strong hue draws text and borders (`color: var(--green)`) while the `-soft` companion fills behind it (`background: var(--green-soft)`).
Three ink levels (`--ink`, `--muted`, `--quiet`) allow secondary chrome, units, and timestamps to recede above the AA threshold without disappearing.
Two border weights separate hairline divisions (`--line`) from structural boundaries (`--line-strong`).
`--surface-dark` provides the inversion token for flipping a specific section dark on a light canvas.
`CONTRAST_PAIRS` in `lint-demo-ui.py` checks AA contrast for `--ink`, `--muted`, and `--quiet` against `--canvas` and `--surface`.

---

## Type

Mono is the house voice using `ui-monospace, SFMono-Regular, Menlo, monospace` with zero font files or network requests.
Optional display faces (such as Barlow Condensed or Archivo) must be vendored locally with `vendor-fonts.py` and never loaded via CDN.
Banned primary typefaces include Inter, Roboto, Arial, Helvetica, helvetica neue, system-ui, -apple-system, and Segoe UI.

Type scale rails are strictly limited to literal values:

| Rail | Use |
|---|---|
| `13px` | every label, caption, pill, table cell — the floor, never below |
| `14px` | body, feed rows |
| `24px` | the big number (`.tile .k`, `.node .big`) |

Optional `18px` and `32px` rails are permitted only when layouts require intermediate subheadings or hero displays.
`--video-strict` errors on type sizes under 13px and counts occurrences under 11px separately.
Keep rails literal and do not hide sizes in `clamp()` (such as `clamp(10px, …)`) or `var()` because linters cannot evaluate them.

---

## Radii, spacing, effects

Corner radii must strictly use the scale: `0 / 2px / 4px / 8px / 16px`, `9999px` for pills, and `50%` for dots (small elements 4px, panels 8px).
`snap-radii.py` snaps strays onto these standard radii rails.
Spacing rules standardise on `12px 14px` panel padding, `12px` grid gaps, and `4px` tight clusters.
Effects budget allows a maximum of 12 declarations per demo (gradients, shadows, blurs) with ambient effects limited to two corner radials and one masthead gradient:

```css
body {
  background:
    radial-gradient(1100px 600px at 10% 6%,  rgba(ACCENT, .12), transparent 60%),
    radial-gradient(900px  560px at 88% 18%, rgba(OK,     .09), transparent 60%),
    #0b1220;
}
header { border-bottom: 2px solid transparent;
         border-image: linear-gradient(90deg, var(--accent), var(--ok)) 1; }
```

All non-ambient visual effects must encode system state (such as a glow on an active element) rather than wallpaper panels.

---

## Component vocabulary

Use standard component shapes from the shared vocabulary:

| Component | Shape | Reference |
|---|---|---|
| **Masthead** | brand + one-line sub + tabs + status pills, sticky, gradient underline | `demo-fleet-telemetry-databricks/dashboard/index.html` |
| **Status pill** | `.pill[data-state="on|warn|off"]` — colored text + alpha border, never a filled chip | fleet `styles.css` |
| **Pulsing dot** | `50%` radius, soft `box-shadow` halo, `@keyframes pulse` — running state only | space-force, modbus |
| **Tab bar** | 2–3 views, `aria-selected`, swaps `[hidden]` sections; no client routing | fleet, modbus `.view-switcher` |
| **KPI tile** | `.tile` — `.k` 24px number over `.l` 13px label; grid `auto-fit minmax(170px,1fr)` | fleet `.tiles` |
| **Topology board** | the hero: fixed-height stage, node cards positioned on it, canvas or SVG flow between them | fleet `.topology` + `canvas#flow`; modbus `.topology-shell` |
| **Node card** | `.node` — name, big number, state; `.disabled { opacity:.45; filter:grayscale(.8) }` is the off state | fleet |
| **Flow particles** | canvas 2D, quadratic-bezier lanes, rAF loop, DPR-aware; density scaled from *measured* rates, never decorative | fleet `app.js` |
| **Event feed** | `.feed li` — timestamped rows, `.fresh` highlight, honest empty state ("awaiting motion", not "No data") | space-force |
| **Bottom shelf** | fixed-height live-stream strip pinned under the main view, 4-column grid | modbus `.stream-shelf` |
| **Hovertable** | data table where color carries the point — `td.raw` amber vs `td.canon` green is a before/after in one row | fleet `.hovertable` |
| **YAML panel** | `pre.yaml` with `.k .s .n .b .v .c` spans — keys accent, strings ok-green, numbers warn-amber | fleet, space-force (same class names) |
| **Popup inspector** | `.popup[data-open]` — `white-space: pre`, JS-set columns; read space-force's comment before "fixing" wrapping | space-force |
| **Site chip grid** | `.site-chip` — dense `repeat(3,1fr)` asset grid, one live number each | fleet `.sites` |
| **Savings meter** | bandwidth kept vs shipped — both quantities in one frame at one scale | space-force `.bandwidth`, modbus `.edge-meter` |

The house pattern rejects third-party charting libraries, preferring hand-drawn canvas or inline SVG.
Accessibility floor requires a `.skip-link` and `:focus-visible { outline: 3px solid var(--warn); outline-offset: 3px; }`.

### Icons and illustrations — `showcase/icons.svg` first

**Make the board graphical.** The presenter talks over every demo and points at what the board shows, so draw the real subject: the truck, the pump, the satellite, the rack, the camera frame, each with a short label to point at. Many small labelled graphics beat one paragraph. `demo-space-force-edge-routing/dashboard/` and `demo-factory-powerbi` are the exemplars, and the reference library's lit factory windows and pumpjacks show the standard.

**Source graphics down this ladder**, taking the first rung that has the real thing:
1. **The kit sprite** when it already has the symbol; copy `showcase/icons.svg` into the demo.
2. **Public icon and illustration repositories** whose licence allows use in an Expanso demo (public domain, CC0, CC BY with attribution, MIT, Apache-2.0, or a vendor's published brand kit for its own logo). Government archives such as NASA images are good subject imagery.
3. **Purchased assets** are fine. Buy what the demo needs and record it the same way.
4. **Custom SVG drawn in Paper** through its local MCP (`http://127.0.0.1:29979/mcp`, Paper Desktop running with a file open) when no source has the subject. Export real SVG with Paper's export tool, never a canvas screenshot. Validate that it parses, has the intended `viewBox`, renders at its board size, and carries no external references or undeclared embedded rasters. If Paper is unavailable, say so, author the SVG directly and validate it the same way; never claim it came from Paper.

**Record every sourced graphic.** Files from rungs 2 to 4 live under the demo's `media/` with a `media/LICENSES.md` entry naming each file, its source URL, author or vendor, licence, any modification, and the date checked (follow `demo-contested-logistics-node/media/LICENSES.md`). The `media-licence` lint warns on a graphic that no entry names.

**Illustrations show real things.** Draw the real subject or the real system state the board already computes. Never draw a fabricated metric, a chart of numbers nothing measured, or a decorative scene with no data behind it.

**The anti-slop list still binds.** No Lucide, sparkle, or other default-library look that the reference anti-slop list forbids (`~/.dotfiles/config/agents/reference/website-anti-slop.md`). A graphic earns its place by depicting the subject, not by filling space.

Kit UI icons are 33 symbols from `showcase/icons.svg` on a 24px grid with 1.75 stroke, `currentColor`, and no fills. A UI icon from another rung uses the same `currentColor` and `em` sizing, and a stroke weight that sits beside the sprite:

```html
<svg class="icon" aria-hidden="true"><use href="icons.svg#alert"/></svg>
```
```css
.icon { display:inline-block; width:1em; height:1em; fill:none;
        stroke:currentColor; stroke-width:1.75; stroke-linecap:round;
        stroke-linejoin:round; vertical-align:-0.125em; flex:none; }
```

Sizing icons in `em` and stroking in `currentColor` ensures they scale with text and match palette token colors automatically.
Never use emoji as icons because they vary across operating systems, sit off optical baselines, and duplicate adjacent labels (e.g. `⚠️ Flagged for Rework`).
The `emoji` lint check errors on emoji pictographs while explicitly exempting punctuation glyphs `✓ ✔ ✗ ✘ ✕ ×`.
Icons beside text labels are decorative (`aria-hidden="true"`), while standalone icons require `<title>` or `aria-label`.
An icon must carry content: the concept class assigned in [SEMANTICS.md](SEMANTICS.md), a state, or the subject itself. A pictograph that only restates the word beside it is noise; cut it. A standalone subject illustration that conveys state needs an accessible name like any standalone icon.

---

## Flow grammar — the standing spec for every topology board

Every topology board visibly includes the source on the left, an Expanso edge node with logo, an orchestrator (Expanso Cloud) above with bidirectional control lanes, and updating destinations on the right.
`probe-motion.py` runs in `just check` to verify that topology boards display motion within 1.5 s at zero state and under forced reduced motion.
Particles originate at individual sources, emit continuously before the pipeline is live, and dissipate at the edge boundary while idle.
Particles appear faint inside the source container and reach full opacity only after exiting.
Flow lanes connect box boundaries (in at left, out at right), never interior chips, with faint guide paths visible between particles.
Particle density scales with measured rates, produces a visible burst on recovery, and weights flow across multiple destinations.
Fault state tints a proportion of source particles to the error color.
`prefers-reduced-motion` damps motion (≈0.35×) but never stops flow entirely.
Non-running stages are grayed out (grayscale plus reduced opacity) rather than hidden, and pre-roll states display calm text like "STANDBY" rather than "LOST".
Topology pipelines are controlled exclusively from Expanso Cloud ("ORCHESTRATED BY EXPANSO CLOUD · JOB RUNNING"), with failure injection running on automated cycles.
Under the source sits a fixed-size live shelf of incoming signals where hovering pauses the stream and displays the complete unclipped record.
Under the Expanso node sits pretty pipeline YAML in `pre.yaml` with `.k/.s/.n/.b/.v/.c` spans.
Presenter views must preserve subject graphics, orchestrator topology, bucket counts, meaningful state, and units, simplifying log rows to explanatory fields while voiceover provides context.
In co-branded demos, sample the partner's palette from their live site, assigning partner accent to their side, Expanso violet to ours, and following host ground.

---

## Layout archetypes

Layout archetypes establish clear structure across demos:
- **A — Topology board (default)**: Masthead, topology stage hero, KPI tile row, two-up detail panels, and footer.
- **B — Tabbed views**: Archetype A with 2–3 tabs swapping `[hidden]` sections in a single document.
- **C — Instrument panel**: The named failure mode ("nothing is prominent, so nothing is") where four equal tiles and a log obscure narrative focus.
- **D — Full-bleed map**: Permitted only when geography is the central claim.

Responsive breakpoints are restricted to ~900px (stacking topology nodes) and optionally ~700px, keeping the payoff in the 9:16-safe center for 16:9 recordings.

---

## Known gate holes

Automated linters enforce necessary baselines but have blind spots:
- `body { background: var(--bg) }` evades the `video-theme` check, which only inspects literal hex values against declared `color-scheme`.
- `clamp()` and `var()` font sizes evade the 13px floor check, requiring literal rail declarations.
- Custom token names outside `CONTRAST_PAIRS` leave contrast unverified.
- The `video-script` check only accepts `RECORDING_SCRIPT.md` at the demo root, rejecting names like `DEMO_SCRIPT.md` or `DEMO_RUNBOOK.md`.
- Non-font CDNs (unpkg, tailwind) must be vendored locally to prevent booth network failures.
- macOS-only system display faces (`Avenir Next`, `SF Pro`, `Helvetica Neue`) must be vendored to prevent silent platform font fallback.
- Tailwind utility classes like `rounded-xl` (12px) evade the radius check because the linter inspects literal `border-radius` declarations.
- Pictographs outside the four unicode ranges in `EMOJI` (such as the hourglass at U+23F3) evade detection unless reviewed visually.
- Canvas animation that triggers only on event arrival passes motion probes but fails causal review.
- Run `just video-check` to validate banned fonts, CDN fonts, emoji, radii, canonical contrast, and sub-13px type.
