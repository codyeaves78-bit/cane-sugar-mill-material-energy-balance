# Web App Port — Progress & Plan

**Goal:** rebuild this entire Streamlit/Python mill balance app (`streamlit_app.py`,
and the ~30 domain classes it drives) as a single self-contained, fully
offline `.html` file (`web/index.html`) for easy distribution — open it in
any browser, no server, no install. Requested by the user 2026-09-10.

Read this file fully before doing anything else in a new session. It is the
only thing carrying context between sessions — this port spans many
independent daily working sessions (see "Working agreement" below), each of
which starts with zero memory of prior ones.

## Working agreement (confirmed with user 2026-09-10)

- **Scope order:** MVP first. Get a usable end-to-end pipeline (Mill Floor →
  Clarification → Juice Heating → Boiler/Turbines) working before circling
  back for Pan Floor, Evaporation, Cooling Tower, Condensate Balance, PFD
  diagrams, and Excel export. Don't try to do everything before anything is
  usable.
- **Fully offline:** no CDN scripts. Everything — steam tables, diagrams,
  export — is embedded in the one `.html` file. It must open and fully
  function from a `file://` URL with no internet connection.
- **Cadence:** an autonomous scheduled cloud routine runs every evening
  (~6pm America/Chicago) on branch `webapp-port` of this repo
  (`https://github.com/codyeaves78-bit/cane-sugar-mill-material-energy-balance`).
  It should: read this file, do the next unchecked chunk of work, validate it,
  commit + push to `webapp-port` (never to `main` — the user merges when
  ready), and append a dated entry to the Session Log below before finishing.
  A meaningful milestone (end of a phase) is a good point to open/update a PR
  to `main` for the user to review, but routine day-to-day progress should
  just be commits on the branch.
- Never force-push, never rewrite history on this branch, never touch `main`
  directly.

## Architecture decisions

- **Source lives in `web/src/*.js` + `web/src/app.css` + `web/template.html`.**
  `web/build.py` (pure Python, no Node needed) string-replaces marker
  comments in the template with each source file's contents and writes
  `web/index.html`. **Never hand-edit `web/index.html` directly** — edit the
  source files and re-run `python web/build.py`. This keeps the single
  deliverable file assemble-able without a JS bundler.
- **No Node.js in this dev sandbox** (confirmed 2026-09-10 — `node`, `npm`,
  `deno`, `bun` all absent). If a future session has Node available, great,
  use it (`node web/dev/validate.mjs` exists for that). If not, use the
  headless-browser trick below — it works and is already proven out.
- **IAPWS-IF97 steam engine (`web/src/iapws97.js`) implements Regions 1, 2,
  and 4 ONLY** (compressed liquid, superheated vapor, saturation dome).
  Region 3 (near-critical) and Region 5 (>1073K) are deliberately NOT
  implemented. This mill never exceeds ~950 psia / ~800°F anywhere in the
  process — nowhere close to the ~16.5 MPa (2398 psia) / 623.15K boundary
  where Region 3 would start to matter. Do not casually "extend to Region 3"
  if some future input pushes past that boundary — it's a substantial
  addition (different EOS form + iterative backward equations); re-scope
  deliberately if it's ever actually needed.
- **Coefficients were transcribed from the installed Python `iapws` package**
  (`iapws97.py` / `_iapws97Constants.py` in site-packages — the same library
  `SteamStream.py` already uses throughout this repo), not from memory. This
  keeps the JS port numerically consistent with the existing Python domain
  classes rather than introducing an independent (and possibly divergent)
  implementation.
- **`web/src/steam_stream.js`** is a thin English-unit wrapper around
  `iapws97.js`, mirroring `SteamStream.py` property-for-property (T °F, P
  psia, h BTU/lb, s BTU/lb·R, x, v ft³/lb, rho, h_fg, is_superheated). Every
  future domain-class port should consume `SteamStream` the same way its
  Python counterpart does — the API is intentionally identical so the port
  of each class can mirror the Python source closely.
- **UI shell (`web/src/app.js` + `app.css`):** a `TABS` array drives both the
  nav buttons and placeholder `<section>`s. To bring a tab online: write a
  `buildXTab()` function (see `buildSteamTab()` for the pattern), call it
  from the `DOMContentLoaded` handler, and flip that tab's `enabled: true`.
  Keep each tab's DOM-building + calculation logic together in one function
  per tab for now; revisit organization if/when this gets unwieldy.
