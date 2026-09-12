// Port of MillTurbines.py — solves a set of mill drive turbines from the
// input lists and a fiber rate, then reports them side by side.

(function (root) {
  'use strict';

  const Turbine = (typeof module !== 'undefined' && module.exports) ? require('./turbine.js') : root.Turbine;

  class MillTurbines {
    constructor({ hp_ton_fiber_hr, isentropic_efficiency, live_steam_object, exhaust_psia, tons_fiber_hr }) {
      if (isentropic_efficiency.length !== hp_ton_fiber_hr.length) {
        throw new Error(
          `isentropic_efficiency has ${isentropic_efficiency.length} entries ` +
          `but hp_ton_fiber_hr has ${hp_ton_fiber_hr.length} -- they must match`
        );
      }
      this.tons_fiber_hr = tons_fiber_hr;

      this.mill_turbines = {
        hp_ton_fiber_hr,
        isentropic_efficiency,
        live_steam_object,
        exhaust_psia,
        hp_list: hp_ton_fiber_hr.map((hptf) => hptf * tons_fiber_hr),
      };

      this.turbines = this.mill_turbines.hp_list.map((hp, i) => new Turbine({
        inlet_steam: this.mill_turbines.live_steam_object,
        outlet_pressure_psia: this.mill_turbines.exhaust_psia,
        isentropic_efficiency: this.mill_turbines.isentropic_efficiency[i] / 100,
        hp_demand: hp,
        name: `Mill ${i + 1}`,
      }));
    }

    get total_hp() {
      return this.turbines.reduce((s, t) => s + t.hp_demand, 0);
    }

    get total_inlet_flow_lb_hr() {
      return this.turbines.reduce((s, t) => s + t.steam_flow_lb_hr, 0);
    }

    get total_exhaust_available_lb_hr() {
      return this.turbines.reduce((s, t) => s + t.exhaust_available, 0);
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MillTurbines;
  } else {
    root.MillTurbines = MillTurbines;
  }
})(typeof window !== 'undefined' ? window : globalThis);
