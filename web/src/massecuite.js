// Port of Massecuite.py — massecuite state in a vacuum pan (or off-boiling in
// a crystallizer/reheater/transport). BPR regression sourced from Birkett fig
// 12.14 in his Nicholl's Class Notes (deg F). Valid range: ml_purity 30-100,
// below 60 is extrapolated.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;
  const { satSteamTemp, getCp, specificGravity } = SugarStream._properties;

  // --- BPR regression, built once at module load (mirrors the Python
  // module-level _build_bpr_regression() call) ---
  const _PURITIES = [100, 90, 80, 70, 60];
  const _Y1 = [9.9, 11, 12.5, 14.1, 16.3];   // BPR (F) at T = 130F
  const _Y2 = [14.6, 16, 18, 20.3, 22.8];    // BPR (F) at T = 185F
  const _T1 = 130, _T2 = 185;

  // np.polyfit(x, y, 1) — least-squares line, returned as [slope, intercept].
  function linearFit(xs, ys) {
    const n = xs.length;
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (let i = 0; i < n; i++) {
      sx += xs[i]; sy += ys[i]; sxx += xs[i] * xs[i]; sxy += xs[i] * ys[i];
    }
    const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);
    const intercept = (sy - slope * sx) / n;
    return [slope, intercept];
  }

  function _buildBprRegression() {
    const slopes = [], bs = [];
    for (let i = 0; i < _PURITIES.length; i++) {
      const m = (_Y2[i] - _Y1[i]) / (_T2 - _T1);
      slopes.push(m);
      bs.push(_Y2[i] - m * _T2);
    }
    return [linearFit(_PURITIES, slopes), linearFit(_PURITIES, bs)];
  }

  const [_slopeCoef, _bCoef] = _buildBprRegression();
  const _slopePoly = (purity) => _slopeCoef[0] * purity + _slopeCoef[1];
  const _bPoly = (purity) => _bCoef[0] * purity + _bCoef[1];

  const PURITY_MIN = 20;
  const PURITY_MAX = 100;

  class Massecuite {
    constructor({ ml_purity, masse_purity, masse_brix, inches_vacuum,
                  supersaturation = null, head_ft = null,
                  flow_lb_hr = null, temp_F = null } = {}) {
      if (!(ml_purity >= PURITY_MIN && ml_purity <= PURITY_MAX)) {
        throw new Error(`Mother liquor purity ${ml_purity} is outside the supported range (${PURITY_MIN}-${PURITY_MAX}).`);
      }
      if (masse_purity < ml_purity) {
        throw new Error(`Massecuite purity (${masse_purity}) cannot be less than mother liquor purity (${ml_purity}).`);
      }
      const ssGiven = supersaturation !== null && supersaturation !== undefined;
      const tempGiven = temp_F !== null && temp_F !== undefined;
      if (ssGiven === tempGiven) {
        throw new Error('Give exactly one of supersaturation (boiling mode) or temp_F (set-temperature mode).');
      }
      if (ssGiven && (head_ft === null || head_ft === undefined)) {
        throw new Error('head_ft is required in boiling (supersaturation) mode.');
      }
      this.ml_purity = ml_purity;
      this.masse_purity = masse_purity;
      this.masse_brix = masse_brix;
      this.inches_vacuum = inches_vacuum;
      this.supersaturation = ssGiven ? supersaturation : null;
      this.head_ft = head_ft;
      this.flow_lb_hr = flow_lb_hr;
      this.temp_F = tempGiven ? temp_F : null;

      this._surfaceSolveCache = null;
      this._headSolveCache = null;
    }

    copy(changes = {}) {
      const params = {
        ml_purity: this.ml_purity,
        masse_purity: this.masse_purity,
        masse_brix: this.masse_brix,
        inches_vacuum: this.inches_vacuum,
        supersaturation: this.supersaturation,
        head_ft: this.head_ft,
        flow_lb_hr: this.flow_lb_hr,
        temp_F: this.temp_F,
      };
      if (changes.temp_F !== undefined && changes.temp_F !== null) {
        params.supersaturation = null;
      }
      if (changes.supersaturation !== undefined && changes.supersaturation !== null) {
        params.temp_F = null;
      }
      Object.assign(params, changes);
      return new Massecuite(params);
    }

    // ------------------------------------------------------------------
    // Private helpers (temperature-parameterized, used during iteration)
    // ------------------------------------------------------------------

    _densityAt() {
      return specificGravity(this.masse_brix) * 62.4;
    }

    _requireBoiling() {
      if (this.temp_F !== null) {
        throw new Error(
          'This property needs the boiling solve, but this massecuite was built with an ' +
          'explicit temp_F (set-temperature mode) -- BPR-based supersaturation is only ' +
          'meaningful at boiling equilibrium. Use copy({supersaturation: ...}) if it is back in a pan.'
        );
      }
    }

    _satBprAt(temp_F) {
      return _slopePoly(this.ml_purity) * temp_F + _bPoly(this.ml_purity);
    }

    // ------------------------------------------------------------------
    // Vapor space pressure
    // ------------------------------------------------------------------

    get vapor_pressure_psia() {
      return 14.696 - this.inches_vacuum * 0.491154;
    }

    // ------------------------------------------------------------------
    // Cached solves (run once, memoized like Python's functools.cached_property)
    // ------------------------------------------------------------------

    _surfaceSolve() {
      if (this._surfaceSolveCache) return this._surfaceSolveCache;
      this._requireBoiling();
      const water_bp = satSteamTemp(this.vapor_pressure_psia);
      let T = water_bp + 20;
      for (let i = 0; i < 100; i++) {
        const T_new = water_bp + this.supersaturation * this._satBprAt(T);
        if (Math.abs(T_new - T) < 1e-6) {
          this._surfaceSolveCache = [T_new, water_bp];
          return this._surfaceSolveCache;
        }
        T = T_new;
      }
      throw new Error('Massecuite surface solve did not converge');
    }

    _headSolve() {
      if (this._headSolveCache) return this._headSolveCache;
      this._requireBoiling();
      const P_vapor = this.vapor_pressure_psia;
      let T = satSteamTemp(P_vapor) + 20;
      for (let i = 0; i < 100; i++) {
        const delta_P = this._densityAt() * this.head_ft / 144;
        const water_bp_head = satSteamTemp(P_vapor + delta_P);
        const T_new = water_bp_head + this.supersaturation * this._satBprAt(T);
        if (Math.abs(T_new - T) < 1e-6) {
          this._headSolveCache = [T_new, water_bp_head];
          return this._headSolveCache;
        }
        T = T_new;
      }
      throw new Error('Massecuite head solve did not converge');
    }

    // ------------------------------------------------------------------
    // Surface condition (head = 0)
    // ------------------------------------------------------------------

    get water_bp_surface() { return this._surfaceSolve()[1]; }
    get massecuite_temp_surface() { return this._surfaceSolve()[0]; }
    get bpr_at_surface() { return this.massecuite_temp_surface - this.water_bp_surface; }

    // ------------------------------------------------------------------
    // Head condition (at specified depth)
    // ------------------------------------------------------------------

    get water_bp_at_head() { return this._headSolve()[1]; }

    get massecuite_temp() {
      if (this.temp_F !== null) return this.temp_F;
      return this._headSolve()[0];
    }

    get bpr_at_head() { return this.massecuite_temp - this.water_bp_at_head; }

    // ------------------------------------------------------------------
    // Physical properties at the converged head temperature
    // ------------------------------------------------------------------

    get density() { return this._densityAt(); }

    get saturation_bpr() { return this._satBprAt(this.massecuite_temp); }

    get specific_heat() { return getCp(this.masse_brix); }

    // ------------------------------------------------------------------
    // Composition
    // ------------------------------------------------------------------

    get crystal_content() {
      return this.masse_brix * (this.masse_purity - this.ml_purity) / (100 - this.ml_purity);
    }

    get mother_liquor_brix() {
      return 100 - 100 * (100 - this.masse_brix) / (100 - this.crystal_content);
    }

    get crystal_yield_pct_brix() {
      return (this.masse_purity - this.ml_purity) / (100 - this.ml_purity) * 100;
    }

    // ------------------------------------------------------------------
    // Flow-based properties (require flow_lb_hr to be set)
    // ------------------------------------------------------------------

    _checkFlow() {
      if (this.flow_lb_hr === null || this.flow_lb_hr === undefined) {
        throw new Error('flow_lb_hr is not set -- pass it to the constructor or assign it directly.');
      }
    }

    get solids_flow() {
      this._checkFlow();
      return this.masse_brix / 100 * this.flow_lb_hr;
    }

    get pol_flow() {
      this._checkFlow();
      return this.masse_purity * this.masse_brix / 10000 * this.flow_lb_hr;
    }

    get cu_ft_hr() {
      return this.flow_lb_hr / this.density;
    }

    // ------------------------------------------------------------------
    // Display
    // ------------------------------------------------------------------

    properties() {
      const d = {
        ml_purity: this.ml_purity,
        masse_purity: this.masse_purity,
        masse_brix: this.masse_brix,
        crystal_content_pct: this.crystal_content,
        mother_liquor_brix: this.mother_liquor_brix,
        crystal_yield_pct_brix_pct: this.crystal_yield_pct_brix,
        density_lb_ft3: this.density,
        massecuite_temp: this.massecuite_temp,
        sat_bpr: this.saturation_bpr,
      };
      if (this.temp_F === null) {
        Object.assign(d, {
          inches_vacuum: this.inches_vacuum,
          vapor_pressure_psia: this.vapor_pressure_psia,
          supersaturation: this.supersaturation,
          head_ft: this.head_ft,
          water_bp_surface: this.water_bp_surface,
          massecuite_temp_surf: this.massecuite_temp_surface,
          bpr_at_surface: this.bpr_at_surface,
          water_bp_at_head: this.water_bp_at_head,
          bpr_at_head: this.bpr_at_head,
        });
      }
      if (this.flow_lb_hr !== null && this.flow_lb_hr !== undefined) {
        d.flow_lb_hr = this.flow_lb_hr;
        d.solids_flow = this.solids_flow;
        d.pol_flow = this.pol_flow;
      }
      return d;
    }
  }

  Massecuite._properties = { linearFit, _slopePoly, _bPoly };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Massecuite;
  } else {
    root.Massecuite = Massecuite;
  }
})(typeof window !== 'undefined' ? window : globalThis);
