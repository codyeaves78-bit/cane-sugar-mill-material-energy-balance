# Barometric condenser object for vacuum pan / evaporator systems.
# Outlet water is below vapor saturation temperature by the specified downleg ΔT.
# Cp of water taken as 1.0 BTU/(lb·°F) — accurate to <0.2% in the typical range.

from SteamStream import EvaporatorSteam


class Condenser:
    """
    Barometric condenser — condenses incoming vapor with cold injection water.

    vapor             : EvaporatorSteam or SteamStream with flow_lb_per_hr set
    water_inlet_temp_F: temperature of the injection water supply (°F)

    water_outlet_temp_drop_F: downleg temperature below vapor saturation (°F),
                             default 5. Outlet water and condensate are mixed.

    Energy balance:
        T_out = T_sat - water_outlet_temp_drop_F
        m_vap × (h_fg + Cp × water_outlet_temp_drop_F)
            = m_water × Cp × (T_out - T_water_in)          [Cp = 1.0 BTU/lb·°F]
    """

    _CP_WATER = 1.0  # BTU / (lb·°F)

    _LABELS = {
        'vapor_sat_temp_F':           'Vapor Saturation Temp (°F)',
        'vapor_h_fg_btu_lb':          'Vapor h_fg (BTU/lb)',
        'vapor_flow_lb_hr':           'Vapor Flow (lb/hr)',
        'heat_load_btu_hr':           'Heat Load (BTU/hr)',
        'water_inlet_temp_F':         'Injection Water Inlet (°F)',
        'water_outlet_temp_F':        'Water Outlet Temp (°F)',
        'injection_water_flow_lb_hr': 'Injection Water Flow (lb/hr)',
        'total_outlet_flow_lb_hr':    'Total Outlet Flow (lb/hr)',
    }

    def __init__(self, vapor, water_inlet_temp_F, water_outlet_temp_drop_F=5):
        self.vapor = vapor
        self.water_inlet_temp_F = water_inlet_temp_F
        self.water_out_temp_drop_F = water_outlet_temp_drop_F # degrees below the vapor temp

    # ------------------------------------------------------------------
    # Vapor properties (supports both EvaporatorSteam and SteamStream)
    # ------------------------------------------------------------------

    @property
    def vapor_sat_temp_F(self):
        """Saturation temperature of the incoming vapor (°F)."""
        if hasattr(self.vapor, 'sat_temp_deg_F'):
            return self.vapor.sat_temp_deg_F   # EvaporatorSteam
        return self.vapor.T                     # SteamStream at sat. conditions

    @property
    def vapor_flow_lb_hr(self):
        return self.vapor.flow_lb_per_hr

    @property
    def vapor_h_fg_btu_lb(self):
        return self.vapor.h_fg

    # ------------------------------------------------------------------
    # Energy & mass balance
    # ------------------------------------------------------------------

    @property
    def heat_load_btu_hr(self):
        """Total heat removed from the vapor (BTU/hr)."""
        return self.vapor_flow_lb_hr * self.vapor_h_fg_btu_lb + self._CP_WATER * self.vapor_flow_lb_hr * self.water_out_temp_drop_F # basically h_fg + h_sens

    @property
    def water_outlet_temp_F(self):
        """Outlet temperature of the water/condensate mixture (°F)."""
        return self.vapor_sat_temp_F - self.water_out_temp_drop_F

    @property
    def injection_water_flow_lb_hr(self):
        """Injection water required to condense the vapor (lb/hr)."""
        delta_T = (self.vapor_sat_temp_F - self.water_out_temp_drop_F) - self.water_inlet_temp_F
        if delta_T <= 0:
            raise ValueError(
                f"Injection water inlet ({self.water_inlet_temp_F}°F) must be "
                f"below condenser downleg outlet temp ({self.water_outlet_temp_F:.2f}°F)."
            )
        return self.heat_load_btu_hr / (self._CP_WATER * delta_T)

    @property
    def total_outlet_flow_lb_hr(self):
        """Total flow leaving the condenser — condensate + injection water (lb/hr)."""
        return self.injection_water_flow_lb_hr + self.vapor_flow_lb_hr

    # ------------------------------------------------------------------
    # Dunder / display
    # ------------------------------------------------------------------

    def __repr__(self):
        return (f"Condenser(vapor_sat_temp={self.vapor_sat_temp_F:.1f}°F, "
                f"water_inlet={self.water_inlet_temp_F}°F, "
                f"vapor_flow={self.vapor_flow_lb_hr:,.0f} lb/hr)")

    def properties(self):
        return {
            'vapor_sat_temp_F':          self.vapor_sat_temp_F,
            'vapor_h_fg_btu_lb':         self.vapor_h_fg_btu_lb,
            'vapor_flow_lb_hr':          self.vapor_flow_lb_hr,
            'heat_load_btu_hr':          self.heat_load_btu_hr,
            'water_inlet_temp_F':        self.water_inlet_temp_F,
            'water_outlet_temp_F':       self.water_outlet_temp_F,
            'injection_water_flow_lb_hr': self.injection_water_flow_lb_hr,
            'total_outlet_flow_lb_hr':   self.total_outlet_flow_lb_hr,
        }

    def display_properties(self):
        props = self.properties()
        print("Units: T(°F), flow(lb/hr), h_fg(BTU/lb), heat_load(BTU/hr)")
        for k, v in props.items():
            print(f"  {k:<30}: {v:,.2f}")

    def neat_display(self):
        print("Condenser Summary:")
        for key, value in self.properties().items():
            label = self._LABELS.get(key, key.replace('_', ' ').title())
            print(f"  {label}: {value:,.2f}")


if __name__ == "__main__":
    # Example: 50,000 lb/hr of vapor at 26.5 in Hg vacuum, 75°F injection water
    vapor = EvaporatorSteam(P_psia=14.696 - 26.5 * 0.491154, flow_lb_per_hr=50_000)
    cond  = Condenser(vapor, water_inlet_temp_F=75, water_outlet_temp_drop_F=5)
    print(cond)
    print()
    cond.neat_display()
