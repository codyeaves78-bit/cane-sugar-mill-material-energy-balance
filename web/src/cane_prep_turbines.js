// Port of CanePrepTurbines.py — solves the cane preparation drive turbines
// (shredders and knives) from the input lists and a fiber rate. Units with
// 0 HP/TFH are skipped in the display (handled by the caller).

(function (root) {
  'use strict';

  const Turbine = (typeof module !== 'undefined' && module.exports) ? require('./turbine.js') : root.Turbine;

  const DEFAULT_NAMES = ['Shredder', 'Knife 1', 'Knife 2', 'Knife 3'];

  class CanePrepTurbines {
    constructor({ hp_ton_fiber_hr, isentropic_efficiency, live_steam_object, exhaust_psia, tons_fiber_hr, name_list = null }) {
      if (isentropic_efficiency.length !== hp_ton_fiber_hr.length) {
        throw new Error(
          `isentropic_efficiency has ${isentropic_efficiency.length} entries ` +
          `but hp_ton_fiber_hr has ${hp_ton_fiber_hr.length} -- they must match`
        );
      }
      this.tons_fiber_hr = tons_fiber_hr;

      const namesSrc = name_list !== null ? name_list : DEFAULT_NAMES;
      const names = hp_ton_fiber_hr.map((_, i) => (i < namesSrc.length ? namesSrc[i] : `Unit ${i + 1}`));

      this.cane_prep_turbines = {
        hp_ton_fiber_hr,
        isentropic_efficiency,
        live_steam_object,
        exhaust_psia,
        name_list: names,
        hp_list: hp_ton_fiber_hr.map((hptf) => hptf * tons_fiber_hr),
      };

      this.turbines = this.cane_prep_turbines.hp_list.map((hp, i) => new Turbine({
        inlet_steam: this.cane_prep_turbines.live_steam_object,
        outlet_pressure_psia: this.cane_prep_turbines.exhaust_psia,
        isentropic_efficiency: this.cane_prep_turbines.isentropic_efficiency[i] / 100,
        hp_demand: hp,
        name: this.cane_prep_turbines.name_list[i],
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
    module.exports = CanePrepTurbines;
  } else {
    root.CanePrepTurbines = CanePrepTurbines;
  }
})(typeof window !== 'undefined' ? window : globalThis);
