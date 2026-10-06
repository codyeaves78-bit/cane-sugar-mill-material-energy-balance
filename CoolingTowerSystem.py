# CoolingTowerSystem: combined M&E balance for ALL barometric condensers in
# the factory (every evaporator set's last-effect condenser + every pan's
# condenser) circulating against one cooling tower.
#
# Water circuit (see notebook sketch):
#   condensers -> hot water return (mixed) -> cooling tower
#   tower losses: evaporated + blowdown
#   cool water -> back to condensers as injection water
#   makeup water keeps everything in balance
#
# Each condenser is input manually from the balance program that owns it, so
# the flowsheet stays simple — this class only combines them, in the same
# spirit as the Four Boiling "streams not shown" table.

from math import isfinite

from CoolingTower import CoolingTower


class CoolingTowerSystem:
    """
    Combined condenser + cooling tower water balance.

    Parameters
    ----------
    condensers        : list of (name, Condenser) tuples — every condenser in
                        the factory. Bare Condenser objects are accepted too
                        (they get auto-named "Condenser N").
    cool_water_temp_F : temperature of cold water the tower supplies back to
                        the condensers (°F) [default 90].
    percent_blowdown  : blowdown as % of hot water return [default 1.0].
    makeup_water_temp_F : temperature of the makeup water (°F). Default None
                        means makeup arrives at cool_water_temp_F, so the
                        delivered injection temp equals the tower cool water
                        temp. When given, the actual delivered injection
                        water temperature is the mass/heat blend (Cp = 1) of
                        tower cool water and makeup.
    name              : display name [default 'Cooling Tower System'].
    water_outlet_temp_drop_F : global condenser downleg temperature drop below
                        vapor saturation temperature (°F). Default None preserves
                        each condenser's existing setting. Must be finite and >= 0.

    Gathering the condensers from the balance programs::

        pan_floor    = FourBoilingDoubleMagma(...)      # or ThreeBoiling...
        evap_station = solve_evaporator_sets(...)       # list of EvaporatorSet

        cts = CoolingTowerSystem(
            condensers=(pan_floor.pan_condensers
                        + [(s.name, s.condenser) for s in evap_station]),
            cool_water_temp_F=90,
            percent_blowdown=1.0,
        )
        cts.neat_display()

    Balance logic
    -------------
    Hot water return   = sum of condenser outlets (injection water + condensed
                         vapor) at the mass-weighted mixed temperature.
    Cooling tower      = CoolingTower(hot return, mixed temp, cool temp, %BD);
                         loses blowdown and evaporation.
    Injection demand   = sum of condenser injection water flows.
    Makeup             = injection demand - cool water from tower
                       = blowdown + evaporated - vapor condensed.
                         Negative makeup means the condensed vapor exceeds
                         tower losses — reported as surplus (overflow) instead.
    """

    _GPM = 8.3 * 60  # lb/hr per GPM, consistent with CoolingTower / MillFloor

    def __init__(self, condensers: list, cool_water_temp_F: float = 90,
                 percent_blowdown: float = 1.0,
                 makeup_water_temp_F: float = None,
                 iterations: int = 15,
                 name: str = 'Cooling Tower System',
                 water_outlet_temp_drop_F: float = None):
        if water_outlet_temp_drop_F is not None:
            if not isfinite(water_outlet_temp_drop_F) or water_outlet_temp_drop_F < 0:
                raise ValueError("Condenser downleg ΔT must be finite and nonnegative (°F).")
        self.water_outlet_temp_drop_F = water_outlet_temp_drop_F
        self.name = name
        self.cool_water_temp_F = cool_water_temp_F
        self.percent_blowdown = percent_blowdown
        self.makeup_water_temp_F = makeup_water_temp_F

        # normalize to [(name, Condenser)]
        self.condensers = []
        for i, item in enumerate(condensers, 1):
            if isinstance(item, tuple):
                self.condensers.append(item)
            else:
                self.condensers.append((f"Condenser {i}", item))

        # remember the inlet temps the condensers arrived solved at
        self._as_received_temps = [(n, c.water_inlet_temp_F)
                                   for n, c in self.condensers]

        # Apply the global downleg setting before any water-demand calculations.
        if water_outlet_temp_drop_F is not None:
            for _, c in self.condensers:
                c.water_out_temp_drop_F = water_outlet_temp_drop_F

        self._solve(iterations)

    def _solve(self, iterations: int = 20):
        """Re-solve every condenser at the delivered injection temperature.

        The delivered temp depends on the makeup flow, which depends on the
        condensers' water demand, which depends on the delivered temp — so
        just loop a fixed number of times (no tolerance, plain iteration).
        With makeup_water_temp_F=None the first pass already lands exact.
        """
        for _ in range(iterations):
            t = self.delivered_water_temp_F
            for _, c in self.condensers:
                c.water_inlet_temp_F = t

    # ------------------------------------------------------------------
    # Combined condenser duty
    # ------------------------------------------------------------------

    @property
    def total_vapor_lb_hr(self):
        """All vapor condensed across the factory (lb/hr)."""
        return sum(c.vapor_flow_lb_hr for _, c in self.condensers)

    @property
    def total_heat_load_btu_hr(self):
        return sum(c.heat_load_btu_hr for _, c in self.condensers)

    @property
    def total_injection_water_lb_hr(self):
        """Cold water demand of all condensers (lb/hr)."""
        return sum(c.injection_water_flow_lb_hr for _, c in self.condensers)

    @property
    def hot_water_return_lb_hr(self):
        """Warm water returning to the tower: injection water + condensate."""
        return sum(c.total_outlet_flow_lb_hr for _, c in self.condensers)

    @property
    def hot_water_return_temp_F(self):
        """Mass-weighted mixed temperature of the combined return (Cp = 1)."""
        flow = self.hot_water_return_lb_hr
        if flow == 0:
            return self.cool_water_temp_F
        heat = sum(c.total_outlet_flow_lb_hr * c.water_outlet_temp_F
                   for _, c in self.condensers)
        return heat / flow

    @property
    def makeup_temp_F(self):
        """Makeup water temperature (°F): user value, or the tower cool water
        temperature when makeup_water_temp_F is None."""
        return (self.makeup_water_temp_F if self.makeup_water_temp_F is not None
                else self.cool_water_temp_F)

    @property
    def delivered_water_temp_F(self):
        """Actual injection water temperature delivered to the condensers (°F):
        mass/heat blend (Cp = 1) of tower cool water and makeup water."""
        demand = self.total_injection_water_lb_hr
        if demand == 0:
            return self.cool_water_temp_F
        makeup = self.makeup_lb_hr
        cool   = demand - makeup           # portion supplied by the tower
        return (cool * self.cool_water_temp_F + makeup * self.makeup_temp_F) / demand

    @property
    def mismatched_inlets(self):
        """Condensers that ARRIVED solved at a different injection temp than
        the final delivered temp. They are re-solved here at the delivered
        temp, but their owning balance program (pan floor / evaporator set)
        still reports water flows at the original temperature."""
        return [(n, t) for (n, t) in self._as_received_temps
                if abs(t - self.delivered_water_temp_F) > 0.01]

    # ------------------------------------------------------------------
    # Cooling tower side
    # ------------------------------------------------------------------

    @property
    def tower(self) -> CoolingTower:
        return CoolingTower(
            hot_water_temp=self.hot_water_return_temp_F,
            hot_water_lb_hr=self.hot_water_return_lb_hr,
            cool_water_temp=self.cool_water_temp_F,
            percent_blowdown=self.percent_blowdown,
        )

    @property
    def evaporated_lb_hr(self):
        return self.tower.evaporated

    @property
    def blowdown_lb_hr(self):
        return self.tower.blowdown_lb_hr

    @property
    def cool_water_from_tower_lb_hr(self):
        return self.tower.cool_water_lb_hr

    @property
    def makeup_lb_hr(self):
        """Fresh water needed so cool water supply meets injection demand."""
        short = self.total_injection_water_lb_hr - self.cool_water_from_tower_lb_hr
        return max(short, 0.0)

    @property
    def surplus_lb_hr(self):
        """Overflow when condensed vapor exceeds tower losses (lb/hr)."""
        short = self.total_injection_water_lb_hr - self.cool_water_from_tower_lb_hr
        return max(-short, 0.0)

    @property
    def balance_check(self):
        """System water balance: in (vapor + makeup) - out (evap + BD + surplus)."""
        water_in  = self.total_vapor_lb_hr + self.makeup_lb_hr
        water_out = self.evaporated_lb_hr + self.blowdown_lb_hr + self.surplus_lb_hr
        return {'in_lb_hr': water_in, 'out_lb_hr': water_out,
                'diff_lb_hr': water_in - water_out}

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self):
        return (f"CoolingTowerSystem({len(self.condensers)} condensers, "
                f"return={self.hot_water_return_lb_hr:,.0f} lb/hr @ "
                f"{self.hot_water_return_temp_F:.1f}°F, "
                f"makeup={self.makeup_lb_hr:,.0f} lb/hr)")

    def neat_display(self):
        W = 115
        HEAVY = "=" * W
        LIGHT = "-" * W

        def section(title):
            print(f"\n{LIGHT}\n  {title}\n{LIGHT}")

        print(HEAVY)
        print(f"{self.name.upper() + ' - COMBINED CONDENSER / TOWER BALANCE':^{W}}")
        print(HEAVY)

        # ── Condenser inventory (streams-not-shown style) ─────────────────
        section(f"CONDENSER INVENTORY  ({len(self.condensers)} condensers, "
                f"delivered injection water @ {self.delivered_water_temp_F:.1f} F)")
        print(f"  {'Condenser':<28} {'Vapor lb/hr':>12} {'Sat T F':>8} {'h_fg':>8}"
              f" {'MM BTU/hr':>10} {'Inj lb/hr':>13} {'Inj GPM':>9}"
              f" {'Out T F':>8} {'Total lb/hr':>13}")
        print()
        for cname, c in self.condensers:
            inj = c.injection_water_flow_lb_hr
            print(f"  {cname:<28} {c.vapor_flow_lb_hr:>12,.0f}"
                  f" {c.vapor_sat_temp_F:>8.1f} {c.vapor_h_fg_btu_lb:>8.1f}"
                  f" {c.heat_load_btu_hr / 1e6:>10.3f} {inj:>13,.0f}"
                  f" {inj / self._GPM:>9,.0f}"
                  f" {c.water_outlet_temp_F:>8.1f} {c.total_outlet_flow_lb_hr:>13,.0f}")
        print(LIGHT)
        print(f"  {'Total':<28} {self.total_vapor_lb_hr:>12,.0f} {'':>8} {'':>8}"
              f" {self.total_heat_load_btu_hr / 1e6:>10.3f}"
              f" {self.total_injection_water_lb_hr:>13,.0f}"
              f" {self.total_injection_water_lb_hr / self._GPM:>9,.0f}"
              f" {'':>8} {self.hot_water_return_lb_hr:>13,.0f}")

        # ── Combined water balance ────────────────────────────────────────
        def row(label, lb_hr, extra=""):
            print(f"  {label:<34} {lb_hr:>14,.0f} lb/hr"
                  f" {lb_hr / self._GPM:>9,.0f} GPM  {extra}")

        section("HOT WATER RETURN TO TOWER")
        row("Injection water (all condensers)", self.total_injection_water_lb_hr)
        row("Vapor condensed (all condensers)", self.total_vapor_lb_hr)
        print(LIGHT)
        row("Total return", self.hot_water_return_lb_hr,
            f"@ {self.hot_water_return_temp_F:.1f} F mixed")

        section(f"COOLING TOWER  ({self.hot_water_return_temp_F:.1f} F -> "
                f"{self.cool_water_temp_F:.0f} F, blowdown {self.percent_blowdown:.1f}%)")
        row("Blowdown", self.blowdown_lb_hr)
        row("Evaporated to atmosphere", self.evaporated_lb_hr)
        row("Cool water from tower", self.cool_water_from_tower_lb_hr,
            f"@ {self.cool_water_temp_F:.0f} F")

        section("SYSTEM BALANCE")
        row("Cold water demand (condensers)", self.total_injection_water_lb_hr)
        row("Cool water available (tower)", self.cool_water_from_tower_lb_hr,
            f"@ {self.cool_water_temp_F:.0f} F")
        if self.makeup_lb_hr > 0:
            row("MAKEUP WATER REQUIRED", self.makeup_lb_hr,
                f"@ {self.makeup_temp_F:.0f} F")
        else:
            row("Surplus (overflow)", self.surplus_lb_hr)
        print(f"\n  Delivered injection water temp (cool + makeup blend): "
              f"{self.delivered_water_temp_F:.1f} F")
        bal = self.balance_check
        print(f"\n  Water in (vapor + makeup)  : {bal['in_lb_hr']:>14,.0f} lb/hr")
        print(f"  Water out (evap + BD + surplus): {bal['out_lb_hr']:>10,.0f} lb/hr")
        print(f"  Net (In - Out)             : {bal['diff_lb_hr']:>14,.2f} lb/hr")
        print(HEAVY)

    def generate_pfd(self, show=True, save_path=None, include_table=True):
        """Generate a process flow diagram with stream tables. Returns the Figure."""
        from cooling_tower_diagram import plot_cooling_tower_system
        return plot_cooling_tower_system(self, show=show, save_path=save_path,
                                         include_table=include_table)

    def to_excel(self, workbook):
        """Write the combined condenser/tower balance to its own styled sheet:
        the PFD (diagram only), condenser inventory, and water balance."""
        import matplotlib.pyplot as plt
        from excel_export import SheetWriter
        from pan_floor_excel import condenser_table

        sw = SheetWriter(workbook, self.name, ncols=9)
        sw.title(self.name,
                 f"{len(self.condensers)} condensers | return = "
                 f"{self.hot_water_return_lb_hr:,.0f} lb/hr @ "
                 f"{self.hot_water_return_temp_F:.1f} °F | makeup = "
                 f"{self.makeup_lb_hr:,.0f} lb/hr")

        sw.section("PROCESS FLOW DIAGRAM")
        sw.blank()
        fig = self.generate_pfd(show=False, include_table=False)
        sw.image(fig, scale=0.55)
        plt.close(fig)

        sw.section("SYSTEM STREAMS  (tags match the diagram)")
        from cooling_tower_diagram import _collect_streams
        sw.table(["#", "Stream", "lb/hr", "GPM", "°F"],
                 _collect_streams(self),
                 fmts=["0", "@", "#,##0", "#,##0", "0.0"])

        sw.section(f"CONDENSER INVENTORY  ({len(self.condensers)} condensers)")
        condenser_table(sw, self.condensers, self.delivered_water_temp_F)

        sw.page_break()
        sw.section("HOT WATER RETURN TO TOWER")
        sw.row("Injection water (all condensers)", self.total_injection_water_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Vapor condensed (all condensers)", self.total_vapor_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Total return", self.hot_water_return_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Total return", self.hot_water_return_lb_hr / self._GPM, "GPM", fmt="#,##0")
        sw.row("Mixed return temperature", self.hot_water_return_temp_F, "°F", fmt="0.0")

        sw.section(f"COOLING TOWER  (blowdown {self.percent_blowdown:.1f}%)")
        sw.row("Hot water in", self.hot_water_return_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Hot water temperature", self.hot_water_return_temp_F, "°F", fmt="0.0")
        sw.row("Cool water temperature", self.cool_water_temp_F, "°F", fmt="0.0")
        sw.row("Blowdown", self.blowdown_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Blowdown", self.blowdown_lb_hr / self._GPM, "GPM", fmt="#,##0")
        sw.row("Evaporated to atmosphere", self.evaporated_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Cool water from tower", self.cool_water_from_tower_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Cool water from tower", self.cool_water_from_tower_lb_hr / self._GPM, "GPM", fmt="#,##0")

        sw.section("SYSTEM BALANCE")
        sw.row("Cold water demand (condensers)", self.total_injection_water_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Cool water available (tower)", self.cool_water_from_tower_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Makeup water required", self.makeup_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Makeup water required", self.makeup_lb_hr / self._GPM, "GPM", fmt="#,##0")
        sw.row("Makeup water temperature", self.makeup_temp_F, "°F", fmt="0.0")
        sw.row("Injection Water",
               self.delivered_water_temp_F, "°F", fmt="0.0")
        sw.row("Surplus (overflow)", self.surplus_lb_hr, "lb/hr", fmt="#,##0")
        bal = self.balance_check
        sw.row("Water in (vapor + makeup)", bal['in_lb_hr'], "lb/hr", fmt="#,##0")
        sw.row("Water out (evap + BD + surplus)", bal['out_lb_hr'], "lb/hr", fmt="#,##0")
        sw.row("Net (In - Out)", bal['diff_lb_hr'], "lb/hr", fmt="#,##0.00")

        ws = sw.finish()
        col_widths_px = {'A': 198, 'B': 184, 'C': 62, 'D': 78, 'E': 109,
                         'F': 98, 'G': 96, 'H': 87, 'I': 98}
        for letter, px in col_widths_px.items():
            ws.column_dimensions[letter].width = (px - 5) / 7
        return ws


if __name__ == "__main__":
    from Condenser import Condenser
    from SteamStream import EvaporatorSteam
    from evaporator_functions import convert_inHg_vacuum_to_psia

    # Stand-ins for the factory's condensers — in the real balance these come
    # from pan_floor.pan_condensers and [(s.name, s.condenser) for s in sets].
    demo = [
        ("Set 1 Condenser", Condenser(EvaporatorSteam(convert_inHg_vacuum_to_psia(25), flow_lb_per_hr=60_000), 90)),
        ("Set 2 Condenser", Condenser(EvaporatorSteam(convert_inHg_vacuum_to_psia(25), flow_lb_per_hr=35_000), 90)),
        ("A Pans",          Condenser(EvaporatorSteam(convert_inHg_vacuum_to_psia(23.5), flow_lb_per_hr=55_000), 90)),
        ("B Pans",          Condenser(EvaporatorSteam(convert_inHg_vacuum_to_psia(25), flow_lb_per_hr=25_000), 90)),
        ("C Pans",          Condenser(EvaporatorSteam(convert_inHg_vacuum_to_psia(26.5), flow_lb_per_hr=15_000), 90)),
    ]

    cts = CoolingTowerSystem(condensers=demo, cool_water_temp_F=90,
                             percent_blowdown=10.0, makeup_water_temp_F=75)
    print(cts)
    cts.neat_display()

    # Excel export demo — one workbook, this unit on its own sheet
    from excel_export import new_workbook
    wb = new_workbook()
    cts.to_excel(wb)
    wb.save("cooling_tower_system.xlsx")
    print("\nSaved cooling_tower_system.xlsx")
