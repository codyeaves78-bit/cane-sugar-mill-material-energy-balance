"""
Evaporator Heat Loss / Gas Bleed / Condensate Flash Recovery — Worked Example

Takes Birkett (1978) Case 7 -- a straight quadruple effect with a V1 bleed to
the juice heaters (see EvaporatorSet.py's __main__ CASES dict) -- and solves
it three ways with EvaporatorSetSciPy so the steam consumption can be
compared side by side:

  1. Birkett as published: no vessel heat loss, no calandria gas bleed,
     no condensate flash recovery (heat_loss_percent / incond_gas_bleed_percent
     default to 0, matching the paper).
  2. Same case, but with real-world derating: 4% heat loss in effect 2, 3% in
     effect 3, 2% in effect 4 (effect 1 stays at 0 -- Hugot's convention,
     see EvaporatorSet._heat_loss_for_effect), plus a 2% incondensable-gas
     bleed on every calandria.
  3. Same losses and bleed as #2, but with recover_condensate_flash=True so
     each effect's calandria condensate self-flashes down to the next
     effect's pressure and the recovered vapor is fed forward as extra
     heating steam (see Evaporator.condensate_flash_vapor_lb_per_hr).

Losing heat to the shell and venting steam as incondensable-gas purge both
mean less of the calandria's heat actually reaches the juice, so case 2
needs more steam than case 1 to hit the same 60 Bx syrup target. Recovering
the flashed condensate vapor in case 3 claws some of that penalty back.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so this runs standalone from any cwd

from EvaporatorSet import EvaporatorSetSciPy
from SugarStream import SugarStream
from SteamStream import EvaporatorSteam
from evaporator_functions import convert_inHg_vacuum_to_psia, convert_psig_to_psia

# ── Birkett Case 7 basis ──────────────────────────────────────────────────
# 200,000 lb/hr clarified juice @ 12 Bx, 225 F, purity 90; 20 psig supply
# steam; 26" Hg vacuum last effect; 60 Bx syrup target; Dessin K = 20,000;
# 100 F injection water; V1 bled for the juice heaters.
LAST_PSIA  = convert_inHg_vacuum_to_psia(26)
STEAM_PSIA = convert_psig_to_psia(20)
AREAS      = [5900, 4600, 4600, 4600]
BLEEDS     = [31_357 + 3_895]

def _juice():
    return SugarStream(brix=12.0, purity=90, flow_lb_per_hr=200_000,
                        temp_deg_F=225, pressure_psia=60, level_ft=0)

def _steam():
    return EvaporatorSteam(P_psia=STEAM_PSIA, flow_lb_per_hr=0)

# ── 1. Birkett as published: no losses, no bleed, no flash recovery ───────
birkett = EvaporatorSetSciPy(
    juice_in=_juice(),
    supply_steam=_steam(),
    last_effect_pressure_psia=LAST_PSIA,
    target_brix_out=60,
    effect_areas_ft2=AREAS,
    vapor_bleeds=BLEEDS,
    dessin_coefficient=20_000,
    name="Case 7 — Birkett (no losses)",
)
birkett.adjust_pressure_profile_scipy()

# ── 2. Realistic losses: heat loss + gas bleed, no flash recovery ─────────
with_losses = EvaporatorSetSciPy(
    juice_in=_juice(),
    supply_steam=_steam(),
    last_effect_pressure_psia=LAST_PSIA,
    target_brix_out=60,
    effect_areas_ft2=AREAS,
    vapor_bleeds=BLEEDS,
    dessin_coefficient=20_000,
    heat_loss_percent=[0.0, 4.0, 3.0, 2.0],   # effect 1 stays at 0 -- see EvaporatorSet._heat_loss_for_effect
    incond_gas_bleed_percent=2.0,             # applied to every calandria
    recover_condensate_flash=False,
    name="Case 7 — Heat Loss + Gas Bleed",
)
with_losses.adjust_pressure_profile_scipy()

# ── 3. Same losses/bleed, but recover the calandria condensate flash ──────
with_flash_recovery = EvaporatorSetSciPy(
    juice_in=_juice(),
    supply_steam=_steam(),
    last_effect_pressure_psia=LAST_PSIA,
    target_brix_out=60,
    effect_areas_ft2=AREAS,
    vapor_bleeds=BLEEDS,
    dessin_coefficient=20_000,
    heat_loss_percent=[0.0, 4.0, 3.0, 2.0],
    incond_gas_bleed_percent=2.0,
    recover_condensate_flash=True,
    name="Case 7 — Heat Loss + Gas Bleed + Condensate Flash Recovery",
)
with_flash_recovery.adjust_pressure_profile_scipy()

# ── Full detail on each ────────────────────────────────────────────────────
for evap_set in (birkett, with_losses, with_flash_recovery):
    evap_set.neat_display()

# ── Steam consumption comparison ───────────────────────────────────────────
steam_birkett = birkett.supply_steam.flow_lb_per_hr
steam_losses  = with_losses.supply_steam.flow_lb_per_hr
steam_flash   = with_flash_recovery.supply_steam.flow_lb_per_hr

W = 78
print(f"\n{'=' * W}")
print("  STEAM CONSUMPTION COMPARISON — Birkett Case 7 (Quadruple, V1 bleed)")
print(f"{'=' * W}")
print(f"  1. Birkett as published (no losses)              : {steam_birkett:>12,.0f} lb/hr")
print(f"  2. + Heat loss (4/3/2%) + 2% gas bleed            : {steam_losses:>12,.0f} lb/hr"
      f"   ({(steam_losses / steam_birkett - 1) * 100:+.2f}% vs. Birkett)")
print(f"  3. + Condensate flash recovery                    : {steam_flash:>12,.0f} lb/hr"
      f"   ({(steam_flash / steam_birkett - 1) * 100:+.2f}% vs. Birkett,"
      f" {(steam_flash / steam_losses - 1) * 100:+.2f}% vs. #2)")
print(f"{'=' * W}")
print(f"  Flash vapor recovered (set total)                 : "
      f"{with_flash_recovery.total_condensate_flash_recovered:>12,.0f} lb/hr")
print(f"{'=' * W}\n")
