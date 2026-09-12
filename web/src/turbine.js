// Port of Turbine.py — isentropic steam turbine with efficiency correction.
// HP demand drives the required steam flow calculation.
//
// Thermodynamic process:
//   1. Ideal:   expand isentropically (s_out = s_in) to outlet pressure -> h_out_isen
//   2. Actual:  h_out = h_in - eta * (h_in - h_out_isen)
//   3. Flow:    m_dot = hp_demand * 2545 BTU/HP-hr / (h_in - h_out)
//   4. Exhaust: SteamStream(P=outlet_pressure_psia, h=h_out, flow=m_dot)

(function (root) {
  'use strict';

  const IAPWS97 = (typeof module !== 'undefined' && module.exports) ? require('./iapws97.js') : root.IAPWS97;
  const SteamStream = (typeof module !== 'undefined' && module.exports) ? require('./steam_stream.js') : root.SteamStream;

  const BTU_PER_HP_HR = 2545.0;
  const PSIA_TO_MPA = 0.00689476;
  const KJ_KG_TO_BTU_LB = 1 / 2.326;
  const BTU_LB_R_TO_KJ_KG_K = 4.1868;

  class Turbine {
    constructor({
      inlet_steam,
      outlet_pressure_psia,
      isentropic_efficiency,
      hp_demand,
      name = 'Turbine',
      desuperheating_water_temp = 212,
    }) {
      if (!(isentropic_efficiency > 0 && isentropic_efficiency <= 1)) {
        throw new Error(`Isentropic efficiency must be between 0 and 1, got ${isentropic_efficiency}`);
      }
      this.inlet_steam = inlet_steam;
      this.outlet_pressure_psia = outlet_pressure_psia;
      this.isentropic_efficiency = isentropic_efficiency;
      this.hp_demand = hp_demand;
      this.name = name;
      this.desuperheating_water_temp = desuperheating_water_temp;
    }

    get h_in() {
      return this.inlet_steam.h;
    }

    get s_in() {
      return this.inlet_steam.s;
    }

    get h_out_isentropic() {
      const s_si = this.s_in * BTU_LB_R_TO_KJ_KG_K;
      const P_si = this.outlet_pressure_psia * PSIA_TO_MPA;
      const state = IAPWS97.solve({ P: P_si, s: s_si });
      return state.h * KJ_KG_TO_BTU_LB;
    }

    get h_out_actual() {
      return this.h_in - this.isentropic_efficiency * (this.h_in - this.h_out_isentropic);
    }

    get work_per_lb() {
      return this.h_in - this.h_out_actual;
    }

    get steam_flow_lb_hr() {
      return (this.hp_demand * BTU_PER_HP_HR) / this.work_per_lb;
    }

    get steam_rate() {
      return BTU_PER_HP_HR / this.work_per_lb;
    }

    get exhaust_steam() {
      return new SteamStream({
        P: this.outlet_pressure_psia,
        h: this.h_out_actual,
        flow_lb_per_hr: this.steam_flow_lb_hr,
      });
    }

    get exhaust_available() {
      const exhaust = this.exhaust_steam;
      const sat_exhaust_h = new SteamStream({ P: this.outlet_pressure_psia, x: 1 }).h;
      if (exhaust.h === sat_exhaust_h) {
        return exhaust.flow_lb_per_hr;
      } else if (exhaust.h > sat_exhaust_h) {
        const h_to_sat = exhaust.h - sat_exhaust_h;
        const water_h = new SteamStream({ P: this.outlet_pressure_psia, T: this.desuperheating_water_temp }).h;
        const btu_1_lb_water = sat_exhaust_h - water_h;
        const water_lb_hr = (h_to_sat * exhaust.flow_lb_per_hr) / btu_1_lb_water;
        return exhaust.flow_lb_per_hr + water_lb_hr;
      } else {
        return exhaust.flow_lb_per_hr * exhaust.x;
      }
    }

    properties() {
      const exhaust = this.exhaust_steam;
      return {
        inlet_pressure_psia: this.inlet_steam.P,
        inlet_temp_F: this.inlet_steam.T,
        inlet_enthalpy_btu_lb: this.h_in,
        inlet_entropy_btu_lb_R: this.s_in,
        outlet_pressure_psia: this.outlet_pressure_psia,
        outlet_temp_F: exhaust.T,
        outlet_enthalpy_btu_lb: this.h_out_actual,
        outlet_quality: exhaust.x,
        h_out_isentropic_btu_lb: this.h_out_isentropic,
        isentropic_efficiency: this.isentropic_efficiency,
        work_per_lb_btu: this.work_per_lb,
        hp_demand: this.hp_demand,
        steam_flow_lb_hr: this.steam_flow_lb_hr,
        steam_rate_lb_per_hp_hr: this.steam_rate,
        exhaust_available: this.exhaust_available,
      };
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Turbine;
  } else {
    root.Turbine = Turbine;
  }
})(typeof window !== 'undefined' ? window : globalThis);
