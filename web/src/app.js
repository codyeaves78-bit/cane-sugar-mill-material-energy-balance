(function () {
  'use strict';

  const TABS = [
    { id: 'steam', label: 'Steam Tables', enabled: true },
    { id: 'mill', label: 'Mill Floor', enabled: true },
    { id: 'clar', label: 'Clarification', enabled: true },
    { id: 'heat', label: 'Juice Heating', enabled: true },
    { id: 'pan', label: 'Pan Floor', enabled: true },
    { id: 'evap', label: 'Evaporation', enabled: false },
    { id: 'exhaust', label: 'Exhaust Summary', enabled: false },
    { id: 'turb', label: 'Turbines & Boiler', enabled: true },
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
  const PlantState = { mill: null, clar: null, heat: null, pan: null };

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

  function checkboxField(id, label, checked) {
    return `<div class="checkbox-field"><input id="${id}" type="checkbox" ${checked ? 'checked' : ''}><label for="${id}" style="margin:0;">${label}</label></div>`;
  }

  // Editable row tables (name/HP/efficiency lists etc.) -- a plain grid of
  // <input> cells, since this app has no spreadsheet-style data editor.
  // A column with type: 'select' renders a <select> of c.options instead.
  function editableRowsTable(id, columns, rows) {
    const header = '<tr>' + columns.map((c) => `<th>${c.label}</th>`).join('') + '</tr>';
    const body = rows.map((row, i) => '<tr>' + columns.map((c) => {
      const inputId = `${id}-${i}-${c.key}`;
      if (c.type === 'select') {
        const opts = c.options.map((o) => `<option value="${o}"${o === row[c.key] ? ' selected' : ''}>${o}</option>`).join('');
        return `<td><select id="${inputId}">${opts}</select></td>`;
      }
      const type = c.type === 'text' ? 'text' : 'number';
      const step = c.type === 'text' ? '' : ` step="${c.step || 'any'}"`;
      return `<td><input id="${inputId}" type="${type}"${step} value="${row[c.key]}"></td>`;
    }).join('') + '</tr>').join('');
    return `<div class="table-wrap"><table class="editable"><thead>${header}</thead><tbody>${body}</tbody></table></div>`;
  }

  function readEditableRows(section, id, columns, count) {
    const rows = [];
    for (let i = 0; i < count; i++) {
      const row = {};
      columns.forEach((c) => {
        const el = section.querySelector(`#${id}-${i}-${c.key}`);
        row[c.key] = (c.type === 'text' || c.type === 'select') ? el.value : parseFloat(el.value);
      });
      rows.push(row);
    }
    return rows;
  }

  function fmtQuality(x) {
    return (x === null || x === undefined || x >= 1.0) ? 'Superheat' : x.toFixed(4);
  }

  // One row per turbine unit + a TOTAL row, mirroring turbine_diagram.py's
  // _group_info() (used by the Python app for its PFD table / Excel export).
  function turbineGroupTable(group, { tfhList = null, skip = null } = {}) {
    const headers = ['Unit', 'Inlet Flow (lb/hr)', 'Exhaust Avail (lb/hr)', 'HP'];
    if (tfhList) headers.push('HP/TFH');
    headers.push('Steam Rate (lb/HP-hr)', 'Inlet psia', 'Inlet °F', 'Outlet psia', 'Outlet °F', 'Outlet Quality');

    const rows = [];
    group.turbines.forEach((trb, i) => {
      if (skip && skip[i]) return;
      const ex = trb.exhaust_steam;
      const row = [trb.name, fmt(trb.steam_flow_lb_hr, 0), fmt(trb.exhaust_available, 0), fmt(trb.hp_demand, 0)];
      if (tfhList) row.push(fmt(tfhList[i], 1));
      row.push(fmt(trb.steam_rate, 2), fmt(trb.inlet_steam.P, 1), fmt(trb.inlet_steam.T, 1), fmt(ex.P, 1), fmt(ex.T, 1), fmtQuality(ex.x));
      rows.push(row);
    });

    const totalRow = ['TOTAL', fmt(group.total_inlet_flow_lb_hr, 0), fmt(group.total_exhaust_available_lb_hr, 0), fmt(group.total_hp, 0)];
    if (tfhList) totalRow.push(fmt(tfhList.reduce((a, b) => a + b, 0), 1));
    totalRow.push(fmt(group.total_inlet_flow_lb_hr / group.total_hp, 2), '', '', '', '', '');
    rows.push(totalRow);

    return renderTable(headers, rows);
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

  // ---------------------------------------------------------------------
  // Turbines & Boiler tab
  //
  // Mirrors streamlit_app.py's "Turbines & Boiler" tab (Cane Prep / Mill /
  // Auxiliary turbine groups + the boiler room), with the Deaerator folded
  // in directly rather than living on its own "Exhaust Summary" tab -- that
  // tab's total exhaust demand is the sum of Juice Heating, Pan Floor, and
  // Evaporation's steam consumption, none of which are ported yet. Until
  // they are, "Additional Exhaust Required" below is a manual placeholder
  // input standing in for that sum; the Deaerator's own steam demand is
  // still added on top of it exactly as Boiler.py's real pipeline does.
  // ---------------------------------------------------------------------
  const KNF_COLS = [
    { key: 'name', label: 'Name', type: 'text' },
    { key: 'hp_tfh', label: 'HP per Ton Fiber/hr', step: 0.5 },
    { key: 'eff', label: 'Isentropic Eff (%)', step: 1 },
  ];
  const MILL_COLS = [
    { key: 'hp_tfh', label: 'HP per Ton Fiber/hr', step: 0.5 },
    { key: 'eff', label: 'Isentropic Eff (%)', step: 1 },
  ];
  const AUX_COLS = [
    { key: 'name', label: 'Name', type: 'text' },
    { key: 'hp', label: 'HP', step: 5 },
    { key: 'eff', label: 'Isentropic Eff (%)', step: 1 },
  ];
  const AUX_DEFAULTS = [
    ['ID 123', 750], ['ID 4', 235], ['ID 5', 400], ['ID 6', 795], ['ID 7', 1200],
    ['FD 7', 233], ['ID 8', 1300], ['FD 8', 350],
    ['BFW 1', 400], ['BFW 2', 400], ['BFW 3', 400], ['JCE 1', 400],
  ];

  function buildTurbTab() {
    const section = document.getElementById('tab-turb');
    if (!PlantState.mill) {
      section.innerHTML = '<div class="panel"><p class="error">Solve the Mill Floor tab first -- the turbine groups need the fiber rate.</p></div>';
      return;
    }

    const numMills = PlantState.mill.number_of_mills;
    const millHpDefaults = [18.0, 16.0, 16.0, 16.0, 16.0, 18.0];
    const millRows0 = Array.from({ length: numMills }, (_, i) => ({
      hp_tfh: i < millHpDefaults.length ? millHpDefaults[i] : 16.0,
      eff: 50,
    }));
    const knfRows0 = [
      { name: 'Knife 1', hp_tfh: 16.0, eff: 50 },
      { name: 'Knife 2', hp_tfh: 16.0, eff: 50 },
      { name: 'Knife 3', hp_tfh: 16.0, eff: 50 },
    ];
    const auxRows0 = AUX_DEFAULTS.map(([name, hp]) => ({ name, hp, eff: 50 }));

    section.innerHTML = `
      <div class="panel">
        <h2>Live Steam Generation</h2>
        <p class="note">The boiler header condition used as the enthalpy source for every turbine group below (throttled to each group's own inlet pressure).</p>
        <div class="grid">
          ${inputField('tb-live_gen_psig', 'Live steam generated (psig)', 185.0, 5)}
          ${inputField('tb-live_gen_superheat', 'Superheat (F above sat, 0 = saturated)', 0.0, 5)}
          ${inputField('tb-live_gen_quality', 'Quality (used if superheat = 0)', 1.0, 0.01)}
        </div>
      </div>

      <div class="panel">
        <h2>Cane Prep (Knife) Turbines</h2>
        <div class="grid">
          ${inputField('tb-knf_live_psig', 'Knife live steam (psig)', 165.0, 5)}
          ${inputField('tb-knf_exh_psig', 'Knife exhaust (psig)', 16.0, 1)}
        </div>
        ${editableRowsTable('tb-knf', KNF_COLS, knfRows0)}
      </div>

      <div class="panel">
        <h2>Mill Turbines</h2>
        <div class="grid">
          ${inputField('tb-mill_live_psig', 'Mill live steam (psig)', 170.0, 5)}
          ${inputField('tb-mill_exh_psig', 'Mill exhaust (psig)', 15.0, 1)}
        </div>
        ${editableRowsTable('tb-mill', MILL_COLS, millRows0)}
      </div>

      <div class="panel">
        <h2>Auxiliary Turbines (fans, pumps, misc.)</h2>
        <div class="grid">
          <div><label for="tb-aux_group_name">Group name</label><input id="tb-aux_group_name" type="text" value="Fan and Pump Turbines"></div>
          ${inputField('tb-aux_live_psig', 'Aux live steam (psig)', 170.0, 5)}
          ${inputField('tb-aux_exh_psig', 'Aux exhaust (psig)', 16.0, 1)}
        </div>
        ${editableRowsTable('tb-aux', AUX_COLS, auxRows0)}
      </div>

      <div class="panel">
        <h2>Losses &amp; Jets</h2>
        <div class="grid">
          ${inputField('tb-jets_lb_hr', 'Live steam for jets (lb/hr)', 25000.0, 1000)}
          ${inputField('tb-loss_pct', 'Live steam losses (% of subtotal)', 2.0, 0.5)}
        </div>
      </div>

      <div class="panel">
        <h2>Boiler Room</h2>
        <div class="grid">
          ${inputField('tb-blr_efficiency', 'Boiler efficiency (%)', 60.0, 1)}
          ${inputField('tb-blr_pressure_psig', 'Boiler pressure (psig)', 185.0, 5)}
          ${inputField('tb-blr_superheat', 'Boiler superheat (F)', 0.0, 5)}
          ${inputField('tb-blr_capacity', 'Boiler capacity (lb/hr, 0 = unlimited)', 900000.0, 10000)}
          ${checkboxField('tb-use_da_fw_temp', 'Feedwater temp = Deaerator water out', true)}
          ${inputField('tb-manual_fw_temp', 'Feedwater temp (F, used if unchecked)', 230.0, 5)}
        </div>
      </div>

      <div class="panel">
        <h2>Deaerator</h2>
        <p class="note">Not yet its own "Exhaust Summary" tab (that needs Juice Heating / Pan Floor / Evaporation, not ported yet) -- folded in here since the Boiler's feedwater temp can depend on it.</p>
        <div class="grid">
          ${inputField('tb-da_psig', 'Deaerator pressure (psig)', 10.0, 1)}
          ${inputField('tb-da_water_temp', 'Water in temp (F)', 200.0, 5)}
          ${inputField('tb-da_water_flow', 'Water in flow (lb/hr)', 800000.0, 10000)}
          ${inputField('tb-da_vent_pct', 'Vent (%)', 4.0, 0.5)}
        </div>
      </div>

      <div class="panel">
        <h2>Exhaust Demand</h2>
        <p class="note">"Additional exhaust required" stands in for Juice Heating / Pan Floor / Evaporation's steam consumption until those stages are ported -- see PROGRESS.md. The Deaerator's own steam demand is added on top of it automatically.</p>
        <div class="grid">
          ${inputField('tb-additional_exhaust', 'Additional exhaust required (lb/hr)', 0.0, 10000)}
        </div>
      </div>

      <p><button class="primary" id="tb-calc">Calculate</button></p>
      <div id="tb-result"></div>`;

    const resultDiv = section.querySelector('#tb-result');

    section.querySelector('#tb-calc').addEventListener('click', () => {
      try {
        const v = readFields(section, [
          'tb-live_gen_psig', 'tb-live_gen_superheat', 'tb-live_gen_quality',
          'tb-knf_live_psig', 'tb-knf_exh_psig', 'tb-mill_live_psig', 'tb-mill_exh_psig',
          'tb-aux_live_psig', 'tb-aux_exh_psig', 'tb-jets_lb_hr', 'tb-loss_pct',
          'tb-blr_efficiency', 'tb-blr_pressure_psig', 'tb-blr_superheat', 'tb-blr_capacity',
          'tb-manual_fw_temp', 'tb-da_psig', 'tb-da_water_temp', 'tb-da_water_flow',
          'tb-da_vent_pct', 'tb-additional_exhaust',
        ]);
        const aux_group_name = section.querySelector('#tb-aux_group_name').value;
        const use_da_fw_temp = section.querySelector('#tb-use_da_fw_temp').checked;

        const knfRows = readEditableRows(section, 'tb-knf', KNF_COLS, knfRows0.length);
        const millRows = readEditableRows(section, 'tb-mill', MILL_COLS, millRows0.length);
        const auxRows = readEditableRows(section, 'tb-aux', AUX_COLS, auxRows0.length);

        const tons_fiber_hr = (PlantState.mill.cane_fiber_pct / 100) * PlantState.mill.cane_tph;

        const live_gen_psia = v['tb-live_gen_psig'] + 14.696;
        const live_steam_sat = new SteamStream({ P: live_gen_psia, x: 1 });
        const live_steam_gen = v['tb-live_gen_superheat'] > 0
          ? new SteamStream({ P: live_gen_psia, T: live_steam_sat.T + v['tb-live_gen_superheat'] })
          : new SteamStream({ P: live_gen_psia, x: v['tb-live_gen_quality'] });
        const groupSteam = (psig) => new SteamStream({ P: psig + 14.696, h: live_steam_gen.h });

        const knf_trbs = new CanePrepTurbines({
          name_list: knfRows.map((r) => r.name),
          hp_ton_fiber_hr: knfRows.map((r) => r.hp_tfh),
          isentropic_efficiency: knfRows.map((r) => r.eff),
          live_steam_object: groupSteam(v['tb-knf_live_psig']),
          exhaust_psia: v['tb-knf_exh_psig'] + 14.696,
          tons_fiber_hr,
        });
        const mill_trbs = new MillTurbines({
          hp_ton_fiber_hr: millRows.map((r) => r.hp_tfh),
          isentropic_efficiency: millRows.map((r) => r.eff),
          live_steam_object: groupSteam(v['tb-mill_live_psig']),
          exhaust_psia: v['tb-mill_exh_psig'] + 14.696,
          tons_fiber_hr,
        });
        const misc_trbs = new AuxillaryTurbines({
          group_name: aux_group_name,
          name_list: auxRows.map((r) => r.name),
          hp_list: auxRows.map((r) => r.hp),
          isentropic_efficiency: auxRows.map((r) => r.eff),
          live_steam_object: groupSteam(v['tb-aux_live_psig']),
          exhaust_psia: v['tb-aux_exh_psig'] + 14.696,
        });

        const live_steam_subtotal = knf_trbs.total_inlet_flow_lb_hr + mill_trbs.total_inlet_flow_lb_hr
          + misc_trbs.total_inlet_flow_lb_hr + v['tb-jets_lb_hr'];
        const live_steam_loss_lb_hr = (live_steam_subtotal * v['tb-loss_pct']) / 100;
        const live_steam_total_lb_hr = live_steam_subtotal + live_steam_loss_lb_hr;
        const exhaust_available = knf_trbs.total_exhaust_available_lb_hr + mill_trbs.total_exhaust_available_lb_hr
          + misc_trbs.total_exhaust_available_lb_hr;

        const da = new Deaerator({
          deaerator_psig: v['tb-da_psig'],
          water_in_deg_F: v['tb-da_water_temp'],
          water_in_lb_hr: v['tb-da_water_flow'],
          vent_pct: v['tb-da_vent_pct'],
        });

        const total_exhaust_required = v['tb-additional_exhaust'] + da.steam_flow_lb_hr;
        const makeup_steam = Math.max(total_exhaust_required - exhaust_available, 0);

        const fw_temp = use_da_fw_temp ? da.water_out.T : v['tb-manual_fw_temp'];
        const blrs = new Boiler({
          bagasse: PlantState.mill.bagasse_stream,
          efficiency: v['tb-blr_efficiency'],
          pressure_psig: v['tb-blr_pressure_psig'],
          deg_superheat: v['tb-blr_superheat'],
          feed_water_temp: fw_temp,
          capacity: v['tb-blr_capacity'],
          name: 'All Boilers',
        });

        PlantState.turb = { knf_trbs, mill_trbs, misc_trbs, blrs, da };

        const liveSteamTable = renderTable(['Item', 'lb/hr'], [
          ['Cane Prep Turbines', fmt(knf_trbs.total_inlet_flow_lb_hr, 0)],
          ['Mill Turbines', fmt(mill_trbs.total_inlet_flow_lb_hr, 0)],
          [aux_group_name, fmt(misc_trbs.total_inlet_flow_lb_hr, 0)],
          ['Steam Jets', fmt(v['tb-jets_lb_hr'], 0)],
          ['Live Steam Losses', fmt(live_steam_loss_lb_hr, 0)],
          ['Total Live Steam', fmt(live_steam_total_lb_hr, 0)],
        ]);

        const metrics = `
          <div class="metrics">
            <div class="metric"><div class="metric-label">Total Live Steam Demand</div><div class="metric-value">${fmt(live_steam_total_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Exhaust Required</div><div class="metric-value">${fmt(total_exhaust_required, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Exhaust Available from Turbines</div><div class="metric-value">${fmt(exhaust_available, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Makeup Required</div><div class="metric-value">${fmt(makeup_steam, 0)} lb/hr</div></div>
          </div>
          <div class="metrics">
            <div class="metric"><div class="metric-label">Steam Available from Bagasse</div><div class="metric-value">${fmt(blrs.steam_availabe_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Live Steam Demand vs. Available</div><div class="metric-value">${fmt(live_steam_total_lb_hr, 0)} / ${fmt(blrs.steam_availabe_lb_hr, 0)} lb/hr</div></div>
          </div>`;

        const fw = blrs.feed_water_stream;
        const st = blrs.steam_stream;
        const condition = blrs.deg_sh > 0 ? 'Superheated' : 'Saturated';
        const bg = blrs.bagasse;

        const boilerParamsTable = renderTable(['Parameter', 'Value'], [
          ['Efficiency (%)', fmt(blrs.efficiency, 2)],
          ['Pressure (psig)', fmt(blrs.psia - 14.696, 2)],
          ['Pressure (psia)', fmt(blrs.psia, 2)],
          ['Feed water temp (F)', fmt(blrs.feed_wat_temp, 2)],
          ['Superheat (F above sat)', fmt(blrs.deg_sh, 2)],
          ['Rated capacity (lb/hr)', fmt(blrs.capacity, 2)],
        ]);
        const boilerStreamsTable = renderTable(['Stream', 'Temp (F)', 'Enthalpy (BTU/lb)', 'Condition'], [
          ['Feed Water', fmt(fw.T, 2), fmt(fw.h, 2), ''],
          ['Steam Out', fmt(st.T, 2), fmt(st.h, 2), condition],
        ]);
        const boilerFuelTable = renderTable(['Fuel Property', 'Value'], [
          ['Flowrate (lb/hr)', fmt(bg.flowrate_lb_hr, 2)],
          ['Fiber (%)', fmt(bg.fiber_pct, 2)],
          ['Moisture (%)', fmt(bg.moisture_pct, 2)],
          ['Brix (%)', fmt(bg.brix_pct, 2)],
          ['Pol (%)', fmt(bg.pol_pct, 2)],
          ['Ash (%)', fmt(bg.ash_pct, 2)],
          ['GCV (BTU/lb)', fmt(bg.gcv, 2)],
        ]);
        const boilerPerfTable = renderTable(['Metric', 'Value'], [
          ['Heat to make 1 lb steam (BTU/lb)', fmt(blrs.btu_for_1_lb, 2)],
          ['Steam/Bagasse ratio (lb/lb)', fmt(blrs.steam_available_per_lb_bagasse, 4)],
          ['Steam available from bagasse (lb/hr)', fmt(blrs.steam_availabe_lb_hr, 2)],
        ]);

        const daTable = renderTable(['Stream', 'Flow (lb/hr)', 'P (psia)', 'Temp (F)'], [
          ['Steam In', fmt(da.steam_flow_lb_hr, 0), fmt(da.psia, 2), fmt(da._steam_state.T, 1)],
          ['Feedwater In', fmt(da.water_in_lb_hr, 0), '14.70', fmt(da.water_in_deg_F, 1)],
          ['Water Out', fmt(da.water_out_flow_lb_hr, 0), fmt(da.psia, 2), fmt(da._water_out_state.T, 1)],
          ['Vent', fmt(da.vent_flow_lb_hr, 0), '14.70', fmt(da._water_out_state.T, 1)],
        ]);

        const knfTfh = knfRows.map((r) => r.hp_tfh);
        const auxHp = auxRows.map((r) => r.hp);

        resultDiv.innerHTML = liveSteamTable + metrics +
          '<h3 class="section-title">Boiler -- Parameters</h3>' + boilerParamsTable +
          '<h3 class="section-title">Boiler -- Feed Water / Steam</h3>' + boilerStreamsTable +
          '<h3 class="section-title">Boiler -- Bagasse Fuel</h3>' + boilerFuelTable +
          '<h3 class="section-title">Boiler -- Performance</h3>' + boilerPerfTable +
          '<h3 class="section-title">Deaerator -- Streams</h3>' + daTable +
          '<h3 class="section-title">Cane Prep (Knife) Turbines -- Output</h3>' +
          turbineGroupTable(knf_trbs, { tfhList: knfTfh, skip: knfTfh.map((x) => x === 0) }) +
          '<h3 class="section-title">Mill Turbines -- Output</h3>' +
          turbineGroupTable(mill_trbs, { tfhList: millRows.map((r) => r.hp_tfh) }) +
          `<h3 class="section-title">${aux_group_name} -- Output</h3>` +
          turbineGroupTable(misc_trbs, { skip: auxHp.map((x) => x === 0) });
      } catch (e) {
        resultDiv.innerHTML = `<p class="error">${e.message}</p>`;
      }
    });

    section.querySelector('#tb-calc').click();
  }

  // ---------------------------------------------------------------------
  // Juice Heating tab
  //
  // Mirrors streamlit_app.py's "Juice Heating" tab: a JuiceHeatingStation
  // (series or parallel, chained off Clarification's limed_juice_cold_stream)
  // plus a standalone Clarified Juice Heater fed from clarified_juice_stream.
  // ---------------------------------------------------------------------
  const STEAM_TYPES = ['Exhaust', 'V1', 'V2', 'V3', 'V4'];
  const DEFAULT_V1_PSIA = 21;
  const HEAT_COLS = [
    { key: 'name', label: 'Group', type: 'text' },
    { key: 'steam_type', label: 'Steam Type', type: 'select', options: STEAM_TYPES },
    { key: 'psia', label: 'Steam Pressure (psia)', step: 1 },
    { key: 'U', label: 'U (Btu/hr·ft²·°F)', step: 5 },
    { key: 'area', label: 'Area (ft²)', step: 500 },
  ];
  const HEAT_COLS_PARALLEL = HEAT_COLS.concat([{ key: 'split_pct', label: 'Split %', step: 5 }]);

  function heaterPerfRow(h) {
    return [
      h.name, STEAM_TYPES[h.steam_type], fmt(h.hot_stream.P, 2), fmt(h.hot_stream.T, 2),
      fmt(h.hot_stream.h_fg, 2), fmt(h.steam_required_lb_per_hr, 2), fmt(h.U, 2),
      fmt(h.installed_area_ft2, 2), fmt(h.required_area_ft2, 2), fmt(h.cold_stream.flow_lb_per_hr, 2),
      fmt(h.cold_stream.temp_deg_F, 2), fmt(h.juice_out_temp_degF, 2), fmt(h.cold_stream.cp_btu_per_lb_deg_F, 2),
      fmt(h.Q_btu_per_hr / 1e6, 2), fmt(h.LMTD_degF, 2),
    ];
  }
  const HEATER_PERF_HEADERS = [
    'Heater', 'Steam Type', 'Steam Pressure (psia)', 'Steam Temp (°F)', 'Steam hfg (BTU/lb)',
    'Steam Flow (lb/hr)', 'U (Btu/hr·ft²·°F)', 'Area Installed (ft²)',
    'Area Required (ft²)', 'Juice Flow In (lb/hr)', 'Juice Temp In (°F)', 'Juice Temp Out (°F)',
    'Juice cp (Btu/lb·°F)', 'Duty (MM BTU/hr)', 'LMTD (deg F)',
  ];

  function buildHeatTab() {
    const section = document.getElementById('tab-heat');
    if (!PlantState.clar) {
      section.innerHTML = '<div class="panel"><p class="error">Solve the Clarification tab first -- Juice Heating needs its limed/clarified juice streams.</p></div>';
      return;
    }

    const clar = PlantState.clar;
    const juice_T_out = clar.limed_juice_hot_temp_f;
    const mode = (section.dataset.mode) || 'parallel';
    const fabExhPsia = section.dataset.fabExhPsia ? parseFloat(section.dataset.fabExhPsia) : 30.0;
    const cjhSteamType = section.dataset.cjhSteamType || 'Exhaust';

    const heaterRows0 = [
      { name: 'V1 Heaters', steam_type: 'V1', psia: DEFAULT_V1_PSIA, U: 200.0, area: 11000.0, split_pct: 75.0 },
      { name: 'Exhaust Heaters', steam_type: 'Exhaust', psia: fabExhPsia, U: 200.0, area: 5000.0, split_pct: 25.0 },
    ];

    section.innerHTML = `
      <div class="panel">
        <h2>Juice Heating Station</h2>
        <div class="grid">
          <div><label>Flow arrangement</label>
            <select id="ht-mode">
              <option value="parallel"${mode === 'parallel' ? ' selected' : ''}>Parallel</option>
              <option value="series"${mode === 'series' ? ' selected' : ''}>Series</option>
            </select>
          </div>
          ${inputField('ht-fab_exh_psia', 'Fabrication exhaust pressure (psia)', fabExhPsia, 1)}
        </div>
        <p class="note">Juice from Clarification's limed juice cold stream (${fmt(clar.limed_juice_cold_stream.flow_lb_per_hr, 0)} lb/hr @ ${fmt(clar.limed_juice_cold_stream.temp_deg_F, 1)} °F).</p>
        ${mode === 'series' ? `<div class="grid">
          ${inputField('ht-primary_temp_out', `${heaterRows0[0].name} exit temp (°F)`, 180.0, 1)}
          <div><label for="ht-secondary_temp_out">${heaterRows0[1].name} exit temp (°F) [locked]</label>
            <input id="ht-secondary_temp_out" type="number" value="${juice_T_out}" disabled title="Fixed to Clarification's Limed juice hot temp input.">
          </div>
        </div>` : ''}
        ${editableRowsTable('ht-heaters', mode === 'parallel' ? HEAT_COLS_PARALLEL : HEAT_COLS, heaterRows0)}
      </div>

      <div class="panel">
        <h2>Clarified Juice Heater</h2>
        <div class="grid">
          <div><label>Steam type</label>
            <select id="ht-cjh_steam_type">
              <option value="Exhaust"${cjhSteamType === 'Exhaust' ? ' selected' : ''}>Exhaust</option>
              <option value="V1"${cjhSteamType === 'V1' ? ' selected' : ''}>V1</option>
            </select>
          </div>
          ${inputField('ht-cjh_temp', 'Juice out temp (°F)', 225.0, 1)}
          ${inputField('ht-cjh_U', 'U (Btu/hr·ft²·°F)', 185.0, 5)}
          ${inputField('ht-cjh_area', 'Area (ft²)', 6000.0, 500)}
          ${inputField('ht-cjh_psia', 'Steam pressure (psia)', cjhSteamType === 'V1' ? DEFAULT_V1_PSIA : fabExhPsia, 1)}
        </div>
      </div>

      <p><button class="primary" id="ht-calc">Calculate</button></p>
      <div id="ht-result"></div>`;

    section.querySelector('#ht-mode').addEventListener('change', (e) => {
      section.dataset.mode = e.target.value;
      buildHeatTab();
    });
    section.querySelector('#ht-fab_exh_psia').addEventListener('change', (e) => {
      section.dataset.fabExhPsia = e.target.value;
      buildHeatTab();
    });
    section.querySelector('#ht-cjh_steam_type').addEventListener('change', (e) => {
      section.dataset.cjhSteamType = e.target.value;
      buildHeatTab();
    });

    const resultDiv = section.querySelector('#ht-result');

    section.querySelector('#ht-calc').addEventListener('click', () => {
      try {
        const heaterRows = readEditableRows(section, 'ht-heaters', mode === 'parallel' ? HEAT_COLS_PARALLEL : HEAT_COLS, heaterRows0.length);
        const cjhTemp = parseFloat(section.querySelector('#ht-cjh_temp').value);
        const cjhU = parseFloat(section.querySelector('#ht-cjh_U').value);
        const cjhArea = parseFloat(section.querySelector('#ht-cjh_area').value);
        const cjhPsia = parseFloat(section.querySelector('#ht-cjh_psia').value);
        const cjhSteamTypeSel = section.querySelector('#ht-cjh_steam_type').value;

        let temp_outs;
        if (mode === 'series') {
          const primaryTempOut = parseFloat(section.querySelector('#ht-primary_temp_out').value);
          temp_outs = [primaryTempOut, juice_T_out];
        } else {
          temp_outs = heaterRows.map(() => juice_T_out);
        }

        const cold_juice = clar.limed_juice_cold_stream;
        const heater_objs = heaterRows.map((row, i) => new JuiceHeaterShellTube({
          cold_stream: cold_juice,
          hot_stream: new SteamStream({ x: 1, P: row.psia }),
          name: row.name,
          juice_out_temp_degF: temp_outs[i],
          U_btu_per_ft2_degF: row.U,
          installed_area_ft2: row.area,
          steam_type: STEAM_TYPES.indexOf(row.steam_type),
        }));
        const split_pcts = mode === 'parallel' ? heaterRows.map((r) => r.split_pct) : null;
        const juice_heaters = new JuiceHeatingStation({
          cold_stream: cold_juice, heaters: heater_objs, mode, split_pcts,
          name: mode === 'parallel' ? 'Parallel Juice Heating Station' : 'Series Juice Heating Station',
        });

        const clar_juice_colder = SugarStream.copy(clar.clarified_juice_stream);
        const clar_juice_heater = new JuiceHeaterShellTube({
          cold_stream: clar_juice_colder,
          hot_stream: new SteamStream({ x: 1, P: cjhPsia }),
          name: 'Clarified Juice Heater',
          juice_out_temp_degF: cjhTemp,
          U_btu_per_ft2_degF: cjhU,
          installed_area_ft2: cjhArea,
          steam_type: STEAM_TYPES.indexOf(cjhSteamTypeSel),
        });

        PlantState.heat = { juice_heaters, clar_juice_heater };

        const heaterPerfTable = renderTable(HEATER_PERF_HEADERS, juice_heaters.heaters.map(heaterPerfRow));

        const metrics = `
          <div class="metrics">
            <div class="metric"><div class="metric-label">Juice out</div><div class="metric-value">${fmt(juice_heaters.juice_out.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Exhaust</div><div class="metric-value">${fmt(juice_heaters.total_exhaust_steam_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">V1</div><div class="metric-value">${fmt(juice_heaters.total_V1_steam_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">V2</div><div class="metric-value">${fmt(juice_heaters.total_V2_steam_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">V3</div><div class="metric-value">${fmt(juice_heaters.total_V3_steam_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">V4</div><div class="metric-value">${fmt(juice_heaters.total_V4_steam_lb_hr, 0)} lb/hr</div></div>
          </div>`;

        const warnings = juice_heaters.heaters
          .filter((h) => h.is_steam_hot_enough !== 'YES')
          .map((h) => `<p class="error">WARNING [${h.name}]: ${h.is_steam_hot_enough}</p>`).join('');

        const condensateTable = renderTable(['Item', 'lb/hr'], [
          ['Clean condensate (Exhaust steam heaters)', fmt(juice_heaters.clean_condensate, 0)],
          ['Dirty condensate (V1-V4 steam heaters)', fmt(juice_heaters.dirty_condensate, 0)],
          ['Total condensate', fmt(juice_heaters.clean_condensate + juice_heaters.dirty_condensate, 0)],
        ]);

        const cjhPerfTable = renderTable(HEATER_PERF_HEADERS, [heaterPerfRow(clar_juice_heater)]);
        const cjhMetrics = `
          <div class="metrics">
            <div class="metric"><div class="metric-label">Flow out</div><div class="metric-value">${fmt(clar_juice_heater.juice_out.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Temp in</div><div class="metric-value">${fmt(clar_juice_heater.cold_stream.temp_deg_F, 1)} °F</div></div>
            <div class="metric"><div class="metric-label">Temp out</div><div class="metric-value">${fmt(clar_juice_heater.juice_out.temp_deg_F, 1)} °F</div></div>
            <div class="metric"><div class="metric-label">Steam required (${cjhSteamTypeSel})</div><div class="metric-value">${fmt(clar_juice_heater.steam_required_lb_per_hr, 0)} lb/hr</div></div>
          </div>`;
        const cjhWarning = clar_juice_heater.is_steam_hot_enough !== 'YES'
          ? `<p class="error">WARNING [Clarified Juice Heater]: ${clar_juice_heater.is_steam_hot_enough}</p>` : '';

        resultDiv.innerHTML =
          '<h3 class="section-title">Juice Heater Performance</h3>' + heaterPerfTable + metrics + warnings +
          '<h3 class="section-title">Condensate Return</h3>' + condensateTable +
          '<h3 class="section-title">Clarified Juice Heater Performance</h3>' + cjhPerfTable + cjhMetrics + cjhWarning;
      } catch (e) {
        resultDiv.innerHTML = `<p class="error">${e.message}</p>`;
      }
    });

    section.querySelector('#ht-calc').click();
  }

  // ---------------------------------------------------------------------
  // Pan Floor tab -- Four Boiling Double Magma (FBDM) scheme only for now
  // (see web/PROGRESS.md Phase 3). Mirrors streamlit_app.py's Pan Floor tab
  // with the boiling-scheme radio fixed to FBDM; TBDM/3B/2B are future work.
  // ---------------------------------------------------------------------

  // resolve_cj() equivalent: clarified juice post juice-heating if that stage
  // has ever solved, otherwise straight from Clarification.
  function resolveCj() {
    return PlantState.heat ? PlantState.heat.clar_juice_heater.juice_out : PlantState.clar.clarified_juice_stream;
  }

  function pfGrade(name, suffix) {
    return name.endsWith(suffix) ? name.slice(0, name.length - suffix.length).trim() : name;
  }

  function pfScaled(stream, pct) {
    const out = SugarStream.copy(stream);
    out.flow_lb_per_hr = stream.flow_lb_per_hr * pct / 100;
    return out;
  }

  function combineStreams(streams) {
    streams = streams.filter((s) => s.flow_lb_per_hr > 0);
    if (!streams.length) return new SugarStream({ brix: 0, purity: 0, flow_lb_per_hr: 0, temp_deg_F: 0 });
    const total_flow = streams.reduce((s, x) => s + x.flow_lb_per_hr, 0);
    const total_solids = streams.reduce((s, x) => s + x.solids_flow, 0);
    const total_pol = streams.reduce((s, x) => s + x.pol_flow, 0);
    const combined = SugarStream.copy(streams[0]);
    combined.flow_lb_per_hr = total_flow;
    combined.brix = total_solids / total_flow * 100;
    combined.purity = total_solids ? total_pol / total_solids * 100 : 0;
    combined.temp_deg_F = streams.reduce((s, x) => s + x.flow_lb_per_hr * x.temp_deg_F, 0) / total_flow;
    return combined;
  }

  function pfStreamRow(section, name, tag, s) {
    return [section, name, tag, fmt(s.flow_lb_per_hr, 0), s.pol ? fmt(s.pol, 2) : '-', fmt(s.brix, 2),
      fmt(s.purity, 2), fmt(s.pol_flow, 0), fmt(s.solids_flow, 0), fmt(s.cu_ft_hr, 1),
      fmt(s.specific_gravity, 3), fmt(s.temp_deg_F, 1), '-'];
  }

  function pfWaterRow(section, name, tag, flow_lb_hr, temp_deg_F = null) {
    return [section, name, tag, fmt(flow_lb_hr, 0), '-', fmt(0, 2), '-', fmt(0, 0), fmt(0, 0),
      fmt(flow_lb_hr ? flow_lb_hr / 62.4 : 0, 1), fmt(1.0, 3),
      temp_deg_F === null ? '-' : fmt(temp_deg_F, 1), '-'];
  }

  function pfVaporRow(section, name, tag, flow_lb_hr, temp_deg_F = null) {
    return [section, name, tag, fmt(flow_lb_hr, 0), '-', fmt(0, 2), '-', fmt(0, 0), fmt(0, 0),
      '-', '-', temp_deg_F === null ? '-' : fmt(temp_deg_F, 1), '-'];
  }

  function pfMasseRow(section, name, tag, masse, flow_lb_hr) {
    return [section, name, tag, fmt(flow_lb_hr, 0), fmt(masse.masse_purity * masse.masse_brix / 100, 2),
      fmt(masse.masse_brix, 2), fmt(masse.masse_purity, 2),
      fmt(flow_lb_hr * masse.masse_purity * masse.masse_brix / 10000, 0),
      fmt(flow_lb_hr * masse.masse_brix / 100, 0), fmt(flow_lb_hr / masse.density, 1),
      fmt(masse.density / 62.4, 3), fmt(masse.massecuite_temp, 1), fmt(masse.crystal_content, 1)];
  }

  function pfPanRows(section, pan, feedNames) {
    const grade = pfGrade(pan.name, 'Pans');
    const rows = pan.feed_streams.map((f, i) => pfStreamRow(section, feedNames[i] || `Feed ${i + 1}`, 'Entering', f));
    rows.push(pfMasseRow(section, `${grade} Massecuite`, 'Leaving', pan.massecuite, pan.massecuite_flow_lb_hr));
    rows.push(pfVaporRow(section, 'Vapors', 'Leaving', pan.water_evaporated_lb_hr, pan.massecuite.water_bp_surface));
    return rows;
  }

  function pfCenRows(section, cen) {
    const grade = pfGrade(cen.name, 'Centrifugals');
    return [
      pfMasseRow(section, `${grade} Massecuite`, 'Entering', cen.massecuite, cen.massecuite_flow_lb_hr),
      pfWaterRow(section, 'Wash Water', 'Entering', cen.wash_water_lb_hr),
      pfStreamRow(section, `${grade} Sugar`, 'Leaving', cen.sugar_stream),
      pfStreamRow(section, `${grade} Molasses`, 'Leaving', cen.molasses_stream),
    ];
  }

  function pfDilRows(section, undiluted, diluted, label) {
    const water = diluted.flow_lb_per_hr - undiluted.flow_lb_per_hr;
    return [
      pfStreamRow(section, `${label} (undiluted)`, 'Entering', undiluted),
      pfWaterRow(section, 'Dilution Water', 'Entering', water),
      pfStreamRow(section, `${label} (diluted)`, 'Leaving', diluted),
    ];
  }

  function pfMagmaRows(section, sugar, magma, label) {
    const water = magma.flow_lb_per_hr - sugar.flow_lb_per_hr;
    return [
      pfStreamRow(section, `${label} Sugar`, 'Entering', sugar),
      pfWaterRow(section, 'Mingler Water', 'Entering', water),
      pfStreamRow(section, `${label} Magma`, 'Leaving', magma),
    ];
  }

  function pfMagmaSplitRows(section, destinations) {
    return destinations.map(([label, s]) => pfStreamRow(section, label, 'Internal', s));
  }

  function pfRemeltRows(section, magmaToRmlt, remelt, label) {
    const water = remelt.flow_lb_per_hr - magmaToRmlt.flow_lb_per_hr;
    return [
      pfStreamRow(section, `${label} Magma (to Remelt)`, 'Entering', magmaToRmlt),
      pfWaterRow(section, 'Remelt Water', 'Entering', water),
      pfStreamRow(section, `${label} Remelt`, 'Leaving', remelt),
    ];
  }

  function pfHeatxRows(section, unit) {
    return [
      pfMasseRow(section, 'Massecuite Entering', 'Entering', unit.massecuite_in, unit.massecuite_flow_lb_hr),
      pfMasseRow(section, 'Massecuite Leaving', 'Leaving', unit.massecuite_out, unit.massecuite_flow_lb_hr),
    ];
  }

  function pfOverallRows(fb, sugarRows) {
    const section = 'Overall';
    const finalMolasses = fb.C_centrifugals.molasses_stream;
    const pans = fb._pans;
    const totalVapor = pans.reduce((s, p) => s + p.water_evaporated_lb_hr, 0);
    const vaporTemp = totalVapor
      ? pans.reduce((s, p) => s + p.water_evaporated_lb_hr * p.massecuite.water_bp_surface, 0) / totalVapor
      : 0;
    const rows = [pfStreamRow(section, 'Syrup From Evaporators', 'Entering', fb.syrup)];
    rows.push(pfWaterRow(section, 'Total Water', 'Entering', fb.total_water.flow_lb_per_hr));
    sugarRows.forEach(([label, s]) => rows.push(pfStreamRow(section, label, 'Leaving', s)));
    rows.push(pfStreamRow(section, 'Final Molasses', 'Leaving', finalMolasses));
    rows.push(pfWaterRow(section, 'Vapors', 'Leaving', totalVapor, vaporTemp));
    return rows;
  }

  function fourBoilingRows(fb) {
    const a1_sugar = fb.A1_centrifugals.sugar_stream;
    const a2_sugar = fb.A2_centrifugals.sugar_stream;
    const combined_remelt = combineStreams([fb._b_remelt, fb._c_remelt]);
    const combined_magma_to_rmlt = combineStreams([fb._b_magma_to_rmlt, fb._c_magma_to_rmlt]);

    let rows = pfOverallRows(fb, [['A1 Sugar', a1_sugar], ['A2 Sugar', a2_sugar]]);
    rows = rows.concat(pfRemeltRows('Remelt Station', combined_magma_to_rmlt, combined_remelt, 'B+C'));

    rows.push(pfStreamRow('Syrup Tanks', 'Syrup From Evaporators', 'Entering', fb.syrup));
    rows.push(pfStreamRow('Syrup Tanks', 'Remelt', 'Entering', combined_remelt));
    rows.push(pfStreamRow('Syrup Tanks', 'Syrup Remelt Blend', 'Leaving', fb.syrup_as_fed));

    rows.push(pfStreamRow('Syrup Distribution', 'Syrup to A1 Pans', 'Internal', pfScaled(fb.syrup_as_fed, fb.syrup_to_A1_pans_pct)));
    rows.push(pfStreamRow('Syrup Distribution', 'Syrup to A2 Pans', 'Internal', pfScaled(fb.syrup_as_fed, fb.syrup_to_A2_pans_pct)));
    rows.push(pfStreamRow('Syrup Distribution', 'Syrup to Grain Pans', 'Internal', pfScaled(fb.syrup_as_fed, fb.syrup_to_grain_pct)));

    rows = rows.concat(pfPanRows('A1 Station - Pans', fb.A1_pans, ['Syrup', 'B Magma A1 Footing']));
    rows = rows.concat(pfCenRows('A1 Station - Centrifugals', fb.A1_centrifugals));
    rows = rows.concat(pfDilRows('A1 Station - A1 Molasses Dilution', fb.A1_centrifugals.molasses_stream, fb._a1_mol_diluted, 'A1 Molasses'));
    rows.push(pfStreamRow('A1 Station - A1 Molasses Distribution', 'A1 Molasses to A2', 'Internal', pfScaled(fb._a1_mol_diluted, fb.a1_mol_to_A2_pct)));
    rows.push(pfStreamRow('A1 Station - A1 Molasses Distribution', 'A1 Molasses to Grain', 'Internal', pfScaled(fb._a1_mol_diluted, fb.a1_mol_to_grain_pct)));
    rows.push(pfStreamRow('A1 Station - A1 Molasses Distribution', 'A1 Molasses to B', 'Internal', pfScaled(fb._a1_mol_diluted, fb.a1_mol_to_B_pct)));

    rows = rows.concat(pfPanRows('A2 Station - Pans', fb.A2_pans, ['Syrup', 'A1 Molasses', 'B Magma A2 Footing']));
    rows = rows.concat(pfCenRows('A2 Station - Centrifugals', fb.A2_centrifugals));
    rows = rows.concat(pfDilRows('A2 Station - A2 Molasses Dilution', fb.A2_centrifugals.molasses_stream, fb._a2_mol_diluted, 'A2 Molasses'));
    rows.push(pfStreamRow('A2 Station - A2 Molasses Distribution', 'A2 Molasses to Grain', 'Internal', pfScaled(fb._a2_mol_diluted, fb.a2_mol_to_grain_pct)));
    rows.push(pfStreamRow('A2 Station - A2 Molasses Distribution', 'A2 Molasses to B', 'Internal', pfScaled(fb._a2_mol_diluted, fb.a2_mol_to_B_pct)));

    rows = rows.concat(pfPanRows('B Station - Pans', fb.B_pans, ['A2 Molasses to B', 'C Magma B Footing', 'A1 Molasses to B']));
    rows = rows.concat(pfCenRows('B Station - Centrifugals', fb.B_centrifugals));
    rows = rows.concat(pfMagmaRows('B Station - B Mingler', fb.B_centrifugals.sugar_stream, fb._b_magma, 'B'));
    rows = rows.concat(pfMagmaSplitRows('B Station - B Magma Distribution', [
      ['B Magma to A1 Footing', fb._b_magma_A1_footing],
      ['B Magma to A2 Footing', fb._b_magma_A2_footing],
      ['B Magma to Remelt', fb._b_magma_to_rmlt],
    ]));
    rows = rows.concat(pfDilRows('B Station - Molasses Dilution', fb.B_centrifugals.molasses_stream, fb._b_mol_diluted, 'B Molasses'));
    rows.push(pfStreamRow('B Station - B Molasses Distribution', 'B Molasses to Grain', 'Internal', pfScaled(fb._b_mol_diluted, fb.b_mol_to_grain_pct)));
    rows.push(pfStreamRow('B Station - B Molasses Distribution', 'B Molasses to C Pans', 'Internal', pfScaled(fb._b_mol_diluted, fb.b_mol_to_C_pct)));

    rows = rows.concat(pfPanRows('Grain Pans', fb.grain_pans, ['Syrup', 'A1 Molasses', 'A2 Molasses', 'B Molasses']));

    rows = rows.concat(pfPanRows('C Station - Pans', fb.C_pans, ['Grain Massecuite', 'B Molasses']));
    rows = rows.concat(pfHeatxRows('C Station - Crystallizers', fb.C_crystallizers));
    rows = rows.concat(pfHeatxRows('C Station - Reheater', fb.C_reheaters));
    rows = rows.concat(pfCenRows('C Station - Centrifugals', fb.C_centrifugals));
    rows = rows.concat(pfMagmaRows('C Station - C Mingler', fb.C_centrifugals.sugar_stream, fb._c_magma, 'C'));
    rows = rows.concat(pfMagmaSplitRows('C Station - C Magma Distribution', [
      ['C Magma to B Footing', fb._c_magma_B_footing],
      ['C Magma to Remelt', fb._c_magma_to_rmlt],
    ]));
    return rows;
  }

  const PAN_FLOOR_COLUMNS = ['Section', 'Stream', 'Entering/Leaving/Internal', 'Flow lb/hr', 'Pol %', 'Brix %',
    'Purity', 'Pol lb/hr', 'Brix lb/hr', 'Cu Ft/hr', 'Specific Gravity', 'Temperature', 'Crystal Content'];

  function panFloorMasseSummaryTable(fb, caneTpd) {
    const grades = fb._pans.map((p) => pfGrade(p.name, 'Pans'));
    const ft3hr = fb._pans.map((p) => p.massecuite_flow_lb_hr / p.massecuite.density);
    const totalFt3Hr = ft3hr.reduce((a, b) => a + b, 0);
    const allFt3Hr = ft3hr.concat([totalFt3Hr]);
    const headers = ['Metric'].concat(grades.map((g) => `${g} Massecuite`), 'Total');
    const rows = [
      ['Cubic Ft / Hr'].concat(allFt3Hr.map((v) => fmt(v, 2))),
      ['Cubic Ft / Day'].concat(allFt3Hr.map((v) => fmt(v * 24, 2))),
      ['Cubic Ft / Ton Cane'].concat(allFt3Hr.map((v) => fmt(caneTpd ? v * 24 / caneTpd : 0, 2))),
    ];
    return renderTable(headers, rows);
  }

  function panFloorSteamTable(fb) {
    const headers = ['Metric'].concat(fb._pans.map((p) => p.name));
    const metrics = [
      ['Steam Used (lb/hr)', (p) => fmt(p.steam_flow_lb_hr, 2)],
      ['Steam Type', (p) => STEAM_TYPES[p.steam_type]],
      ['Steam Pressure (psia)', (p) => fmt(p.calandria_pressure_psia, 2)],
      ['Steam Temp (F)', (p) => fmt(p.calandria_T_sat_F, 2)],
      ['Steam hfg (BTU/lb)', (p) => fmt(p.h_fg_calandria, 2)],
      ['Massecuite Temp (F)', (p) => fmt(p.massecuite.massecuite_temp, 2)],
      ['Vapor Evaporated (lb/hr)', (p) => fmt(p.water_evaporated_lb_hr, 2)],
      ['Vapor Temp (F)', (p) => fmt(p.massecuite.water_bp_surface, 2)],
      ['Vapor Pressure (psia)', (p) => fmt(p.massecuite.vapor_pressure_psia, 2)],
      ['Vapor hfg (BTU/lb)', (p) => fmt(p.h_fg_vapor, 2)],
      ['Heating Surface (ft2)', (p) => fmt(p.heating_surface_ft2, 2)],
      ['U (Btu/hr.ft2.F)', (p) => fmt(p.U_btu_hr_ft2_F, 2)],
    ];
    const rows = metrics.map(([label, fn]) => [label].concat(fb._pans.map(fn)));
    return renderTable(headers, rows);
  }

  const PAN_COLS = [
    { key: 'grade', label: 'Grade', type: 'text' },
    { key: 'area', label: 'Heating Surface (ft²)', step: 100 },
    { key: 'vacuum', label: 'Vacuum (in Hg)', step: 0.5 },
    { key: 'ss', label: 'Supersaturation', step: 0.05 },
    { key: 'head', label: 'Head (ft)', step: 0.5 },
    { key: 'masse_brix', label: 'Masse Brix', step: 0.5 },
    { key: 'ml_purity', label: 'Mother Liquor Purity', step: 1 },
    { key: 'calandria_psia', label: 'Calandria (psia)', step: 0.5 },
    { key: 'heat_loss', label: 'Heat Loss Factor', step: 0.01 },
    { key: 'steam_type', label: 'Steam Type', type: 'select', options: STEAM_TYPES },
  ];
  const CEN_COLS = [
    { key: 'grade', label: 'Grade', type: 'text' },
    { key: 'mol_brix_out', label: 'Molasses Brix Out', step: 1 },
    { key: 'purity_rise', label: 'Purity Rise', step: 0.5 },
    { key: 'sugar_purity', label: 'Sugar Purity', step: 0.1 },
    { key: 'sugar_moisture', label: 'Sugar Moisture', step: 0.1 },
    { key: 'sugar_temp', label: 'Sugar Temp', step: 1 },
    { key: 'molasses_temp', label: 'Molasses Temp', step: 1 },
  ];
  const FBDM_PAN_DEFAULTS = [
    { grade: 'A1', area: 16000, vacuum: 23.5, ss: 1.2, head: 2, masse_brix: 92, ml_purity: 75, calandria_psia: 21.696, heat_loss: 0.02, steam_type: 'V1' },
    { grade: 'A2', area: 6000, vacuum: 23.5, ss: 1.2, head: 2, masse_brix: 92, ml_purity: 70, calandria_psia: 21.696, heat_loss: 0.02, steam_type: 'V1' },
    { grade: 'B', area: 7500, vacuum: 25.0, ss: 1.2, head: 2, masse_brix: 94, ml_purity: 52, calandria_psia: 29.696, heat_loss: 0.05, steam_type: 'Exhaust' },
    { grade: 'Grain', area: 3000, vacuum: 25.5, ss: 1.2, head: 2, masse_brix: 88, ml_purity: 45, calandria_psia: 29.696, heat_loss: 0.05, steam_type: 'Exhaust' },
    { grade: 'C', area: 12000, vacuum: 26.5, ss: 1.2, head: 2, masse_brix: 95.5, ml_purity: 33, calandria_psia: 21.696, heat_loss: 0.05, steam_type: 'V1' },
  ];
  const FBDM_CEN_DEFAULTS = [
    { grade: 'A1', mol_brix_out: 80.0, purity_rise: 0.0, sugar_purity: 99.7, sugar_moisture: 0.2, sugar_temp: 150, molasses_temp: 145 },
    { grade: 'A2', mol_brix_out: 80.0, purity_rise: 0.0, sugar_purity: 99.3, sugar_moisture: 0.2, sugar_temp: 150, molasses_temp: 145 },
    { grade: 'B', mol_brix_out: 82.0, purity_rise: 0.0, sugar_purity: 92.0, sugar_moisture: 5.0, sugar_temp: 150, molasses_temp: 145 },
    { grade: 'C', mol_brix_out: 82.0, purity_rise: 0.0, sugar_purity: 82.0, sugar_moisture: 5.0, sugar_temp: 150, molasses_temp: 145 },
  ];

  function buildPanTab() {
    const section = document.getElementById('tab-pan');
    if (!PlantState.clar) {
      section.innerHTML = '<div class="panel"><p class="error">Solve the Clarification tab first -- Pan Floor needs its clarified juice stream.</p></div>';
      return;
    }

    section.innerHTML = `
      <div class="panel">
        <h2>Pan Floor -- Four Boiling Double Magma</h2>
        <p class="note">Only the FBDM scheme is implemented so far -- see web/PROGRESS.md Phase 3.</p>
        <div class="grid">
          ${inputField('pf-syrup_brix', 'Syrup brix', 65.0, 0.5)}
          ${inputField('pf-inj_water', 'Injection water temp (°F)', 90.0, 1)}
          ${inputField('pf-cond_leg', 'Condenser leg ΔT (°F)', 5.0, 0.5)}
          ${inputField('pf-b_magma_brix', 'B magma brix', 92.0, 0.5)}
          ${inputField('pf-b_remelt_brix', 'B remelt brix', 65.0, 0.5)}
          ${inputField('pf-c_magma_brix', 'C magma brix', 92.0, 0.5)}
          ${inputField('pf-c_remelt_brix', 'C remelt brix', 65.0, 0.5)}
        </div>
      </div>

      <div class="panel">
        <h3 class="section-title">Pans</h3>
        ${editableRowsTable('pf-pans', PAN_COLS, FBDM_PAN_DEFAULTS)}
        <h3 class="section-title">Centrifugals</h3>
        ${editableRowsTable('pf-cens', CEN_COLS, FBDM_CEN_DEFAULTS)}
      </div>

      <div class="panel">
        <h3 class="section-title">C Crystallizer / Reheater (low-grade cooling train)</h3>
        <div class="grid">
          ${inputField('pf-cryst_temp_out', 'Crystallizer masse out (°F)', 120.0, 1)}
          ${inputField('pf-cryst_ml_purity_out', 'Crystallizer mother liquor purity out (%)', 30.0, 1)}
          ${inputField('pf-reheat_temp_out', 'Reheater masse out (°F)', 140.0, 1)}
        </div>
        <p class="note">Cooling water fixed 85→105°F, reheat water fixed 150→135°F.</p>
      </div>

      <div class="panel">
        <h3 class="section-title">Split fractions</h3>
        <div class="grid">
          ${inputField('pf-syrup_to_A1', 'Syrup to A1 pans (%)', 75.0, 1)}
          ${inputField('pf-syrup_to_A2', 'Syrup to A2 pans (%)', 20.0, 1)}
          ${inputField('pf-a1_to_A2', 'A1 mol to A2 (%)', 80.0, 1)}
          ${inputField('pf-a1_to_grain', 'A1 mol to grain (%)', 3.0, 1)}
          ${inputField('pf-a2_to_grain', 'A2 mol to grain (%)', 0.0, 1)}
          ${inputField('pf-b_to_grain', 'B mol to grain (%)', 10.0, 1)}
          ${inputField('pf-b_A1_footing', 'B magma A1 footing (%)', 40.0, 1)}
          ${inputField('pf-b_A2_footing', 'B magma A2 footing (%)', 40.0, 1)}
          ${inputField('pf-c_B_footing', 'C magma B footing (%)', 80.0, 1)}
        </div>
      </div>

      <p><button class="primary" id="pf-calc">Calculate</button></p>
      <div id="pf-result"></div>`;

    const resultDiv = section.querySelector('#pf-result');

    section.querySelector('#pf-calc').addEventListener('click', () => {
      try {
        const cj = resolveCj();
        const syrup_brix = parseFloat(section.querySelector('#pf-syrup_brix').value);
        const syrup = SugarStream.copy(cj);
        syrup.flow_lb_per_hr = cj.flow_lb_per_hr * cj.brix / syrup_brix;
        syrup.brix = syrup_brix;

        const panRows = readEditableRows(section, 'pf-pans', PAN_COLS, FBDM_PAN_DEFAULTS.length);
        const pans = {};
        panRows.forEach((row) => {
          pans[row.grade] = new Pan({
            feed_streams: null,
            heating_surface_ft2: row.area,
            inches_vacuum: row.vacuum,
            supersaturation: row.ss,
            head_ft: row.head,
            masse_brix: row.masse_brix,
            ml_purity: row.ml_purity,
            calandria_pressure_psia: row.calandria_psia,
            heat_loss_factor: row.heat_loss,
            steam_type: STEAM_TYPES.indexOf(row.steam_type),
            name: `${row.grade} Pans`,
          });
        });

        const cenRows = readEditableRows(section, 'pf-cens', CEN_COLS, FBDM_CEN_DEFAULTS.length);
        const cens = {};
        cenRows.forEach((row) => {
          cens[row.grade] = new Centrifugal({
            massecuite: null,
            massecuite_flow_lb_hr: 0,
            target_molasses_brix: row.mol_brix_out,
            purity_rise: row.purity_rise,
            sugar_purity: row.sugar_purity,
            sugar_moisture: row.sugar_moisture,
            sugar_temp: row.sugar_temp,
            molasses_temp: row.molasses_temp,
            name: `${row.grade} Centrifugals`,
          });
        });

        const cCrystallizers = new Crystallizer({
          massecuite_in: null, massecuite_flow_lb_hr: 0,
          masse_temp_out_deg_F: parseFloat(section.querySelector('#pf-cryst_temp_out').value),
          ml_purity_out: parseFloat(section.querySelector('#pf-cryst_ml_purity_out').value),
          water_temp_in_deg_F: 85, water_temp_out_deg_F: 105, name: 'C Crystallizers',
        });
        const cReheaters = new Reheater({
          massecuite_in: null, massecuite_flow_lb_hr: 0,
          masse_temp_out_deg_F: parseFloat(section.querySelector('#pf-reheat_temp_out').value),
          water_temp_in_deg_F: 150, water_temp_out_deg_F: 135, name: 'C Reheaters',
        });

        const panFloor = new FourBoilingDoubleMagma({
          syrup,
          A1_pans: pans.A1, A2_pans: pans.A2, B_pans: pans.B, C_pans: pans.C, grain_pans: pans.Grain,
          A1_centrifugals: cens.A1, A2_centrifugals: cens.A2, B_centrifugals: cens.B, C_centrifugals: cens.C,
          C_crystallizers: cCrystallizers, C_reheaters: cReheaters,
          syrup_to_A1_pans_pct: parseFloat(section.querySelector('#pf-syrup_to_A1').value),
          syrup_to_A2_pans_pct: parseFloat(section.querySelector('#pf-syrup_to_A2').value),
          a1_mol_to_A2_pct: parseFloat(section.querySelector('#pf-a1_to_A2').value),
          a1_mol_to_grain_pct: parseFloat(section.querySelector('#pf-a1_to_grain').value),
          a2_mol_to_grain_pct: parseFloat(section.querySelector('#pf-a2_to_grain').value),
          b_mol_to_grain_pct: parseFloat(section.querySelector('#pf-b_to_grain').value),
          b_magma_A1_footing_pct: parseFloat(section.querySelector('#pf-b_A1_footing').value),
          b_magma_A2_footing_pct: parseFloat(section.querySelector('#pf-b_A2_footing').value),
          c_magma_B_footing_pct: parseFloat(section.querySelector('#pf-c_B_footing').value),
          b_magma_brix: parseFloat(section.querySelector('#pf-b_magma_brix').value),
          c_magma_brix: parseFloat(section.querySelector('#pf-c_magma_brix').value),
          b_remelt_brix: parseFloat(section.querySelector('#pf-b_remelt_brix').value),
          c_remelt_brix: parseFloat(section.querySelector('#pf-c_remelt_brix').value),
          injection_water_temp_F: parseFloat(section.querySelector('#pf-inj_water').value),
          condenser_leg_temp_drop_F: parseFloat(section.querySelector('#pf-cond_leg').value),
          iterations: 20,
        });

        PlantState.pan = panFloor;

        const rawSugar = panFloor.total_raw_sugar;
        const finalMolasses = panFloor.C_centrifugals.molasses_stream;

        const metrics = `
          <div class="metrics">
            <div class="metric"><div class="metric-label">Entering syrup</div><div class="metric-value">${fmt(panFloor.syrup.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Total raw sugar</div><div class="metric-value">${fmt(rawSugar.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Total final molasses</div><div class="metric-value">${fmt(finalMolasses.flow_lb_per_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">Exhaust steam</div><div class="metric-value">${fmt(panFloor.total_exhaust_steam_lb_hr, 0)} lb/hr</div></div>
            <div class="metric"><div class="metric-label">V1 steam</div><div class="metric-value">${fmt(panFloor.total_V1_steam_lb_hr, 0)} lb/hr</div></div>
          </div>`;

        const condensateTable = renderTable(['Item', 'lb/hr'], [
          ['Clean condensate (Exhaust steam pans)', fmt(panFloor.clean_condensate, 0)],
          ['Dirty condensate (V1-V4 steam pans)', fmt(panFloor.dirty_condensate, 0)],
          ['Total condensate', fmt(panFloor.clean_condensate + panFloor.dirty_condensate, 0)],
        ]);

        const caneTpd = PlantState.mill ? PlantState.mill.cane_tpd : 0;
        const masseTable = panFloorMasseSummaryTable(panFloor, caneTpd);
        const steamTable = panFloorSteamTable(panFloor);
        const streamTable = renderTable(PAN_FLOOR_COLUMNS, fourBoilingRows(panFloor));

        resultDiv.innerHTML = metrics +
          '<h3 class="section-title">Massecuite Summary</h3>' + masseTable +
          '<h3 class="section-title">Steam Consumption</h3>' + steamTable +
          '<h3 class="section-title">Condensate Return</h3>' + condensateTable +
          '<h3 class="section-title">Pan Floor Output Table</h3>' + streamTable;
      } catch (e) {
        resultDiv.innerHTML = `<p class="error">${e.message}</p>`;
      }
    });

    section.querySelector('#pf-calc').click();
  }

  document.addEventListener('DOMContentLoaded', () => {
    buildTabs();
    buildSteamTab();
    buildMillTab();
    buildClarTab();
    buildHeatTab();
    buildPanTab();
    buildTurbTab();
  });
})();
