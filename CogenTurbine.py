# Cogen turbine: identical thermodynamics to Turbine, but sized by electrical
# (generator) output in kW instead of mechanical shaft horsepower — the
# natural input when a turbine's whole job is spinning a generator.

from Turbine import Turbine
from SteamStream import SteamStream

_KW_PER_HP = 0.7456998715822702  # 1 mechanical HP = 0.7456998715822702 kW


class CogenTurbine(Turbine):
    """
    Steam turbine sized by electrical output instead of shaft HP.

    inlet_steam           : SteamStream at live steam conditions
    outlet_pressure_psia  : desired exhaust (back) pressure (psia)
    isentropic_efficiency : turbine isentropic efficiency (0-1, e.g. 0.75)
    kw_demand             : electrical power output required (kW)
                            -> converted to the equivalent hp_demand so every
                               Turbine calculation (flow, exhaust, steam
                               rate, etc.) runs exactly as it does on Turbine

    Everything else — inlet_steam, outlet_pressure_psia,
    isentropic_efficiency, desuperheating_water_temp — behaves exactly as it
    does on Turbine; only the input unit and the display/export methods
    (which report kW instead of HP) differ.
    """

    def __init__(self, inlet_steam, outlet_pressure_psia, isentropic_efficiency,
                 kw_demand, name="Cogen Turbine", desuperheating_water_temp=212):
        super().__init__(
            inlet_steam=inlet_steam,
            outlet_pressure_psia=outlet_pressure_psia,
            isentropic_efficiency=isentropic_efficiency,
            hp_demand=kw_demand / _KW_PER_HP,
            name=name,
            desuperheating_water_temp=desuperheating_water_temp,
        )

    # ------------------------------------------------------------------
    # Electrical output
    # ------------------------------------------------------------------

    @property
    def kw_output(self):
        """Electrical output (kW) — the kW equivalent of hp_demand."""
        return self.hp_demand * _KW_PER_HP

    @property
    def steam_rate_kw(self):
        """Steam rate (lb steam / kW-hr) — the electrical-output analogue of steam_rate."""
        return self.steam_flow_lb_hr / self.kw_output

    # ------------------------------------------------------------------
    # Dunder / display
    # ------------------------------------------------------------------

    def __repr__(self):
        return (
            f"CogenTurbine(P_in={self.inlet_steam.P:.1f} psia -> "
            f"P_out={self.outlet_pressure_psia:.1f} psia, "
            f"eta={self.isentropic_efficiency:.0%}, "
            f"kW={self.kw_output:,.0f})"
        )

    def properties(self):
        props = super().properties()
        props['kw_output'] = self.kw_output
        props['steam_rate_lb_per_kw_hr'] = self.steam_rate_kw
        return props

    def neat_display(self):
        exhaust = self.exhaust_steam

        def fmt_x(x):
            return "Superheat" if x is None or x >= 1.0 else f"{x:.4f}"

        C0, C1, C2, C3, C4 = 5, 9, 10, 16, 10
        sep = "-"*C0 + "-+-" + "-"*C1 + "-+-" + "-"*C2 + "-+-" + "-"*C3 + "-+-" + "-"*C4
        W   = len(sep)
        div = "=" * W

        hdr = (f"{'':>{C0}} | {'psia':^{C1}} | {'temp °F':^{C2}} | "
               f"{'enthalpy BTU/lb':^{C3}} | {'quality':^{C4}}")

        def drow(label, P, T, h, x):
            return (f"{label:>{C0}} | {P:>{C1},.1f} | {T:>{C2},.1f} | "
                    f"{h:>{C3},.2f} | {fmt_x(x):^{C4}}")

        summary = (f"Steam Rate: {self.steam_rate_kw:,.2f} lb/kW-hr  |  "
                   f"kW: {self.kw_output:,.0f}  |  "
                   f"Flow: {self.steam_flow_lb_hr:,.0f} lb/hr  |  "
                   f"Eff: {self.isentropic_efficiency:.1%}")

        exhaust_line = f"Exhaust for Process: {self.exhaust_available:,.0f} lb/hr"
        is_superheated = exhaust.x is None or exhaust.x >= 1.0
        if is_superheated:
            dsw = self.exhaust_available - exhaust.flow_lb_per_hr
            exhaust_line += f"  |  Desuperheater Water: {dsw:,.0f} lb/hr"

        print(div)
        print(f"COGEN TURBINE  —  {self.name.upper()}".center(W))
        print(div)
        print(hdr)
        print(sep)
        print(drow("IN",  self.inlet_steam.P, self.inlet_steam.T, self.h_in,        self.inlet_steam.x))
        print(drow("OUT", self.outlet_pressure_psia, exhaust.T,   self.h_out_actual, exhaust.x))
        print(div)
        print(summary)
        print(exhaust_line)
        print(div)

    # ------------------------------------------------------------------
    # PFD / Excel export
    # ------------------------------------------------------------------

    def generate_pfd(self, show=True, save_path=None):
        """Generate a process flow diagram (turbine + generator). Returns the Figure."""
        from cogen_turbine_diagram import plot_cogen_turbine
        return plot_cogen_turbine(self, show=show, save_path=save_path)

    def to_excel(self, workbook, sheet_writer=None, name=None):
        """Write this cogen turbine to its own styled sheet (PFD, streams,
        and performance). Pass an existing SheetWriter to append onto a
        shared sheet instead of creating a new one."""
        from cogen_turbine_diagram import cogen_turbine_to_excel
        return cogen_turbine_to_excel(self, workbook, sheet_writer=sheet_writer, name=name)


if __name__ == "__main__":
    # Example: 600 psia / 750°F live steam expanding to 30 psia back pressure
    # 75% isentropic efficiency, sized for a 3500 kW generator
    live_steam = SteamStream(x=1, P=180)
    cogen = CogenTurbine(
        inlet_steam=live_steam,
        outlet_pressure_psia=32,
        isentropic_efficiency=0.6,
        kw_demand=3500,
    )
    print(cogen)
    print()
    cogen.neat_display()
    print()
    print("Exhaust steam:")
    cogen.exhaust_steam.display_properties()
    cogen.generate_pfd()
