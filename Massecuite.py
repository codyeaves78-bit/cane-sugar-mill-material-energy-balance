# Massecuite class for vacuum pan calculations.
# BPR regression sourced from Birkett fig 12.14 in his Nicholl's Class Notes (°F). Valid range: ml_purity 30–100.
# Below ml_purity 60 is extrapolated — use with caution.

import functools
import numpy as np
from SteamStream import EvaporatorSteam
from sugar_stream_properties import specific_gravity, get_cp

# --- BPR regression built once at import ---
_PURITIES = [100,  90,   80,   70,   60  ]
_Y1       = [9.9,  11,   12.5, 14.1, 16.3]   # BPR (°F) at T = 130°F
_Y2       = [14.6, 16,   18,   20.3, 22.8]   # BPR (°F) at T = 185°F
_T1, _T2  = 130, 185

def _build_bpr_regression():
    slopes, bs = [], []
    for y1, y2 in zip(_Y1, _Y2):
        m = (y2 - y1) / (_T2 - _T1)
        slopes.append(m)
        bs.append(y2 - m * _T2)
    return (np.poly1d(np.polyfit(_PURITIES, slopes, 1)),
            np.poly1d(np.polyfit(_PURITIES, bs,     1)))

_slope_poly, _b_poly = _build_bpr_regression()

# --- Predicted mother liquor purity from massecuite purity (Birkett correlation) ---
# Birkett found crystal yield (% on brix) regresses linearly against massecuite purity;
# mother liquor purity is then back-calculated from that crystal yield via the standard
# identity CY = (Pm - Pml) / (1 - Pml/100), solved for Pml.
# DISPLAY AID ONLY: an approximate check against the ml_purity actually supplied to
# Pan/Massecuite (lab analysis or process knowledge) -- not a substitute for it.

def predict_mother_liquor_purity(masse_purity, use_birkett=True, slope=None, intercept=None):
    """Predict mother liquor purity (%) from massecuite purity (%).

    use_birkett=True (default) uses Birkett's fitted crystal-yield-vs-massecuite-purity
    slope/intercept (0.7609, -11.693). Pass use_birkett=False with your own slope/intercept
    to use a different crystal-yield correlation instead.
    """
    if use_birkett:
        m, b = 0.7609, -11.693
    else:
        m, b = float(slope), float(intercept)
    crystal_yield = m * masse_purity + b
    return (masse_purity - crystal_yield) / (1 - crystal_yield / 100)


