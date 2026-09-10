"""
Speed / accuracy comparison: EvaporatorSteam (polynomial) vs SteamStream (IAPWS-97).

Last Results Yeilded this
  Steam required (total):
    Poly  :   97,300.4 lb/hr
    IAPWS :   97,316.3 lb/hr
    Delta :      +15.9 lb/hr

  Solve time (total of 30 runs):
    Polynomial  :    419.4 ms
    IAPWS-97    :  77684.6 ms   THIS IS OVER A MINUTE!!!!
    IAPWS / Poly:    185.2 x slower

Architecture
------------
SteamStreamAdapter  — thin wrapper around SteamStream(x=1) that exposes the
                      same interface as EvaporatorSteam (.P_psia, .sat_temp_deg_F,
                      .h_fg, .flow_lb_per_hr) so it drops in without touching
                      any parent class logic.

EvaporatorIAPWS     — bypasses Evaporator.__init__ to substitute SteamStreamAdapter
                      for all steam-side objects; overrides lbs_evaporated_per_hr
                      to use IAPWS h_fg for vapor latent heat instead of the
                      SugarStream polynomial lookup.

EvaporatorSetIAPWS  — subclass of EvaporatorSet; only build_effects() is overridden
                      to create EvaporatorIAPWS bodies and SteamStreamAdapter
                      inter-effect steam objects.  Everything else (solve_for_steam,
                      update_steam_flow, adjust_pressure_profile, neat_display)
                      works unchanged because SteamStreamAdapter is interface-compatible.
"""

from time import perf_counter

from SteamStream import SteamStream, EvaporatorSteam
from SugarStream import SugarStream
from Evaporator import Evaporator
from EvaporatorSet import EvaporatorSet
from evaporator_functions import convert_psig_to_psia, convert_inHg_vacuum_to_psia


# ---------------------------------------------------------------------------
# SteamStreamAdapter
# ---------------------------------------------------------------------------

class SteamStreamAdapter:
    """
    Drop-in replacement for EvaporatorSteam backed by IAPWS-97.

    Exposes identical attributes so every existing Evaporator / EvaporatorSet
    property that touches the calandria or vapor stream works unchanged:
        .P_psia          settable — rebuilds IAPWS state on assignment
        .sat_temp_deg_F  saturation temperature (°F)
        .h_fg            latent heat (BTU/lb)  — 2 IAPWS calls per access
        .flow_lb_per_hr  plain instance attribute
    """

    def __init__(self, P_psia: float, flow_lb_per_hr: float = 0):
        self.flow_lb_per_hr = flow_lb_per_hr
        self._P_psia = P_psia
        self._state  = SteamStream(x=1, P=P_psia)

    # --- pressure (settable, triggers IAPWS rebuild) ----------------------

    @property
    def P_psia(self):
        return self._P_psia

    @P_psia.setter
    def P_psia(self, value):
        self._P_psia = value
        self._state  = SteamStream(x=1, P=value)

    # --- thermodynamic properties ----------------------------------------

    @property
    def sat_temp_deg_F(self):
        return self._state.T          # SteamStream.T is already in °F

    @property
    def h_fg(self):
        return self._state.h_fg       # 2 IAPWS97 calls internally

    def __repr__(self):
        return (f"SteamStreamAdapter(P={self._P_psia:.2f} psia, "
                f"T_sat={self.sat_temp_deg_F:.1f} degF, "
                f"flow={self.flow_lb_per_hr:,.0f} lb/hr)")


# ---------------------------------------------------------------------------
# EvaporatorIAPWS
# ---------------------------------------------------------------------------