- **Validation harness** (steam engine correctness):
  1. `python web/dev/regenerate_reference.py` — runs Python `iapws` across
     the mill's real operating envelope (pressures ~1–950 psia, temps to
     ~800°F, all of TP/Ph/Ps/Px input combos, including two-phase/wet-steam
     cases) and writes `web/dev/reference.json` + `reference.js` (the same
     data as a `window.REFERENCE_CASES = [...]` global, since `file://` pages
     can't reliably `fetch()` a local JSON file).
  2. Run `web/dev/validate.html` headlessly and read its output. Exact
     commands (Windows + git-bash; adjust the repo path if it moved):
     ```
     cd "c:\Python Projects\cane-sugar-mill-material-energy-balance"
     FILEURL="file:///$(cygpath -w "$(pwd)/web/dev/validate.html" | sed 's/\\\\/\//g; s/ /%20/g')"
     "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --virtual-time-budget=5000 --dump-dom "$FILEURL" 2>/dev/null > /tmp/dump.html
     grep -n '<pre' -A 20 /tmp/dump.html
     ```
     (Chrome works too if Edge isn't present:
     `/c/Program Files/Google/Chrome/Application/chrome.exe`.) The `file:///`
     + `cygpath -w` + manual `%20`-escaping is required — a bare `$(pwd)`
     produces a malformed URL that Edge silently mis-resolves (spent real
     time debugging this on 2026-09-10; don't redo that detour). Delete the
     `/tmp/dump.html` scratch file after reading it.
  3. If Node.js IS available in the session: `node web/dev/validate.mjs` does
     the identical check and is much less ceremony — prefer it when possible.
  - **Current status (2026-09-10): 580/580 cases pass**, max |Δh| / |Δs| /
    |ΔT| all at floating-point noise level (Newton-refined against the exact
    forward equations). `SteamStream.js` cross-checked directly against live
    `SteamStream.py` output too (see git history for the one-off check) —
    matched to ~1e-9 relative.
  - **Re-run this validation after ANY change to `iapws97.js`.** If a change
    is made to widen the pressure/temperature envelope (e.g. someone adds a
    boiler pushing past ~950 psia), widen `gen_reference.py`'s grid first,
    regenerate, then validate — don't just trust it.

## Directory map

```
web/
  index.html            <- THE deliverable (built, don't hand-edit)
  template.html         <- page shell with /*__MARKER__*/ placeholders
  build.py               <- assembles index.html from template + src/
  PROGRESS.md            <- this file
  src/
    iapws97.js            <- steam property engine (Regions 1,2,4)
    steam_stream.js       <- English-unit wrapper mirroring SteamStream.py
    sugar_stream.js       <- port of SugarStream.py + sugar_stream_properties.py
    bagasse.js            <- port of Bagasse.py
    mill_floor.js         <- port of MillFloor.py
    clarification.js      <- port of Clarification.py
    boiler.js             <- port of Boiler.py
    turbine.js             <- port of Turbine.py
    cogen_turbine.js        <- port of CogenTurbine.py (extends Turbine)
    mill_turbines.js         <- port of MillTurbines.py
    cane_prep_turbines.js    <- port of CanePrepTurbines.py
    auxillary_turbines.js    <- port of AuxillaryTurbines.py
    deaerator.js             <- port of Deaerator.py
    app.js                <- tab shell + per-tab UI/calc logic
    app.css               <- styling (light/dark aware)
  dev/                    <- dev-only tooling, not shipped in index.html
    gen_reference.py       <- generates reference.json via Python iapws
    json_to_js.py          <- wraps reference.json as reference.js
    regenerate_reference.py<- runs both of the above
    reference.json/.js     <- generated (safe to regenerate, don't hand-edit)
    validate.html           <- browser-based validation harness (see above)
    validate.mjs            <- Node equivalent, use if Node is available
```

## Plant-wide config to promote into a shared object

(from an audit of `streamlit_app.py` / `main.py` — see git log around
2026-09-10 for the full dependency-order writeup if more detail is needed).
These values are read by many stages and should live in one shared JS config
object (e.g. `PlantConfig`) rather than being re-entered per tab:

- `cane_tpd` (~19000), `cane_fiber_pct` (~14%) — feeds Mill Floor, Cane Prep /
  Mill Turbines (tons fiber/hr).
- Steam header pressures: fabrication exhaust psia (~30), V1–V4 vapor
  headers, live/boiler steam psig (~165–185). Used almost everywhere.
- Injection water temp (~90°F) and condenser leg ΔT (~5°F) — shared between
  Pan Floor and Evaporation.
- Target syrup brix (~65) — shared between Clarification output sizing, Pan
  Floor, and Evaporation.
- Default isentropic efficiency (~50%) — reused across all turbine groups.
- Boiling scheme choice (FBDM / TBDM / 3-boiling single magma / 2-boiling) —
  a structural choice, not just a number; determines which Pan Floor module
  gets built/used.

## Phase plan

Mirrors the pipeline order both `main.py` and `streamlit_app.py` already
follow. Check items off as they land; add sub-notes on tricky bits so the
next session doesn't have to rediscover them.

- [x] **Phase 0 — Steam engine foundation.** `iapws97.js`, `steam_stream.js`,
      validation harness, UI shell + working "Steam Tables" utility tab.
      **DONE 2026-09-10.**
- [x] **Phase 1 — Mill Floor + Clarification.** Port `MillFloor.py`,
      `Clarification.py`, `Bagasse.py`, `SugarStream.py`. Build the Mill
      Floor + Clarification tabs (inputs sidebar-equivalent + stream tables +
      balance-check tables, mirroring `streamlit_app.py`'s Mill Floor/
      Clarification tab sections). `MillFloor.mixed_juice_stream` feeds
      `Clarification`; `MillFloor.bagasse_stream` will later feed the Boiler.
      **DONE 2026-09-11.**
- [ ] **Phase 2 — Juice Heating, Boiler, Turbines, Deaerator.** Port
      `JuiceHeater.py` / `JuiceHeatingStation.py`, `Boiler.py`, `Turbine.py` /
      `CogenTurbine.py`, `MillTurbines.py` / `CanePrepTurbines.py` /
      `AuxillaryTurbines.py`, `Deaerator.py`. This closes an end-to-end MVP
      loop (cane in → bagasse → boiler steam → turbines → exhaust) which is
      the "usable" milestone worth a PR to `main` for the user to try.
      - [x] **Phase 2a — Boiler + Turbines + Deaerator.** **DONE 2026-09-12.**
        `Boiler.py`, `Turbine.py`, `CogenTurbine.py`, `MillTurbines.py`,
        `CanePrepTurbines.py`, `AuxillaryTurbines.py`, `Deaerator.py` ported
        and wired into a working "Turbines & Boiler" tab.
      - [ ] **Phase 2b — Juice Heating.** `JuiceHeater.py` /
        `JuiceHeatingStation.py` (needs `condensate_utils.flash_condensate`
        too). Not started. Once this lands, Phase 2 as a whole is complete
        and worth a PR to `main`.
- [ ] **Phase 3 — Pan Floor.** The most structurally complex phase — 4
      selectable schemes (`FourBoilingDoubleMagma`, `ThreeBoilingDoubleMagma`,
      `ThreeBoiling`, `TwoBoiling`), each with `Pan`, `Centrifugal`,
      `Crystallizer`, `Reheater` and scheme-specific split-fraction inputs.
      Port one scheme fully first (suggest FBDM, since it's the default in
      both existing entry points), get it working end to end, then add the
      other three.
- [ ] **Phase 4 — Evaporation.** `PreEvaporator.py` + the `EvaporatorSet`
      family (iterative solver — check `multi_effect_solver_scipy.py` /
      `EvaporatorSetIAPWS.py` for the exact algorithm; will need a JS
      iterative solver, e.g. simple fixed-point or Newton, in place of scipy).
      Depends on vapor bleed demand from Phase 2/3's steam totals.
- [ ] **Phase 5 — Cooling Tower + Condensate Balance + Exhaust Summary
      integration.** `CoolingTowerSystem.py`, `condensate_balance.py` /
      `condensate_utils.py`, tying together exhaust/vapor totals across all
      prior stages.
- [ ] **Phase 6 — PFD diagrams.** Inline SVG per station, echoing the visual
      language already established in the `*_diagram.py` files (tagged-arrow
      streams, trapezoid turbine glyph, etc. — see `cogen_turbine_diagram.py`
      for a recent example). Can be done incrementally alongside each phase
      above rather than saved entirely for the end, if a session has spare
      time after finishing that phase's calculations.
- [ ] **Phase 7 — Export.** Python side uses `openpyxl` (zipped .xlsx) which
      needs a JS zip library — against the offline/no-CDN constraint unless
      fully vendored inline. Leaning toward hand-writing the legacy
      **SpreadsheetML 2003 XML** format instead (plain XML, `.xls` extension,
      Excel opens it natively, no compression/zip library needed at all —
      fits the offline constraint far more easily). Decide for real when this
      phase starts; CSV-per-section export is the fallback if XML output
      proves troublesome.

## Session Log

- **2026-09-10** — Kicked off. Surveyed `streamlit_app.py`/`main.py` (via
  Explore agent) to map the 11-tab pipeline, inputs, and dependency order.
  Chose scope (MVP-first), offline-only, and autonomous daily-6pm cadence
  with the user. Built and validated the Region 1/2/4 IAPWS-IF97 engine
  against the installed Python `iapws` package (580 test cases, effectively
  exact match). Built the single-file assembly pipeline (`template.html` +
  `build.py`) and a working "Steam Tables" utility tab as the first real
  piece of `web/index.html`. Discovered this sandbox has no Node.js;
  worked out a headless-Edge/Chrome `--dump-dom` validation technique as the
  fallback (documented above in detail so it isn't re-derived). Created
  branch `webapp-port` for all of this work. Next session: start Phase 1
  (Mill Floor + Clarification) — read `MillFloor.py` and `Clarification.py`
  closely, port the calculations first (no UI), sanity-check numbers against
  a `python main.py` run with matching inputs, then build the tab UI.

- **2026-09-11** — Phase 1 complete: Mill Floor + Clarification fully ported
  and wired up. This sandbox turned out to *have* Node.js v22 available
  (unlike 2026-09-10 — availability apparently varies by sandbox instance,
  as PROGRESS.md already anticipated), so used `node -e`/`require()` directly
  against the `.js` source files for cross-checking rather than the
  headless-browser trick — much less ceremony when Node is present. Still
  did a final headless-Chromium `--dump-dom` pass (binary was preinstalled
  at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` in this container,
  not the Windows Edge/Chrome paths the 2026-09-10 notes describe — worth
  checking `/opt/pw-browsers` first in a Linux cloud sandbox before assuming
  no headless browser is available) to sanity-check the *built* `index.html`
  end-to-end with real DOM/JS, not just the source modules in isolation.
  - Ported `SugarStream.py` + `sugar_stream_properties.py` -> `sugar_stream.js`,
    `Bagasse.py` -> `bagasse.js`, `MillFloor.py` -> `mill_floor.js`,
    `Clarification.py` -> `clarification.js`. Same property/method names as
    the Python classes throughout (e.g. `mixed_juice_stream`, `bagasse_stream`,
    `balance_check`, `_stream_table_rows()`, `_collect_streams()`), per the
    working agreement, so the JS reads line-for-line against its Python
    source. These four are plain data/calc classes with no IAPWS97
    dependency — `SugarStream`'s BPE/latent-heat/sat-temp properties use the
    same fast polynomial correlations the Python does (deliberately *not*
    IAPWS97, matching the source's own choice — only valid 1-60 psia, fine
    for this mill's juice-side pressures).
  - Cross-checked against live Python (`python3 -c "..."` instantiating
    `MillFloor`/`Clarification` with matching inputs, dumped every property +
    `mill_balances` + both `balance_check` dicts + the full `streams` dict as
    JSON) across 4 cases: the Streamlit sidebar defaults (19000 TPD/6 mills),
    a second full case with different purities/temps/mill count (17000
    TPD/4 mills), the `number_of_mills=2` minimum-mills edge case, and the
    `limed_juice_hot_temp_f <= 212` branch where flash vapor is deliberately
    zero. All matched to float noise (< 1e-6 relative) on every field,
    including the per-mill maceration balance list and the full stream
    table dict — see git history for the exact one-off comparison scripts
    (not committed, they were `/tmp` scratch).
  - **Gotcha**: `clarification_diagram.py`'s `_collect_streams()` output
    order is `TAG_ORDER`, which is *not* the same order the `streams` dict
    is built in inside `Clarification.__init__` (compare the `raw` list
    there vs. `TAG_ORDER` — Flash Vapors/Clarified Juice/Filter Cake come
    right after Filter Wash Water in `TAG_ORDER`, before the "Internal"
    streams, whereas the dict's own insertion order has all the "In" streams
    first, then "Out", then "Internal"). Ported `_collect_streams()` as a
    `Clarification` method using the literal `TAG_ORDER` list transcribed
    from `clarification_diagram.py` — don't derive this order from the
    `streams` dict's insertion order, it's wrong.
  - UI: added `mill_floor.js`/`clarification.js`/`sugar_stream.js`/
    `bagasse.js` markers to `template.html` + `build.py`; added
    `buildMillTab()`/`buildClarTab()` to `app.js` following the
    `buildSteamTab()` pattern (one function per tab, inputs matching the
    Streamlit sidebar defaults exactly, a Calculate button, metrics + stream
    table + balance-check table). Introduced a small module-level
    `PlantState = { mill, clar }` in `app.js` so the Clarification tab can
    read back the Mill Floor tab's solved `mixed_juice_stream` — Clarification
    shows an error message telling the user to solve Mill Floor first if it
    hasn't been solved yet, rather than silently using stale/default data.
    Both tabs auto-solve once on page load with their default inputs (Mill
    Floor first, which lets Clarification's own auto-solve succeed
    immediately too) so the tabs aren't empty on first look. Added a small
    `.metrics`/`.metric` card CSS block and a generic `renderTable()` helper
    to `app.js` for the stream/balance tables (reused across both tabs; will
    likely get reused again by every future phase's tab).
  - Full plant "Solve Entire Plant" button (the Streamlit sidebar's global
    solve gate) was *not* ported — each tab solves independently against its
    own inputs for now, since only two of many future stages exist. Revisit
    this when more phases land and cross-tab recompute coupling gets
    unwieldy; for now the simpler per-tab Calculate button (matching the
    existing Steam Tables tab) was judged good enough and avoids premature
    plumbing for tabs that don't exist yet.
  - **Next step for a future session: start Phase 2** (Juice Heating,
    Boiler, Turbines, Deaerator) — read `JuiceHeater.py`/
    `JuiceHeatingStation.py`, `Boiler.py`, `Turbine.py`/`CogenTurbine.py`,
    `MillTurbines.py`/`CanePrepTurbines.py`/`AuxillaryTurbines.py`,
    `Deaerator.py` closely first. This phase is explicitly called out in the
    Phase Plan as the "usable MVP" milestone (cane in -> bagasse -> boiler
    steam -> turbines -> exhaust) — once it's done and validated, that's the
    point to open a PR to `main` for the user to actually try the app,
    per the working agreement above.

- **2026-09-12** — Phase 2a complete: Boiler + Turbines + Deaerator ported
  and wired up (Phase 2b, Juice Heating, is still open — see below). Node.js
  v22 was available in this sandbox too; used `node -e`/`require()` against
  the `.js` sources for cross-checking, plus a final headless-Chromium
  `--dump-dom` pass (binary at `/opt/pw-browsers/chromium-1194/chrome-linux/
  chrome`, same as 2026-09-11's container) against the *built* `index.html`.
  - Ported `Boiler.py` -> `boiler.js`, `Turbine.py` -> `turbine.js`,
    `CogenTurbine.py` -> `cogen_turbine.js` (extends `Turbine`, same as the
    Python class), `MillTurbines.py`/`CanePrepTurbines.py`/
    `AuxillaryTurbines.py` -> `mill_turbines.js`/`cane_prep_turbines.js`/
    `auxillary_turbines.js` (all three are thin "solve a list of `Turbine`s"
    wrappers, same property/method names as their Python originals), and
    `Deaerator.py` -> `deaerator.js`. `Turbine.h_out_isentropic` calls
    `IAPWS97.solve({P, s})` directly (not through `SteamStream`), mirroring
    the Python source's own direct `iapws.IAPWS97(P=..., s=...)` call — this
    is the same P/s-input path `iapws97.js` already validated in Phase 0, so
    no changes to the steam engine itself were needed.
  - Cross-checked against live Python (`python3 -c "..."`) for: `Boiler` at
    default/superheated/production-scale conditions (3 cases), `Turbine`/
    `CogenTurbine` at the classes' own `__main__` example conditions,
    `MillTurbines`/`CanePrepTurbines`/`AuxillaryTurbines`/`Deaerator` at
    their own `__main__` example conditions, and finally the *entire*
    "Turbines & Boiler" tab's default-input calculation end-to-end (every
    metric on the tab — live steam subtotal/total, exhaust available,
    exhaust required, makeup, boiler feed water temp from the deaerator,
    steam available from bagasse) against an equivalent hand-assembled
    Python script using the real `MillFloor`/`Boiler`/`Deaerator`/turbine-
    group classes with the same default inputs the tab ships with. All
    matched to float noise (< 1e-6 relative) on every field checked.
  - **Scope decision — Deaerator moved into this tab, "Exhaust Summary" not
    built as its own tab yet.** In `streamlit_app.py`, the Deaerator lives on
    a separate "Steam & Exhaust Summary" tab whose `total_exhaust_required`
    is `exhaust_for_Pre + exhaust_for_evaporators + exhaust_for_pans +
    exhaust_for_heaters + exhaust_for_da`, i.e. it needs Pre-Evaporator,
    Evaporator Sets, Pan Floor, and Juice Heating — none of which are ported
    yet (Juice Heating is Phase 2b; Pan Floor/Evaporation are Phases 3-4).
    Building a faithful "Exhaust Summary" tab now is therefore impossible.
    Instead: the Deaerator was folded directly into the "Turbines & Boiler"
    tab (its own panel, since the Boiler's feedwater-temp-from-deaerator
    coupling is real and worth keeping), and a manual "Additional exhaust
    required (lb/hr)" input stands in for the other stages' contribution —
    the tab still adds the Deaerator's own (correctly-computed)
    `steam_flow_lb_hr` on top of that manual number, so `total_exhaust_
    required` isn't just a placeholder, only the *other* consumers are.
    **When Phase 2b/3/4 land, this manual input should be replaced** by
    summing those stages' real exhaust demand, and the Deaerator panel
    should probably move to a dedicated "Exhaust Summary" tab matching the
    Python app's structure — don't forget to remove the placeholder input
    and its explanatory `<p class="note">` text at that point.
  - UI: added `boiler.js`/`turbine.js`/`cogen_turbine.js`/`mill_turbines.js`/
    `cane_prep_turbines.js`/`auxillary_turbines.js`/`deaerator.js` markers to
    `template.html` + `build.py`; flipped the `turb` tab to `enabled: true`
    in `app.js`'s `TABS` array; added `buildTurbTab()` following the
    established one-function-per-tab pattern. This tab needed one new UI
    pattern the earlier two tabs didn't: **editable row lists** (one row per
    knife/mill/auxiliary-turbine unit, since those lists vary in length —
    e.g. `number_of_mills` from the Mill Floor tab). Added a small
    `editableRowsTable()`/`readEditableRows()` helper pair to `app.js` for
    this — a plain grid of `<input>` cells keyed `${id}-${rowIndex}-${col
    Key}`, not a real spreadsheet-style editor (this app has no such
    widget) — reusable by any future tab with the same shape of input
    (Pan Floor's per-pan/per-centrifugal tables will likely want it too).
    Also added `turbineGroupTable()`, a JS port of `turbine_diagram.py`'s
    `_group_info()` adapter (one row per turbine + a TOTAL row, optional
    HP/TFH column, `skip` list for 0-HP units left out of the display) so
    all three turbine-group tables render with the same logic the Python
    app's PFD table / Excel export uses.
    The Mill Turbines row count is read from `PlantState.mill.number_of_
    mills` at tab-build time (Mill Floor auto-solves on page load before
    this tab builds, so it's always available) rather than being editable
    itself — matches the Python sidebar's own list-length coupling.
  - **Next step for a future session: Phase 2b — Juice Heating.** Read
    `JuiceHeater.py` (`JuiceHeaterShellTube`, ~180 lines) and
    `JuiceHeatingStation.py` (series/parallel heater trains, ~340 lines)
    closely. `JuiceHeatingStation` also imports `condensate_utils.
    flash_condensate` for its `clean_condensate`/`dirty_condensate`
    properties — read that function too (it's small) and port it alongside
    (e.g. as a `condensate_utils.js` shared module, since Pan Floor/
    Evaporation will need condensate flashing too later). Once Juice Heating
    is wired into its own tab (chaining off `Clarification`'s
    `clarified_juice_stream` / `limed_juice` streams, per
    `streamlit_app.py`'s "Juice Heating Station" + "Clarified Juice Heater"
    subsections around line 481/521), Phase 2 as a whole is done — that's
    the point to open a PR to `main` per the working agreement.
