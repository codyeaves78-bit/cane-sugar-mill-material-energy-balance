// Port of Bagasse.py — bagasse composition + GCV (gross calorific value).

(function (root) {
  'use strict';

  class Bagasse {
    constructor({ moisture_pct, brix_pct, pol_pct, ash_pct, flowrate_lb_hr }) {
      this.moisture_pct = moisture_pct;
      this.brix_pct = brix_pct;
      this.pol_pct = pol_pct;
      this.ash_pct = ash_pct;
      this.flowrate_lb_hr = flowrate_lb_hr;
    }

    get fiber_pct() {
      return 100 - this.moisture_pct - this.brix_pct;
    }

    get gcv() {
      const M = this.moisture_pct;
      const A = this.ash_pct;
      const B = this.brix_pct;
      return (19605 - 196.05 * M - 196.05 * A - 31.14 * B) * 0.4299;
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Bagasse;
  } else {
    root.Bagasse = Bagasse;
  }
})(typeof window !== 'undefined' ? window : globalThis);
