# Evaporator class for modeling steam evaporator behavior and multiple effect evaporators
from Condenser import Condenser
from SugarStream import SugarStream
from SteamStream import EvaporatorSteam, SteamStream
from Evaporator import Evaporator
from evaporator_functions import (initial_brix_profile, pressure_profile_initial,
                                  shortcut_evaporator_steam, convert_inHg_vacuum_to_psia,
                                  convert_psig_to_psia, convert_psia_to_psig,
                                  convert_psia_to_inHgVac)
from condensate_utils import flash_condensate
import time
from statistics import stdev

class EvaporatorSet:
    """
    Model of a multiple-effect evaporator set.

    Solves the rigorous heat and material balance across all effects, iterating
    on steam flow (to hit a target syrup brix) and on the pressure profile
    (to equalise U ratios across effects per the Dessin equation).

    Examples
    --------
    Basic triple effect, no bleeds::

        from EvaporatorSet import EvaporatorSet
        from SugarStream import SugarStream
        from SteamStream import EvaporatorSteam
        from evaporator_functions import convert_inHg_vacuum_to_psia, convert_psig_to_psia

        juice = SugarStream(brix=12, purity=90, flow_lb_per_hr=200_000,
                            temp_deg_F=225, pressure_psia=60, level_ft=0)
        steam = EvaporatorSteam(P_psia=convert_psig_to_psia(20), flow_lb_per_hr=0)

        evap_set = EvaporatorSet(
            juice_in=juice,
            supply_steam=steam,
            last_effect_pressure_psia=convert_inHg_vacuum_to_psia(26),
            target_brix_out=60,
            effect_areas_ft2=[4800, 4800, 4800],
            name="Triple Effect",
        )
        evap_set.adjust_pressure_profile()
        evap_set.neat_display()
        evap_set.generate_pfd()

    With vapor bleeds (first-effect bleed to heaters and pans)::

        evap_set = EvaporatorSet(
            juice_in=juice,
            supply_steam=steam,
            last_effect_pressure_psia=convert_inHg_vacuum_to_psia(26),
            target_brix_out=60,
            effect_areas_ft2=[8800, 3100, 3100],
            vapor_bleeds=[31_357 + 3_895 + 28_108],
            name="Triple — V1 Bleed",
        )
        evap_set.adjust_pressure_profile()
        evap_set.neat_display()

    With a pre-evaporator::

        from PreEvaporator import PreEvaporator

        pre = PreEvaporator(
            juice_in=juice,
            supply_steam=EvaporatorSteam(P_psia=convert_psig_to_psia(20), flow_lb_per_hr=0),
            vapor_bleed_lb_per_hr=35_252,
            area_ft2=3_300,
        )
        evap_set = EvaporatorSet(
            juice_in=pre.juice_out,
            supply_steam=steam,
            last_effect_pressure_psia=convert_inHg_vacuum_to_psia(26),
            target_brix_out=60,
            effect_areas_ft2=[3800, 3800, 3800],
            name="Pre-evap + Triple",
        )
        evap_set.adjust_pressure_profile()
        evap_set.generate_pfd(pre_evap=pre)

    With shell heat loss, calandria gas bleed, and condensate flash recovery::

        evap_set = EvaporatorSet(
            juice_in=juice,
            supply_steam=steam,
            last_effect_pressure_psia=convert_inHg_vacuum_to_psia(26),
            target_brix_out=60,
            effect_areas_ft2=[4800, 4800, 4800],
            incond_gas_bleed_percent=1.0,       # % of each calandria's steam vented to purge incondensables
            heat_loss_percent=[0.0, 2.5, 2.0],  # per-effect vessel shell loss; effect 1 stays at 0
            recover_condensate_flash=True,      # let calandria condensate self-flash to the next effect
            name="Triple — Heat Loss + Gas Bleed + Condensate Flash",
        )
        evap_set.adjust_pressure_profile()
        evap_set.neat_display()
    """
    def __init__(self, juice_in: SugarStream,
                 supply_steam: EvaporatorSteam,
                 last_effect_pressure_psia=2.4,
                 target_brix_out=65,
                 effect_areas_ft2=[1000, 1000, 1000],
                 vapor_bleeds=[0, 0],
                 incond_gas_bleed_percent=1.0,
                 heat_loss_percent=[0.0, 2.5, 2.0], # descends along each effect; effect 1 stays at 0, see note in build_effects
                 recover_condensate_flash=False,
                 condensate_temp_drop=True,
                 dessin_coefficient=18000,
                 liquid_level_ft=2,
                 injection_water_temp_F=90,
                 condenser_leg_temp_drop_F=5,
                 name: str = 'Evaporator Set',):
        """initialize class"""
        self.name = name
        self.juice_in = juice_in
        self.supply_steam = supply_steam
        self.last_effect_pressure_psia = last_effect_pressure_psia
        self.target_brix_out = target_brix_out
        self.effect_areas_ft2 = effect_areas_ft2
        self.vapor_bleeds = vapor_bleeds
        self.dessin_coefficient = dessin_coefficient
        self.liquid_level_ft = liquid_level_ft
        self.injection_water_temp_F = injection_water_temp_F
        self.condenser_leg_temp_drop_F = condenser_leg_temp_drop_F # degrees below the vapor temp
        self.number_of_effects = len(self.effect_areas_ft2)
        self.incond_gas_bleed_percent = incond_gas_bleed_percent
        self.heat_loss_percent = heat_loss_percent
        self.recover_condensate_flash = recover_condensate_flash
        self.condensate_temp_drop = condensate_temp_drop
        # 1. Package the shared arguments into a temporary dictionary
        evap_args = {
            "juice_in_lb_per_hr": self.juice_in.flow_lb_per_hr,
            "brix_in": self.juice_in.brix,
            "brix_out": self.target_brix_out,
            "number_of_effects": self.number_of_effects,
            "vapor_bleeds": self.vapor_bleeds
        }
        self.steam_initial_guess = shortcut_evaporator_steam(**evap_args)
        self.initial_brix_profile = initial_brix_profile(**evap_args)
        self.pressure_profile_initial = pressure_profile_initial(self.supply_steam.P_psia, self.last_effect_pressure_psia, self.number_of_effects)
        self.supply_steam.flow_lb_per_hr = self.steam_initial_guess
        self.build_effects()
    
    def _heat_loss_for_effect(self, i):
        """Vessel heat-loss % for effect i. Effect 1 defaults to 0 -- its calandria runs on fresh
        exhaust and is assumed well insulated, so losses are only counted from effect 2 onward
        (Hugot's convention). The list is padded with its last value if it's shorter than the set."""
        losses = self.heat_loss_percent
        if not losses:
            return 0.0
        return losses[i] if i < len(losses) else losses[-1]

    def _vapor_to_next_effect(self, i):
        """Vapor feeding effect i+1's calandria: effect i's evaporated vapor net of its own bleed,
        plus any calandria-condensate flash vapor recovered from effect i (if enabled)."""
        eff = self.evaporator_list[i]
        vapor = eff.lbs_evaporated_per_hr - eff.vapor_bleed.flow_lb_per_hr
        if self.recover_condensate_flash:
            vapor += eff.condensate_flash_vapor_lb_per_hr
        return vapor

    def build_effects(self):
        """Builds the evaporator effects objects and stores them in a list"""
        # print(f"Steam initial guess: {self.steam_initial_guess:,.1f} lb/hr")
        # print(f"Brix profile: {[f'{b:.1f}' for b in self.initial_brix_profile]}")
        # print(f"Pressure profile: {[f'{p:.2f}' for p in self.pressure_profile_initial]}")
        self.evaporator_list = [Evaporator(
            juice_side_in=self.juice_in,
            calandria_side=self.supply_steam,
            area_ft2=self.effect_areas_ft2[0],
            liquid_level_ft=self.liquid_level_ft,
            dessin_coefficient=self.dessin_coefficient,
            vapor_pressure_psia=self.pressure_profile_initial[1], # first list item is calandria, so second item [1] is first effect vapor pressure
            vapor_bleed=self.vapor_bleeds[0],
            heat_loss_percent=self._heat_loss_for_effect(0),
            calandria_bleed_pec=self.incond_gas_bleed_percent,
            condensate_temp_drop=self.condensate_temp_drop,
            cond_flash_to_next=self.recover_condensate_flash and self.number_of_effects > 1,
        )]

        self.evaporator_list[0].solve()

        for i in range(self.number_of_effects - 1):
            steam_to_next = self._vapor_to_next_effect(i)
            bled_vapor = self.vapor_bleeds[i+1] if i+1 < len(self.vapor_bleeds) else 0 # safety check if out of range
            is_last_effect = (i + 1) == self.number_of_effects - 1
            evaporator = Evaporator(
                juice_side_in=self.evaporator_list[i].juice_side_out,
                calandria_side=EvaporatorSteam(P_psia=self.pressure_profile_initial[i + 1],flow_lb_per_hr=steam_to_next), # recall, pressure profile list starts with supply steam
                area_ft2=self.effect_areas_ft2[i + 1],
                liquid_level_ft=self.liquid_level_ft,
                dessin_coefficient=self.dessin_coefficient,
                vapor_pressure_psia=self.pressure_profile_initial[i + 2], # remember, first list item is supply steam, so 2 list items down would be second eff vap press, so on and so forth
                vapor_bleed=bled_vapor,
                heat_loss_percent=self._heat_loss_for_effect(i + 1),
                calandria_bleed_pec=self.incond_gas_bleed_percent,
                condensate_temp_drop=self.condensate_temp_drop,
                cond_flash_to_next=self.recover_condensate_flash and not is_last_effect,
            )
        # note on the logic, okay look, if the number of effects is 3, then the list length of the pressure profile will be 4.
        # so the loop number in this case would be 3 - 1 = 2.
        # So that way, the calandria side on building evap effect 2 in the first loop (list item [1]) gets the second list item for juice_side_in
        # And the vapor_pressure_psia gets the third list item
        # the final loop logic will not be out of range because on the last loop (which means i=1, second loop because first i=0) i + 2 = 3,
        #  which is the 4th and last list item on the self.pressure_profile_initial list
            evaporator.solve()
            self.evaporator_list.append(evaporator)

    def update_steam_flow(self, new_steam_flow_lb_per_hr):
        """changes steam flow to the set and resolves the effects"""
        self.supply_steam.flow_lb_per_hr = new_steam_flow_lb_per_hr
        self.evaporator_list[0].calandria_side.flow_lb_per_hr = self.supply_steam.flow_lb_per_hr
        for i in range(self.number_of_effects - 1):
            self.evaporator_list[i+1].calandria_side.flow_lb_per_hr = self._vapor_to_next_effect(i)
        self.update_set()
        # Joke: what effect would effect 1 have on effect 2 while effectively bleeding effect 1 gases?
        # Answer: effectively just a little bit

    def update_set(self):
        for i in range(self.number_of_effects):
            self.evaporator_list[i].solve()

    def solve_for_steam(self):
        """Trial and error method to get the actual required steam flow rate"""
        # warm start: use current steam if already set, fall back to shortcut guess
        x_n_min_1 = self.supply_steam.flow_lb_per_hr if self.supply_steam.flow_lb_per_hr > 0 else self.steam_initial_guess
        self.update_steam_flow(x_n_min_1)
        max_iterations = 100
        tolerance = 0.0001 # higher or lower brix target difference
        current_iteration = 0
        f_x_n_min_1 = self.target_brix_out - self.evaporator_list[-1].juice_side_out.brix
        x_n = x_n_min_1 * 1.02
        while abs(self.brix_target_difference) >= tolerance and current_iteration < max_iterations:
            self.update_steam_flow(x_n)
            f_x_n = self.target_brix_out - self.evaporator_list[-1].juice_side_out.brix
            f_prime_x_n_min_1 = (f_x_n - f_x_n_min_1) / (x_n - x_n_min_1)
            x_n_min_1 = x_n
            x_n = x_n_min_1 - (f_x_n / f_prime_x_n_min_1)
            f_x_n_min_1 = f_x_n
            #print(f"Current guess: {x_n_min_1:,.2f} lb/hr | Difference: {self.brix_target_difference:,.4f} | Iteration: {current_iteration}")
            current_iteration += 1
        
        if abs(self.brix_target_difference) <= tolerance:
            pass # incase you want to take the # out of the print line
            #print(f"Convergence succesful! Final guess: {x_n_min_1:,.2f} lb/hr | Difference: {self.brix_target_difference:,.4f} | Iteration: {current_iteration}")
        else:
            #pass # incase you want to take the # out of the print line
            print(f"XXX Failure to converge! XXX : Final guess: {x_n_min_1:,.2f} lb/hr | Difference: {self.brix_target_difference:,.6f} | Iteration: {current_iteration}")
        self.update_steam_flow(x_n_min_1)  # apply last evaluated converged value, not the next extrapolation

    def adjust_pressure_profile(self):
        """Adjust the pressure profile based on the average_u_ratio / current body u_ratio"""
        self.update_set()
        # print(f"Initial pressure profiel: {self.pressure_profile_initial}")
        u_dessin_list = [evaporator.dessin_U for evaporator in self.evaporator_list]
        u_calc_list = [evaporator.heat_xfer_U for evaporator in self.evaporator_list]
        u_ratio_list = [float(u_calc / u_dessin) for u_calc, u_dessin in zip(u_calc_list, u_dessin_list)]
        average_u_ratio = sum(u_ratio_list) / len(u_ratio_list) # u_calc / u_dessin

        # adjust the pressures now
        pressure_iteration = 0
        max_pressure_iterations = 100
        # guard: stdev requires finite values; bail out if physics are invalid
        if not all(u == u and u != float('inf') and u != float('-inf') for u in u_ratio_list):
            print("Warning: non-finite U ratio encountered before pressure loop, skipping adjustment.")
            return
        while stdev(u_ratio_list) > 0.0001 and pressure_iteration < max_pressure_iterations:

            for i in range(self.number_of_effects - 1): # don't change last effect pressure
                ratio = average_u_ratio / u_ratio_list[i]
                if ratio > 0:  # skip adjustment if ratio is non-positive (avoids nan from negative base)
                    self.evaporator_list[i].vapor_pressure_psia *= ratio**0.1
                self.evaporator_list[i + 1].calandria_side.P_psia = self.evaporator_list[i].vapor_pressure_psia
            self.update_set()
            self.solve_for_steam()

            # update lists and average
            u_dessin_list = [evaporator.dessin_U for evaporator in self.evaporator_list]
            u_calc_list = [evaporator.heat_xfer_U for evaporator in self.evaporator_list]
            u_ratio_list = [float(u_calc / u_dessin) for u_calc, u_dessin in zip(u_calc_list, u_dessin_list)]
            average_u_ratio = sum(u_ratio_list) / len(u_ratio_list) # u_calc / u_dessin
            pressure_iteration += 1
            # bail out if nan/inf crept in during iteration
            if not all(u == u and u != float('inf') and u != float('-inf') for u in u_ratio_list):
                print("Warning: non-finite U ratio encountered during pressure adjustment, stopping early.")
                break
        current_pressure_list = [evaporator.vapor_pressure_psia for evaporator in self.evaporator_list]
        # print(f"Current pressure profile: {current_pressure_list} | Iterations to complete: {pressure_iteration}")
        # print(f"U ratio list: {u_ratio_list}")

    def manually_set_pressures(self, pressure_list):
        """Manually set the presure profile for testing purposes"""
        for i in range(self.number_of_effects - 1):
            self.evaporator_list[i].vapor_pressure_psia = pressure_list[i]
            self.evaporator_list[i + 1].calandria_side.P_psia = pressure_list[i]
        self.update_set()
        self.solve_for_steam()
    @property
    def total_hs(self):
        return sum(self.effect_areas_ft2)
    
    @property
    def hs_num_eff_ratio(self):
        return self.total_hs / self.number_of_effects
    
    @property
    def delta_P_set(self):
        return self.supply_steam.P_psia - self.last_effect_pressure_psia
    
    @property
    def weight_for_init_distr(self):
        return self.hs_num_eff_ratio * self.delta_P_set

    @property
    def brix_target_difference(self):
        return self.target_brix_out - self.evaporator_list[-1].juice_side_out.brix
    
    @property
    def U_ratio_avg(self):
        u_rat_list = [self.evaporator_list[i].U_ratio for i in range(self.number_of_effects)]
        u_avg = sum(u_rat_list) / self.number_of_effects
        return u_avg
    
    @property
    def condenser(self):
        """Condenser for the last effect's vapor (net of any last-effect bleed)."""
        last = self.evaporator_list[-1]
        to_condenser = EvaporatorSteam(
            P_psia=last.vapor_pressure_psia,
            flow_lb_per_hr=last.lbs_evaporated_per_hr - last.vapor_bleed.flow_lb_per_hr,
        )
        return Condenser(vapor=to_condenser, water_inlet_temp_F=self.injection_water_temp_F,
                         water_outlet_temp_drop_F=self.condenser_leg_temp_drop_F)
    
    @property
    def clean_condensate(self):
        """Post-flash condensate from the first effect (fresh exhaust) (lb/hr).
        Nets out incondensable-gas bleed and, if recover_condensate_flash is on, whatever already
        self-flashed off to the next effect's calandria before hitting atmospheric letdown."""
        eff = self.evaporator_list[0]
        return flash_condensate(eff.condensate_liquid_after_flash_lb_per_hr, eff.condensate_liquid_temp_after_flash_deg_F)

    @property
    def dirty_condensate(self):
        """Sum of post-flash condensate from effect 2 to the last effect (inter-effect vapor) (lb/hr)."""
        return sum(
            flash_condensate(eff.condensate_liquid_after_flash_lb_per_hr, eff.condensate_liquid_temp_after_flash_deg_F)
            for eff in self.evaporator_list[1:]
        )

    @property
    def total_condensate_flash_recovered(self):
        """Total vapor recovered across the set by letting calandria condensate self-flash down to
        the next effect's calandria pressure (lb/hr). Zero unless recover_condensate_flash is on."""
        return sum(eff.condensate_flash_vapor_lb_per_hr for eff in self.evaporator_list)

    def generate_pfd(self, show: bool = True, save_path: str = None, pre_evap=None):
        """Render the process flow diagram. Pass a solved PreEvaporator to include it on the same figure."""
        from evaporator_diagram import plot_set_diagram  # lazy import avoids circular dependency
        return plot_set_diagram(self, set_name=self.name, show=show, save_path=save_path, pre_evap=pre_evap)

    def show_brix_list_actual(self):
        print(f"Brix of Entering Juice: {self.juice_in.brix}")
        for i in range(self.number_of_effects):
            print(f"Brix in effect {i+1}: {self.evaporator_list[i].juice_side_out.brix}")

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

    def show_me_evaporator_details(self):
        for i in range(self.number_of_effects):
            print(f"\n \n Evaporator {i+1} Details:\n {'-'*50} \n")
            self.evaporator_list[i].display_properties()
        print(f"\n {'-'*5} Steam Required for Set: {self.supply_steam.flow_lb_per_hr:,.2f} lb/hr {'-'*5} \n")

    def neat_display(self):
        n  = self.number_of_effects
        ef = self.evaporator_list
        syrup_out  = ef[-1].juice_side_out
        steam_psig = convert_psia_to_psig(self.supply_steam.P_psia)
        last_vac   = convert_psia_to_inHgVac(self.last_effect_pressure_psia)

        LBL = 18
        COL = 11
        SEP = " | "
        W   = LBL + len(SEP) + (COL + len(SEP)) * n

        heavy = "=" * W
        light = "-" * W

        # ── Set summary ──────────────────────────────────────────────────
        print(f"\n{heavy}")
        print(f"  {self.name}")
        print(f"{heavy}")
        print(f"  Juice In     : {self.juice_in.flow_lb_per_hr:>12,.0f} lb/hr"
              f"  |  {self.juice_in.brix:>6.2f} brix"
              f"  |  {self.juice_in.temp_deg_F:>6.1f} deg F")
        print(f"  Syrup Out    : {syrup_out.flow_lb_per_hr:>12,.0f} lb/hr"
              f"  |  {syrup_out.brix:>6.2f} brix"
              f"  |  {syrup_out.temp_deg_F:>6.1f} deg F")
        print(f"  Steam Req'd  : {self.supply_steam.flow_lb_per_hr:>12,.0f} lb/hr"
              f"  |  {self.supply_steam.P_psia:>6.2f} psia - {steam_psig:>6.2f} psig"
              f"  |  {self.supply_steam.sat_temp_deg_F:>6.1f} deg F")
        print(f"  Last Eff Vac : {last_vac:>6.2f} inHg")
        print(f"  Avg U Ratio  : {self.U_ratio_avg:>6.3f}")

        # ── Effect detail table ──────────────────────────────────────────
        print(f"\n{light}")

        def row(label, values, fmt="{:>11,.0f}"):
            cells = SEP.join(fmt.format(v) for v in values)
            print(f"{label:<{LBL}}{SEP}{cells}")

        # header
        hdrs = SEP.join(f"{'Effect ' + str(i+1):>{COL}}" for i in range(n))
        print(f"{self.name:<{LBL}}{SEP}{hdrs}")
        print(light)

        row("juice in lb/hr",   [e.juice_side_in.flow_lb_per_hr        for e in ef])
        row("syrup out lb/hr",  [e.juice_side_out.flow_lb_per_hr       for e in ef])
        row("steam in lb/hr",   [e.calandria_side.flow_lb_per_hr       for e in ef])
        row("evaporated lb/hr", [e.lbs_evaporated_per_hr               for e in ef])
        row("vap bleed lb/hr",  [e.vapor_bleed.flow_lb_per_hr          for e in ef])
        print(light)
        row("brix in",          [e.juice_side_in.brix                  for e in ef], "{:>11.2f}")
        row("brix out",         [e.juice_side_out.brix                 for e in ef], "{:>11.2f}")
        row("juice temp deg F", [e.juice_side_in.temp_deg_F            for e in ef], "{:>11.1f}")
        row("syrup temp deg F", [e.juice_side_out.temp_deg_F           for e in ef], "{:>11.1f}")
        row("juice cp",         [e.juice_side_in.cp_btu_per_lb_deg_F  for e in ef], "{:>11.3f}")
        row("syrup cp",         [e.juice_side_out.cp_btu_per_lb_deg_F for e in ef], "{:>11.3f}")
        print(light)
        row("vapor psia",       [e.vapor_pressure_psia                 for e in ef], "{:>11.2f}")
        row("vapor temp deg F", [e.vapor_temperature                   for e in ef], "{:>11.1f}")
        row("vapor h_fg BTU/lb",[e.vapor_out.h_fg                     for e in ef], "{:>11.1f}")
        row("calandria psia",   [e.calandria_side.P_psia               for e in ef], "{:>11.2f}")
        row("calandria deg F",  [e.calandria_side.sat_temp_deg_F       for e in ef], "{:>11.1f}")
        row("cal h_fg BTU/lb",  [e.calandria_side.h_fg                 for e in ef], "{:>11.1f}")
        print(light)
        row("Duty MM BTU/hr",   [e.heat_duty_btu_per_hr / 1e6         for e in ef], "{:>11.3f}")
        row("HS ft2",           [e.area_ft2                            for e in ef], "{:>11,.0f}")
        row("U calc",           [e.heat_xfer_U                         for e in ef], "{:>11.1f}")
        row("U Dessin",         [e.dessin_U                            for e in ef], "{:>11.1f}")
        print(light)
        print(f"  U is in BTU/(hr*ft2*degF)\n")

        # ── Energy balance per effect ────────────────────────────────────
        print(f"\n{light}")
        print(f"  ENERGY BALANCE AT EACH EFFECT FOR: {self.name}")
        print(light)
        for i, e in enumerate(ef):
            steam_flow  = e.calandria_side.flow_lb_per_hr
            h_fg_steam  = e.calandria_side.h_fg
            condensing  = e.condensing_steam_lb_per_hr
            entering    = e.heat_duty_btu_per_hr / 1e6
            heat_loss   = e.heat_loss_btu_per_hr / 1e6

            juice_flow  = e.juice_side_in.flow_lb_per_hr
            cp          = e.juice_side_in.cp_btu_per_lb_deg_F
            T_in        = e.juice_side_in.temp_deg_F
            T_out       = e.juice_side_out.temp_deg_F
            sensible    = e.heat_from_flash / 1e6   # positive when flashing (T_in > T_out)

            net         = e.heat_available_for_evaporation / 1e6
            h_fg_vap    = e.juice_side_out.latent_heat_btu_per_lb
            evap        = e.lbs_evaporated_per_hr

            print(f"\n  Effect {i + 1}")
            print(f"  {'Condensing':<12}"
                  f"  {steam_flow:>10,.0f} lb/hr"
                  f" * (1 - {e.calandria_bleed_pec:.2f}% gas bleed)"
                  f"  =  {condensing:>10,.0f} lb/hr")
            print(f"  {'Entering  ':<12}"
                  f"  {condensing:>10,.0f} lb/hr"
                  f" * {h_fg_steam:>7.1f} BTU/lb"
                  f" / 10^6"
                  f"  =  {entering:>8.3f} MM BTU/hr")
            print(f"  {'Heat Loss ':<12}"
                  f"  {entering:>10.3f} MM BTU/hr"
                  f" * {e.heat_loss_percent:>5.2f}% shell loss"
                  f"  =  {heat_loss:>8.3f} MM BTU/hr")
            print(f"  {'Sensible  ':<12}"
                  f"  {juice_flow:>10,.0f} lb/hr"
                  f" * {cp:>5.3f} cp"
                  f" * ({T_in:.1f} - {T_out:.1f}) degF"
                  f" / 10^6"
                  f"  =  {sensible:>8.3f} MM BTU/hr")

            print(f"  Net for Evaporation  -->  "
                  f"{entering:.3f} - ({heat_loss:.3f}) + ({sensible:.3f})"
                  f"  =  {net:.3f} MM BTU/hr")
            print(f"  Evaporated  =  {net:.3f} MM BTU/hr * 10^6"
                  f" / {h_fg_vap:.1f} BTU/lb"
                  f"  =  {evap:,.0f} lb/hr")
            if self.recover_condensate_flash and e.cond_flash_to_next:
                print(f"  Condensate flash to next effect: {e.condensate_out:,.0f} lb/hr @ {e.condensate_temperature:.1f}°F"
                      f"  ->  {e.condensate_flash_vapor_lb_per_hr:,.0f} lb/hr vapor recovered")
            print(f"  {'-' * (W - 2)}")
        print(f"\n{light}\n")

        # ── Last effect condenser ────────────────────────────────────────
        cond = self.condenser
        print(light)
        print(f"  LAST EFFECT CONDENSER  —  {self.name}"
              f"  (injection water @ {self.injection_water_temp_F:.0f} °F)")
        print(light)
        print(f"  Vapor to condenser    : {cond.vapor_flow_lb_hr:>12,.0f} lb/hr"
              f"  @ {cond.vapor_sat_temp_F:.1f} °F sat, h_fg = {cond.vapor_h_fg_btu_lb:.1f} BTU/lb")
        print(f"  Heat load             : {cond.heat_load_btu_hr:>12,.0f} BTU/hr"
              f"  ({cond.heat_load_btu_hr / 1e6:.2f} MM BTU/hr)")
        print(f"  Injection water       : {cond.injection_water_flow_lb_hr:>12,.0f} lb/hr"
              f"  ({cond.injection_water_flow_lb_hr / 500.4:,.0f} GPM)"
              f"  {self.injection_water_temp_F:.0f} -> {cond.water_outlet_temp_F:.1f} °F")
        print(f"  Total outlet flow     : {cond.total_outlet_flow_lb_hr:>12,.0f} lb/hr")
        print(f"  Note: if using CoolingTowerSystem, ignore this injection water"
              f" demand - it is re-solved there at the delivered water temp.")
        print(f"{light}\n")

        # ── Condensate return ────────────────────────────────────────────
        print(light)
        print(f"  CONDENSATE RETURN  —  {self.name}")
        print(light)
        print(f"  Clean condensate (Effect 1, fresh exhaust) : {self.clean_condensate:>12,.0f} lb/hr")
        print(f"  Dirty condensate (Effect 2+, inter-effect) : {self.dirty_condensate:>12,.0f} lb/hr")
        print(f"  Total condensate                           : {self.clean_condensate + self.dirty_condensate:>12,.0f} lb/hr")
        if self.recover_condensate_flash:
            print(f"  Flash vapor recovered to next effect       : {self.total_condensate_flash_recovered:>12,.0f} lb/hr")
        print(f"{light}\n")

    def to_excel(self, workbook, sheet_writer=None):
        """Write this set (summary, effect detail, energy balance, condenser,
        PFD) to Excel. Pass an existing SheetWriter to append this set onto a
        shared sheet (see sets_to_excel); otherwise a new sheet is created."""
        import matplotlib.pyplot as plt
        from excel_export import SheetWriter

        n  = self.number_of_effects
        ef = self.evaporator_list
        standalone = sheet_writer is None
        sw = sheet_writer or SheetWriter(workbook, self.name, ncols=max(7, n + 1))
        if standalone:
            sw.title(self.name,
                     f"{n} effects | steam = {self.supply_steam.flow_lb_per_hr:,.0f} lb/hr "
                     f"| syrup out = {ef[-1].juice_side_out.brix:.2f} Bx")

        sw.section(f"{self.name} — PROCESS FLOW DIAGRAM")
        sw.blank()
        fig = self.generate_pfd(show=False)
        sw.image(fig, width_in=8.75)
        plt.close(fig)

        syrup_out = ef[-1].juice_side_out
        sw.section(f"{self.name} — SUMMARY")
        sw.table(
            ["Stream", "Flow (lb/hr)", "Brix / P (psia)", "Temp (°F)"],
            [
                ("Juice In",     self.juice_in.flow_lb_per_hr, self.juice_in.brix, self.juice_in.temp_deg_F),
                ("Syrup Out",    syrup_out.flow_lb_per_hr,     syrup_out.brix,     syrup_out.temp_deg_F),
                ("Steam Req'd",  self.supply_steam.flow_lb_per_hr, self.supply_steam.P_psia,
                                 self.supply_steam.sat_temp_deg_F),
            ],
            fmts=["@", "#,##0", "0.00", "0.0"],
        )
        sw.row("Steam pressure", convert_psia_to_psig(self.supply_steam.P_psia), "psig")
        sw.row("Last effect vacuum", convert_psia_to_inHgVac(self.last_effect_pressure_psia), '"Hg')
        sw.row("Avg U ratio (calc/Dessin)", self.U_ratio_avg, "", fmt="0.000")

        eff_hdrs = [""] + [f"Effect {i + 1}" for i in range(n)]

        sw.section(f"{self.name} — EFFECT FLOWS")
        sw.table(eff_hdrs, [
            ("Juice in (lb/hr)",    *[e.juice_side_in.flow_lb_per_hr  for e in ef]),
            ("Syrup out (lb/hr)",   *[e.juice_side_out.flow_lb_per_hr for e in ef]),
            ("Steam in (lb/hr)",    *[e.calandria_side.flow_lb_per_hr for e in ef]),
            ("Evaporated (lb/hr)",  *[e.lbs_evaporated_per_hr         for e in ef]),
            ("Vapor bleed (lb/hr)", *[e.vapor_bleed.flow_lb_per_hr    for e in ef]),
            ("Heating surface (ft²)", *[e.area_ft2                    for e in ef]),
        ], fmts=["@"] + ["#,##0"] * n)

        sw.page_break()
        sw.section(f"{self.name} — EFFECT CONDITIONS")
        sw.table(eff_hdrs, [
            ("Brix in",              *[e.juice_side_in.brix                  for e in ef]),
            ("Brix out",             *[e.juice_side_out.brix                 for e in ef]),
            ("Juice temp (°F)",      *[e.juice_side_in.temp_deg_F            for e in ef]),
            ("Syrup temp (°F)",      *[e.juice_side_out.temp_deg_F           for e in ef]),
            ("Juice cp",             *[e.juice_side_in.cp_btu_per_lb_deg_F   for e in ef]),
            ("Syrup cp",             *[e.juice_side_out.cp_btu_per_lb_deg_F  for e in ef]),
            ("Vapor P (psia)",       *[e.vapor_pressure_psia                 for e in ef]),
            ("Vapor temp (°F)",      *[e.vapor_temperature                   for e in ef]),
            ("Vapor h_fg (BTU/lb)",  *[e.vapor_out.h_fg                      for e in ef]),
            ("Calandria P (psia)",   *[e.calandria_side.P_psia               for e in ef]),
            ("Calandria temp (°F)",  *[e.calandria_side.sat_temp_deg_F       for e in ef]),
            ("Calandria h_fg (BTU/lb)", *[e.calandria_side.h_fg              for e in ef]),
            ("Duty (MM BTU/hr)",     *[e.heat_duty_btu_per_hr / 1e6          for e in ef]),
            ("Gas bleed (%)",        *[e.calandria_bleed_pec                 for e in ef]),
            ("Heat loss (%)",        *[e.heat_loss_percent                   for e in ef]),
            ("U calc (BTU/hr·ft²·°F)",  *[e.heat_xfer_U                      for e in ef]),
            ("U Dessin (BTU/hr·ft²·°F)", *[e.dessin_U                        for e in ef]),
        ], fmts=["@"] + ["#,##0.00"] * n)

        sw.section(f"{self.name} — ENERGY BALANCE PER EFFECT")
        sw.table(
            ["Effect", "Steam (lb/hr)", "h_fg (BTU/lb)", "Entering (MM BTU/hr)",
             "Heat Loss (MM BTU/hr)", "Sensible (MM BTU/hr)", "Net for Evap (MM BTU/hr)", "Evaporated (lb/hr)"],
            [
                (f"Effect {i + 1}",
                 e.calandria_side.flow_lb_per_hr,
                 e.calandria_side.h_fg,
                 e.heat_duty_btu_per_hr / 1e6,
                 e.heat_loss_btu_per_hr / 1e6,
                 e.heat_from_flash / 1e6,
                 e.heat_available_for_evaporation / 1e6,
                 e.lbs_evaporated_per_hr)
                for i, e in enumerate(ef)
            ],
            fmts=["@", "#,##0", "0.0", "0.000", "0.000", "0.000", "0.000", "#,##0"],
        )

        cond = self.condenser
        sw.section(f"{self.name} — LAST EFFECT CONDENSER")
        sw.row("Vapor to condenser",    cond.vapor_flow_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Vapor saturation temp", cond.vapor_sat_temp_F, "°F", fmt="0.0")
        sw.row("Vapor h_fg",            cond.vapor_h_fg_btu_lb, "BTU/lb", fmt="0.0")
        sw.row("Heat load",             cond.heat_load_btu_hr, "BTU/hr", fmt="#,##0")
        sw.row("Injection water in",    self.injection_water_temp_F, "°F", fmt="0.0")
        sw.row("Water outlet temp",     cond.water_outlet_temp_F, "°F", fmt="0.0")
        sw.row("Injection water flow",  cond.injection_water_flow_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Injection water flow",  cond.injection_water_flow_lb_hr / 500.4, "GPM", fmt="#,##0")
        sw.row("Total outlet flow",     cond.total_outlet_flow_lb_hr, "lb/hr", fmt="#,##0")
        sw.row("Note: if using CoolingTowerSystem, ignore this injection water "
               "demand - it is re-solved there at the delivered water temp.", "")

        sw.section(f"{self.name} — CONDENSATE RETURN")
        sw.row("Clean condensate", self.clean_condensate, "lb/hr", fmt="#,##0")
        sw.row("Dirty condensate", self.dirty_condensate, "lb/hr", fmt="#,##0")
        sw.row("Total condensate", self.clean_condensate + self.dirty_condensate, "lb/hr", fmt="#,##0")
        if self.recover_condensate_flash:
            sw.row("Flash vapor recovered to next effect", self.total_condensate_flash_recovered, "lb/hr", fmt="#,##0")

        if not standalone:
            return sw
        ws = sw.finish()
        col_widths_px = {'A': 145, 'B': 81, 'C': 81, 'D': 130, 'E': 130, 'F': 153, 'G': 109}
        for letter, px in col_widths_px.items():
            ws.column_dimensions[letter].width = (px - 5) / 7
        return ws

    def check_material_balance(self):
        """Checks the material balance of the system"""
        print(f"\n Checking Material Balance \n")
        for i in range(self.number_of_effects):
            # Juice Side Balance
            entering_juice = self.evaporator_list[i].juice_side_in.flow_lb_per_hr
            exiting_juice = self.evaporator_list[i].juice_side_out.flow_lb_per_hr
            vapors = self.evaporator_list[i].vapor_out.flow_lb_per_hr
            balance = entering_juice - exiting_juice - vapors
            balance_tolerance = 0.1
            if abs(balance) > balance_tolerance:
                print(f"warning! Balance Error in effect {i+1}, ")
                print(f"IN juice {entering_juice:,.2f} - OUT juice {exiting_juice:,.2f} - OUT {vapors:,.2f} = {balance:,.2f} lb/hr")
            # Steam Side Balance (condensate_out already nets out the incondensable-gas bleed,
            # so add that vented flow back in to check the calandria closes)
            steam_in = self.evaporator_list[i].calandria_side.flow_lb_per_hr
            condensate_out = self.evaporator_list[i].condensate_out
            gas_bleed_out = steam_in - self.evaporator_list[i].condensing_steam_lb_per_hr
            calandria_balance = steam_in - condensate_out - gas_bleed_out
            calandria_tolerance = 0.1
            if abs(calandria_balance) > calandria_tolerance:
                print(f"warning! Balance Error in effect {i}, ")
                print(f"IN steam {steam_in:,.2f} - OUT condensate {condensate_out:,.2f} - OUT gas bleed {gas_bleed_out:,.2f} = {calandria_balance:,.2f} lb/hr")
            else:
                print(f"Material Balance OK in effect {i+1}")


    def check_energy_balance(self):
        """Checks the energy balance of the system"""
        print(f"\n Checking Energy Balance \n")
        for i in range(self.number_of_effects):

            # Juice Heat Energy Sensible Rise plus Vapor Latent Heat
            temp_in = self.evaporator_list[i].juice_side_in.temp_deg_F
            temp_out = self.evaporator_list[i].juice_side_out.temp_deg_F
            latent_heat = self.evaporator_list[i].juice_side_out.latent_heat_btu_per_lb
            flow_pph = self.evaporator_list[i].juice_side_in.flow_lb_per_hr
            cp = self.evaporator_list[i].juice_side_in.cp_btu_per_lb_deg_F
            temp_change = temp_out - temp_in
            Q_dot_sens = flow_pph * cp * temp_change
            Q_dot_latent = self.evaporator_list[i].vapor_out.flow_lb_per_hr * latent_heat
            juice_energy_rise = Q_dot_sens + Q_dot_latent

            # from supply steam, net of the incondensable-gas bleed and vessel heat loss --
            # that's the energy actually delivered to the juice side
            eff = self.evaporator_list[i]
            steam_energy_drop = eff.heat_duty_btu_per_hr - eff.heat_loss_btu_per_hr

            # balance them
            energy_balance = juice_energy_rise - steam_energy_drop

            # check balance
            energy_tolerance = 100 # its a big number, so big tolerance

            if abs(energy_balance) > energy_tolerance:
                print(f"warning! Energy Balance Error in effect {i+1}, ")
                print(f"Juice: sensible heat: {Q_dot_sens:,.2f} + Latent heat: {Q_dot_latent:,.2f} = {juice_energy_rise:,.2f} BTU/hr")
                print(f"Steam (net of gas bleed + heat loss): {steam_energy_drop:,.2f} BTU/hr")
                print(f"Balance: {energy_balance:,.2f} BTU/hr")
            else:
                print(f"Energy Balance OK in effect {i+1}")


def sets_to_excel(evap_sets, workbook, sheet_name="Evaporator Station"):
    """Write several solved EvaporatorSets onto ONE shared sheet, each with
    its summary, effect tables, energy balance, condenser, and PFD.

    Usage with solve_evaporator_sets:
        evap_station = solve_evaporator_sets(...)
        wb = new_workbook()
        sets_to_excel(evap_station, wb)
        wb.save("factory_balance.xlsx")
    """
    from excel_export import SheetWriter

    ncols = max(7, max(s.number_of_effects for s in evap_sets) + 1)
    sw = SheetWriter(workbook, sheet_name, ncols=ncols)
    total_steam = sum(s.supply_steam.flow_lb_per_hr for s in evap_sets)
    total_inj   = sum(s.condenser.injection_water_flow_lb_hr for s in evap_sets)
    sw.title(sheet_name,
             f"{len(evap_sets)} sets  |  total steam = {total_steam:,.0f} lb/hr  "
             f"|  total condenser injection water = {total_inj:,.0f} lb/hr "
             f"({total_inj / 500.4:,.0f} GPM)")
    for i, es in enumerate(evap_sets):
        if i > 0:
            sw.page_break()
        es.to_excel(workbook, sheet_writer=sw)
        sw.blank()
    ws = sw.finish()
    col_widths_px = {'A': 145, 'B': 81, 'C': 81, 'D': 130, 'E': 130, 'F': 153, 'G': 109}
    for letter, px in col_widths_px.items():
        ws.column_dimensions[letter].width = (px - 5) / 7
    return ws

import numpy as np
from scipy.optimize import root
 
from EvaporatorSet import EvaporatorSet
 
 
class EvaporatorSetSciPy(EvaporatorSet):
    """EvaporatorSet with a scipy.optimize.root pressure-profile solver."""
 
    def _apply_pressures(self, P_interior):
        """Push the N-1 interior vapor pressures into the effects.
 
        Effect i's vapor space is set to P_interior[i], and that same pressure
        becomes the calandria (heating) pressure of effect i+1. The last effect's
        vapor pressure stays pinned to the condenser.
        """
        for i in range(self.number_of_effects - 1):
            self.evaporator_list[i].vapor_pressure_psia = float(P_interior[i])
            self.evaporator_list[i + 1].calandria_side.P_psia = float(P_interior[i])
 
    def _profile_residuals(self, P_interior):
        """One residual per pair of adjacent effects: their U_ratios should match.
 
        np.diff([a, b, c]) -> [b-a, c-b]. When both are zero, all three U_ratios
        are equal -- the same target as your stdev(U_ratio) -> 0 criterion.
        """
        self._apply_pressures(P_interior)
        self.update_set()
        self.solve_for_steam()   # your trusted 1-D secant keeps brix on target
        u = np.array([e.U_ratio for e in self.evaporator_list])
        return np.diff(u)
 
    def _equal_split_guess(self):
        """Starting profile: split the total pressure drop evenly across effects.
 
        This mirrors evaporator_functions.pressure_profile_initial and gives a
        valid, correctly ordered profile to start from.
        """
        P_top = self.supply_steam.P_psia
        P_bot = self.last_effect_pressure_psia
        step = (P_top - P_bot) / self.number_of_effects
        return np.array([P_top - step * (i + 1)
                         for i in range(self.number_of_effects - 1)])
 
    def adjust_pressure_profile_scipy(self, method="hybr", tol=None):
        """Solve the pressure profile with scipy.optimize.root.
 
        Returns the scipy OptimizeResult (check .success, .x). The converged
        profile and steam flow are already applied to the set on return.
        """
        if self.number_of_effects < 2:          # nothing to distribute
            self.update_set()
            self.solve_for_steam()
            return None
 
        P0 = self._equal_split_guess()
        sol = root(self._profile_residuals, P0, method=method, tol=tol)
        self._profile_residuals(sol.x)          # apply the converged state
 
        if not sol.success:
            print(f"[EvaporatorSetSciPy] root did not fully converge: {sol.message}")
        return sol

if __name__ == "__main__":
    from PreEvaporator import PreEvaporator

    # ── Birkett (1978) — 13 Evaporator Cases ─────────────────────────────────
    # Basis: 200,000 lb/hr clarified juice @ 12° Brix, 225°F, purity 90;
    #        20 psig supply steam; 26" Hg vacuum last effect; 60° Brix syrup target;
    #        Dessin K = 20,000 (per paper); 100°F injection water.
    # Cases 4, 5, 10 include a pre-evaporator — the pre-evap is solved first and
    # its juice_out is passed as juice_in to the main EvaporatorSet.

    LAST_PSIA  = convert_inHg_vacuum_to_psia(26)
    STEAM_PSIA = convert_psig_to_psia(20)

    def _j(brix=12.0, flow=200_000, temp=225):
        return SugarStream(brix=brix, purity=90, flow_lb_per_hr=flow,
                           temp_deg_F=temp, pressure_psia=60, level_ft=0)

    # pre_evap: None, or dict(area_ft2=..., bleed=...) where bleed is total vapor bleed lb/hr
    CASES = {
         1: dict(desc="Straight Triple Effect",               areas=[4800, 4800, 4800],               bleeds=[0],                            pre_evap=None),
         2: dict(desc="Triple — V1 bleed (heaters)",          areas=[6700, 3900, 3900],               bleeds=[31_357+3_895],                  pre_evap=None),
         3: dict(desc="Triple — V1 bleed (heaters + pans)",   areas=[8800, 3100, 3100],               bleeds=[31_357+3_895+28_108],           pre_evap=None),
         4: dict(desc="Pre-evap + Triple",                    areas=[3800, 3800, 3800],               bleeds=[0],                            pre_evap=dict(area_ft2=3_300, bleed=31_357+3_895)),
         5: dict(desc="Pre-evap + Triple, pan bleed",         areas=[3000, 3000, 3000],               bleeds=[0],                            pre_evap=dict(area_ft2=5_900, bleed=31_357+3_895+28_108)),
         6: dict(desc="Straight Quadruple Effect",            areas=[5100, 5100, 5100, 5100],         bleeds=[0],                            pre_evap=None),
         7: dict(desc="Quadruple — V1 bleed (heaters)",       areas=[5900, 4600, 4600, 4600],         bleeds=[31_357+3_895],                  pre_evap=None),
         8: dict(desc="Quadruple — V1 bleed (heaters + pans)",areas=[8200, 3650, 3650, 3650],         bleeds=[31_357+3_895+28_108],           pre_evap=None),
         9: dict(desc="Quadruple — V1+V2 double-robbed",      areas=[7750, 6250, 3125, 3125],         bleeds=[8_959+3_895+28_108, 22_120],    pre_evap=None),
        10: dict(desc="Pre-evap + Quadruple, pan bleed",      areas=[3200, 3200, 3200, 3200],         bleeds=[0],                            pre_evap=dict(area_ft2=5_900, bleed=31_357+3_895+28_108)),
        11: dict(desc="Straight Quintuple Effect",            areas=[5350, 5350, 5350, 5350, 5350],   bleeds=[0],                            pre_evap=None),
        12: dict(desc="Quintuple — V1+V2 double-robbed",      areas=[13700, 8150, 3600, 3600, 3600],  bleeds=[8_959+3_895+28_108, 22_189],    pre_evap=None),
        13: dict(desc="Quintuple — V1+V2+V3 triple-robbed",   areas=[10750, 7200, 6100, 2100, 2100],  bleeds=[3_920+28_108, 8_922, 22_006],   pre_evap=None),
    }

    print("\nBirkett (1978) — The Multiple Effect Evaporator in the Raw Sugar Factory")
    print("=" * 74)
    for n, cfg in CASES.items():
        tag = "  [pre-evap]" if cfg['pre_evap'] else ""
        print(f"  {n:>2}: {cfg['desc']}{tag}")

    raw = 13 # select a case number here to run, you can compare to Birkett's numbers

    if int(raw) not in CASES:
        print("Invalid selection — choose a number from 1 to 13.")
    else:
        case_num = int(raw)
        cfg = CASES[case_num]
        print(f"\nCase {case_num}: {cfg['desc']}\n")
        start = time.time()

        juice_in = _j()
        pre = None

        if cfg['pre_evap']:
            pre = PreEvaporator(
                juice_in              = juice_in,
                supply_steam          = EvaporatorSteam(P_psia=STEAM_PSIA, flow_lb_per_hr=0),
                vapor_bleed_lb_per_hr = cfg['pre_evap']['bleed'],
                area_ft2              = cfg['pre_evap']['area_ft2'],
                liquid_level_ft       = 2,
                dessin_coefficient    = 20_000,
            )
            print("Pre-Evaporator:")
            pre.display_properties()
            print()
            juice_in = pre.juice_out

        evap_set = EvaporatorSetSciPy(
            juice_in               = juice_in,
            supply_steam           = EvaporatorSteam(P_psia=STEAM_PSIA, flow_lb_per_hr=0),
            last_effect_pressure_psia = LAST_PSIA,
            target_brix_out        = 60,
            effect_areas_ft2       = cfg['areas'],
            vapor_bleeds           = cfg['bleeds'],
            dessin_coefficient     = 20_000,
            liquid_level_ft        = 2,
            injection_water_temp_F = 100,
            name                   = f"Birkett Case {case_num} — {cfg['desc']}",
        )

        evap_set.adjust_pressure_profile_scipy()
        solve_time = (time.time() - start) * 1000

        evap_set.neat_display()
        evap_set.condenser.neat_display()
        evap_set.generate_pfd(pre_evap=pre)

        # Excel export demo — one workbook, this unit on its own sheet
        from excel_export import new_workbook
        wb = new_workbook()
        evap_set.to_excel(wb)
        wb.save("evaporation.xlsx")
        print("\nSaved evaporation.xlsx")
        print(f"\nSolve time: {solve_time:.4f} ms")