class Massecuite:
    """
    Represents a massecuite in a vacuum pan.

    ml_purity       : mother liquor apparent purity (10–100)
                      Note: BPR data exists for 60–100; below 60 is extrapolated.
    masse_purity    : overall massecuite apparent purity
    masse_brix      : overall massecuite Brix
    inches_vacuum   : vapor space vacuum in inches Hg
    supersaturation : target supersaturation coefficient (e.g. 1.05) — boiling mode
    head_ft         : massecuite depth in the pan (ft) — required in boiling mode
    flow_lb_hr      : massecuite flow rate (lb/hr) — optional; unlocks flow-based properties
    temp_F          : explicit massecuite temperature (°F) — set-temperature mode

    Two modes — give exactly one of supersaturation / temp_F:

    Boiling mode (supersaturation given): the massecuite is boiling in a pan,
    and its temperature is solved from vacuum, static head, and the BPR
    regression. All boiling properties (water bp, BPR at surface/head) apply.

    Set-temperature mode (temp_F given): the massecuite is off-boiling
    (crystallizer, reheater, transport) and its temperature is imposed by
    heat exchange. massecuite_temp returns temp_F directly; supersaturation
    is None and the boiling-solve properties raise, since BPR-based
    supersaturation is only meaningful at boiling equilibrium.

    Solve results are cached on first access — iterations run once per instance.
    """

    PURITY_MIN = 20
    PURITY_MAX = 100

    def __init__(self, ml_purity, masse_purity, masse_brix,
                 inches_vacuum, supersaturation=None, head_ft=None,
                 flow_lb_hr=None, temp_F=None):
        if not (self.PURITY_MIN <= ml_purity <= self.PURITY_MAX):
            raise ValueError(
                f"Mother liquor purity {ml_purity} is outside the supported range "
                f"({self.PURITY_MIN}–{self.PURITY_MAX})."
            )
        if masse_purity < ml_purity:
            raise ValueError(
                f"Massecuite purity ({masse_purity}) cannot be less than "
                f"mother liquor purity ({ml_purity})."
            )
        if (supersaturation is None) == (temp_F is None):
            raise ValueError(
                "Give exactly one of supersaturation (boiling mode) "
                "or temp_F (set-temperature mode)."
            )
        if supersaturation is not None and head_ft is None:
            raise ValueError("head_ft is required in boiling (supersaturation) mode.")
        self.ml_purity       = ml_purity
        self.masse_purity    = masse_purity
        self.masse_brix      = masse_brix
        self.inches_vacuum   = inches_vacuum
        self.supersaturation = supersaturation
        self.head_ft         = head_ft
        self.flow_lb_hr      = flow_lb_hr
        self.temp_F          = temp_F

    def copy(self, **changes):
        """
        Return a new Massecuite with the same inputs, overriding any given
        as keyword arguments:

            b_masse = a_masse.copy(masse_brix=93)

        Overriding temp_F switches the copy to set-temperature mode (the old
        supersaturation is dropped), and overriding supersaturation switches
        back to boiling mode — so a pan massecuite can flow into a
        crystallizer with:

            out = pan_masse.copy(temp_F=120, ml_purity=64)

        Goes back through __init__, so validation re-runs and the new
        instance solves fresh (no stale cached results carry over).
        """
        params = {
            'ml_purity':       self.ml_purity,
            'masse_purity':    self.masse_purity,
            'masse_brix':      self.masse_brix,
            'inches_vacuum':   self.inches_vacuum,
            'supersaturation': self.supersaturation,
            'head_ft':         self.head_ft,
            'flow_lb_hr':      self.flow_lb_hr,
            'temp_F':          self.temp_F,
        }
        if changes.get('temp_F') is not None:
            params['supersaturation'] = None
        if changes.get('supersaturation') is not None:
            params['temp_F'] = None
        params.update(changes)
        return type(self)(**params)

    # ------------------------------------------------------------------
    # Private helpers (temperature-parameterized, used during iteration)
    # ------------------------------------------------------------------

    def _density_at(self):
        return specific_gravity(self.masse_brix) * 62.4

    def _require_boiling(self):
        if self.temp_F is not None:
            raise AttributeError(
                "This property needs the boiling solve, but this massecuite was "
                "built with an explicit temp_F (set-temperature mode) — BPR-based "
                "supersaturation is only meaningful at boiling equilibrium. "
                "Use copy(supersaturation=...) if it is back in a pan."
            )

    def _sat_bpr_at(self, temp_F):
        """Saturation BPR (°F) at a given temperature — used inside solve loops."""
        return float(_slope_poly(self.ml_purity)) * temp_F + float(_b_poly(self.ml_purity))

    # ------------------------------------------------------------------
    # Vapor space pressure
    # ------------------------------------------------------------------

    @property
    def vapor_pressure_psia(self):
        """Vapor space absolute pressure (psia)."""
        return 14.696 - self.inches_vacuum * 0.491154

    # ------------------------------------------------------------------
    # Cached solves (run once, stored in instance __dict__ by cached_property)
    # ------------------------------------------------------------------

    @functools.cached_property
    def _surface_solve(self):
        """Solve for massecuite temp at surface (head = 0). Returns (T, water_bp)."""
        self._require_boiling()
        water_bp = EvaporatorSteam(self.vapor_pressure_psia).sat_temp_deg_F
        T = water_bp + 20
        for _ in range(100):
            T_new = water_bp + self.supersaturation * self._sat_bpr_at(T)
            if abs(T_new - T) < 1e-6:
                return T_new, water_bp
            T = T_new
        raise RuntimeError("Massecuite surface solve did not converge")

    @functools.cached_property
    def _head_solve(self):
        """Solve for massecuite temp at specified head depth. Returns (T, water_bp_at_head)."""
        self._require_boiling()
        P_vapor = self.vapor_pressure_psia
        T = EvaporatorSteam(P_vapor).sat_temp_deg_F + 20
        for _ in range(100):
            delta_P       = self._density_at() * self.head_ft / 144
            water_bp_head = EvaporatorSteam(P_vapor + delta_P).sat_temp_deg_F
            T_new         = water_bp_head + self.supersaturation * self._sat_bpr_at(T)
            if abs(T_new - T) < 1e-6:
                return T_new, water_bp_head
            T = T_new
        raise RuntimeError("Massecuite head solve did not converge")

    # ------------------------------------------------------------------
    # Surface condition (head = 0)
    # ------------------------------------------------------------------

    @property
    def water_bp_surface(self):
        """Water boiling point at the vapor space — no static head (°F)."""
        return self._surface_solve[1]

    @property
    def massecuite_temp_surface(self):
        """Massecuite temperature to reach target SS at the surface (°F)."""
        return self._surface_solve[0]

    @property
    def bpr_at_surface(self):
        """BPR at the surface condition (°F)."""
        return self.massecuite_temp_surface - self.water_bp_surface

    # ------------------------------------------------------------------
    # Head condition (at specified depth)
    # ------------------------------------------------------------------

    @property
    def water_bp_at_head(self):
        """Water boiling point at the specified pan depth, including static head (°F)."""
        return self._head_solve[1]

    @property
    def massecuite_temp(self):
        """Massecuite temperature (°F) — the given temp_F in set-temperature mode,
        otherwise solved to reach target SS at the specified head depth."""
        if self.temp_F is not None:
            return self.temp_F
        return self._head_solve[0]

    @property
    def bpr_at_head(self):
        """BPR at the specified head depth (°F)."""
        return self.massecuite_temp - self.water_bp_at_head

    # ------------------------------------------------------------------
    # Physical properties at the converged head temperature
    # ------------------------------------------------------------------

    @property
    def density(self):
        """Massecuite density."""
        return self._density_at()

    @property
    def saturation_bpr(self):
        """Saturation BPR at the converged head temperature — SS = 1.0 reference (°F)."""
        return self._sat_bpr_at(self.massecuite_temp)
    
    @property
    def specific_heat(self):
        return get_cp(self.masse_brix)

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    @property
    def crystal_content(self):
        """
        Crystal content (% by mass of massecuite).
            C = masse_brix × (masse_purity - ml_purity) / (100 - ml_purity)
        """
        return self.masse_brix * (self.masse_purity - self.ml_purity) / (100 - self.ml_purity)

    @property
    def mother_liquor_brix(self):
        """
        Mother liquor Brix — derived from overall Brix and crystal content via water balance:
            B_ml = 100 - 100 × (100 - masse_brix) / (100 - crystal_content)
        """
        return 100 - 100 * (100 - self.masse_brix) / (100 - self.crystal_content)

    @property
    def crystal_yield_pct_brix(self):
        """
        Crystal yield (%) — fraction of sucrose crystallized relative to what is
        theoretically achievable at this mother liquor purity:
            yield = (masse_purity - ml_purity) / (100 - ml_purity) × 100
        """
        return (self.masse_purity - self.ml_purity) / (100 - self.ml_purity) * 100

    # ------------------------------------------------------------------
    # Flow-based properties (require flow_lb_hr to be set)
    # ------------------------------------------------------------------

    def _check_flow(self):
        if self.flow_lb_hr is None:
            raise AttributeError(
                "flow_lb_hr is not set — pass it to the constructor or assign it directly."
            )

    @property
    def solids_flow(self):
        """Total dissolved + crystal solids flow (lb/hr).  = masse_brix/100 × flow"""
        self._check_flow()
        return self.masse_brix / 100 * self.flow_lb_hr

    @property
    def pol_flow(self):
        """Sucrose (pol) flow (lb/hr).  = masse_purity × masse_brix / 10000 × flow"""
        self._check_flow()
        return self.masse_purity * self.masse_brix / 10000 * self.flow_lb_hr
    
    @property
    def cu_ft_hr(self):
        return self.flow_lb_hr / self.density

    # ------------------------------------------------------------------
    # Dunder / display
    # ------------------------------------------------------------------

    def __repr__(self):
        flow_str = f", flow_lb_hr={self.flow_lb_hr:,.0f}" if self.flow_lb_hr is not None else ""
        mode_str = (f"temp_F={self.temp_F}" if self.temp_F is not None else
                    f"inches_vacuum={self.inches_vacuum}, "
                    f"supersaturation={self.supersaturation}, head_ft={self.head_ft}")
        return (
            f"Massecuite(ml_purity={self.ml_purity}, masse_purity={self.masse_purity}, "
            f"masse_brix={self.masse_brix}, {mode_str}{flow_str})"
        )

    def properties(self):
        d = {
            'ml_purity':                     self.ml_purity,
            'masse_purity':                  self.masse_purity,
            'masse_brix':                    self.masse_brix,
            'crystal_content_pct':           self.crystal_content,
            'mother_liquor_brix':            self.mother_liquor_brix,
            'crystal_yield_pct_brix_pct':    self.crystal_yield_pct_brix,
            'density_lb_ft3':                self.density,
            'massecuite_temp':               self.massecuite_temp,
            'sat_bpr':                       self.saturation_bpr,
        }
        if self.temp_F is None:   # boiling mode — full solve available
            d.update({
                'inches_vacuum':             self.inches_vacuum,
                'vapor_pressure_psia':       self.vapor_pressure_psia,
                'supersaturation':           self.supersaturation,
                'head_ft':                   self.head_ft,
                'water_bp_surface':          self.water_bp_surface,
                'massecuite_temp_surf':      self.massecuite_temp_surface,
                'bpr_at_surface':            self.bpr_at_surface,
                'water_bp_at_head':          self.water_bp_at_head,
                'bpr_at_head':               self.bpr_at_head,
            })
        if self.flow_lb_hr is not None:
            d['flow_lb_hr']    = self.flow_lb_hr
            d['solids_flow']   = self.solids_flow
            d['pol_flow']      = self.pol_flow
        return d

    def display_properties(self):
        props = self.properties()
        print("Units: T(°F), BPR(°F), density(lb/ft³), flow(lb/hr), purity/brix/yield(%)")
        for k, v in props.items():
            print(f"  {k:<29}: {v:.3f}")


if __name__ == "__main__":
    import time

    masse = Massecuite(ml_purity=70, masse_purity=90, masse_brix=92,
                       inches_vacuum=23.5, supersaturation=1.2, head_ft=2,
                       flow_lb_hr=500_000)
    print(masse)
    print()
    t0 = time.perf_counter()
    masse.display_properties()
    print(masse)
    print(f"\nchanging temp test\n")
    masse.temp_F = 160
    masse.display_properties()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\n  solved in {elapsed_ms:.3f} ms")
