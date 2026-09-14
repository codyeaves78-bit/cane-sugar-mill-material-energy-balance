// Port of AuxillaryTurbines.py — solves the auxillary drive turbines
// (ID fans, pumps, etc.) from the input lists. Units with 0 HP are skipped
// in the display (handled by the caller).

(function (root) {
  'use strict';

  const Turbine = (typeof module !== 'undefined' && module.exports) ? require('./turbine.js') : root.Turbine;

  class AuxillaryTurbines {
    constructor({ group_name, name_list, hp_list, isentropic_efficiency, live_steam_object, exhaust_psia }) {
      if (name_list.length !== hp_list.length) {
        throw new Error(
          `name_list has ${name_list.length} entries but hp_list has ${hp_list.length} -- they must match`
        );
      }
      if (isentropic_efficiency.length !== hp_list.length) {
        throw new Error(
          `isentropic_efficiency has ${isentropic_efficiency.length} entries ` +
          `but hp_list has ${hp_list.length} -- they must match`
        );
      }

      this.group_name = group_name;

      this.auxillary_turbines = {
        name_list,
        isentropic_efficiency,
        live_steam_object,
        exhaust_psia,
        hp_list,
      };

      this.turbines = hp_list.map((hp, i) => new Turbine({
        inlet_steam: this.auxillary_turbines.live_steam_object,
        outlet_pressure_psia: this.auxillary_turbines.exhaust_psia,
        isentropic_efficiency: this.auxillary_turbines.isentropic_efficiency[i] / 100,
        hp_demand: hp,
        name: this.auxillary_turbines.name_list[i],
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
    module.exports = AuxillaryTurbines;
  } else {
    root.AuxillaryTurbines = AuxillaryTurbines;
  }
})(typeof window !== 'undefined' ? window : globalThis);
