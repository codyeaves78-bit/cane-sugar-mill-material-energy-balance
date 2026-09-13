// Port of JuiceHeater.py's JuiceHeaterShellTube — a shell & tube juice
// heater. Display/PFD/Excel export methods are not ported (offline HTML
// app has its own UI for that); the calculation properties mirror the
// Python class name-for-name.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;

  class JuiceHeaterShellTube {
    constructor({
      cold_stream,
      hot_stream,
      name = 'Heater',
      juice_out_temp_degF = 220,
      U_btu_per_ft2_degF = 220,
      installed_area_ft2 = 22000,
      steam_type = 0, // 0 = Exh, 1 = V1, 2 = V2, 3 = V3, 4 = V4
    } = {}) {
      this.name = name;
      this.U = U_btu_per_ft2_degF;
      this.cold_stream = cold_stream;
      this.hot_stream = hot_stream;
      this.juice_out_temp_degF = juice_out_temp_degF;
      this.installed_area_ft2 = installed_area_ft2;
      this.steam_type = steam_type;

      this.juice_out = new SugarStream({
        brix: this.cold_stream.brix,
        purity: this.cold_stream.purity,
        flow_lb_per_hr: this.cold_stream.flow_lb_per_hr,
        temp_deg_F: this.juice_out_temp_degF,
        pressure_psia: this.cold_stream.pressure_psia,
        level_ft: this.cold_stream.level_ft,
      });

      // Stamp the required steam flow onto the supply stream so downstream
      // code can read hot_stream.flow_lb_per_hr directly. NOTE: if one
      // SteamStream object is shared by several heaters, the last heater
      // constructed wins -- give each heater its own SteamStream.
      this.hot_stream.flow_lb_per_hr = this.steam_required_lb_per_hr;
    }

    get cold_delta_T() {
      return this.juice_out_temp_degF - this.cold_stream.temp_deg_F;
    }

    get Q_btu_per_hr() {
      return this.cold_stream.flow_lb_per_hr * this.cold_stream.cp_btu_per_lb_deg_F * this.cold_delta_T;
    }

    get LMTD_degF() {
      const delta_T1 = this.hot_stream.T - this.cold_stream.temp_deg_F;
      const delta_T2 = this.hot_stream.T - this.juice_out_temp_degF;
      if (delta_T1 === delta_T2) return delta_T1;
      return (delta_T1 - delta_T2) / Math.log(delta_T1 / delta_T2);
    }

    get required_area_ft2() {
      return this.Q_btu_per_hr / (this.U * this.LMTD_degF);
    }

    get steam_required_lb_per_hr() {
      return this.Q_btu_per_hr / this.hot_stream.h_fg;
    }

    get is_steam_hot_enough() {
      if (this.hot_stream.T <= this.juice_out_temp_degF) {
        return `NO! Steam temp (${this.hot_stream.T.toFixed(2)} °F) <= juice out temperature (${this.juice_out_temp_degF} °F).`;
      }
      return 'YES';
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = JuiceHeaterShellTube;
  } else {
    root.JuiceHeaterShellTube = JuiceHeaterShellTube;
  }
})(typeof window !== 'undefined' ? window : globalThis);
