// Port of Boiler.py — bagasse-fired boiler: feed water in, steam out, sized
// against the fuel value of the bagasse it burns.

(function (root) {
  'use strict';

  const SteamStream = (typeof module !== 'undefined' && module.exports) ? require('./steam_stream.js') : root.SteamStream;

  class Boiler {
    constructor({
      bagasse,
      efficiency = 70,
      pressure_psig = 180,
      deg_superheat = 0,
      feed_water_temp = 230,
      capacity = 0,
      name = 'Boiler #',
    }) {
      this.name = name;
      this.bagasse = bagasse;
      this.efficiency = efficiency;
      this.capacity = capacity;
      this.psia = pressure_psig + 14.696;
      this.deg_sh = deg_superheat;
      this.feed_wat_temp = feed_water_temp;
    }

    get feed_water_stream() {
      return new SteamStream({ T: this.feed_wat_temp, P: this.psia });
    }

    get steam_stream() {
      const sat_steam = new SteamStream({ P: this.psia, x: 1 });
      if (this.deg_sh > 0) {
        const temp = sat_steam.T + this.deg_sh;
        return new SteamStream({ P: this.psia, T: temp });
      }
      return sat_steam;
    }

    get btu_for_1_lb() {
      return this.steam_stream.h - this.feed_water_stream.h;
    }

    get steam_available_per_lb_bagasse() {
      return (this.bagasse.gcv * this.efficiency) / 100 / this.btu_for_1_lb;
    }

    get steam_availabe_lb_hr() {
      return this.steam_available_per_lb_bagasse * this.bagasse.flowrate_lb_hr;
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Boiler;
  } else {
    root.Boiler = Boiler;
  }
})(typeof window !== 'undefined' ? window : globalThis);
