// Port of SugarStream.py + sugar_stream_properties.py. A generic sugar
// solution stream (brix/purity/flow/temp/pressure/level) used throughout the
// mill balance (mixed juice, clarified juice, syrup, massecuite, etc). Fast
// polynomial correlations are used here (not IAPWS97) for BPE/latent
// heat/sat-temp, matching the Python source's own choice for speed over the
// 1-60 psia range these correlations were fitted to.

(function (root) {
  'use strict';

  function bpeBrix(brix) {
    return 4.266667 * brix / (100 - brix);
  }

  function bpeHead(lvl, brix, tVap) {
    const brixPoly = (
      0.99991
      + 0.0038008 * brix
      + 0.000012662 * brix ** 2
      + 0.00000009596 * brix ** 3
    );
    const tempPoly = (
      5.314
      - 0.07135 * tVap
      + 0.00033908 * tVap ** 2
      - 0.00000055728 * tVap ** 3
    );
    let bpeCalc = lvl * 6 * brixPoly * tempPoly;
    if (bpeCalc < 1) bpeCalc = 1;
    return bpeCalc;
  }

  function satSteamTemp(pPsia) {
    // Only valid for pressure 1-60 psia.
    const A = 6.239238;
    const B = 2988.801361;
    const C = 377.305590;
    return B / (A - Math.log10(pPsia)) - C;
  }

  function bpeTotal(lvl, brix, pVapPsia) {
    const tVap = satSteamTemp(pVapPsia);
    return bpeBrix(brix) + bpeHead(lvl, brix, tVap);
  }

  function getLatentHeat(pPsia) {
    // Only valid for psia 1-60.
    const temp = satSteamTemp(pPsia);
    return -0.00000152231563 * temp ** 3 + 0.000504774867 * temp ** 2 - 0.634291695987 * temp + 1096.29;
  }

  function getCp(brix) {
    return 0.9964 - 0.005656 * brix;
  }

  function specificGravity(brix) {
    // Specific gravity of a sugar solution, at 68 deg F.
    return (
      62.2511
      + 0.24081 * brix
      + 0.0007902404 * brix ** 2
      + 0.00000423954 * brix ** 3
      - 0.00000001657193 * brix ** 4
    ) / 62.4;
  }

  let _count = 0;

  class SugarStream {
    constructor({ brix = 0, purity = 0, flow_lb_per_hr = 0, temp_deg_F = 90, pressure_psia = 14.7, level_ft = 0 } = {}) {
      _count += 1;
      this.stream_id = _count;
      this.brix = brix;
      this.purity = purity;
      this.flow_lb_per_hr = flow_lb_per_hr;
      this.temp_deg_F = temp_deg_F;
      this.pressure_psia = pressure_psia;
      this.level_ft = level_ft;
    }

    get pol() {
      return (this.brix > 0 && this.purity > 0) ? this.purity * this.brix / 100 : 0;
    }

    get boiling_point_elevation_deg_F() {
      return this.brix > 0 ? bpeTotal(this.level_ft, this.brix, this.pressure_psia) : 0;
    }

    get cp_btu_per_lb_deg_F() {
      return this.brix > 0 ? getCp(this.brix) : 1;
    }

    get specific_gravity() {
      return this.brix > 0 ? specificGravity(this.brix) : 1;
    }

    get cu_ft_hr() {
      return this.flow_lb_per_hr / (62.4 * this.specific_gravity);
    }

    get latent_heat_btu_per_lb() {
      return this.pressure_psia > 0 ? getLatentHeat(this.pressure_psia) : 0;
    }

    get vapor_saturation_temp_deg_F() {
      return this.pressure_psia > 0 ? satSteamTemp(this.pressure_psia) : 0;
    }

    get solids_flow() {
      return this.brix * this.flow_lb_per_hr / 100;
    }

    get pol_flow() {
      return this.pol * this.flow_lb_per_hr / 100;
    }

    // Sets the current temp to the vapor boiling temp + boiling point
    // elevation, useful in evaporator calculations.
    current_temp_to_bpe_plus_vapor_temp() {
      this.temp_deg_F = this.vapor_saturation_temp_deg_F + this.boiling_point_elevation_deg_F;
    }

    // A quick transform into syrup, convenient for clarified juice --> syrup
    // for Pan Floor calcs.
    evaporate(new_brix = 65, new_temp = 140) {
      const currentSolids = this.solids_flow;
      const newFlow = 100 / new_brix * currentSolids;
      this.flow_lb_per_hr = newFlow;
      this.brix = new_brix;
      this.temp_deg_F = new_temp;
    }

    properties() {
      return {
        stream_id: this.stream_id,
        brix: this.brix,
        purity: this.purity,
        flow_lb_per_hr: this.flow_lb_per_hr,
        temp_deg_F: this.temp_deg_F,
        pressure_psia: this.pressure_psia,
        level_ft: this.level_ft,
        pol: this.pol,
        boiling_point_elevation_deg_F: this.boiling_point_elevation_deg_F,
        cp_btu_per_lb_deg_F: this.cp_btu_per_lb_deg_F,
        specific_gravity: this.specific_gravity,
        cu_ft_hr: this.cu_ft_hr,
        latent_heat_btu_per_lb: this.latent_heat_btu_per_lb,
        vapor_saturation_temp_deg_F: this.vapor_saturation_temp_deg_F,
        solids_flow: this.solids_flow,
        pol_flow: this.pol_flow,
      };
    }

    static copy(stream, overrides = {}) {
      return new SugarStream(Object.assign({
        brix: stream.brix,
        purity: stream.purity,
        flow_lb_per_hr: stream.flow_lb_per_hr,
        temp_deg_F: stream.temp_deg_F,
        pressure_psia: stream.pressure_psia,
        level_ft: stream.level_ft,
      }, overrides));
    }
  }

  SugarStream._properties = { bpeBrix, bpeHead, satSteamTemp, bpeTotal, getLatentHeat, getCp, specificGravity };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SugarStream;
  } else {
    root.SugarStream = SugarStream;
  }
})(typeof window !== 'undefined' ? window : globalThis);
