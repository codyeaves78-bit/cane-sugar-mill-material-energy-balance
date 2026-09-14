// English-unit wrapper around IAPWS97, mirroring Python's SteamStream class
// (SteamStream.py) property-for-property so the rest of the JS port reads
// exactly like the Python domain classes it's replacing.
//
// Pass any 2 of {T (F), P (psia), h (BTU/lb), s (BTU/lb-R), x (0-1)}.

(function (root) {
  'use strict';

  const IAPWS97 = (typeof module !== 'undefined' && module.exports) ? require('./iapws97.js') : root.IAPWS97;
  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;
  const { satSteamTemp, getLatentHeat } = SugarStream._properties;

  const MPA_PER_PSIA = 0.00689476;
  const KJKG_PER_BTULB = 2.326;
  const KJKGK_PER_BTULBR = 4.1868;
  const M3KG_PER_FT3LB = 1 / 16.0185; // ft3/lb -> m3/kg

  const fToK = (f) => (f - 32) * 5 / 9 + 273.15;
  const kToF = (k) => (k - 273.15) * 9 / 5 + 32;
  const psiaToMpa = (p) => p * MPA_PER_PSIA;
  const mpaToPsia = (p) => p / MPA_PER_PSIA;
  const btuLbToKjKg = (h) => h * KJKG_PER_BTULB;
  const kjKgToBtuLb = (h) => h / KJKG_PER_BTULB;
  const btuLbRToKjKgK = (s) => s * KJKGK_PER_BTULBR;
  const kjKgKToBtuLbR = (s) => s / KJKGK_PER_BTULBR;
  const m3KgToFt3Lb = (v) => v / M3KG_PER_FT3LB;

  class SteamStream {
    constructor({ T, P, h, s, x, flow_lb_per_hr = 0 } = {}) {
      this.flow_lb_per_hr = flow_lb_per_hr;
      this._definingParams = { T, P, h, s, x };
      this._state = SteamStream._buildState({ T, P, h, s, x });
    }

    static _buildState({ T, P, h, s, x }) {
      const kwargs = {};
      if (T !== undefined) kwargs.T = fToK(T);
      if (P !== undefined) kwargs.P = psiaToMpa(P);
      if (h !== undefined) kwargs.h = btuLbToKjKg(h);
      if (s !== undefined) kwargs.s = btuLbRToKjKgK(s);
      if (x !== undefined) kwargs.x = x;
      return IAPWS97.solve(kwargs);
    }

    update({ T, P, h, s, x } = {}) {
      this._state = SteamStream._buildState({ T, P, h, s, x });
    }

    get T() { return kToF(this._state.T); }
    get P() { return mpaToPsia(this._state.P); }
    get h() { return kjKgToBtuLb(this._state.h); }
    get s() { return kjKgKToBtuLbR(this._state.s); }
    get x() { return this._state.x; }
    get v() { return m3KgToFt3Lb(this._state.v); }
    get rho() { return 1 / this.v; }

    get h_fg() {
      const satLiq = IAPWS97.solve({ P: this._state.P, x: 0 });
      const satVap = IAPWS97.solve({ P: this._state.P, x: 1 });
      return kjKgToBtuLb(satVap.h - satLiq.h);
    }

    get is_superheated() {
      const satVap = IAPWS97.solve({ P: this._state.P, x: 1 });
      const satTempF = kToF(satVap.T);
      return this.T > satTempF + 0.01;
    }

    properties() {
      return {
        flow_lb_per_hr: this.flow_lb_per_hr,
        T: this.T, P: this.P, h: this.h, s: this.s, x: this.x,
        v: this.v, rho: this.rho, h_fg: this.h_fg,
        is_superheated: this.is_superheated,
      };
    }
  }

  // A simpler steam stream class specifically for evaporator/pan trial-and-error
  // calculations, built for speed (fast polynomial correlations, not full
  // IAPWS97) -- mirrors Python's EvaporatorSteam, also defined in SteamStream.py.
  // Only valid for 1-60 psia, same range as the sugar_stream_properties.py
  // correlations it wraps.
  class EvaporatorSteam {
    constructor(P_psia = 14.7, flow_lb_per_hr = 0) {
      this.P_psia = P_psia;
      this.flow_lb_per_hr = flow_lb_per_hr;
    }

    get sat_temp_deg_F() { return satSteamTemp(this.P_psia); }
    get h_fg() { return getLatentHeat(this.P_psia); }

    properties() {
      return { P_psia: this.P_psia, flow_lb_per_hr: this.flow_lb_per_hr, sat_temp_deg_F: this.sat_temp_deg_F, h_fg: this.h_fg };
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SteamStream;
    module.exports.EvaporatorSteam = EvaporatorSteam;
  } else {
    root.SteamStream = SteamStream;
    root.EvaporatorSteam = EvaporatorSteam;
  }
})(typeof window !== 'undefined' ? window : globalThis);