class EvaporatorIAPWS(Evaporator):
    """
    Evaporator body using IAPWS-97 steam properties throughout.

    Bypasses Evaporator.__init__ so vapor_out and vapor_bleed are
    SteamStreamAdapter objects instead of EvaporatorSteam.

    lbs_evaporated_per_hr is overridden to use IAPWS h_fg for the
    vapor-space latent heat (parent uses SugarStream polynomial lookup).

    All other properties (dessin_U, heat_xfer_U, delta_T_juice_steam, …)
    inherit unchanged — they already call calandria_side.sat_temp_deg_F
    which SteamStreamAdapter provides via IAPWS.
    """

    def __init__(self, juice_side_in: SugarStream,
                 calandria_side: SteamStreamAdapter,
                 area_ft2: float = 1,
                 liquid_level_ft: float = 2,
                 dessin_coefficient: float = 18000,
                 vapor_pressure_psia: float = 14.7,
                 vapor_bleed: float = 0):

        self.juice_side_in      = juice_side_in
        self.calandria_side     = calandria_side
        self.area_ft2           = area_ft2
        self.dessin_coefficient = dessin_coefficient
        self.vapor_pressure_psia = vapor_pressure_psia
        self.liquid_level_ft    = liquid_level_ft

        self.juice_side_out = SugarStream(
            brix=self._initial_brix_guess_out(),
            purity=self.juice_side_in.purity,
            flow_lb_per_hr=self.juice_side_in.flow_lb_per_hr,
            temp_deg_F=self.juice_side_in.temp_deg_F,
            pressure_psia=self.vapor_pressure_psia,
            level_ft=self.liquid_level_ft,
        )
        self.juice_side_out.current_temp_to_bpe_plus_vapor_temp()

        # IAPWS-backed vapor streams
        self.vapor_out   = SteamStreamAdapter(P_psia=vapor_pressure_psia, flow_lb_per_hr=0)
        self.vapor_bleed = SteamStreamAdapter(P_psia=vapor_pressure_psia, flow_lb_per_hr=vapor_bleed)

        # Evaporator.__init__ is bypassed above, so set these explicitly: heat_duty_btu_per_hr
        # (inherited unchanged) depends on them. This variant doesn't model heat loss, gas bleed,
        # or condensate flash recovery -- it's off by default here.
        self.condensate_temp_drop = False
        self.heat_loss_percent    = 0
        self.calandria_bleed_pec  = 0
        self.cond_flash_to_next   = False

    @property
    def lbs_evaporated_per_hr(self):
        """Same formula as parent; uses vapor_out.h_fg (IAPWS) for vapor latent heat."""
        juice_temp_rise  = self.juice_side_in.temp_deg_F - self.juice_side_out.temp_deg_F
        h_fg_vapors      = self.vapor_out.h_fg                           # IAPWS
        cp_juice         = self.juice_side_in.cp_btu_per_lb_deg_F
        heat_from_flash  = self.juice_side_in.flow_lb_per_hr * cp_juice * juice_temp_rise
        heat_for_evap    = self.heat_duty_btu_per_hr + heat_from_flash   # calandria IAPWS via h_fg
        return heat_for_evap / h_fg_vapors


# ---------------------------------------------------------------------------
# EvaporatorSetIAPWS
# ---------------------------------------------------------------------------

class EvaporatorSetIAPWS(EvaporatorSet):
    """
    EvaporatorSet using IAPWS-97 steam throughout.

    Only build_effects() is overridden.  All solving logic
    (solve_for_steam, update_steam_flow, adjust_pressure_profile)
    inherits from EvaporatorSet and works unchanged because
    SteamStreamAdapter is interface-compatible with EvaporatorSteam.

    Pass supply_steam as a SteamStreamAdapter (not EvaporatorSteam).
    """

    def build_effects(self):
        self.evaporator_list = [EvaporatorIAPWS(
            juice_side_in=self.juice_in,
            calandria_side=self.supply_steam,              # SteamStreamAdapter
            area_ft2=self.effect_areas_ft2[0],
            liquid_level_ft=self.liquid_level_ft,
            dessin_coefficient=self.dessin_coefficient,
            vapor_pressure_psia=self.pressure_profile_initial[1],
            vapor_bleed=self.vapor_bleeds[0],
        )]
        self.evaporator_list[0].solve()

        for i in range(self.number_of_effects - 1):
            steam_to_next = (self.evaporator_list[i].lbs_evaporated_per_hr
                             - self.evaporator_list[i].vapor_bleed.flow_lb_per_hr)
            bled_vapor = self.vapor_bleeds[i + 1] if i + 1 < len(self.vapor_bleeds) else 0
            evap = EvaporatorIAPWS(
                juice_side_in=self.evaporator_list[i].juice_side_out,
                calandria_side=SteamStreamAdapter(
                    P_psia=self.pressure_profile_initial[i + 1],
                    flow_lb_per_hr=steam_to_next,
                ),
                area_ft2=self.effect_areas_ft2[i + 1],
                liquid_level_ft=self.liquid_level_ft,
                dessin_coefficient=self.dessin_coefficient,
                vapor_pressure_psia=self.pressure_profile_initial[i + 2],
                vapor_bleed=bled_vapor,
            )
            evap.solve()
            self.evaporator_list.append(evap)


