(function () {
  'use strict';

  const TABS = [
    { id: 'steam', label: 'Steam Tables', enabled: true },
    { id: 'mill', label: 'Mill Floor', enabled: false },
    { id: 'clar', label: 'Clarification', enabled: false },
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

  document.addEventListener('DOMContentLoaded', () => {
    buildTabs();
    buildSteamTab();
  });
})();
