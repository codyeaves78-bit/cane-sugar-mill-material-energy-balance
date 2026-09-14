// Port of MillFloor.py — mill floor material balance for a counter-current
// cane milling train. All mass balance calculations run in the constructor;
// results are stored as instance properties, mirroring the Python class.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;
  const Bagasse = (typeof module !== 'undefined' && module.exports) ? require('./bagasse.js') : root.Bagasse;

  class MillFloor {
    constructor({
      cane_tpd,
      cane_pol_pct,
      cane_fiber_pct,
      imbibition_pct_on_cane,
      bagasse_pol_pct,
      last_roll_purity,
      bagasse_moisture_pct,
      mix_juice_purity,
      number_of_mills,
      juice_temp_F = 90.0,
      bagasse_ash_pct = 2.0,
      mill_1_fiber_rise_load_fraction = 0.35,
      name = 'Mill Floor',
    }) {
      this.name = name;
      this.cane_tpd = cane_tpd;
      this.cane_tph = this.cane_tpd / 24;
      this.cane_lb_hr = this.cane_tpd * 2000 / 24;
      this.cane_pol_pct = cane_pol_pct;
      this.cane_fiber_pct = cane_fiber_pct;
      this.imbibition_pct_on_cane = imbibition_pct_on_cane;
      this.imbibition_lb_hr = this.imbibition_pct_on_cane / 100 * this.cane_lb_hr;
      this.imbibition_tph = this.imbibition_lb_hr / 2000;
      this.bagasse_pol_pct = bagasse_pol_pct;
      this.last_roll_purity = last_roll_purity;
      this.bagasse_moisture_pct = bagasse_moisture_pct;
      this.bagasse_ash_pct = bagasse_ash_pct;
      this.mix_juice_purity = mix_juice_purity;
      this.number_of_mills = number_of_mills;
      this.juice_temp_F = juice_temp_F;
      this.mill_1_fiber_rise_load_fraction = mill_1_fiber_rise_load_fraction;

      // -- Imbibition --------------------------------------------------------
      const imb_tpd = cane_tpd * imbibition_pct_on_cane / 100;
      const imb_gpm = imb_tpd * 2000 / 24 / 60 / 8.3;

      // -- Bagasse -------------------------------------------------------------
      const bag_brix_pct = bagasse_pol_pct / last_roll_purity * 100;
      const bag_fiber_pct = 100 - bag_brix_pct - bagasse_moisture_pct;
      const bag_tpd = cane_tpd * cane_fiber_pct / bag_fiber_pct;

      // -- Mixed Juice -----------------------------------------------------
      const mix_juice_tpd = cane_tpd + imb_tpd - bag_tpd;
      const tons_pol_juice = cane_tpd * cane_pol_pct / 100 - bag_tpd * bagasse_pol_pct / 100;
      const tons_brix_juice = tons_pol_juice * 100 / mix_juice_purity;
      const mix_juice_brix = tons_brix_juice / mix_juice_tpd * 100;
      const mix_juice_pol = mix_juice_brix * mix_juice_purity / 100;
      const mix_juice_lb_hr = mix_juice_tpd / 24 * 2000;

      // -- Cane (back-calculated brix and moisture) -------------------------
      const cane_brix_pct = (tons_brix_juice + bag_tpd * bag_brix_pct / 100) / cane_tpd * 100;
      const cane_moist_pct = 100 - cane_brix_pct - cane_fiber_pct;
      this.cane_brix_pct = cane_brix_pct;
      this.cane_moist_pct = cane_moist_pct;

      // -- Mill extraction ---------------------------------------------------
      this.mill_extraction_pct = tons_pol_juice / (cane_tpd * cane_pol_pct / 100) * 100;
      this.imbibition_gpm = imb_gpm;

      // -- Per-mill intermediate flows (for maceration pump sizing) ----------
      const tons_fiber = cane_tpd * cane_fiber_pct / 100;
      const fib_change = bag_fiber_pct - cane_fiber_pct;
      const mill_1_bag_fib = cane_fiber_pct + mill_1_fiber_rise_load_fraction * fib_change;
      const fib_step = (bag_fiber_pct - mill_1_bag_fib) / Math.max(number_of_mills - 1, 1);

      const fiber_list = [mill_1_bag_fib];
      for (let i = 0; i < number_of_mills - 1; i++) {
        fiber_list.push(fiber_list[i] + fib_step);
      }

      const bag_flows = fiber_list.map((fib) => tons_fiber / (fib / 100));
      const j1 = cane_tpd - bag_flows[0];
      const j2 = mix_juice_tpd - j1;
      const juice_flows = [j1, j2];
      for (let i = 0; i < number_of_mills - 2; i++) {
        juice_flows.push(juice_flows[i + 1] - bag_flows[i] + bag_flows[i + 1]);
      }

      const mill_balances = [];
      for (let idx = 0; idx < number_of_mills; idx++) {
        const mill_num = idx + 1;
        const bag_in = idx === 0 ? cane_tpd : bag_flows[idx - 1];
        const bag_out = bag_flows[idx];
        const juice_out = juice_flows[idx];

        let mac_in, mac_src;
        if (mill_num === 1) {
          mac_in = 0.0; mac_src = 'None';
        } else if (mill_num === number_of_mills) {
          mac_in = imb_tpd; mac_src = 'Imbibition';
        } else {
          mac_in = juice_flows[idx + 1];
          mac_src = `Mill ${mill_num + 1} maceration`;
        }

        const dest = mill_num <= 2 ? 'To process' : `Mill ${mill_num - 1} maceration`;
        mill_balances.push({
          mill: mill_num,
          bagasse_in_tpd: bag_in,
          mac_in_tpd: mac_in,
          mac_in_source: mac_src,
          bagasse_out_tpd: bag_out,
          juice_out_tpd: juice_out,
          juice_out_dest: dest,
        });
      }

      this.mill_balances = mill_balances;

      // -- Mixed juice output --------------------------------------------------
      this.mixed_juice_stream = new SugarStream({
        brix: mix_juice_brix,
        purity: mix_juice_purity,
        flow_lb_per_hr: mix_juice_lb_hr,
        temp_deg_F: juice_temp_F,
        pressure_psia: 14.7,
        level_ft: 0,
      });

      // -- Bagasse output --------------------------------------------------
      this.bagasse_stream = new Bagasse({
        moisture_pct: bagasse_moisture_pct,
        brix_pct: bag_brix_pct,
        pol_pct: bagasse_pol_pct,
        ash_pct: bagasse_ash_pct,
        flowrate_lb_hr: bag_tpd / 24 * 2000,
      });
    }

    get balance_check() {
      const mj = this.mixed_juice_stream;
      const bag = this.bagasse_stream;

      const mj_tph = mj.flow_lb_per_hr / 2000;
      const mj_brix_tph = mj.solids_flow / 2000;
      const mj_pol_tph = mj.pol_flow / 2000;
      const mj_moist_tph = mj_tph - mj_brix_tph;

      const bag_tph = bag.flowrate_lb_hr / 2000;
      const bag_brix_tph = bag_tph * bag.brix_pct / 100;
      const bag_pol_tph = bag_tph * bag.pol_pct / 100;
      const bag_fiber_tph = bag_tph * bag.fiber_pct / 100;
      const bag_moist_tph = bag_tph * bag.moisture_pct / 100;

      const total_in = this.cane_tph + this.imbibition_tph;
      const total_out = mj_tph + bag_tph;

      const pol_in = this.cane_tph * this.cane_pol_pct / 100;
      const pol_out = mj_pol_tph + bag_pol_tph;

      const brix_in = this.cane_tph * this.cane_brix_pct / 100;
      const brix_out = mj_brix_tph + bag_brix_tph;

      const fiber_in = this.cane_tph * this.cane_fiber_pct / 100;
      const fiber_out = bag_fiber_tph;

      const water_in = this.cane_tph * this.cane_moist_pct / 100 + this.imbibition_tph;
      const water_out = mj_moist_tph + bag_moist_tph;

      return {
        total: { in_tph: total_in, out_tph: total_out, diff_tph: total_in - total_out },
        pol: { in_tph: pol_in, out_tph: pol_out, diff_tph: pol_in - pol_out },
        brix: { in_tph: brix_in, out_tph: brix_out, diff_tph: brix_in - brix_out },
        fiber: { in_tph: fiber_in, out_tph: fiber_out, diff_tph: fiber_in - fiber_out },
        water: { in_tph: water_in, out_tph: water_out, diff_tph: water_in - water_out },
      };
    }

    // Stream component flows (TPH) as data: { rows, in_tot, out_tot }.
    _stream_table_rows() {
      const mj = this.mixed_juice_stream;
      const bag = this.bagasse_stream;

      const mj_tph = mj.flow_lb_per_hr / 2000;
      const mj_brix_tph = mj.solids_flow / 2000;
      const mj_pol_tph = mj.pol_flow / 2000;
      const mj_water_tph = mj_tph - mj_brix_tph;

      const bag_tph = bag.flowrate_lb_hr / 2000;
      const bag_pol_tph = bag_tph * bag.pol_pct / 100;
      const bag_brix_tph = bag_tph * bag.brix_pct / 100;
      const bag_fiber_tph = bag_tph * bag.fiber_pct / 100;
      const bag_water_tph = bag_tph * bag.moisture_pct / 100;

      const cane_pol_tph = this.cane_tph * this.cane_pol_pct / 100;
      const cane_brix_tph = this.cane_tph * this.cane_brix_pct / 100;
      const cane_fiber_tph = this.cane_tph * this.cane_fiber_pct / 100;
      const cane_water_tph = this.cane_tph * this.cane_moist_pct / 100;

      const rows = [
        ['Cane', 'In', this.cane_tph, cane_pol_tph, cane_brix_tph, cane_fiber_tph, cane_water_tph],
        ['Imbibition', 'In', this.imbibition_tph, 0.0, 0.0, 0.0, this.imbibition_tph],
        ['Mixed Juice', 'Out', mj_tph, mj_pol_tph, mj_brix_tph, 0.0, mj_water_tph],
        ['Bagasse', 'Out', bag_tph, bag_pol_tph, bag_brix_tph, bag_fiber_tph, bag_water_tph],
      ];

      const in_tot = [0, 0, 0, 0, 0];
      const out_tot = [0, 0, 0, 0, 0];
      for (const [, direction, ...vals] of rows) {
        const totals = direction === 'In' ? in_tot : out_tot;
        vals.forEach((v, i) => { totals[i] += v; });
      }
      return { rows, in_tot, out_tot };
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MillFloor;
  } else {
    root.MillFloor = MillFloor;
  }
})(typeof window !== 'undefined' ? window : globalThis);
