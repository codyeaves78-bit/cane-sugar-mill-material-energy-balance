(function () {
  'use strict';

  const TABS = [
    { id: 'steam', label: 'Steam Tables', enabled: true },
    { id: 'mill', label: 'Mill Floor', enabled: true },
    { id: 'clar', label: 'Clarification', enabled: true },
    { id: 'heat', label: 'Juice Heating', enabled: false },
    { id: 'pan', label: 'Pan Floor', enabled: false },
    { id: 'evap', label: 'Evaporation', enabled: false },
    { id: 'exhaust', label: 'Exhaust Summary', enabled: false },
    { id: 'turb', label: 'Turbines & Boiler', enabled: false },
    { id: 'cool', label: 'Cooling Tower', enabled: false },
    { id: 'cond', label: 'Condensate Balance', enabled: false },
    { id: 'export', label: 'Download', enabled: false },
  ];

  function buildTabs() {
    const nav = document.getElementById('tabs');
    const main = document.getElementById('main');
    TABS.forEach((tab, i) => {
      const btn = document.createElement('button');
      btn.textContent = tab.label;
      btn.disabled = !tab.enabled;
      btn.dataset.tab = tab.id;
      if (i === 0) btn.classList.add('active');
      btn.addEventListener('click', () => showTab(tab.id));
      nav.appendChild(btn);

      const section = document.createElement('section');
      section.id = 'tab-' + tab.id;
      section.hidden = i !== 0;
      if (!tab.enabled) {
        section.innerHTML = `<div class="panel"><p class="placeholder">${tab.label} is not built yet. See web/PROGRESS.md for the port roadmap.</p></div>`;
      }
      main.appendChild(section);
    });
  }

  function showTab(id) {
    document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
    document.querySelectorAll('main section').forEach(s => s.hidden = s.id !== 'tab-' + id);
  }

  // ---------------------------------------------------------------------
  // Steam Tables utility tab -- a live sanity check of the IAPWS97 port,
  // and a standalone steam-property lookup tool in its own right.
  // ---------------------------------------------------------------------

  const MODES = {
    TP: { a: { key: 'T', label: 'Temperature (F)' }, b: { key: 'P', label: 'Pressure (psia)' } },
    Px: { a: { key: 'P', label: 'Pressure (psia)' }, b: { key: 'x', label: 'Quality (0-1)' } },
    Tx: { a: { key: 'T', label: 'Temperature (F)' }, b: { key: 'x', label: 'Quality (0-1)' } },
    Ph: { a: { key: 'P', label: 'Pressure (psia)' }, b: { key: 'h', label: 'Enthalpy (BTU/lb)' } },
    Ps: { a: { key: 'P', label: 'Pressure (psia)' }, b: { key: 's', label: 'Entropy (BTU/lb-R)' } },
  };

  function buildSteamTab() {
    const section = document.getElementById('tab-steam');
    section.innerHTML = `
      <div class="panel">
        <h2>Steam Property Lookup (IAPWS-97)</h2>
        <div class="grid">
          <div>
            <label>Input pair</label>
            <select id="ss-mode">
              <option value="TP">Temperature &amp; Pressure</option>
              <option value="Px">Pressure &amp; Quality</option>
              <option value="Tx">Temperature &amp; Quality</option>
              <option value="Ph">Pressure &amp; Enthalpy</option>
              <option value="Ps">Pressure &amp; Entropy</option>
            </select>
          </div>
          <div><label id="ss-label-a"></label><input id="ss-a" type="number" step="any"></div>
          <div><label id="ss-label-b"></label><input id="ss-b" type="number" step="any"></div>
          <div><label>Flow (lb/hr, optional)</label><input id="ss-flow" type="number" step="any" value="0"></div>
        </div>
        <p><button class="primary" id="ss-calc">Calculate</button></p>
        <div id="ss-result"></div>
      </div>`;

    const modeSel = section.querySelector('#ss-mode');
    const labelA = section.querySelector('#ss-label-a');
    const labelB = section.querySelector('#ss-label-b');
    const inputA = section.querySelector('#ss-a');
    const inputB = section.querySelector('#ss-b');
    const resultDiv = section.querySelector('#ss-result');

    function applyMode() {
      const m = MODES[modeSel.value];
      labelA.textContent = m.a.label;
      labelB.textContent = m.b.label;
    }
    modeSel.addEventListener('change', applyMode);
    applyMode();

    // sensible defaults: 180 psig saturated steam
    modeSel.value = 'Px';
    applyMode();
    inputA.value = 194.7;
    inputB.value = 1;

    section.querySelector('#ss-calc').addEventListener('click', () => {
      const m = MODES[modeSel.value];
      const kwargs = {};
      kwargs[m.a.key] = parseFloat(inputA.value);
      kwargs[m.b.key] = parseFloat(inputB.value);
      kwargs.flow_lb_per_hr = parseFloat(section.querySelector('#ss-flow').value) || 0;

      try {
        const s = new SteamStream(kwargs);
        const p = s.properties();
        const rows = [
          ['Temperature', p.T.toFixed(2), 'F'],
          ['Pressure', p.P.toFixed(3), 'psia'],
          ['Enthalpy', p.h.toFixed(2), 'BTU/lb'],
          ['Entropy', p.s.toFixed(4), 'BTU/lb-R'],
          ['Quality', p.x === null || p.x === undefined ? '-' : p.x.toFixed(4), ''],
          ['Specific volume', p.v.toFixed(4), 'ft3/lb'],
          ['Density', p.rho.toFixed(4), 'lb/ft3'],
          ['Latent heat (h_fg at P)', p.h_fg.toFixed(2), 'BTU/lb'],
          ['Superheated?', p.is_superheated ? 'Yes' : 'No', ''],
          ['Flow', p.flow_lb_per_hr.toLocaleString(), 'lb/hr'],
        ];
        resultDiv.innerHTML = '<table><tbody>' +
          rows.map(([k, v, u]) => `<tr><td>${k}</td><td>${v}</td><td>${u}</td></tr>`).join('') +
          '</tbody></table>';
      } catch (e) {
        resultDiv.innerHTML = `<p class="error">${e.message}</p>`;
      }
    });
  }

  // ---------------------------------------------------------------------
  // Shared plant state -- lets later tabs (Clarification, ...) chain off
  // the mill floor's mixed juice / bagasse streams once it has been solved.
  // ---------------------------------------------------------------------
  const PlantState = { mill: null, clar: null };

  function inputField(id, label, value, step) {
    return `<div><label for="${id}">${label}</label><input id="${id}" type="number" step="${step || 'any'}" value="${value}"></div>`;
  }

  function readFields(section, ids) {
    const out = {};
    ids.forEach((id) => { out[id] = parseFloat(section.querySelector('#' + id).value); });
    return out;
  }

  function fmt(v, digits) {
    if (v === null || v === undefined || Number.isNaN(v)) return '-';
    return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function renderTable(headers, rows) {
    const thead = '<thead><tr>' + headers.map((h) => `<th>${h}</th>`).join('') + '</tr></thead>';
    const tbody = '<tbody>' + rows.map((r) => '<tr>' + r.map((c) => `<td>${c}</td>`).join('') + '</tr>').join('') + '</tbody>';
    return `<div class="table-wrap"><table>${thead}${tbody}</table></div>`;
  }

  // ---------------------------------------------------------------------
  // Mill Floor tab
  // ---------------------------------------------------------------------
  function buildMillTab() {
    const section = document.getElementById('tab-mill');
    section.innerHTML = `
      <div class="panel">
        <h2>Mill Floor Inputs</h2>
        <div class="grid">
          ${inputField('mf-cane_tpd', 'Cane throughput (TPD)', 19000, 100)}
          ${inputField('mf-cane_pol_pct', 'Cane pol (%)', 13.5, 0.1)}
          ${inputField('mf-cane_fiber_pct', 'Cane fiber (%)', 14.0, 0.1)}
          ${inputField('mf-number_of_mills', 'Number of mills', 6, 1)}
          ${inputField('mf-mill_1_fiber_rise_load_fraction', 'Mill 1 fiber rise load fraction', 0.35, 0.01)}
          ${inputField('mf-imbibition_pct_on_cane', 'Imbibition (% on cane)', 30.0, 0.5)}
          ${inputField('mf-juice_temp_F', 'Juice temperature (F)', 90.0, 1)}
          ${inputField('mf-mix_juice_purity', 'Mixed juice purity (%)', 88.0, 0.1)}
          ${inputField('mf-bagasse_pol_pct', 'Bagasse pol (%)', 2.1, 0.1)}
          ${inputField('mf-last_roll_purity', 'Last roll juice purity (%)', 72.0, 0.5)}
          ${inputField('mf-bagasse_moisture_pct', 'Bagasse moisture (%)', 49.5, 0.5)}
          ${inputField('mf-bagasse_ash_pct', 'Bagasse ash (%)', 5.0, 0.5)}
        </div>
        <p><button class="primary" id="mf-calc">Calculate</button></p>
        <div id="mf-result"></div>
      </div>`;

    const resultDiv = section.querySelector('#mf-result');

    section.querySelector('#mf-calc').addEventListener('click', () => {
      try {
        const v = readFields(section, [
          'mf-cane_tpd', 'mf-cane_pol_pct', 'mf-cane_fiber_pct', 'mf-number_of_mills',
          'mf-mill_1_fiber_rise_load_fraction', 'mf-imbibition_pct_on_cane', 'mf-juice_temp_F',
          'mf-mix_juice_purity', 'mf-bagasse_pol_pct', 'mf-last_roll_purity',
          'mf-bagasse_moisture_pct', 'mf-bagasse_ash_pct',
        ]);

        const mill = new MillFloor({
          cane_tpd: v['mf-cane_tpd'],
          cane_pol_pct: v['mf-cane_pol_pct'],
          cane_fiber_pct: v['mf-cane_fiber_pct'],
          imbibition_pct_on_cane: v['mf-imbibition_pct_on_cane'],
          bagasse_pol_pct: v['mf-bagasse_pol_pct'],
          last_roll_purity: v['mf-last_roll_purity'],
          bagasse_moisture_pct: v['mf-bagasse_moisture_pct'],
          bagasse_ash_pct: v['mf-bagasse_ash_pct'],
          mix_juice_purity: v['mf-mix_juice_purity'],
          number_of_mills: Math.round(v['mf-number_of_mills']),
          juice_temp_F: v['mf-juice_temp_F'],
          mill_1_fiber_rise_load_fraction: v['mf-mill_1_fiber_rise_load_fraction'],
          name: 'Mill Floor',
        });

        PlantState.mill = mill;

        const mj = mill.mixed_juice_stream;
        const bag = mill.bagasse_stream;

        const metrics = `
          <div class="metrics">
            <div class="metric"><div class="metric-label">Mill extraction</div><div class="metric-value">${fmt(mill.mill_extraction_pct, 2)}%</div></div>
            <div class="metric"><div class="metric-label">Mixed juice flow</div><div class="metric-value">${fmt(mj.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Mixed juice brix / purity</div><div class="metric-value">${fmt(mj.brix, 2)}% / ${fmt(mj.purity, 1)}%</div></div>
            <div class="metric"><div class="metric-label">Bagasse flow</div><div class="metric-value">${fmt(bag.flowrate_lb_hr / 2000 * 24, 0)} TPD</div></div>
          </div>`;

        const { rows, in_tot, out_tot } = mill._stream_table_rows();
        const diff = in_tot.map((x, i) => x - out_tot[i]);
        const streamRows = rows.map(([name, dir, ...vals]) => [name, dir, ...vals.map((x) => fmt(x, 2))]);
        streamRows.push(['Total In', '', ...in_tot.map((x) => fmt(x, 2))]);
        streamRows.push(['Total Out', '', ...out_tot.map((x) => fmt(x, 2))]);
        streamRows.push(['Difference', '', ...diff.map((x) => fmt(x, 4))]);
        const streamTable = renderTable(
          ['Stream', 'Dir', 'Flow (TPH)', 'Pol (TPH)', 'Brix (TPH)', 'Fiber (TPH)', 'Water (TPH)'],
          streamRows,
        );

        const mbRows = mill.mill_balances.map((m) => [
          m.mill, fmt(m.bagasse_in_tpd, 1), fmt(m.mac_in_tpd, 1), m.mac_in_source,
          fmt(m.bagasse_out_tpd, 1), fmt(m.juice_out_tpd, 1), m.juice_out_dest,
        ]);
        const mbTable = renderTable(
          ['Mill', 'Bagasse In', 'Liquid In', 'Liquid In Source', 'Bagasse Out', 'Juice Out', 'Juice Out Dest'],
          mbRows,
        );

        const bal = mill.balance_check;
        const balRows = Object.entries(bal).map(([k, v]) => [k, fmt(v.in_tph, 4), fmt(v.out_tph, 4), fmt(v.diff_tph, 6)]);
        const balTable = renderTable(['Quantity', 'In (TPH)', 'Out (TPH)', 'Diff (TPH)'], balRows);

        resultDiv.innerHTML = metrics +
          '<h3 class="section-title">Stream Table (TPH)</h3>' + streamTable +
          '<h3 class="section-title">Per-Mill Maceration Balance (TPD)</h3>' + mbTable +
          '<h3 class="section-title">Balance Check</h3>' + balTable;
      } catch (e) {
        resultDiv.innerHTML = `<p class="error">${e.message}</p>`;
      }
    });

    section.querySelector('#mf-calc').click();
  }

  // ---------------------------------------------------------------------
  // Clarification tab
  // ---------------------------------------------------------------------
  function buildClarTab() {
    const section = document.getElementById('tab-clar');
    section.innerHTML = `
      <div class="panel">
        <h2>Clarification Inputs</h2>
        <div class="grid">
          ${inputField('cl-filter_wash_water_pct_on_cane', 'Filter wash water (% on cane)', 5.0, 0.5)}
          ${inputField('cl-filter_cake_pct_on_cane', 'Filter cake (% on cane)', 5.0, 0.5)}
          ${inputField('cl-filter_cake_pol_pct', 'Filter cake pol (%)', 2.4, 0.1)}
          ${inputField('cl-clarified_juice_purity', 'Clarified juice purity (%)', 88.5, 0.1)}
          ${inputField('cl-limed_juice_cold_temp_f', 'Limed juice cold temp (F)', 95.0, 1)}
          ${inputField('cl-limed_juice_hot_temp_f', 'Limed juice hot temp (F)', 220.0, 1)}
          ${inputField('cl-clarified_juice_temp_f', 'Clarified juice temp (F)', 205.0, 1)}
          ${inputField('cl-lime_lb_per_ton_cane', 'Lime dose (lb/ton cane)', 1.3, 0.1)}
          ${inputField('cl-lime_baume', 'Milk of lime (Baume)', 10.0, 0.5)}
          ${inputField('cl-polymer_conc_ppm', 'Polymer concentration (ppm)', 5000.0, 100)}
          ${inputField('cl-polymer_lb_per_ton_cane', 'Polymer dose (lb/ton cane)', 0.045, 0.005)}
          ${inputField('cl-clarifier_underflow_pct_cane', 'Clarifier underflow (% on cane)', 20.0, 0.5)}
        </div>
        <p><button class="primary" id="cl-calc">Calculate</button></p>
        <div id="cl-result"></div>
      </div>`;

    const resultDiv = section.querySelector('#cl-result');

    section.querySelector('#cl-calc').addEventListener('click', () => {
      if (!PlantState.mill) {
        resultDiv.innerHTML = '<p class="error">Solve the Mill Floor tab first -- Clarification needs its mixed juice stream.</p>';
        return;
      }
      try {
        const v = readFields(section, [
          'cl-filter_wash_water_pct_on_cane', 'cl-filter_cake_pct_on_cane', 'cl-filter_cake_pol_pct',
          'cl-clarified_juice_purity', 'cl-limed_juice_cold_temp_f', 'cl-limed_juice_hot_temp_f',
          'cl-clarified_juice_temp_f', 'cl-lime_lb_per_ton_cane', 'cl-lime_baume',
          'cl-polymer_conc_ppm', 'cl-polymer_lb_per_ton_cane', 'cl-clarifier_underflow_pct_cane',
        ]);

        const clar = new Clarification({
          mixed_juice_stream: PlantState.mill.mixed_juice_stream,
          cane_tpd: PlantState.mill.cane_tpd,
          filter_wash_water_pct_on_cane: v['cl-filter_wash_water_pct_on_cane'],
          filter_cake_pct_on_cane: v['cl-filter_cake_pct_on_cane'],
          filter_cake_pol_pct: v['cl-filter_cake_pol_pct'],
          clarified_juice_purity: v['cl-clarified_juice_purity'],
          limed_juice_cold_temp_f: v['cl-limed_juice_cold_temp_f'],
          limed_juice_hot_temp_f: v['cl-limed_juice_hot_temp_f'],
          clarified_juice_temp_f: v['cl-clarified_juice_temp_f'],
          lime_lb_per_ton_cane: v['cl-lime_lb_per_ton_cane'],
          lime_baume: v['cl-lime_baume'],
          polymer_conc_ppm: v['cl-polymer_conc_ppm'],
          polymer_lb_per_ton_cane: v['cl-polymer_lb_per_ton_cane'],
          clarifier_underflow_pct_cane: v['cl-clarifier_underflow_pct_cane'],
          name: 'Clarification',
        });

        PlantState.clar = clar;
        const cj = clar.clarified_juice_stream;

        const metrics = `
          <div class="metrics">
            <div class="metric"><div class="metric-label">Clarified juice flow</div><div class="metric-value">${fmt(cj.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Clarified juice brix / purity</div><div class="metric-value">${fmt(cj.brix, 2)}% / ${fmt(cj.purity, 1)}%</div></div>
            <div class="metric"><div class="metric-label">Flash vapor</div><div class="metric-value">${fmt(clar.flash_vapor_pct, 3)}%</div></div>
            <div class="metric"><div class="metric-label">Filter cake pol loss</div><div class="metric-value">${fmt(clar.filter_cake_pol_lb_per_day, 0)} lb/day</div></div>
          </div>`;

        const streamRows = clar._collect_streams().map((r) => [
          r[0], r[1], r[2], fmt(r[3], 0), fmt(r[4], 0), fmt(r[5], 0), fmt(r[6], 0),
          fmt(r[7], 2), fmt(r[8], 2), r[9] === null ? '-' : fmt(r[9], 1), fmt(r[10], 2),
          r[11] === null ? '-' : fmt(r[11], 0),
        ]);
        const streamTable = renderTable(
          ['#', 'Stream', 'Dir', 'lb/hr', 'GPM', 'Brix lb/hr', 'Pol lb/hr', 'Brix %', 'Pol %', 'Purity %', '% on Cane', 'F'],
          streamRows,
        );

        const bal = clar.balance_check;
        const balRows = ['lb_per_hr', 'brix_lb_per_hr', 'pol_lb_per_hr'].map((k) => [
          k, fmt(bal.in[k], 2), fmt(bal.out[k], 2), fmt(bal.difference[k], 4),
        ]);
        const balTable = renderTable(['Quantity', 'In', 'Out', 'Diff'], balRows);

        resultDiv.innerHTML = metrics +
          '<h3 class="section-title">Stream Table (tags match the diagram)</h3>' + streamTable +
          '<h3 class="section-title">Balance Check</h3>' + balTable;
      } catch (e) {
        resultDiv.innerHTML = `<p class="error">${e.message}</p>`;
      }
    });

    if (PlantState.mill) section.querySelector('#cl-calc').click();
  }

  document.addEventListener('DOMContentLoaded', () => {
    buildTabs();
    buildSteamTab();
    buildMillTab();
    buildClarTab();
  });
})();
