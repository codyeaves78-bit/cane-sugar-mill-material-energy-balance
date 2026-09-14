// Port of Crystallizer_and_Reheater.py — water-cooled crystallizer and
// hot-water reheater for low-grade (C) massecuite. Both are non-contact heat
// exchangers: cooling/heating water never mixes with the massecuite, so
// massecuite mass flow is conserved through each unit. Heat balance is
// sensible-heat only -- heat of crystallization of sucrose is small and
// neglected here.

(function (root) {
  'use strict';

  const _CP_WATER = 1.0;       // BTU/lb-F
  const _LB_PER_GAL_H2O = 8.34; // lb per US gallon of water

  class Crystallizer {
    constructor({ massecuite_in, massecuite_flow_lb_hr, masse_temp_out_deg_F = 120.0,
                  ml_purity_out = null, water_temp_in_deg_F = 85.0, water_temp_out_deg_F = 105.0,
                  name = 'Crystallizer' } = {}) {
      if (water_temp_out_deg_F <= water_temp_in_deg_F) {
        throw new Error(`Cooling water must leave hotter than it enters (${water_temp_in_deg_F}→${water_temp_out_deg_F}°F).`);
      }
      this.massecuite_in = massecuite_in;
      this.massecuite_flow_lb_hr = massecuite_flow_lb_hr;
      this.masse_temp_out_deg_F = masse_temp_out_deg_F;
      this.ml_purity_out = ml_purity_out;
      this.water_temp_in_deg_F = water_temp_in_deg_F;
      this.water_temp_out_deg_F = water_temp_out_deg_F;
      this.name = name;
    }

    get masse_temp_in_deg_F() { return this.massecuite_in.massecuite_temp; }

    get massecuite_out() {
      const ml_out = (this.ml_purity_out !== null && this.ml_purity_out !== undefined)
        ? this.ml_purity_out : this.massecuite_in.ml_purity;
      return this.massecuite_in.copy({ temp_F: this.masse_temp_out_deg_F, ml_purity: ml_out });
    }

    get crystal_growth_lb_hr() {
      const delta_pct = this.massecuite_out.crystal_content - this.massecuite_in.crystal_content;
      return this.massecuite_flow_lb_hr * delta_pct / 100.0;
    }

    get duty_btu_hr() {
      const dT = this.masse_temp_in_deg_F - this.masse_temp_out_deg_F;
      if (dT <= 0) {
        throw new Error(`Crystallizer outlet (${this.masse_temp_out_deg_F}°F) must be cooler than the inlet massecuite (${this.masse_temp_in_deg_F.toFixed(1)}°F).`);
      }
      return this.massecuite_flow_lb_hr * this.massecuite_in.specific_heat * dT;
    }

    get water_lb_hr() {
      return this.duty_btu_hr / (_CP_WATER * (this.water_temp_out_deg_F - this.water_temp_in_deg_F));
    }

    get water_gpm() { return this.water_lb_hr / (_LB_PER_GAL_H2O * 60); }

    properties() {
      return {
        masse_flow_lb_hr: this.massecuite_flow_lb_hr,
        masse_temp_in_F: this.masse_temp_in_deg_F,
        masse_temp_out_F: this.masse_temp_out_deg_F,
        ml_purity_in: this.massecuite_in.ml_purity,
        ml_purity_out: this.massecuite_out.ml_purity,
        crystal_content_in_pct: this.massecuite_in.crystal_content,
        crystal_content_out_pct: this.massecuite_out.crystal_content,
        crystal_growth_lb_hr: this.crystal_growth_lb_hr,
        duty_btu_hr: this.duty_btu_hr,
        water_temp_in_F: this.water_temp_in_deg_F,
        water_temp_out_F: this.water_temp_out_deg_F,
        water_lb_hr: this.water_lb_hr,
        water_gpm: this.water_gpm,
      };
    }
  }

  class Reheater {
    constructor({ massecuite_in, massecuite_flow_lb_hr, masse_temp_out_deg_F = 130.0,
                  ml_purity_out = null, water_temp_in_deg_F = 150.0, water_temp_out_deg_F = 135.0,
                  name = 'Reheater' } = {}) {
      if (water_temp_in_deg_F <= water_temp_out_deg_F) {
        throw new Error(`Heating water must enter hotter than it leaves (${water_temp_in_deg_F}→${water_temp_out_deg_F}°F).`);
      }
      this.massecuite_in = massecuite_in;
      this.massecuite_flow_lb_hr = massecuite_flow_lb_hr;
      this.masse_temp_out_deg_F = masse_temp_out_deg_F;
      this.ml_purity_out = ml_purity_out;
      this.water_temp_in_deg_F = water_temp_in_deg_F;
      this.water_temp_out_deg_F = water_temp_out_deg_F;
      this.name = name;
    }

    get masse_temp_in_deg_F() { return this.massecuite_in.massecuite_temp; }

    get massecuite_out() {
      const ml_out = (this.ml_purity_out !== null && this.ml_purity_out !== undefined)
        ? this.ml_purity_out : this.massecuite_in.ml_purity;
      return this.massecuite_in.copy({ temp_F: this.masse_temp_out_deg_F, ml_purity: ml_out });
    }

    get duty_btu_hr() {
      const dT = this.masse_temp_out_deg_F - this.masse_temp_in_deg_F;
      if (dT <= 0) {
        throw new Error(`Reheater outlet (${this.masse_temp_out_deg_F}°F) must be hotter than the inlet massecuite (${this.masse_temp_in_deg_F.toFixed(1)}°F).`);
      }
      return this.massecuite_flow_lb_hr * this.massecuite_in.specific_heat * dT;
    }

    get water_lb_hr() {
      return this.duty_btu_hr / (_CP_WATER * (this.water_temp_in_deg_F - this.water_temp_out_deg_F));
    }

    get water_gpm() { return this.water_lb_hr / (_LB_PER_GAL_H2O * 60); }

    properties() {
      return {
        masse_flow_lb_hr: this.massecuite_flow_lb_hr,
        masse_temp_in_F: this.masse_temp_in_deg_F,
        masse_temp_out_F: this.masse_temp_out_deg_F,
        ml_purity_out: this.massecuite_out.ml_purity,
        duty_btu_hr: this.duty_btu_hr,
        water_temp_in_F: this.water_temp_in_deg_F,
        water_temp_out_F: this.water_temp_out_deg_F,
        water_lb_hr: this.water_lb_hr,
        water_gpm: this.water_gpm,
      };
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Crystallizer, Reheater };
  } else {
    root.Crystallizer = Crystallizer;
    root.Reheater = Reheater;
  }
})(typeof window !== 'undefined' ? window : globalThis);
