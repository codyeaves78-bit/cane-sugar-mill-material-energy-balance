// Port of JuiceHeatingStation.py — arranges JuiceHeaterShellTube units in
// SERIES or PARALLEL and solves the train. The heat transfer math itself
// lives in JuiceHeaterShellTube (juice_heater.js); this class only wires
// the cold streams together (chained outlet->inlet for series, flow split
// for parallel), then reports totals. Display/PFD/Excel export methods are
// not ported (offline HTML app has its own UI for that).

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;
  const SteamStream = (typeof module !== 'undefined' && module.exports) ? require('./steam_stream.js') : root.SteamStream;
  const JuiceHeaterShellTube = (typeof module !== 'undefined' && module.exports) ? require('./juice_heater.js') : root.JuiceHeaterShellTube;
  const condensate_utils = (typeof module !== 'undefined' && module.exports) ? require('./condensate_utils.js') : root.condensate_utils;

  class JuiceHeatingStation {
    constructor({
      cold_stream,
      heaters,
      mode = 'series',
      split_pcts = null,
      name = 'Juice Heating Station',
    } = {}) {
      mode = mode.toLowerCase();
      if (mode !== 'series' && mode !== 'parallel') {
        throw new Error(`mode must be 'series' or 'parallel', got '${mode}'`);
      }
      this.name = name;
      this.mode = mode;
      this.cold_stream = cold_stream;
      this._heater_cfgs = heaters;

      if (mode === 'parallel') {
        const n = heaters.length;
        this.split_pcts = split_pcts !== null ? split_pcts : Array(n).fill(100.0 / n);
        if (this.split_pcts.length !== n) {
          throw new Error('split_pcts must have one entry per heater');
        }
        const total = this.split_pcts.reduce((a, b) => a + b, 0);
        if (Math.abs(total - 100.0) > 0.01) {
          throw new Error(`split_pcts must sum to 100, got ${total}`);
        }
      } else {
        this.split_pcts = null;
      }

      this._solve();
    }

    // Fresh SteamStream at the same conditions, so each solved heater
    // stamps its steam requirement onto its OWN stream (JuiceHeater sets
    // hot_stream.flow_lb_per_hr at construction).
    static _copy_steam(s) {
      if (s.x !== null && s.x !== undefined && s.x >= 0 && s.x <= 1) {
        return new SteamStream({ P: s.P, x: s.x });
      }
      return new SteamStream({ P: s.P, T: s.T });
    }

    // Fresh SteamStream at a new pressure, keeping the same quality (if
    // saturated) or temperature (if superheated) as the original.
    static _repressure_steam(old, P) {
      if (old.x !== null && old.x !== undefined && old.x >= 0 && old.x <= 1) {
        return new SteamStream({ P, x: old.x });
      }
      return new SteamStream({ P, T: old.T });
    }

    // Update the steam pressure for every heater on a given steam_type
    // (0=Exhaust, 1=V1, 2=V2, 3=V3, 4=V4) and resolve the station.
    set_steam_pressure(steam_type, P) {
      let matched = false;
      this._heater_cfgs.forEach((cfg) => {
        if (cfg.steam_type === steam_type) {
          cfg.hot_stream = JuiceHeatingStation._repressure_steam(cfg.hot_stream, P);
          matched = true;
        }
      });
      if (!matched) throw new Error(`no heaters found with steam_type=${steam_type}`);
      this._solve();
    }

    _rebuild(cfg, cold) {
      return new JuiceHeaterShellTube({
        cold_stream: cold,
        hot_stream: JuiceHeatingStation._copy_steam(cfg.hot_stream),
        name: cfg.name,
        juice_out_temp_degF: cfg.juice_out_temp_degF,
        U_btu_per_ft2_degF: cfg.U,
        installed_area_ft2: cfg.installed_area_ft2,
        steam_type: cfg.steam_type,
      });
    }

    _solve() {
      this.heaters = [];
      if (this.mode === 'series') {
        let cold = this.cold_stream;
        this._heater_cfgs.forEach((cfg) => {
          const heater = this._rebuild(cfg, cold);
          this.heaters.push(heater);
          cold = heater.juice_out;
        });
        this.juice_out = this.heaters[this.heaters.length - 1].juice_out;
      } else {
        this._heater_cfgs.forEach((cfg, i) => {
          const pct = this.split_pcts[i];
          const split = SugarStream.copy(this.cold_stream);
          split.flow_lb_per_hr = (pct / 100) * this.cold_stream.flow_lb_per_hr;
          this.heaters.push(this._rebuild(cfg, split));
        });
        // combined hot juice: total flow at the mass-weighted blend temp
        const total = this.heaters.reduce((sum, h) => sum + h.juice_out.flow_lb_per_hr, 0);
        const blend = this.heaters.reduce((sum, h) => sum + h.juice_out.flow_lb_per_hr * h.juice_out.temp_deg_F, 0) / total;
        const out = SugarStream.copy(this.cold_stream);
        out.flow_lb_per_hr = total;
        out.temp_deg_F = blend;
        this.juice_out = out;
      }
    }

    get total_steam_lb_hr() {
      return this.heaters.reduce((sum, h) => sum + h.steam_required_lb_per_hr, 0);
    }

    _steam_demand_lb_hr(steam_type) {
      return this.heaters
        .filter((h) => h.steam_type === steam_type)
        .reduce((sum, h) => sum + h.steam_required_lb_per_hr, 0);
    }

    get total_exhaust_steam_lb_hr() {
      return this._steam_demand_lb_hr(0);
    }

    get total_V1_steam_lb_hr() {
      return this._steam_demand_lb_hr(1);
    }

    get total_V2_steam_lb_hr() {
      return this._steam_demand_lb_hr(2);
    }

    get total_V3_steam_lb_hr() {
      return this._steam_demand_lb_hr(3);
    }

    get total_V4_steam_lb_hr() {
      return this._steam_demand_lb_hr(4);
    }

    get clean_condensate() {
      return this.heaters
        .filter((h) => h.steam_type === 0)
        .reduce((sum, h) => sum + condensate_utils.flash_condensate(h.steam_required_lb_per_hr, h.hot_stream.T), 0);
    }

    get dirty_condensate() {
      return this.heaters
        .filter((h) => h.steam_type !== 0)
        .reduce((sum, h) => sum + condensate_utils.flash_condensate(h.steam_required_lb_per_hr, h.hot_stream.T), 0);
    }

    get total_duty_btu_hr() {
      return this.heaters.reduce((sum, h) => sum + h.Q_btu_per_hr, 0);
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = JuiceHeatingStation;
  } else {
    root.JuiceHeatingStation = JuiceHeatingStation;
  }
})(typeof window !== 'undefined' ? window : globalThis);
