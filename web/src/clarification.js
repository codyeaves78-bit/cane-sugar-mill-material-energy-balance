// Port of Clarification.py — clarification section material balance for a
// single-clarifier cane sugar factory. All mass balance calculations run in
// the constructor; the clarified juice output is a SugarStream so this unit
// can chain directly into juice heating / evaporation / pan floor.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;

  function specificGravity(brix) {
    return (
      62.2511
      + 0.24081 * brix
      + 0.0007902404 * brix ** 2
      + 0.00000423954 * brix ** 3
      - 0.00000001657193 * brix ** 4
    ) / 62.4;
  }

  function getCp(brix) {
    return 0.9964 - 0.005656 * brix;
  }

  class Clarification {
    constructor({
      mixed_juice_stream,
      cane_tpd,
      filter_wash_water_pct_on_cane,
      filter_cake_pct_on_cane,
      filter_cake_pol_pct,
      clarified_juice_purity,
      limed_juice_cold_temp_f = 85.0,
      limed_juice_hot_temp_f = 220.0,
      clarified_juice_temp_f = 205.0,
      lime_lb_per_ton_cane = 1.3,
      lime_baume = 10,
      polymer_lb_per_ton_cane = 0.045,
      polymer_conc_ppm = 5000,
      clarifier_underflow_pct_cane = 20,
      name = 'Clarification',
    }) {
      this.name = name;
      this.cane_tpd = cane_tpd;
      this.filter_wash_water_pct_on_cane = filter_wash_water_pct_on_cane;
      this.filter_cake_pct_on_cane = filter_cake_pct_on_cane;
      this.filter_cake_pol_pct = filter_cake_pol_pct;
      this.clarified_juice_purity = clarified_juice_purity;
      this.limed_juice_cold_temp_f = limed_juice_cold_temp_f;
      this.limed_juice_hot_temp_f = limed_juice_hot_temp_f;
      this.clarified_juice_temp_f = clarified_juice_temp_f;
      this.lime_lb_per_ton_cane = lime_lb_per_ton_cane;
      this.lime_baume = lime_baume;
      this.polymer_lb_per_ton_cane = polymer_lb_per_ton_cane;
      this.polymer_conc_ppm = polymer_conc_ppm;
      this.clarifier_underflow_pct_cane = clarifier_underflow_pct_cane;

      const FLASH_TEMP_F = 212.0;

      // -- Unpack mixed juice from SugarStream --------------------------------
      const mj_lb_hr = mixed_juice_stream.flow_lb_per_hr;
      const mj_brix_pct = mixed_juice_stream.brix;
      const mj_purity = mixed_juice_stream.purity;
      const mj_temp_f = mixed_juice_stream.temp_deg_F;
      const mj_pol_pct = mj_brix_pct * mj_purity / 100;

      const cane_lb_hr = cane_tpd * 2000 / 24;

      // -- Fixed external inputs (lb/hr) --------------------------------------
      const lime_lb_hr = cane_tpd * lime_lb_per_ton_cane / 24;
      const lime_water_lb_hr = lime_lb_hr / (lime_baume / 100) - lime_lb_hr;
      const polymer_lb_hr = cane_tpd * polymer_lb_per_ton_cane / 24;
      const poly_water_lb_hr = polymer_lb_hr * 10 ** 6 / polymer_conc_ppm - polymer_lb_hr;
      const wash_water_lb_hr = cane_lb_hr * filter_wash_water_pct_on_cane / 100;
      const fc_lb_hr = cane_lb_hr * filter_cake_pct_on_cane / 100;
      const mol_lb_hr = lime_lb_hr + lime_water_lb_hr;
      const poly_sol_lb_hr = polymer_lb_hr + poly_water_lb_hr;
      const fixed_lb_hr = mj_lb_hr + mol_lb_hr + poly_sol_lb_hr;

      // -- MJ brix/pol (lb/hr) -------------------------------------------------
      const mj_brix_lb_hr = mj_lb_hr * mj_brix_pct / 100;
      const mj_pol_lb_hr = mj_lb_hr * mj_pol_pct / 100;
      const fc_pol_lb_hr = fc_lb_hr * filter_cake_pol_pct / 100;

      // -- CJ brix/pol -- external pol and brix balances ----------------------
      const cj_pol_lb_hr = mj_pol_lb_hr - fc_pol_lb_hr;
      const cj_brix_lb_hr = cj_pol_lb_hr * 100 / clarified_juice_purity;

      // -- Filter cake brix ------------------------------------------------
      const fc_brix_lb_hr = mj_brix_lb_hr - cj_brix_lb_hr;
      const fc_purity = fc_pol_lb_hr / fc_brix_lb_hr * 100;
      const fc_brix_pct = fc_brix_lb_hr / fc_lb_hr * 100;

      // -- Clarifier underflow -------------------------------------------------
      const uf_brix_pct = mj_brix_pct;
      const uf_pol_pct = uf_brix_pct * fc_purity / 100;
      const uf_lb_hr = clarifier_underflow_pct_cane / 100 * cane_lb_hr;
      const uf_pol_lb_hr = uf_lb_hr * uf_pol_pct / 100;
      const uf_brix_lb_hr = uf_lb_hr * uf_brix_pct / 100;

      // -- Rotary filter -- filtrate = underflow + wash - cake -----------------
      const filtrate_lb_hr = wash_water_lb_hr + uf_lb_hr - fc_lb_hr;
      const filtrate_pol_lb_hr = uf_pol_lb_hr - fc_pol_lb_hr;
      const filtrate_brix_lb_hr = uf_brix_lb_hr - fc_brix_lb_hr;
      const filtrate_brix_pct = filtrate_brix_lb_hr / filtrate_lb_hr * 100;
      const filtrate_pol_pct = filtrate_pol_lb_hr / filtrate_lb_hr * 100;
      const filtrate_purity = filtrate_pol_lb_hr / filtrate_brix_lb_hr * 100;

      // -- Limed juice -------------------------------------------------------
      const lj_lb_hr = fixed_lb_hr + filtrate_lb_hr;
      const lj_brix_lb_hr = mj_brix_lb_hr + filtrate_brix_lb_hr;
      const lj_pol_lb_hr = mj_pol_lb_hr + filtrate_pol_lb_hr;
      const lj_brix_pct = lj_brix_lb_hr / lj_lb_hr * 100;
      const lj_pol_pct = lj_pol_lb_hr / lj_lb_hr * 100;

      // -- Flash tank ----------------------------------------------------------
      const flash_vapor_lb_hr = limed_juice_hot_temp_f > 212
        ? lj_lb_hr * (limed_juice_hot_temp_f - 212) * getCp(lj_brix_pct) / 970
        : 0;
      const fj_lb_hr = lj_lb_hr - flash_vapor_lb_hr;
      const fj_brix_lb_hr = lj_brix_lb_hr;
      const fj_pol_lb_hr = lj_pol_lb_hr;
      const fj_brix_pct = fj_brix_lb_hr / fj_lb_hr * 100;
      const fj_pol_pct = fj_pol_lb_hr / fj_lb_hr * 100;

      // -- Clarified juice -------------------------------------------------
      const cj_lb_hr = fixed_lb_hr + wash_water_lb_hr - fc_lb_hr - flash_vapor_lb_hr;
      const cj_pol_pct = cj_pol_lb_hr / cj_lb_hr * 100;
      const cj_brix_pct = cj_brix_lb_hr / cj_lb_hr * 100;

      // -- Scalar outputs --------------------------------------------------
      this.flash_vapor_pct = flash_vapor_lb_hr / lj_lb_hr * 100;
      this.filter_cake_pol_lb_per_day = fc_pol_lb_hr * 24;
      this.filter_wash_water_lb_hr = wash_water_lb_hr;

      // -- Clarified juice output stream ---------------------------------------
      this.clarified_juice_stream = new SugarStream({
        brix: cj_brix_pct,
        purity: clarified_juice_purity,
        flow_lb_per_hr: cj_lb_hr,
        temp_deg_F: clarified_juice_temp_f,
        pressure_psia: 14.7,
        level_ft: 0,
      });

      // also include the Limed Juice as an output stream for use in JuiceHeating
      this.limed_juice_cold_stream = new SugarStream({
        brix: lj_brix_pct,
        purity: lj_pol_lb_hr / lj_brix_lb_hr * 100,
        flow_lb_per_hr: lj_lb_hr,
        temp_deg_F: limed_juice_cold_temp_f,
      });

      // -- Stream table ------------------------------------------------------
      const gpm = (lb_hr, sg) => lb_hr / (sg * 8.34 * 60);

      const raw = [
        ['Mixed Juice', 'In', mj_lb_hr, mj_brix_pct, mj_pol_pct, mj_temp_f],
        ['Lime', 'In', lime_lb_hr, 0.0, 0.0, null],
        ['Water for Lime', 'In', lime_water_lb_hr, 0.0, 0.0, null],
        ['Polymer', 'In', polymer_lb_hr, 0.0, 0.0, null],
        ['Polymer Water', 'In', poly_water_lb_hr, 0.0, 0.0, null],
        ['Filter Wash Water', 'In', wash_water_lb_hr, 0.0, 0.0, null],
        ['Flash Vapors', 'Out', flash_vapor_lb_hr, 0.0, 0.0, FLASH_TEMP_F],
        ['Clarified Juice', 'Out', cj_lb_hr, cj_brix_pct, cj_pol_pct, clarified_juice_temp_f],
        ['Filter Cake', 'Out', fc_lb_hr, fc_brix_pct, filter_cake_pol_pct, null],
        ['Milk of Lime', 'Internal', mol_lb_hr, 0.0, 0.0, null],
        ['Polymer Solution', 'Internal', poly_sol_lb_hr, 0.0, 0.0, null],
        ['Limed Juice Cold', 'Internal', lj_lb_hr, lj_brix_pct, lj_pol_pct, limed_juice_cold_temp_f],
        ['Limed Juice Hot', 'Internal', lj_lb_hr, lj_brix_pct, lj_pol_pct, limed_juice_hot_temp_f],
        ['Flashed Juice', 'Internal', fj_lb_hr, fj_brix_pct, fj_pol_pct, FLASH_TEMP_F],
        ['Clarifier Underflow', 'Internal', uf_lb_hr, uf_brix_pct, uf_pol_pct, null],
        ['Filtrate', 'Internal', filtrate_lb_hr, filtrate_brix_pct, filtrate_pol_pct, null],
      ];

      this.streams = {};
      for (const [sname, direction, lb_hr, brix, pol, temp] of raw) {
        const purity = brix > 0 ? pol / brix * 100 : 0.0;
        const sg = brix > 0 ? specificGravity(brix) : 1.0;
        this.streams[sname] = {
          direction,
          lb_per_hr: lb_hr,
          gpm: gpm(lb_hr, sg),
          brix_pct: brix,
          pol_pct: pol,
          purity_pct: purity,
          sg,
          brix_lb_per_hr: lb_hr * brix / 100,
          pol_lb_per_hr: lb_hr * pol / 100,
          pct_on_cane: lb_hr / cane_lb_hr * 100,
          temp_f: temp,
        };
      }
    }

    get balance_check() {
      const keys = ['lb_per_hr', 'brix_lb_per_hr', 'pol_lb_per_hr'];
      const totals = { in: {}, out: {}, difference: {} };
      const streams = Object.values(this.streams);
      for (const key of keys) {
        const in_ = streams.filter((s) => s.direction === 'In').reduce((a, s) => a + s[key], 0);
        const out_ = streams.filter((s) => s.direction === 'Out').reduce((a, s) => a + s[key], 0);
        totals.in[key] = in_;
        totals.out[key] = out_;
        totals.difference[key] = in_ - out_;
      }
      return totals;
    }

    // Numbered stream rows in Python's `_collect_streams(clar)` diagram order
    // (see clarification_diagram.py's TAG_ORDER).
    _collect_streams() {
      const TAG_ORDER = [
        'Mixed Juice', 'Lime', 'Water for Lime', 'Polymer', 'Polymer Water',
        'Filter Wash Water',
        'Flash Vapors', 'Clarified Juice', 'Filter Cake',
        'Milk of Lime', 'Polymer Solution', 'Limed Juice Cold', 'Limed Juice Hot',
        'Flashed Juice', 'Clarifier Underflow', 'Filtrate',
      ];
      return TAG_ORDER.map((name, i) => {
        const s = this.streams[name];
        return [
          i + 1, name, s.direction, s.lb_per_hr, s.gpm, s.brix_lb_per_hr,
          s.pol_lb_per_hr, s.brix_pct, s.pol_pct,
          s.brix_pct > 0 ? s.purity_pct : null,
          s.pct_on_cane, s.temp_f,
        ];
      });
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Clarification;
  } else {
    root.Clarification = Clarification;
  }
})(typeof window !== 'undefined' ? window : globalThis);