# ---------------------------------------------------------------------------
# Speed / accuracy test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # ── Shared problem definition ─────────────────────────────────────────
    JUICE = dict(
        brix=12, purity=90, flow_lb_per_hr=200_000,
        temp_deg_F=225, pressure_psia=60, level_ft=0,
    )
    SUPPLY_PSIA      = convert_psig_to_psia(20)   # 34.70 psia
    LAST_EFFECT_PSIA = convert_inHg_vacuum_to_psia(26)
    AREAS            = [8800, 3100, 3100]
    VAPOR_BLEEDS     = [31357 + 3895 + 28108]
    DESSIN           = 18000
    LEVEL            = 2
    TARGET_BRIX      = 60

    RUNS = 30   # 30 is how many total loops I use for solving 3 sets (10 loops per set to distribute juices)

    # ── Polynomial (EvaporatorSteam) ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("  POLYNOMIAL  (EvaporatorSteam — fast lookup)")
    print("=" * 70)

    total_poly = 0.0
    poly_set   = None

    for _ in range(RUNS):
        t0 = perf_counter()
        s = EvaporatorSet(
            juice_in=SugarStream(**JUICE),
            supply_steam=EvaporatorSteam(P_psia=SUPPLY_PSIA),
            last_effect_pressure_psia=LAST_EFFECT_PSIA,
            target_brix_out=TARGET_BRIX,
            effect_areas_ft2=AREAS,
            vapor_bleeds=VAPOR_BLEEDS,
            dessin_coefficient=DESSIN,
            liquid_level_ft=LEVEL,
            name="Poly Set",
        )
        s.adjust_pressure_profile()
        total_poly += (perf_counter() - t0) * 1000
        poly_set    = s

    poly_set.neat_display()
    print(f"  >>> Total of {RUNS} runs: {total_poly:.1f} ms\n")

    # ── IAPWS-97 (SteamStream) ────────────────────────────────────────────
    print("=" * 70)
    print("  IAPWS-97  (SteamStream — full equation of state)")
    print("=" * 70)

    total_iapws = 0.0
    iapws_set   = None

    for _ in range(RUNS):
        t0 = perf_counter()
        s = EvaporatorSetIAPWS(
            juice_in=SugarStream(**JUICE),
            supply_steam=SteamStreamAdapter(P_psia=SUPPLY_PSIA),
            last_effect_pressure_psia=LAST_EFFECT_PSIA,
            target_brix_out=TARGET_BRIX,
            effect_areas_ft2=AREAS,
            vapor_bleeds=VAPOR_BLEEDS,
            dessin_coefficient=DESSIN,
            liquid_level_ft=LEVEL,
            name="IAPWS Set",
        )
        s.adjust_pressure_profile()
        total_iapws += (perf_counter() - t0) * 1000
        iapws_set    = s

    iapws_set.neat_display()
    print(f"  >>> Total of {RUNS} runs: {total_iapws:.1f} ms\n")

    # ── Side-by-side comparison ───────────────────────────────────────────
    print("=" * 70)
    print("  COMPARISON  (IAPWS vs Polynomial)")
    print("=" * 70)

    pef  = poly_set.evaporator_list
    ief  = iapws_set.evaporator_list
    n    = poly_set.number_of_effects
    LBL  = 28
    COL  = 12

    def cmp_row(label, p_vals, i_vals, fmt="{:.3f}"):
        dfmt = fmt.replace("{:", "{:+", 1)   # insert sign flag for delta column
        pcols = "  ".join(f"{fmt.format(v):>{COL}}"  for v in p_vals)
        icols = "  ".join(f"{fmt.format(v):>{COL}}"  for v in i_vals)
        dcols = "  ".join(f"{dfmt.format(iv - pv):>{COL}}" for pv, iv in zip(p_vals, i_vals))
        print(f"  {label:<{LBL}}  Poly: {pcols}   IAPWS: {icols}   Delta: {dcols}")

    hdrs = "  ".join(f"{'Eff ' + str(i+1):>{COL}}" for i in range(n))
    print(f"\n  {'':>{LBL}}  {'Effects':>{COL * n + 2 * (n-1)}}")
    print(f"  {'':<{LBL}}  {hdrs}   {hdrs}   {hdrs}")
    print(f"  {'-' * (LBL + (COL + 2) * n * 3 + 20)}")

    cmp_row("steam in lb/hr",    [e.calandria_side.flow_lb_per_hr for e in pef],
                                  [e.calandria_side.flow_lb_per_hr for e in ief], "{:.0f}")
    cmp_row("evaporated lb/hr",  [e.lbs_evaporated_per_hr         for e in pef],
                                  [e.lbs_evaporated_per_hr         for e in ief], "{:.0f}")
    cmp_row("calandria h_fg",    [e.calandria_side.h_fg            for e in pef],
                                  [e.calandria_side.h_fg            for e in ief])
    cmp_row("vapor h_fg",        [e.vapor_out.h_fg                 for e in pef],
                                  [e.vapor_out.h_fg                 for e in ief])
    cmp_row("calandria T_sat F", [e.calandria_side.sat_temp_deg_F  for e in pef],
                                  [e.calandria_side.sat_temp_deg_F  for e in ief])
    cmp_row("brix out",          [e.juice_side_out.brix            for e in pef],
                                  [e.juice_side_out.brix            for e in ief])
    cmp_row("U calc",            [e.heat_xfer_U                    for e in pef],
                                  [e.heat_xfer_U                    for e in ief])

    print(f"\n  Steam required (total):")
    print(f"    Poly  : {poly_set.supply_steam.flow_lb_per_hr:>10,.1f} lb/hr")
    print(f"    IAPWS : {iapws_set.supply_steam.flow_lb_per_hr:>10,.1f} lb/hr")
    print(f"    Delta : {iapws_set.supply_steam.flow_lb_per_hr - poly_set.supply_steam.flow_lb_per_hr:>+10,.1f} lb/hr")

    print(f"\n  Solve time (total of {RUNS} runs):")
    print(f"    Polynomial  : {total_poly:>8.1f} ms")
    print(f"    IAPWS-97    : {total_iapws:>8.1f} ms")
    print(f"    IAPWS / Poly: {total_iapws / total_poly:>8.1f} x slower")
    print()
