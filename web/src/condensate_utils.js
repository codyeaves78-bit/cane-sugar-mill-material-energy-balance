// Port of condensate_utils.py — shared post-flash condensate helper.
// Condensate hotter than atmospheric partially flashes to vapor when let
// down to atmospheric pressure for return to the boiler feed system; this
// returns the liquid fraction that survives. Used by JuiceHeatingStation
// (and, later, EvaporatorSet / Pan Floor) to total "clean" (exhaust) vs
// "dirty" (V1-V4) condensate return.

(function (root) {
  'use strict';

  const FLASH_TEMP_F = 212.0;
  const H_FG_FLASH_BTU_LB = 970.0;

  function flash_condensate(flow_lb_per_hr, sat_temp_deg_F,
                             flash_temp_F = FLASH_TEMP_F,
                             h_fg_flash_btu_lb = H_FG_FLASH_BTU_LB) {
    if (sat_temp_deg_F <= flash_temp_F) return flow_lb_per_hr;
    const flash = flow_lb_per_hr * (sat_temp_deg_F - flash_temp_F) / h_fg_flash_btu_lb;
    return flow_lb_per_hr - flash;
  }

  const condensate_utils = { flash_condensate, FLASH_TEMP_F, H_FG_FLASH_BTU_LB };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = condensate_utils;
  } else {
    root.condensate_utils = condensate_utils;
  }
})(typeof window !== 'undefined' ? window : globalThis);
