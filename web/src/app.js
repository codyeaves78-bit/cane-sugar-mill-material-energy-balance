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

  function checkboxField(id, label, checked) {
    return `<div class="checkbox-field"><input id="${id}" type="checkbox" ${checked ? 'checked' : ''}><label for="${id}" style="margin:0;">${label}</label></div>`;
  }

  // Editable row tables (name/HP/efficiency lists etc.) -- a plain grid of
  // <input> cells, since this app has no spreadsheet-style data editor.
  function editableRowsTable(id, columns, rows) {
    const header = '<tr>' + columns.map((c) => `<th>${c.label}</th>`).join('') + '</tr>';
    const body = rows.map((row, i) => '<tr>' + columns.map((c) => {
      const inputId = `${id}-${i}-${c.key}`;
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
        row[c.key] = c.type === 'text' ? el.value : parseFloat(el.value);
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

  document.addEventListener('DOMContentLoaded', () => {
    buildTabs();
    buildSteamTab();
    buildMillTab();
    buildClarTab();
    buildTurbTab();
  });
})();
