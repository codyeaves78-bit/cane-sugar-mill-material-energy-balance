# Vacuum pan — complete material and energy balance.
# Massecuite purity is derived from the feed stream pol/solids balance (not specified directly).
# Mother liquor purity (ml_purity) is a direct user input — set it from lab analysis or
# process knowledge. Crystal yield is derived from ml_purity and masse_purity.
# Calandria steam is specified by pressure (psia); h_fg and T_sat are computed live by
# EvaporatorSteam. Update calandria_pressure_psia at any time (e.g. after an evaporator
# balance) and all heat transfer results recalculate automatically.

from SteamStream import EvaporatorSteam
from Massecuite import Massecuite, predict_mother_liquor_purity
from SugarStream import SugarStream

class Pan:
    """
    Vacuum pan material and energy balance.

    feed_streams           : SugarStream or list of SugarStreams entering the pan
                             (syrup, footing, seed remelt, etc.)
    heating_surface_ft2    : calandria heating area (ft²)
    inches_vacuum          : pan vapor space vacuum (in Hg)
    supersaturation        : target supersaturation coefficient (e.g. 1.1)
    head_ft                : massecuite depth in the pan (ft)
    masse_brix             : target massecuite outlet Brix
    ml_purity              : mother liquor apparent purity (%) — direct input from lab
                             analysis or process knowledge. Crystal yield is derived from
                             this and masse_purity: (J - M) / (100 - M).
    calandria_pressure_psia: heating steam pressure (psia). T_sat and h_fg are computed
                             live from this by EvaporatorSteam — no lookup table needed.
                             Update this attribute at any time (e.g. after an evaporator
                             balance) and all heat transfer results recalculate automatically.

    Massecuite apparent purity is computed from the feed pol/solids balance:
        masse_purity = Σ(flow_i × purity_i × brix_i) / Σ(flow_i × brix_i)

    Solve order:
        1. Pol/solids balance     →  masse_purity, feed_solids_lb_hr
        2. Crystal yield derived  →  crys_yld_frac_brix = (masse_purity - ml_purity) / (100 - ml_purity)
        3. Massecuite object      →  T_massecuite, vapor_pressure, BPR
        4. Material balance       →  massecuite_flow_lb_hr, water_evaporated_lb_hr
        5. Energy balance         →  Q = Q_sensible + Q_latent  (h_fg at vapor-space pressure)
        6. Steam consumption      →  steam_flow = Q / h_fg_calandria  (h_fg from calandria_pressure_psia)
        7. Back-calculate         →  U = Q / (A × ΔT)  where ΔT = T_sat(calandria) − T_massecuite
    """

    def __init__(self, feed_streams, heating_surface_ft2,
                 inches_vacuum, supersaturation, head_ft,
                 masse_brix, ml_purity: float,
                 calandria_pressure_psia: float = 21.696,
                 heat_loss_factor: float = 0.0,
                 name: str = 'Pan',
                 steam_type: int = 0):
        if feed_streams is None:
            self.feed_streams = [SugarStream(brix=65, purity=88, flow_lb_per_hr=100, temp_deg_F=140)]
        else:
            self.feed_streams        = (feed_streams if isinstance(feed_streams, list)
                                        else [feed_streams])
        self.heating_surface_ft2      = heating_surface_ft2
        self.inches_vacuum            = inches_vacuum
        self.supersaturation          = supersaturation
        self.head_ft                  = head_ft
        self.masse_brix               = masse_brix
        self.ml_purity                = ml_purity
        self.crys_yld_frac_brix       = (self.masse_purity - ml_purity) / (100 - ml_purity)
        self.calandria_pressure_psia  = calandria_pressure_psia
        self.heat_loss_factor         = heat_loss_factor
        self.name                     = name
        self.steam_type               = steam_type # 0 = Exh,  1 = V1,  2 = V2,  3 = V3,  4 = V4

        # Build the Massecuite using the pol/solids-derived purity
        self.massecuite = Massecuite(
            ml_purity=self.ml_purity,
            masse_purity=self.masse_purity,
            masse_brix=masse_brix,
            inches_vacuum=inches_vacuum,
            supersaturation=supersaturation,
            head_ft=head_ft,
        )

    # ------------------------------------------------------------------
    # Calandria steam (computed live from calandria_pressure_psia)
    # ------------------------------------------------------------------

    @property
    def _calandria_steam(self):
        """EvaporatorSteam instance for the calandria side. Re-created on each access
        so that updating calandria_pressure_psia immediately propagates everywhere."""
        return EvaporatorSteam(self.calandria_pressure_psia)

    @property
    def calandria_T_sat_F(self):
        """Saturation temperature of the calandria steam (°F)."""
        return self._calandria_steam.sat_temp_deg_F

    @property
    def h_fg_calandria(self):
        """Latent heat of the calandria steam (BTU/lb) — computed from calandria_pressure_psia."""
        return self._calandria_steam.h_fg

    # ------------------------------------------------------------------
    # Feed-side helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cp_sugar(brix):
        """Specific heat of a sugar solution (BTU/lb·°F) — linear Brix approximation."""
        return 1.0 - 0.006 * brix

    @property
    def feed_flow_lb_hr(self):
        """Total inlet flow — sum of all feed streams (lb/hr)."""
        return sum(f.flow_lb_per_hr for f in self.feed_streams)

    @property
    def feed_solids_lb_hr(self):
        """Total dissolved solids entering the pan (lb/hr)."""
        return sum(f.flow_lb_per_hr * f.brix / 100 for f in self.feed_streams)

    @property
    def feed_temp_F(self):
        """Flow-weighted average temperature of all feed streams (°F)."""
        return (sum(f.flow_lb_per_hr * f.temp_deg_F for f in self.feed_streams)
                / self.feed_flow_lb_hr)

    @property
    def masse_purity(self):
        """Massecuite apparent purity from feed pol/solids balance:
        P = Σ(flow × purity × brix) / Σ(flow × brix)
        """
        total_pol    = sum(f.flow_lb_per_hr * f.purity * f.brix / 10000
                           for f in self.feed_streams)
        total_solids = self.feed_solids_lb_hr
        return total_pol / total_solids * 100

    @property
    def predicted_ml_purity(self):
        """Predicted mother liquor purity (%) from masse_purity via Birkett's crystal-yield
        correlation -- a display-only sanity check against the ml_purity actually supplied,
        not a substitute for it. See Massecuite.predict_mother_liquor_purity."""
        return predict_mother_liquor_purity(self.masse_purity)

    @property
    def cp_massecuite(self):
        """Cp used for the sensible heat term (BTU/lb·°F)."""
        return self._cp_sugar(self.masse_brix)

    # ------------------------------------------------------------------
    # Material balance
    # ------------------------------------------------------------------

    @property
    def massecuite_flow_lb_hr(self):
        """Massecuite outlet flow from solids balance: feed_solids / (masse_brix / 100) (lb/hr)."""
        return self.feed_solids_lb_hr / (self.masse_brix / 100)

    @property
    def water_evaporated_lb_hr(self):
        """Water removed by boiling: total feed minus massecuite out (lb/hr)."""
        return self.feed_flow_lb_hr - self.massecuite_flow_lb_hr

    # ------------------------------------------------------------------
    # Energy balance  (h_fg here is at vapor-space pressure, not calandria)
    # ------------------------------------------------------------------

    @property
    def h_fg_vapor(self):
        """Latent heat of vaporization at the pan vapor-space pressure (BTU/lb)."""
        return EvaporatorSteam(self.massecuite.vapor_pressure_psia).h_fg

    @property
    def heat_sensible_btu_hr(self):
        """Sensible heat to raise the feed to the massecuite boiling point (BTU/hr)."""
        return (self.feed_flow_lb_hr * self.cp_massecuite
                * (self.massecuite.massecuite_temp - self.feed_temp_F))

    @property
    def heat_evaporation_btu_hr(self):
        """Latent heat carried away by evaporated water (BTU/hr)."""
        return self.water_evaporated_lb_hr * self.h_fg_vapor

    @property
    def heat_loss_btu_hr(self):
        """Radiation and convection losses from the pan body (BTU/hr)."""
        return (self.heat_sensible_btu_hr + self.heat_evaporation_btu_hr) * self.heat_loss_factor

    @property
    def heat_transfer_btu_hr(self):
        """Total calandria duty  Q = Q_sensible + Q_latent + Q_loss (BTU/hr)."""
        return self.heat_sensible_btu_hr + self.heat_evaporation_btu_hr + self.heat_loss_btu_hr

    # ------------------------------------------------------------------
    # Steam consumption  (h_fg here is the calandria-side standard value)
    # ------------------------------------------------------------------

    @property
    def steam_flow_lb_hr(self):
        """Steam consumed by the calandria: Q / h_fg_calandria (lb/hr).
        h_fg is computed from calandria_pressure_psia via EvaporatorSteam.
        """
        return self.heat_transfer_btu_hr / self.h_fg_calandria

    @property
    def steam_to_evaporation_ratio(self):
        """lb steam consumed per lb water evaporated — compare to Birkett (A=1.15, C=1.25)."""
        return self.steam_flow_lb_hr / self.water_evaporated_lb_hr

    # ------------------------------------------------------------------
    # Back-calculated heat transfer coefficient
    # ------------------------------------------------------------------

    @property
    def delta_T(self):
        """Driving force: T_sat(calandria) − T_massecuite (°F)."""
        dT = self.calandria_T_sat_F - self.massecuite.massecuite_temp
        if dT <= 0:
            raise ValueError(
                f"Calandria steam T_sat ({self.calandria_T_sat_F:.1f}°F at "
                f"{self.calandria_pressure_psia:.2f} psia) must exceed "
                f"massecuite boiling point ({self.massecuite.massecuite_temp:.1f}°F)."
            )
        return dT

    @property
    def U_btu_hr_ft2_F(self):
        """Overall HTC back-calculated: U = Q / (A × ΔT) (BTU/hr·ft²·°F).
        Update calandria_pressure_psia to the actual measured header pressure
        after an evaporator solve to refine U — no re-instantiation required.
        """
        return self.heat_transfer_btu_hr / (self.heating_surface_ft2 * self.delta_T)

    # ------------------------------------------------------------------
    # Vapor leaving the pan
    # ------------------------------------------------------------------

    @property
    def vapor_evaporated(self):
        """EvaporatorSteam at the pan vapor-space pressure; flow = water_evaporated_lb_hr."""
        P_vap = self.massecuite.vapor_pressure_psia
        return EvaporatorSteam(P_vap, flow_lb_per_hr=self.water_evaporated_lb_hr)

    # ------------------------------------------------------------------
    # Dunder / display
    # ------------------------------------------------------------------

    def __repr__(self):
        return (
            f"Pan(calandria={self.calandria_pressure_psia:.2f} psia, "
            f"A={self.heating_surface_ft2:,.0f} ft², "
            f"vacuum={self.inches_vacuum:.1f} inHg, "
            f"SS={self.supersaturation:.2f}, "
            f"feed={self.feed_flow_lb_hr:,.0f} lb/hr)"
        )

    def properties(self):
        return {
            # Feed
            'feed_flow_lb_hr':            self.feed_flow_lb_hr,
            'feed_solids_lb_hr':          self.feed_solids_lb_hr,
            'feed_temp_F':                self.feed_temp_F,
            # Massecuite composition
            'ml_purity':                  self.ml_purity,
            'predicted_ml_purity':        self.predicted_ml_purity,
            'masse_purity':               self.masse_purity,
            'masse_brix':                 self.masse_brix,
            'crystal_content_pct':        self.massecuite.crystal_content,
            'mother_liquor_brix':         self.massecuite.mother_liquor_brix,
            'crystal_yield_pct_brix':     self.massecuite.crystal_yield_pct_brix,
            # Material balance
            'massecuite_flow_lb_hr':      self.massecuite_flow_lb_hr,
            'water_evaporated_lb_hr':     self.water_evaporated_lb_hr,
            # Thermodynamic state
            'inches_vacuum':              self.inches_vacuum,
            'vapor_pressure_psia':        self.massecuite.vapor_pressure_psia,
            'supersaturation':            self.supersaturation,
            'head_ft':                    self.head_ft,
            'water_bp_surface_F':         self.massecuite.water_bp_surface,
            'massecuite_temp_surface_F':  self.massecuite.massecuite_temp_surface,
            'water_bp_at_head_F':         self.massecuite.water_bp_at_head,
            'massecuite_temp_F':          self.massecuite.massecuite_temp,
            'bpr_at_head_F':              self.massecuite.bpr_at_head,
            'density_lb_ft3':             self.massecuite.density,
            # Energy balance
            'cp_massecuite':              self.cp_massecuite,
            'h_fg_vapor':                 self.h_fg_vapor,
            'heat_sensible_btu_hr':       self.heat_sensible_btu_hr,
            'heat_evaporation_btu_hr':    self.heat_evaporation_btu_hr,
            'heat_loss_factor':           self.heat_loss_factor,
            'heat_loss_btu_hr':           self.heat_loss_btu_hr,
            'heat_transfer_btu_hr':       self.heat_transfer_btu_hr,
            # Steam consumption
            'calandria_pressure_psia':    self.calandria_pressure_psia,
            'calandria_T_sat_F':          self.calandria_T_sat_F,
            'h_fg_calandria':             self.h_fg_calandria,
            'steam_flow_lb_hr':           self.steam_flow_lb_hr,
            'steam_to_evaporation_ratio': self.steam_to_evaporation_ratio,
            # Heat transfer coefficient
            'delta_T_F':                  self.delta_T,
            'heating_surface_ft2':        self.heating_surface_ft2,
            'U_btu_hr_ft2_F':             self.U_btu_hr_ft2_F,
        }

    def display_properties(self):
        props = self.properties()
        print("Units: T(°F), flow(lb/hr), Q(BTU/hr), A(ft²), U(BTU/hr·ft²·°F), density(lb/ft³)")
        for k, v in props.items():
            if isinstance(v, str):
                print(f"  {k:<30}: {v}")
            else:
                print(f"  {k:<30}: {v:,.3f}")

    def neat_display(self):
        def row(label, value, unit=""):
            if isinstance(value, str):
                print(f"  {label:<35} {value}")
            else:
                print(f"  {label:<35} {value:>14,.1f}  {unit}")

        def section(title):
            print(f"\n  {'-' * 55}")
            print(f"  {title}")
            print(f"  {'-' * 55}")

        print(f"\n{'=' * 59}")
        print(f"  {self.name}  |  {self.calandria_pressure_psia:.2f} psia steam  |  {self.heating_surface_ft2:,.0f} ft²  |  {self.inches_vacuum} inHg vacuum")
        print(f"{'=' * 59}")

        section("FEED")
        row("Total feed flow",         self.feed_flow_lb_hr,        "lb/hr")
        row("Feed solids",             self.feed_solids_lb_hr,      "lb/hr")
        row("Feed temperature",        self.feed_temp_F,            "°F")

        section("MASSECUITE")
        row("Massecuite flow",         self.massecuite_flow_lb_hr,  "lb/hr")
        row("Massecuite brix",         self.masse_brix,             "%")
        row("Massecuite purity",       self.masse_purity,           "%")
        row("Mother liquor purity",    self.ml_purity,              "%")
        row("Predicted ML Purity",     self.predicted_ml_purity,    "%  (Birkett, display only)")
        row("Crystal content",         self.massecuite.crystal_content, "%")
        row("Mother liquor brix",      self.massecuite.mother_liquor_brix, "%")

        section("EVAPORATION")
        row("Water evaporated",        self.water_evaporated_lb_hr, "lb/hr")
        row("Massecuite temp",         self.massecuite.massecuite_temp, "°F")
        row("Vapor pressure",          self.massecuite.vapor_pressure_psia, "psia")
        row("BPR at head",             self.massecuite.bpr_at_head, "°F")

        section("ENERGY BALANCE")
        row("Sensible heat",           self.heat_sensible_btu_hr,   "BTU/hr")
        row("Evaporation heat",        self.heat_evaporation_btu_hr,"BTU/hr")
        row("Heat loss",               self.heat_loss_btu_hr,       "BTU/hr")
        row("Total duty",              self.heat_transfer_btu_hr,   "BTU/hr")

        section("STEAM & HEAT TRANSFER")
        row("Calandria pressure",      self.calandria_pressure_psia,    "psia")
        row("Calandria T_sat",         self.calandria_T_sat_F,          "°F")
        row("h_fg calandria",          self.h_fg_calandria,             "BTU/lb")
        row("Steam flow",              self.steam_flow_lb_hr,           "lb/hr")
        row("Steam/evaporation ratio", self.steam_to_evaporation_ratio, "lb/lb")
        row("dT (calandria - masse)",  self.delta_T,                    "°F")
        row("U (back-calc)",           self.U_btu_hr_ft2_F,            "BTU/hr·ft²·°F")

        print(f"\n{'=' * 59}\n")


if __name__ == "__main__":
    from SugarStream import SugarStream

    syrup   = SugarStream(brix=80, purity=88, flow_lb_per_hr=250_000,
                          temp_deg_F=144, pressure_psia=14.7, level_ft=0)
    footing = SugarStream(brix=88, purity=92, flow_lb_per_hr=50_000,
                          temp_deg_F=150, pressure_psia=14.7, level_ft=0)

    pan = Pan(
        feed_streams=[syrup, footing],
        heating_surface_ft2=22_000,
        inches_vacuum=26.5,
        supersaturation=1.2,
        head_ft=2,
        masse_brix=96,
        ml_purity=70,
        calandria_pressure_psia=21.696,   # V1 steam (7 psig)
        heat_loss_factor=0.05,
    )

    print(pan)
    print()
    pan.neat_display()

    print()
    print("--- single-pass U refinement after evaporator balance ---")
    pan.calandria_pressure_psia = 20.5   # actual measured V1 header pressure
    print(f"  U (21.696 psia) -> U (20.5 psia): {pan.U_btu_hr_ft2_F:.1f} BTU/hr.ft2.F")
