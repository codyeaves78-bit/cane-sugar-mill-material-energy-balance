import math

from SteamStream import SteamStream

class WaterCooler:
    """Water-to-water cooler using an enthalpy balance without heat losses."""

    def __init__(self, T_ci, T_co, T_hi, T_ho, gpm_h, psia_h, psia_c, U):
        """
        Initialize the water cooler class
        All temperatures in deg F
        T_ci: cold fluid temperature in
        T_co: cold fluid temperature out
        T_hi: hot fluid temperature in
        T_ho: hot fluid temperature out
        gpm_h: hot fluid inlet flowrate in US gal/min
        psia_h: hot fluid absolute pressure in psi
        psia_c: cold fluid absolute pressure in psi
        U: overall heat transfer coefficient in BTU/(ft²·h·°F)
        Surface sizing assumes countercurrent flow (correction factor = 1).
        """
        self.T_ci = T_ci
        self.T_co = T_co
        self.T_hi = T_hi
        self.T_ho = T_ho
        self.gpm_h = gpm_h
        self.psia_h = psia_h
        self.psia_c = psia_c
        self.U = U
    
    @property
    def rho_h(self):
        """Hot fluid inlet density in lb/US gal."""
        return SteamStream(T=self.T_hi, P=self.psia_h).rho * 0.133681 # lb/gal
    
    @property
    def rho_c(self):
        """Cold fluid inlet density in lb/US gal."""
        return SteamStream(T=self.T_ci, P=self.psia_c).rho * 0.133681

    @property
    def lb_hr_h(self):
        """Hot fluid mass flowrate in lb/hr."""
        return self.gpm_h * 60 * self.rho_h
    
    @property
    def duty_btu_hr(self):
        """Heat removed from the hot fluid in BTU/hr."""
        hot_in = SteamStream(T=self.T_hi, P=self.psia_h)
        if hot_in.x > 0:
            print(f"Warning, hot fluid in is either flashing or is steam, quality {hot_in.x} > 0")
        hot_out = SteamStream(T=self.T_ho, P=self.psia_h)
        if hot_out.x > 0:
            print(f"Warning, hot fluid out is either flashing or is steam, quality {hot_out.x} > 0")

        return self.lb_hr_h * (hot_in.h - hot_out.h)
    
    @property
    def lb_hr_c(self):
        """Cold fluid mass flowrate required by the heat balance in lb/hr."""
        cold_in = SteamStream(T=self.T_ci, P=self.psia_c)
        if cold_in.x > 0:
            print(f"Warning, cold fluid in is either flashing or is steam, quality {cold_in.x} > 0")
        cold_out = SteamStream(T=self.T_co, P=self.psia_c)
        if cold_out.x > 0:
            print(f"Warning, cold fluid out is either flashing or is steam, quality {cold_out.x} > 0")

        enthalpy_rise = cold_out.h - cold_in.h
        if enthalpy_rise <= 0:
            raise ValueError("Cold fluid outlet enthalpy must exceed inlet enthalpy.")
        return self.duty_btu_hr / enthalpy_rise
    
    @property
    def gpm_c(self):
        """Cold fluid inlet volumetric flowrate in US gal/min."""
        return self.lb_hr_c / 60 / self.rho_c

    @property
    def lmtd(self):
        """Countercurrent log mean temperature difference in °F."""
        delta_1 = self.T_hi - self.T_co
        delta_2 = self.T_ho - self.T_ci
        if not all(math.isfinite(d) and d > 0 for d in (delta_1, delta_2)):
            raise ValueError("Countercurrent terminal temperature differences must be finite and positive.")
        if math.isclose(delta_1, delta_2, rel_tol=1e-9):
            return (delta_1 + delta_2) / 2
        return (delta_1 - delta_2) / (math.log(delta_1) - math.log(delta_2))

    @property
    def heating_surface_ft2(self):
        """Required heat transfer area in ft², with LMTD correction factor = 1."""
        if not math.isfinite(self.U) or self.U <= 0:
            raise ValueError("U must be finite and positive in BTU/(ft²·h·°F).")
        return self.duty_btu_hr / (self.U * self.lmtd)

    def show_properties(self):
        """Print all inputs and calculated properties with their units."""
        sections = {
            "Inputs": [
                ("T_ci", "Cold inlet temperature", self.T_ci, "°F"),
                ("T_co", "Cold outlet temperature", self.T_co, "°F"),
                ("T_hi", "Hot inlet temperature", self.T_hi, "°F"),
                ("T_ho", "Hot outlet temperature", self.T_ho, "°F"),
                ("gpm_h", "Hot inlet flowrate", self.gpm_h, "US gal/min"),
                ("psia_h", "Hot pressure", self.psia_h, "psia"),
                ("psia_c", "Cold pressure", self.psia_c, "psia"),
                ("U", "Overall heat transfer coefficient", self.U, "BTU/(ft²·h·°F)"),
            ],
            "Calculated properties": [
                ("rho_h", "Hot inlet density", self.rho_h, "lb/US gal"),
                ("rho_c", "Cold inlet density", self.rho_c, "lb/US gal"),
                ("lb_hr_h", "Hot mass flowrate", self.lb_hr_h, "lb/hr"),
                ("duty_btu_hr", "Heat duty", self.duty_btu_hr, "BTU/hr"),
                ("lb_hr_c", "Cold mass flowrate", self.lb_hr_c, "lb/hr"),
                ("gpm_c", "Cold inlet flowrate", self.gpm_c, "US gal/min"),
                ("lmtd", "Countercurrent LMTD", self.lmtd, "°F"),
                ("heating_surface_ft2", "Heating surface (F = 1)", self.heating_surface_ft2, "ft²"),
            ],
        }
        rows = [row for section in sections.values() for row in section]
        name_width = max(len("Property"), *(len(row[0]) for row in rows))
        label_width = max(len("Description"), *(len(row[1]) for row in rows))
        value_width = max(len("Value"), *(len(f"{row[2]:,.2f}") for row in rows))
        header = (
            f"{'Property':<{name_width}}  {'Description':<{label_width}}  "
            f"{'Value':>{value_width}}  Units"
        )
        print("Water Cooler")
        for section, properties in sections.items():
            print(f"\n{section}")
            print(header)
            print("-" * (len(header) + 5))
            for name, label, value, unit in properties:
                print(
                    f"{name:<{name_width}}  {label:<{label_width}}  "
                    f"{value:>{value_width},.2f}  {unit}"
                )


if __name__ == "__main__":
    floc_water_cooler = WaterCooler(
        T_ci=90, T_co=110, T_hi=205, T_ho=120,
        gpm_h=75, psia_c=70, psia_h=40,
        U=140,  # Illustrative value; replace with the design coefficient.
    )
    floc_water_cooler.show_properties()
