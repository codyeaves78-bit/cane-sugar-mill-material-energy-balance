# Evaporator class for modeling steam evaporator behavior and multiple effect evaporators
from SugarStream import SugarStream
from SteamStream import EvaporatorSteam, SteamStream
from evaporator_functions import calculate_U_dessin, calculate_U_heat_xfer, convert_inHg_vacuum_to_psia, convert_psig_to_psia

class Evaporator:
    """Class to represent a Robert Evaporator"""
    def __init__(self, 
                 juice_side_in: SugarStream, 
                 calandria_side: EvaporatorSteam, 
                 area_ft2=1, 
                 liquid_level_ft=2, 
                 dessin_coefficient=18000, 
                 vapor_pressure_psia=14.7,
                 vapor_bleed=0,
                 condensate_temp_drop=False,
                 heat_loss_percent=3.0,
                 calandria_bleed_pec=1.0,
                 cond_flash_to_next=False):
        self.juice_side_in = juice_side_in
        self.calandria_side = calandria_side
        self.area_ft2 = area_ft2
        self.dessin_coefficient = dessin_coefficient
        self.vapor_pressure_psia = vapor_pressure_psia
        self.liquid_level_ft = liquid_level_ft
        self.juice_side_out = SugarStream(
            brix=self._initial_brix_guess_out(),
            purity=self.juice_side_in.purity,
            flow_lb_per_hr=self.juice_side_in.flow_lb_per_hr,
            temp_deg_F=self.juice_side_in.temp_deg_F,
            pressure_psia=self.vapor_pressure_psia,
            level_ft=self.liquid_level_ft
        ) # initial juice_side_out instance, will update later on
        # set the initial juice out temp to the boiling point elevation + vapor saturation temp, which is a reasonable starting point for the calculations    
        self.juice_side_out.current_temp_to_bpe_plus_vapor_temp() 
        self.vapor_out = EvaporatorSteam(P_psia=self.vapor_pressure_psia, flow_lb_per_hr=0)
        self.vapor_bleed = EvaporatorSteam(P_psia=self.vapor_pressure_psia, flow_lb_per_hr=vapor_bleed)
        self.condensate_temp_drop = condensate_temp_drop # true or false

    def _initial_brix_guess_out(self):
        """Calculate an initial guess for the outlet brix using the heat duty and latent heat"""
        flow_out_lb_per_hr_initial = self.juice_side_in.flow_lb_per_hr - self.calandria_side.flow_lb_per_hr 
        solids_lb_per_hour = self.juice_side_in.flow_lb_per_hr * self.juice_side_in.brix / 100
        brix_out_guess = solids_lb_per_hour / flow_out_lb_per_hr_initial * 100 if flow_out_lb_per_hr_initial > 0 else self.juice_side_in.brix
        return brix_out_guess

    @property
    def heat_duty_btu_per_hr(self):
        """Calculate the heat duty in BTU/hr"""
        Q = self.calandria_side.flow_lb_per_hr * self.calandria_side.h_fg
        return Q
    
    @property
    def lbs_evaporated_per_hr(self):
        """Calculate the pounds of juice evaporated per hour"""
        juice_side_temp_rise = - self.juice_side_out.temp_deg_F + self.juice_side_in.temp_deg_F # positive if flashing
        h_fg_juice_vapors = self.juice_side_out.latent_heat_btu_per_lb 
        cp_juice = self.juice_side_in.cp_btu_per_lb_deg_F
        heat_from_flash = self.juice_side_in.flow_lb_per_hr * cp_juice * juice_side_temp_rise
        heat_for_evaporation = self.heat_duty_btu_per_hr + heat_from_flash # deduct if heating juices
        lbs_evap = heat_for_evaporation / h_fg_juice_vapors
        return lbs_evap
    
    @property
    def heat_from_flash(self):
        """Calculate the heat from flash"""
        juice_side_temp_rise = - self.juice_side_out.temp_deg_F + self.juice_side_in.temp_deg_F # positive if flashing
        cp_juice = self.juice_side_in.cp_btu_per_lb_deg_F
        heat_from_flash = self.juice_side_in.flow_lb_per_hr * cp_juice * juice_side_temp_rise
        return heat_from_flash

    @property
    def condensate_temperature(self):
        T_stm = self.calandria_side.sat_temp_deg_F
        T_j = self.juice_side_out.temp_deg_F
        temp_drop = T_stm - 0.4 * (T_stm - T_j)
        cond_temp = T_stm - temp_drop
        return cond_temp if self.condensate_temp_drop == True else T_stm
        
    @property
    def heat_available_for_evaporation(self):
        """Calculate the heat available for evaporation"""
        heat_available_for_evaporation = self.heat_duty_btu_per_hr + self.heat_from_flash
        return heat_available_for_evaporation

    @property
    def brix_out(self):
        """Calculate the outlet brix based on the pounds evaporated and the inlet properties"""
        flow_out_lb_per_hr = self.juice_side_in.flow_lb_per_hr - self.lbs_evaporated_per_hr
        solids_lb_per_hour = self.juice_side_in.flow_lb_per_hr * self.juice_side_in.brix / 100
        brix_out = solids_lb_per_hour / flow_out_lb_per_hr * 100 if flow_out_lb_per_hr > 0 else self.juice_side_in.brix
        return brix_out
    
    @property
    def delta_T_juice_steam(self):
        """Calculates the difference between hot and cold side"""
        return self.calandria_side.sat_temp_deg_F - self.juice_side_out.temp_deg_F
    
    @property
    def dessin_U(self):
        """Calculate the overall heat transfer coefficient using Dessin's method"""
        u = calculate_U_dessin(
            brix_out=self.brix_out,
            calandria_temp_deg_F=self.calandria_side.sat_temp_deg_F,
            h_fg_juice_vapors=self.juice_side_out.latent_heat_btu_per_lb,
            dessin_coefficient=self.dessin_coefficient
        )
        return u
    
    @property
    def heat_xfer_U(self):
        """Calculates the OHTC via the basic Q=UAdT equation"""
        u = calculate_U_heat_xfer(
            heat_duty_btu_per_hr=self.heat_duty_btu_per_hr,
            area_ft2=self.area_ft2,
            temp_diff_deg_F= self.calandria_side.sat_temp_deg_F - self.juice_side_out.temp_deg_F  
        )
        return u
    
    @property
    def U_ratio(self):
        """U_calc / U_dessin"""
        return self.heat_xfer_U / self.dessin_U
    
    @property
    def bpe_juice(self):
        return self.juice_side_out.boiling_point_elevation_deg_F
    
    @property
    def vapor_temperature(self):
        return self.juice_side_out.vapor_saturation_temp_deg_F
    
    @property
    def condensate_out(self):
        return self.calandria_side.flow_lb_per_hr
    
    def _update_juice_side_out(self, lbs_evap):
        """Update the juice_side_out properties based on the current calculations"""
        flow_out = self.juice_side_in.flow_lb_per_hr - lbs_evap
        solids   = self.juice_side_in.flow_lb_per_hr * self.juice_side_in.brix / 100
        self.juice_side_out.brix = solids / flow_out * 100 if flow_out > 0 else self.juice_side_in.brix
        self.juice_side_out.flow_lb_per_hr = flow_out
        self.juice_side_out.pressure_psia = self.vapor_pressure_psia
        self.juice_side_out.level_ft = self.liquid_level_ft
        self.juice_side_out.current_temp_to_bpe_plus_vapor_temp()

    def _update_vapor_out(self, lbs_evap):
        """Update the vapor_out properties based on the current calculations"""
        self.vapor_out.P_psia = self.vapor_pressure_psia
        self.vapor_out.flow_lb_per_hr = lbs_evap

    def solve(self):
        """Compute evaporation once and push to vapor_out and juice_side_out"""
        lbs_evap = self.lbs_evaporated_per_hr
        self._update_vapor_out(lbs_evap)
        self._update_juice_side_out(lbs_evap)

    def __repr__(self):
        return (f"Evaporator(juice_side_in={self.juice_side_in}, calandria_side={self.calandria_side}, "
                f"area_ft2={self.area_ft2}, liquid_level_ft={self.liquid_level_ft}, "
                f"vapor_pressure_psia={self.vapor_pressure_psia})")
    
    def properties(self) -> dict:
        cls = type(self)
        prop_names = [k for k, v in vars(cls).items() if isinstance(v, property)]
        instance_vars = {k: v for k, v in vars(self).items() if not k.startswith('_')}
        return {**instance_vars, **{k: getattr(self, k) for k in prop_names}}
    
    def display_properties(self):
        props = self.properties()
        print("Units: T(°F), P(psia), h_fg(BTU/lb)")
        for key, value in props.items():
            formatted = f"{value:,.2f}" if isinstance(value, (int, float)) else str(value)
            print(f"{key}: {formatted}")
        print("\n Juice In details: \n")
        self.juice_side_in.display_properties()
        print("\n Juice Out details: \n")
        self.juice_side_out.display_properties()
        print("\n Steam In details: \n")
        self.calandria_side.display_properties()
        print("\n Steam Out details: \n")
        self.vapor_out.display_properties()
        print("\n Material and Energy Balance\n")
        print(f"Entering: {self.calandria_side.flow_lb_per_hr:,.2f} lb/hr * {self.calandria_side.h_fg:,.2f} BTU/lb = {self.heat_duty_btu_per_hr:,.2f} BTU/hr")
        print(f"Plus: {self.juice_side_in.flow_lb_per_hr:,.2f} lb/hr * {self.juice_side_in.cp_btu_per_lb_deg_F:,.2f} BTU/lb * ({self.juice_side_in.temp_deg_F - self.juice_side_out.temp_deg_F:,.2f}°F) = {self.heat_from_flash:,.2f} BTU/hr")
        print(f"Available for Evaporation: {self.heat_duty_btu_per_hr:,.2f} + {self.heat_from_flash:,.2f} = {self.heat_available_for_evaporation:,.2f} BTU/hr")

# Test below, unwrap to see outputs
if __name__ == "__main__":
    clear_juice = SugarStream(brix=14, purity=90, flow_lb_per_hr=1_000_000, temp_deg_F=225, pressure_psia=60, level_ft=0)
    exhaust_steam_evaporator = EvaporatorSteam(P_psia=30, flow_lb_per_hr=100000)
    evaporator = Evaporator(
        juice_side_in=clear_juice,
        calandria_side=exhaust_steam_evaporator,
        area_ft2=25000,
        liquid_level_ft=2,
        dessin_coefficient=18000,
        vapor_pressure_psia=25
    )

    evaporator.solve()
    evaporator.display_properties()
    print("\n adjusting vapor pressure \n")
    evaporator.vapor_pressure_psia = 22
    evaporator.solve()
    evaporator.display_properties()

