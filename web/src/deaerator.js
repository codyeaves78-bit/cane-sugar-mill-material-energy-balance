// Port of Deaerator.py — deaerator energy and mass balance. Incoming cold
// water is heated to saturation at deaerator pressure by condensing live
// steam; vent loss is applied to the steam requirement.

(function (root) {
  'use strict';

  const SteamStream = (typeof module !== 'undefined' && module.exports) ? require('./steam_stream.js') : root.SteamStream;

  class Deaerator {
    constructor({ deaerator_psig = 10, water_in_deg_F = 200, water_in_lb_hr = 100, vent_pct = 1.0 } = {}) {
      this.psia = deaerator_psig + 14.696;
      this.water_in_deg_F = water_in_deg_F;
      this.water_in_lb_hr = water_in_lb_hr;
      this.vent_pct = vent_pct;
    }

    get _steam_state() {
      return new SteamStream({ x: 1, P: this.psia });
    }

    get _water_out_state() {
      return new SteamStream({ x: 0, P: this.psia });
    }

    get _water_in_state() {
      return new SteamStream({ x: 0, T: this.water_in_deg_F });
    }

    get steam_flow_lb_hr() {
      const Q_sens = this.water_in_lb_hr * (this._water_out_state.h - this._water_in_state.h);
      const steam_net = Q_sens / this._steam_state.h_fg;
      return steam_net / (1 - this.vent_pct / 100);
    }

    get vent_flow_lb_hr() {
      return (this.steam_flow_lb_hr * this.vent_pct) / 100;
    }

    get water_out_flow_lb_hr() {
      return this.water_in_lb_hr + this.steam_flow_lb_hr - this.vent_flow_lb_hr;
    }

    get steam_in() {
      const s = new SteamStream({ x: 1, P: this.psia });
      s.flow_lb_per_hr = this.steam_flow_lb_hr;
      return s;
    }

    get water_in() {
      const s = new SteamStream({ x: 0, T: this.water_in_deg_F });
      s.flow_lb_per_hr = this.water_in_lb_hr;
      return s;
    }

    get water_out() {
      const s = new SteamStream({ x: 0, P: this.psia });
      s.flow_lb_per_hr = this.water_out_flow_lb_hr;
      return s;
    }

    get vent() {
      const s = new SteamStream({ x: 1, P: 14.696 });
      s.flow_lb_per_hr = this.vent_flow_lb_hr;
      return s;
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Deaerator;
  } else {
    root.Deaerator = Deaerator;
  }
})(typeof window !== 'undefined' ? window : globalThis);
