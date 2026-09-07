# A ThermoCompressor modeled after the equation given in Hugot's book
# Hugot calls it the Truffault formula
import numpy as np
import pandas as pd
from scipy.optimize import root
from SteamStream import EvaporatorSteam

def get_entrainment_ratio(mix_psia, actuating_steam_psia, low_psia):
    """
    a function to help solve for the entrainment ratio mu_o
    mix_psia is the pressure of the mixture psia
    actuating_steam_psia is the pressure of the actuating steam (high pressure) psia
    vapor_psia is the pressure of the vapors psia
    mu_o will be the output
    """
    mix_steam = EvaporatorSteam(P_psia=mix_psia)
    low_steam = EvaporatorSteam(P_psia=low_psia)

    t_m = mix_steam.sat_temp_deg_F
    t_o = low_steam.sat_temp_deg_F

    A = (144 / (t_m - t_o))
    B = np.log10(actuating_steam_psia) - np.log10(mix_psia)
    C = 0.0056 * (t_o - 212)
    return np.sqrt(A * (B - C)) - 1 # solve to isolate uo

if __name__ == '__main__':

    # hugot test examples table 32.12
    calandria_pressures = np.array([34.7, 29.7, 24.7, 19.7])
    vapor_pressures = np.array([26.8, 22.4, 18.2, 15.3])
    act_steam_pressures = np.array([250, 300, 350, 400, 640])

    ent_ratios = [get_entrainment_ratio(calandria_pressures, P, vapor_pressures) for P in act_steam_pressures]

    df = pd.DataFrame({
        'Cal psia': calandria_pressures,
        'Cal temp deg F': EvaporatorSteam(P_psia=calandria_pressures).sat_temp_deg_F,
        'Vap psia': vapor_pressures,
        'Vap temp deg F': EvaporatorSteam(P_psia=vapor_pressures).sat_temp_deg_F,
        '250 psia act steam': ent_ratios[0],
        '300 psia act steam': ent_ratios[1],
        '350 psia act steam': ent_ratios[2],
        '400 psia act steam': ent_ratios[3],
        '640 psia act steam': ent_ratios[4],
    })

    print(df)
    # Outputs pasted below, pretty close to Hugots numbers in his table 32.12, unsure where the error comes from
    # I do notice on page 558 that there is a p = 0.95 * mu_o, but I have no clue what p is. P is HP steam, there
    # is a pm and a pc, but now p. The scanned version of this book does contain many irregularities with formulas like this
    # anyone with a real copy feel free to make the correction.
    """
        Cal psia  Cal temp deg F  Vap psia  Vap temp deg F  250 psia act steam  300 psia act steam  350 psia act steam  400 psia act steam  640 psia act steam
    0      34.7      258.757305      26.8      243.924351            1.567138            1.712729            1.829987            1.927767            2.248606
    1      29.7      249.740026      22.4      234.027502            1.710811            1.841508            1.947493            2.036312            2.330147
    2      24.7      239.381926      18.2      222.955778            1.876565            1.994791            2.091223            2.172388            2.442886
    3      19.7      227.131075      15.3      214.003901            2.461442            2.584713            2.685722            2.771034            3.057070
    """

    my_entrainment_ratio = get_entrainment_ratio(mix_psia=30, actuating_steam_psia=185, low_psia=22)
    print(my_entrainment_ratio)

class ThermoCompressor:
    """
    Steam-jet thermo-compressor, sized by Truffault's formula (Hugot's book).

    A thermo-compressor entrains low-pressure "vapor" steam using high-pressure
    "motive" (actuating) steam, discharging both as a single mixed stream —
    typically back into an evaporator calandria — so bled vapor that would
    otherwise be vented or condensed can be reused instead.

    p_mix           : mixed (discharge) steam pressure, psia
    p_vap           : entrained (low-pressure vapor) steam pressure, psia
    p_high          : motive (high-pressure actuating) steam pressure, psia
    act_steam_lb_hr : motive steam flow rate, lb/hr

    The entrainment ratio mu_o (lb vapor entrained per lb motive steam) is
    solved from Truffault's formula:
        (mu_o + 1)^2 = (144 / (T_mix - T_vap)) * (log10(p_high / p_mix) - 0.0056 * (T_vap - 212))
    where T_mix and T_vap are the saturation temperatures at p_mix and p_vap.
    See get_entrainment_ratio() for the implementation and a note on a possible
    missing correction term — results run close to, but not exact against,
    Hugot's table 32.12.
    """
    def __init__(self, p_mix=30, p_vap=22, p_high=180, act_steam_lb_hr=1):
        # All pressures are in psia
        self.p_mix = p_mix
        self.T_mix = EvaporatorSteam(self.p_mix).sat_temp_deg_F
        self.p_vap = p_vap
        self.T_vap = EvaporatorSteam(self.p_vap).sat_temp_deg_F
        self.p_high = p_high
        self.act_steam_lb_hr = act_steam_lb_hr

    @property
    def entrainment_ratio(self):
        return get_entrainment_ratio(self.p_mix, self.p_high, self.p_vap)
    
    @property
    def low_pressure_steam_lb_hr(self):
        return self.entrainment_ratio * self.act_steam_lb_hr

    @property
    def mix_steam_lb_hr(self):
        return self.act_steam_lb_hr + self.low_pressure_steam_lb_hr

    def properties(self):
        return {
            "p_mix": self.p_mix,
            "T_mix": self.T_mix,
            "p_vap": self.p_vap,
            "T_vap": self.T_vap,
            "p_high": self.p_high,
            "act_steam_lb_hr": self.act_steam_lb_hr,
            "entrainment_ratio": self.entrainment_ratio,
            "low_pressure_steam_lb_hr": self.low_pressure_steam_lb_hr,
            "mix_steam_lb_hr": self.mix_steam_lb_hr,
        }

    def __repr__(self):
        return (f"ThermoCompressor(p_high={self.p_high:.1f} psia, "
                f"p_mix={self.p_mix:.1f} psia, p_vap={self.p_vap:.1f} psia, "
                f"mu_o={self.entrainment_ratio:.3f})")

    def neat_display(self):
        W = 60
        div = "=" * W
        sep = "-" * W

        print(div)
        print("THERMOCOMPRESSOR".center(W))
        print(div)
        print(f"  {'Motive (HP) steam':<28}: {self.p_high:>10,.1f} psia")
        print(f"  {'Mixed (discharge) steam':<28}: {self.p_mix:>10,.1f} psia  ({self.T_mix:,.1f} °F)")
        print(f"  {'Entrained (vapor) steam':<28}: {self.p_vap:>10,.1f} psia  ({self.T_vap:,.1f} °F)")
        print(sep)
        print(f"  {'Entrainment ratio (mu_o)':<28}: {self.entrainment_ratio:>10,.3f} lb vapor / lb motive")
        print(f"  {'Motive steam flow':<28}: {self.act_steam_lb_hr:>10,.0f} lb/hr")
        print(f"  {'Entrained vapor flow':<28}: {self.low_pressure_steam_lb_hr:>10,.0f} lb/hr")
        print(f"  {'Mixed discharge flow':<28}: {self.mix_steam_lb_hr:>10,.0f} lb/hr")
        print(div)

if __name__ == "__main__":
    my_thermo_compressor = ThermoCompressor(p_mix=30, p_vap=22, p_high=180, act_steam_lb_hr=100000)
    my_thermo_compressor.neat_display()

    


