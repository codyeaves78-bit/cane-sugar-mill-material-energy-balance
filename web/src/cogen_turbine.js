// Port of CogenTurbine.py — identical thermodynamics to Turbine, but sized by
// electrical (generator) output in kW instead of mechanical shaft horsepower.

(function (root) {
  'use strict';

  const Turbine = (typeof module !== 'undefined' && module.exports) ? require('./turbine.js') : root.Turbine;

  const KW_PER_HP = 0.7456998715822702; // 1 mechanical HP = 0.7456998715822702 kW

  class CogenTurbine extends Turbine {
    constructor({
      inlet_steam,
      outlet_pressure_psia,
      isentropic_efficiency,
      kw_demand,
      name = 'Cogen Turbine',
      desuperheating_water_temp = 212,
    }) {
      super({
        inlet_steam,
        outlet_pressure_psia,
        isentropic_efficiency,
        hp_demand: kw_demand / KW_PER_HP,
        name,
        desuperheating_water_temp,
      });
    }

    get kw_output() {
      return this.hp_demand * KW_PER_HP;
    }

    get steam_rate_kw() {
      return this.steam_flow_lb_hr / this.kw_output;
    }

    properties() {
      const props = super.properties();
      props.kw_output = this.kw_output;
      props.steam_rate_lb_per_kw_hr = this.steam_rate_kw;
      return props;
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = CogenTurbine;
  } else {
    root.CogenTurbine = CogenTurbine;
  }
})(typeof window !== 'undefined' ? window : globalThis);
