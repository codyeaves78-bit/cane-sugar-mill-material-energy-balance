// Port of FourBoilingDoubleMagma.py — Four Boiling Double Magma pan floor
// balance: A1, A2, B, C pans with grain pans. When constructing with Pan and
// Centrifugal "config" objects, feed_streams/massecuite are ignored -- the
// solver rebuilds a fresh Pan/Centrifugal each iteration with the real,
// upstream-derived feed streams (see _rebuildPan/_rebuildCentrifugal), same
// as the Python source.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;
  const Pan = (typeof module !== 'undefined' && module.exports) ? require('./pan.js') : root.Pan;
  const Centrifugal = (typeof module !== 'undefined' && module.exports) ? require('./centrifugal.js') : root.Centrifugal;
  const { Crystallizer, Reheater } = (typeof module !== 'undefined' && module.exports) ? require('./crystallizer_reheater.js') : { Crystallizer: root.Crystallizer, Reheater: root.Reheater };
  const condensate_utils = (typeof module !== 'undefined' && module.exports) ? require('./condensate_utils.js') : root.condensate_utils;

  function makeMagma(sugar_stream, mingler_brix) {
    const magma = SugarStream.copy(sugar_stream);
    const solids = magma.solids_flow;
    magma.brix = mingler_brix;
    magma.flow_lb_per_hr = solids / magma.brix * 100;
    return magma;
  }

  function makeRemelt(magma, remelt_brix) {
    const remelt = SugarStream.copy(magma);
    const brix_flow = magma.solids_flow;
    const new_flow = brix_flow * 100 / remelt_brix;
    const new_brix = brix_flow / new_flow * 100;
    remelt.flow_lb_per_hr = new_flow;
    remelt.brix = new_brix;
    return remelt;
  }

  function diluteMolasses(mol, diluted_brix) {
    const diluted = SugarStream.copy(mol);
    diluted.brix = diluted_brix;
    diluted.flow_lb_per_hr = mol.solids_flow / (diluted_brix / 100);
    return diluted;
  }

  class FourBoilingDoubleMagma {
    constructor({
      syrup,
      A1_pans, A2_pans, B_pans, C_pans, grain_pans,
      A1_centrifugals, A2_centrifugals, B_centrifugals, C_centrifugals,
      C_crystallizers = null, C_reheaters = null,
      syrup_to_A1_pans_pct = 75, syrup_to_A2_pans_pct = 20,
      a1_mol_to_A2_pct = 80, a1_mol_to_grain_pct = 3,
      a2_mol_to_grain_pct = 3, b_mol_to_grain_pct = 10,
      b_magma_A1_footing_pct = 40, b_magma_A2_footing_pct = 40,
      c_magma_B_footing_pct = 80,
      a1_mol_dilution_brix = 70, a2_mol_dilution_brix = 70, b_mol_dilution_brix = 70,
      b_magma_brix = 92, c_magma_brix = 92,
      b_remelt_brix = 65, c_remelt_brix = 65,
      injection_water_temp_F = 90, condenser_leg_temp_drop_F = 5,
      iterations = 15,
    } = {}) {
      this.syrup = syrup;
      this.injection_water_temp_F = injection_water_temp_F;
      this.condensor_leg_temp_drop_F = condenser_leg_temp_drop_F;

      this._A1_pans_cfg = A1_pans;
      this._A2_pans_cfg = A2_pans;
      this._B_pans_cfg = B_pans;
      this._C_pans_cfg = C_pans;
      this._grain_pans_cfg = grain_pans;
      this._A1_cen_cfg = A1_centrifugals;
      this._A2_cen_cfg = A2_centrifugals;
      this._B_cen_cfg = B_centrifugals;
      this._C_cen_cfg = C_centrifugals;
      this._C_crys_cfg = C_crystallizers !== null && C_crystallizers !== undefined
        ? C_crystallizers
        : new Crystallizer({ massecuite_in: null, massecuite_flow_lb_hr: 0, name: 'C Crystallizers' });
      this._C_reheat_cfg = C_reheaters !== null && C_reheaters !== undefined
        ? C_reheaters
        : new Reheater({ massecuite_in: null, massecuite_flow_lb_hr: 0, name: 'C Reheaters' });

      this.syrup_to_A1_pans_pct = syrup_to_A1_pans_pct;
      this.syrup_to_A2_pans_pct = syrup_to_A2_pans_pct;
      this.syrup_to_grain_pct = 100.0 - syrup_to_A1_pans_pct - syrup_to_A2_pans_pct;

      this.a1_mol_to_A2_pct = a1_mol_to_A2_pct;
      this.a1_mol_to_grain_pct = a1_mol_to_grain_pct;
      this.a1_mol_to_B_pct = 100.0 - a1_mol_to_A2_pct - a1_mol_to_grain_pct;

      this.a2_mol_to_grain_pct = a2_mol_to_grain_pct;
      this.a2_mol_to_B_pct = 100.0 - a2_mol_to_grain_pct;

      this.b_mol_to_grain_pct = b_mol_to_grain_pct;
      this.b_mol_to_C_pct = 100.0 - b_mol_to_grain_pct;

      this.b_magma_A1_footing_pct = b_magma_A1_footing_pct;
      this.b_magma_A2_footing_pct = b_magma_A2_footing_pct;
      this.b_magma_remelt_pct = 100.0 - b_magma_A1_footing_pct - b_magma_A2_footing_pct;

      this.c_magma_B_footing_pct = c_magma_B_footing_pct;
      this.c_magma_remelt_pct = 100.0 - c_magma_B_footing_pct;

      this.a1_mol_dilution_brix = a1_mol_dilution_brix;
      this.a2_mol_dilution_brix = a2_mol_dilution_brix;
      this.b_mol_dilution_brix = b_mol_dilution_brix;
      this.b_magma_brix = b_magma_brix;
      this.c_magma_brix = c_magma_brix;
      this.b_remelt_brix = b_remelt_brix;
      this.c_remelt_brix = c_remelt_brix;

      this._solve(iterations);
    }

    _rebuildPan(config, feed_streams) {
      return new Pan({
        feed_streams: feed_streams,
        heating_surface_ft2: config.heating_surface_ft2,
        inches_vacuum: config.inches_vacuum,
        supersaturation: config.supersaturation,
        head_ft: config.head_ft,
        masse_brix: config.masse_brix,
        ml_purity: config.ml_purity,
        calandria_pressure_psia: config.calandria_pressure_psia,
        heat_loss_factor: config.heat_loss_factor,
        name: config.name,
        steam_type: config.steam_type,
      });
    }

    _rebuildCentrifugal(config, massecuite, massecuite_flow_lb_hr) {
      return new Centrifugal({
        massecuite: massecuite,
        massecuite_flow_lb_hr: massecuite_flow_lb_hr,
        target_molasses_brix: config.target_molasses_brix,
        purity_rise: config.purity_rise,
        sugar_purity: config.sugar_purity,
        sugar_moisture: config.sugar_moisture,
        name: config.name,
        sugar_temp: config.sugar_temp,
        molasses_temp: config.molasses_temp,
      });
    }

    _rebuildCrystallizer(config, massecuite_in, massecuite_flow_lb_hr) {
      return new Crystallizer({
        massecuite_in: massecuite_in,
        massecuite_flow_lb_hr: massecuite_flow_lb_hr,
        masse_temp_out_deg_F: config.masse_temp_out_deg_F,
        ml_purity_out: config.ml_purity_out,
        water_temp_in_deg_F: config.water_temp_in_deg_F,
        water_temp_out_deg_F: config.water_temp_out_deg_F,
        name: config.name,
      });
    }

    _rebuildReheater(config, massecuite_in, massecuite_flow_lb_hr) {
      return new Reheater({
        massecuite_in: massecuite_in,
        massecuite_flow_lb_hr: massecuite_flow_lb_hr,
        masse_temp_out_deg_F: config.masse_temp_out_deg_F,
        ml_purity_out: config.ml_purity_out,
        water_temp_in_deg_F: config.water_temp_in_deg_F,
        water_temp_out_deg_F: config.water_temp_out_deg_F,
        name: config.name,
      });
    }

    _solve(iterations = 15) {
      let b_magma_A1_footing = new SugarStream({ brix: this.b_magma_brix, purity: 92, flow_lb_per_hr: 0, temp_deg_F: 130 });
      let b_magma_A2_footing = new SugarStream({ brix: this.b_magma_brix, purity: 92, flow_lb_per_hr: 0, temp_deg_F: 130 });
      let c_magma_B_footing = new SugarStream({ brix: this.c_magma_brix, purity: 85, flow_lb_per_hr: 0, temp_deg_F: 130 });

      let syrup_as_fed = SugarStream.copy(this.syrup);

      let a1_mol_diluted, a2_mol_diluted, b_mol_diluted;
      let b_magma, c_magma, b_magma_to_rmlt, c_magma_to_rmlt, b_remelt, c_remelt;

      for (let iter = 0; iter < iterations; iter++) {
        // -- Split syrup --
        const syrup_to_A1 = SugarStream.copy(syrup_as_fed);
        syrup_to_A1.flow_lb_per_hr = this.syrup_to_A1_pans_pct / 100 * syrup_as_fed.flow_lb_per_hr;

        const syrup_to_A2 = SugarStream.copy(syrup_as_fed);
        syrup_to_A2.flow_lb_per_hr = this.syrup_to_A2_pans_pct / 100 * syrup_as_fed.flow_lb_per_hr;

        const syrup_to_grain = SugarStream.copy(syrup_as_fed);
        syrup_to_grain.flow_lb_per_hr = this.syrup_to_grain_pct / 100 * syrup_as_fed.flow_lb_per_hr;

        // -- A1 pans --
        this.A1_pans = this._rebuildPan(this._A1_pans_cfg, [syrup_to_A1, b_magma_A1_footing]);
        this.A1_centrifugals = this._rebuildCentrifugal(this._A1_cen_cfg, this.A1_pans.massecuite, this.A1_pans.massecuite_flow_lb_hr);

        a1_mol_diluted = diluteMolasses(this.A1_centrifugals.molasses_stream, this.a1_mol_dilution_brix);

        const a1_mol_to_A2 = SugarStream.copy(a1_mol_diluted);
        a1_mol_to_A2.flow_lb_per_hr = this.a1_mol_to_A2_pct / 100 * a1_mol_diluted.flow_lb_per_hr;

        const a1_mol_to_grain = SugarStream.copy(a1_mol_diluted);
        a1_mol_to_grain.flow_lb_per_hr = this.a1_mol_to_grain_pct / 100 * a1_mol_diluted.flow_lb_per_hr;

        const a1_mol_to_B = SugarStream.copy(a1_mol_diluted);
        a1_mol_to_B.flow_lb_per_hr = this.a1_mol_to_B_pct / 100 * a1_mol_diluted.flow_lb_per_hr;

        // -- A2 pans --
        this.A2_pans = this._rebuildPan(this._A2_pans_cfg, [syrup_to_A2, a1_mol_to_A2, b_magma_A2_footing]);
        this.A2_centrifugals = this._rebuildCentrifugal(this._A2_cen_cfg, this.A2_pans.massecuite, this.A2_pans.massecuite_flow_lb_hr);

        a2_mol_diluted = diluteMolasses(this.A2_centrifugals.molasses_stream, this.a2_mol_dilution_brix);

        const a2_mol_to_grain = SugarStream.copy(a2_mol_diluted);
        a2_mol_to_grain.flow_lb_per_hr = this.a2_mol_to_grain_pct / 100 * a2_mol_diluted.flow_lb_per_hr;

        const a2_mol_to_B = SugarStream.copy(a2_mol_diluted);
        a2_mol_to_B.flow_lb_per_hr = this.a2_mol_to_B_pct / 100 * a2_mol_diluted.flow_lb_per_hr;

        // -- B pans --
        this.B_pans = this._rebuildPan(this._B_pans_cfg, [a2_mol_to_B, c_magma_B_footing, a1_mol_to_B]);
        this.B_centrifugals = this._rebuildCentrifugal(this._B_cen_cfg, this.B_pans.massecuite, this.B_pans.massecuite_flow_lb_hr);

        b_magma = makeMagma(this.B_centrifugals.sugar_stream, this.b_magma_brix);
        b_magma_A1_footing = SugarStream.copy(b_magma);
        b_magma_A1_footing.flow_lb_per_hr = this.b_magma_A1_footing_pct / 100 * b_magma.flow_lb_per_hr;
        b_magma_A2_footing = SugarStream.copy(b_magma);
        b_magma_A2_footing.flow_lb_per_hr = this.b_magma_A2_footing_pct / 100 * b_magma.flow_lb_per_hr;
        b_magma_to_rmlt = SugarStream.copy(b_magma);
        b_magma_to_rmlt.flow_lb_per_hr = this.b_magma_remelt_pct / 100 * b_magma.flow_lb_per_hr;

        b_mol_diluted = diluteMolasses(this.B_centrifugals.molasses_stream, this.b_mol_dilution_brix);

        const b_mol_to_grain = SugarStream.copy(b_mol_diluted);
        b_mol_to_grain.flow_lb_per_hr = this.b_mol_to_grain_pct / 100 * b_mol_diluted.flow_lb_per_hr;

        const b_mol_to_C = SugarStream.copy(b_mol_diluted);
        b_mol_to_C.flow_lb_per_hr = this.b_mol_to_C_pct / 100 * b_mol_diluted.flow_lb_per_hr;

        // -- Grain pans --
        this.grain_pans = this._rebuildPan(this._grain_pans_cfg, [syrup_to_grain, a1_mol_to_grain, a2_mol_to_grain, b_mol_to_grain]);

        const grain_massecuite = new SugarStream({
          brix: this.grain_pans.masse_brix,
          purity: this.grain_pans.masse_purity,
          flow_lb_per_hr: this.grain_pans.massecuite_flow_lb_hr,
          temp_deg_F: this.grain_pans.massecuite.massecuite_temp,
          pressure_psia: 14.7,
          level_ft: 0,
        });

        // -- C pans --
        this.C_pans = this._rebuildPan(this._C_pans_cfg, [grain_massecuite, b_mol_to_C]);

        this.C_crystallizers = this._rebuildCrystallizer(this._C_crys_cfg, this.C_pans.massecuite, this.C_pans.massecuite_flow_lb_hr);
        this.C_reheaters = this._rebuildReheater(this._C_reheat_cfg, this.C_crystallizers.massecuite_out, this.C_pans.massecuite_flow_lb_hr);
        this.C_centrifugals = this._rebuildCentrifugal(this._C_cen_cfg, this.C_reheaters.massecuite_out, this.C_pans.massecuite_flow_lb_hr);

        c_magma = makeMagma(this.C_centrifugals.sugar_stream, this.c_magma_brix);
        c_magma_B_footing = SugarStream.copy(c_magma);
        c_magma_B_footing.flow_lb_per_hr = this.c_magma_B_footing_pct / 100 * c_magma.flow_lb_per_hr;
        c_magma_to_rmlt = SugarStream.copy(c_magma);
        c_magma_to_rmlt.flow_lb_per_hr = this.c_magma_remelt_pct / 100 * c_magma.flow_lb_per_hr;

        b_remelt = makeRemelt(b_magma_to_rmlt, this.b_remelt_brix);
        c_remelt = makeRemelt(c_magma_to_rmlt, this.c_remelt_brix);

        const total_flows = this.syrup.flow_lb_per_hr + b_remelt.flow_lb_per_hr + c_remelt.flow_lb_per_hr;
        const total_solids = this.syrup.solids_flow + b_remelt.solids_flow + c_remelt.solids_flow;
        const total_pols = this.syrup.pol_flow + b_remelt.pol_flow + c_remelt.pol_flow;

        syrup_as_fed = SugarStream.copy(this.syrup);
        syrup_as_fed.flow_lb_per_hr = total_flows;
        syrup_as_fed.brix = total_solids / total_flows * 100;
        syrup_as_fed.purity = total_pols / total_solids * 100;
      }

      this.syrup_as_fed = syrup_as_fed;

      this._a1_mol_diluted = a1_mol_diluted;
      this._a2_mol_diluted = a2_mol_diluted;
      this._b_mol_diluted = b_mol_diluted;

      this._b_magma = b_magma;
      this._c_magma = c_magma;
      this._b_magma_A1_footing = b_magma_A1_footing;
      this._b_magma_A2_footing = b_magma_A2_footing;
      this._c_magma_B_footing = c_magma_B_footing;
      this._b_magma_to_rmlt = b_magma_to_rmlt;
      this._c_magma_to_rmlt = c_magma_to_rmlt;
      this._b_remelt = b_remelt;
      this._c_remelt = c_remelt;
    }

    get _pans() {
      return [this.A1_pans, this.A2_pans, this.B_pans, this.grain_pans, this.C_pans];
    }

    _steamDemandLbHr(steam_type) {
      return this._pans.filter((p) => p.steam_type === steam_type).reduce((s, p) => s + p.steam_flow_lb_hr, 0);
    }

    get total_raw_sugar() {
      const a1 = this.A1_centrifugals.sugar_stream;
      const a2 = this.A2_centrifugals.sugar_stream;
      const total_flow = a1.flow_lb_per_hr + a2.flow_lb_per_hr;
      const total_solids = a1.solids_flow + a2.solids_flow;
      const total_pol = a1.pol_flow + a2.pol_flow;
      const combined = SugarStream.copy(a1);
      combined.flow_lb_per_hr = total_flow;
      combined.brix = total_solids / total_flow * 100;
      combined.purity = total_pol / total_solids * 100;
      return combined;
    }

    get total_exhaust_steam_lb_hr() { return this._steamDemandLbHr(0); }
    get total_V1_steam_lb_hr() { return this._steamDemandLbHr(1); }
    get total_V2_steam_lb_hr() { return this._steamDemandLbHr(2); }
    get total_V3_steam_lb_hr() { return this._steamDemandLbHr(3); }
    get total_V4_steam_lb_hr() { return this._steamDemandLbHr(4); }

    get clean_condensate() {
      return this._pans.filter((p) => p.steam_type === 0)
        .reduce((s, p) => s + condensate_utils.flash_condensate(p.steam_flow_lb_hr, p.calandria_T_sat_F), 0);
    }

    get dirty_condensate() {
      return this._pans.filter((p) => p.steam_type !== 0)
        .reduce((s, p) => s + condensate_utils.flash_condensate(p.steam_flow_lb_hr, p.calandria_T_sat_F), 0);
    }

    get total_water() {
      const cen_wash = this.A1_centrifugals.wash_water_lb_hr + this.A2_centrifugals.wash_water_lb_hr
        + this.B_centrifugals.wash_water_lb_hr + this.C_centrifugals.wash_water_lb_hr;
      const b_mingler = this._b_magma.flow_lb_per_hr - this.B_centrifugals.sugar_stream.flow_lb_per_hr;
      const c_mingler = this._c_magma.flow_lb_per_hr - this.C_centrifugals.sugar_stream.flow_lb_per_hr;
      const b_rmlt_water = this._b_remelt.flow_lb_per_hr - this._b_magma_to_rmlt.flow_lb_per_hr;
      const c_rmlt_water = this._c_remelt.flow_lb_per_hr - this._c_magma_to_rmlt.flow_lb_per_hr;
      const a1_dil_water = this._a1_mol_diluted.flow_lb_per_hr - this.A1_centrifugals.molasses_stream.flow_lb_per_hr;
      const a2_dil_water = this._a2_mol_diluted.flow_lb_per_hr - this.A2_centrifugals.molasses_stream.flow_lb_per_hr;
      const b_dil_water = this._b_mol_diluted.flow_lb_per_hr - this.B_centrifugals.molasses_stream.flow_lb_per_hr;
      const total_lb_hr = cen_wash + b_mingler + c_mingler + b_rmlt_water + c_rmlt_water
        + a1_dil_water + a2_dil_water + b_dil_water;
      return new SugarStream({ brix: 0, purity: 0, flow_lb_per_hr: total_lb_hr });
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { FourBoilingDoubleMagma, makeMagma, makeRemelt, diluteMolasses };
  } else {
    root.FourBoilingDoubleMagma = FourBoilingDoubleMagma;
  }
})(typeof window !== 'undefined' ? window : globalThis);
