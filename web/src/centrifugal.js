// Port of Centrifugal.py — centrifugal separator, SJM (Sugar-Massecuite-
// Molasses) material balance. Two-step approach: (1) SJM ideal split with
// specified S, J, M0; (2) crystal loss as 100%-pol sucrose fragments dissolve
// into molasses, updating M; (3) final SJM with updated M.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;

  const _GAL_PER_FT3 = 7.48052; // US gallons per cubic foot

  function _sugarDensityLbFt3(brix, temp_F = 77.0) {
    const rho_20C = 0.99823 + 3.848e-3 * brix + 1.427e-5 * brix ** 2 + 1.5e-8 * brix ** 3;
    const temp_C = (temp_F - 32) * 5 / 9;
    return rho_20C * (1 - 4.1e-4 * (temp_C - 20)) * 62.428;
  }

  class Centrifugal {
    constructor({ massecuite, massecuite_flow_lb_hr, target_molasses_brix = 85.0,
                  purity_rise = 2.0, sugar_purity = 99.5, sugar_moisture = 0.5,
                  name = 'Centrifugal', sugar_temp = 155, molasses_temp = 155 } = {}) {
      this.massecuite = massecuite;
      this.massecuite_flow_lb_hr = massecuite_flow_lb_hr;
      this.target_molasses_brix = target_molasses_brix;
      this.purity_rise = purity_rise;
      this.sugar_purity = sugar_purity;
      this.sugar_moisture = sugar_moisture;
      this.name = name;
      this.sugar_temp = sugar_temp;
      this.molasses_temp = molasses_temp;
    }

    // ------------------------------------------------------------------
    // SJM balance (S = sugar_purity, J = masse_purity, M = molasses_purity)
    // ------------------------------------------------------------------

    get massecuite_solids_lb_hr() {
      return this.massecuite_flow_lb_hr * this.massecuite.masse_brix / 100.0;
    }

    get molasses_purity() {
      return this.massecuite.ml_purity + this.purity_rise;
    }

    get crystals_to_sugar_lb_hr() {
      const S = this.sugar_purity;
      const J = this.massecuite.masse_purity;
      const M = this.molasses_purity;
      return this.massecuite_solids_lb_hr * (J - M) / (S - M);
    }

    // ------------------------------------------------------------------
    // Sugar product
    // ------------------------------------------------------------------

    get sugar_wet_lb_hr() {
      return this.crystals_to_sugar_lb_hr / (1.0 - this.sugar_moisture / 100.0);
    }

    get sugar_moisture_lb_hr() {
      return this.sugar_wet_lb_hr - this.crystals_to_sugar_lb_hr;
    }

    get sugar_brix() { return 100.0 - this.sugar_moisture; }

    get sugar_pol_lb_hr() {
      return this.crystals_to_sugar_lb_hr * this.sugar_purity / 100.0;
    }

    // ------------------------------------------------------------------
    // Molasses balance
    // ------------------------------------------------------------------

    get pol_in_lb_hr() {
      return this.massecuite_solids_lb_hr * this.massecuite.masse_purity / 100.0;
    }

    get molasses_solids_lb_hr() {
      return this.massecuite_solids_lb_hr - this.crystals_to_sugar_lb_hr;
    }

    get molasses_brix() { return this.target_molasses_brix; }

    get molasses_flow_lb_hr() {
      return this.molasses_solids_lb_hr / (this.target_molasses_brix / 100.0);
    }

    get wash_water_lb_hr() {
      const ww = this.molasses_flow_lb_hr + this.sugar_wet_lb_hr - this.massecuite_flow_lb_hr;
      if (ww < 0) {
        const naturalBrix = this.molasses_solids_lb_hr / (this.massecuite_flow_lb_hr - this.sugar_wet_lb_hr) * 100;
        throw new Error(
          `target_molasses_brix (${this.target_molasses_brix.toFixed(1)}) is higher than the natural ` +
          `molasses Brix without wash water (${naturalBrix.toFixed(1)}). ` +
          'Lower the target or set it to None to skip washing.'
        );
      }
      return ww;
    }

    get pol_to_sugar_lb_hr() { return this.sugar_pol_lb_hr; }

    get pol_to_molasses_lb_hr() { return this.pol_in_lb_hr - this.pol_to_sugar_lb_hr; }

    get molasses_density_lb_ft3() { return _sugarDensityLbFt3(this.molasses_brix, 77.0); }

    get molasses_density_lb_gal() { return this.molasses_density_lb_ft3 / _GAL_PER_FT3; }

    get molasses_flow_gal_min() { return this.molasses_flow_lb_hr / (this.molasses_density_lb_gal * 60.0); }

    get sugar_pol() { return this.sugar_pol_lb_hr / this.sugar_wet_lb_hr * 100; }

    // ------------------------------------------------------------------
    // Crystal yield
    // ------------------------------------------------------------------

    get station_crystal_yield_pct_brix() {
      const J = this.massecuite.masse_purity;
      const M = this.molasses_purity;
      return 100.0 * (J - M) / (100.0 - M);
    }

    get station_crystal_yield_pct_masse() {
      return this.station_crystal_yield_pct_brix * this.massecuite.masse_brix / 100.0;
    }

    // ------------------------------------------------------------------
    // Output streams
    // ------------------------------------------------------------------

    get sugar_stream() {
      return new SugarStream({
        brix: this.sugar_brix,
        purity: this.sugar_purity,
        flow_lb_per_hr: this.sugar_wet_lb_hr,
        temp_deg_F: this.sugar_temp,
        pressure_psia: 14.7,
        level_ft: 0,
      });
    }

    get molasses_stream() {
      return new SugarStream({
        brix: this.molasses_brix,
        purity: this.molasses_purity,
        flow_lb_per_hr: this.molasses_flow_lb_hr,
        temp_deg_F: this.molasses_temp,
        pressure_psia: 14.7,
        level_ft: 0,
      });
    }

    // ------------------------------------------------------------------
    // Dict outputs
    // ------------------------------------------------------------------

    get sugar() {
      return {
        flow_wet_lb_hr: this.sugar_wet_lb_hr,
        flow_dry_lb_hr: this.crystals_to_sugar_lb_hr,
        pol_lb_hr: this.sugar_pol_lb_hr,
        purity_pct: this.sugar_purity,
        moisture_pct: this.sugar_moisture,
      };
    }

    get molasses() {
      return {
        flow_lb_hr: this.molasses_flow_lb_hr,
        brix: this.molasses_brix,
        purity: this.molasses_purity,
        pol_lb_hr: this.pol_to_molasses_lb_hr,
      };
    }

    properties() {
      return {
        massecuite_flow_lb_hr: this.massecuite_flow_lb_hr,
        masse_brix: this.massecuite.masse_brix,
        masse_purity: this.massecuite.masse_purity,
        ml_purity: this.massecuite.ml_purity,
        sugar_purity_pct: this.sugar_purity,
        molasses_purity_target: this.molasses_purity,
        purity_rise: this.purity_rise,
        target_molasses_brix: this.target_molasses_brix,
        wash_water_lb_hr: this.wash_water_lb_hr,
        sugar_solids_lb_hr: this.crystals_to_sugar_lb_hr,
        sugar_moisture_pct: this.sugar_moisture,
        sugar_wet_lb_hr: this.sugar_wet_lb_hr,
        sugar_moisture_lb_hr: this.sugar_moisture_lb_hr,
        sugar_pol_lb_hr: this.sugar_pol_lb_hr,
        pol_in_lb_hr: this.pol_in_lb_hr,
        pol_to_sugar_lb_hr: this.pol_to_sugar_lb_hr,
        pol_to_molasses_lb_hr: this.pol_to_molasses_lb_hr,
        molasses_flow_lb_hr: this.molasses_flow_lb_hr,
        molasses_brix: this.molasses_brix,
        molasses_purity: this.molasses_purity,
        station_crystal_yield_pct_brix: this.station_crystal_yield_pct_brix,
        station_crystal_yield_pct_masse: this.station_crystal_yield_pct_masse,
      };
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Centrifugal;
  } else {
    root.Centrifugal = Centrifugal;
  }
})(typeof window !== 'undefined' ? window : globalThis);
