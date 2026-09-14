// Port of Pan.py — vacuum pan complete material and energy balance.
// Massecuite purity is derived from the feed stream pol/solids balance (not
// specified directly). Mother liquor purity (ml_purity) is a direct user
// input; crystal yield is derived from ml_purity and masse_purity.

(function (root) {
  'use strict';

  const SugarStream = (typeof module !== 'undefined' && module.exports) ? require('./sugar_stream.js') : root.SugarStream;
  const Massecuite = (typeof module !== 'undefined' && module.exports) ? require('./massecuite.js') : root.Massecuite;
  const EvaporatorSteam = (typeof module !== 'undefined' && module.exports) ? require('./steam_stream.js').EvaporatorSteam : root.EvaporatorSteam;

  class Pan {
    constructor({ feed_streams = null, heating_surface_ft2, inches_vacuum, supersaturation,
                  head_ft, masse_brix, ml_purity, calandria_pressure_psia = 21.696,
                  heat_loss_factor = 0.0, name = 'Pan', steam_type = 0 } = {}) {
      if (feed_streams === null || feed_streams === undefined) {
        this.feed_streams = [new SugarStream({ brix: 65, purity: 88, flow_lb_per_hr: 100, temp_deg_F: 140 })];
      } else {
        this.feed_streams = Array.isArray(feed_streams) ? feed_streams : [feed_streams];
      }
      this.heating_surface_ft2 = heating_surface_ft2;
      this.inches_vacuum = inches_vacuum;
      this.supersaturation = supersaturation;
      this.head_ft = head_ft;
      this.masse_brix = masse_brix;
      this.ml_purity = ml_purity;
      this.crys_yld_frac_brix = (this.masse_purity - ml_purity) / (100 - ml_purity);
      this.calandria_pressure_psia = calandria_pressure_psia;
      this.heat_loss_factor = heat_loss_factor;
      this.name = name;
      this.steam_type = steam_type; // 0 = Exh, 1 = V1, 2 = V2, 3 = V3, 4 = V4

      this.massecuite = new Massecuite({
        ml_purity: this.ml_purity,
        masse_purity: this.masse_purity,
        masse_brix: masse_brix,
        inches_vacuum: inches_vacuum,
        supersaturation: supersaturation,
        head_ft: head_ft,
      });
    }

    // ------------------------------------------------------------------
    // Calandria steam (computed live from calandria_pressure_psia)
    // ------------------------------------------------------------------

    get _calandria_steam() {
      return new EvaporatorSteam(this.calandria_pressure_psia);
    }

    get calandria_T_sat_F() { return this._calandria_steam.sat_temp_deg_F; }
    get h_fg_calandria() { return this._calandria_steam.h_fg; }

    // ------------------------------------------------------------------
    // Feed-side helpers
    // ------------------------------------------------------------------

    static _cpSugar(brix) {
      return 1.0 - 0.006 * brix;
    }

    get feed_flow_lb_hr() {
      return this.feed_streams.reduce((s, f) => s + f.flow_lb_per_hr, 0);
    }

    get feed_solids_lb_hr() {
      return this.feed_streams.reduce((s, f) => s + f.flow_lb_per_hr * f.brix / 100, 0);
    }

    get feed_temp_F() {
      return this.feed_streams.reduce((s, f) => s + f.flow_lb_per_hr * f.temp_deg_F, 0) / this.feed_flow_lb_hr;
    }

    get masse_purity() {
      const total_pol = this.feed_streams.reduce((s, f) => s + f.flow_lb_per_hr * f.purity * f.brix / 10000, 0);
      const total_solids = this.feed_solids_lb_hr;
      return total_pol / total_solids * 100;
    }

    get cp_massecuite() { return Pan._cpSugar(this.masse_brix); }

    // ------------------------------------------------------------------
    // Material balance
    // ------------------------------------------------------------------

    get massecuite_flow_lb_hr() {
      return this.feed_solids_lb_hr / (this.masse_brix / 100);
    }

    get water_evaporated_lb_hr() {
      return this.feed_flow_lb_hr - this.massecuite_flow_lb_hr;
    }

    // ------------------------------------------------------------------
    // Energy balance (h_fg here is at vapor-space pressure, not calandria)
    // ------------------------------------------------------------------

    get h_fg_vapor() {
      return new EvaporatorSteam(this.massecuite.vapor_pressure_psia).h_fg;
    }

    get heat_sensible_btu_hr() {
      return this.feed_flow_lb_hr * this.cp_massecuite * (this.massecuite.massecuite_temp - this.feed_temp_F);
    }

    get heat_evaporation_btu_hr() {
      return this.water_evaporated_lb_hr * this.h_fg_vapor;
    }

    get heat_loss_btu_hr() {
      return (this.heat_sensible_btu_hr + this.heat_evaporation_btu_hr) * this.heat_loss_factor;
    }

    get heat_transfer_btu_hr() {
      return this.heat_sensible_btu_hr + this.heat_evaporation_btu_hr + this.heat_loss_btu_hr;
    }

    // ------------------------------------------------------------------
    // Steam consumption (h_fg here is the calandria-side standard value)
    // ------------------------------------------------------------------

    get steam_flow_lb_hr() {
      return this.heat_transfer_btu_hr / this.h_fg_calandria;
    }

    get steam_to_evaporation_ratio() {
      return this.steam_flow_lb_hr / this.water_evaporated_lb_hr;
    }

    // ------------------------------------------------------------------
    // Back-calculated heat transfer coefficient
    // ------------------------------------------------------------------

    get delta_T() {
      const dT = this.calandria_T_sat_F - this.massecuite.massecuite_temp;
      if (dT <= 0) {
        throw new Error(
          `Calandria steam T_sat (${this.calandria_T_sat_F.toFixed(1)}°F at ` +
          `${this.calandria_pressure_psia.toFixed(2)} psia) must exceed ` +
          `massecuite boiling point (${this.massecuite.massecuite_temp.toFixed(1)}°F).`
        );
      }
      return dT;
    }

    get U_btu_hr_ft2_F() {
      return this.heat_transfer_btu_hr / (this.heating_surface_ft2 * this.delta_T);
    }

    // ------------------------------------------------------------------
    // Vapor leaving the pan
    // ------------------------------------------------------------------

    get vapor_evaporated() {
      const P_vap = this.massecuite.vapor_pressure_psia;
      return new EvaporatorSteam(P_vap, this.water_evaporated_lb_hr);
    }

    // ------------------------------------------------------------------
    // Display
    // ------------------------------------------------------------------

    properties() {
      return {
        feed_flow_lb_hr: this.feed_flow_lb_hr,
        feed_solids_lb_hr: this.feed_solids_lb_hr,
        feed_temp_F: this.feed_temp_F,
        ml_purity: this.ml_purity,
        masse_purity: this.masse_purity,
        masse_brix: this.masse_brix,
        crystal_content_pct: this.massecuite.crystal_content,
        mother_liquor_brix: this.massecuite.mother_liquor_brix,
        crystal_yield_pct_brix: this.massecuite.crystal_yield_pct_brix,
        massecuite_flow_lb_hr: this.massecuite_flow_lb_hr,
        water_evaporated_lb_hr: this.water_evaporated_lb_hr,
        inches_vacuum: this.inches_vacuum,
        vapor_pressure_psia: this.massecuite.vapor_pressure_psia,
        supersaturation: this.supersaturation,
        head_ft: this.head_ft,
        water_bp_surface_F: this.massecuite.water_bp_surface,
        massecuite_temp_surface_F: this.massecuite.massecuite_temp_surface,
        water_bp_at_head_F: this.massecuite.water_bp_at_head,
        massecuite_temp_F: this.massecuite.massecuite_temp,
        bpr_at_head_F: this.massecuite.bpr_at_head,
        density_lb_ft3: this.massecuite.density,
        cp_massecuite: this.cp_massecuite,
        h_fg_vapor: this.h_fg_vapor,
        heat_sensible_btu_hr: this.heat_sensible_btu_hr,
        heat_evaporation_btu_hr: this.heat_evaporation_btu_hr,
        heat_loss_factor: this.heat_loss_factor,
        heat_loss_btu_hr: this.heat_loss_btu_hr,
        heat_transfer_btu_hr: this.heat_transfer_btu_hr,
        calandria_pressure_psia: this.calandria_pressure_psia,
        calandria_T_sat_F: this.calandria_T_sat_F,
        h_fg_calandria: this.h_fg_calandria,
        steam_flow_lb_hr: this.steam_flow_lb_hr,
        steam_to_evaporation_ratio: this.steam_to_evaporation_ratio,
        delta_T_F: this.delta_T,
        heating_surface_ft2: this.heating_surface_ft2,
        U_btu_hr_ft2_F: this.U_btu_hr_ft2_F,
      };
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Pan;
  } else {
    root.Pan = Pan;
  }
})(typeof window !== 'undefined' ? window : globalThis);
