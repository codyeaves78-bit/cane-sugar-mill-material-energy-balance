# A ThermoCompressor modeled after the equation given in Hugot's book
# Hugot calls it the Truffault formula
import numpy as np
import pandas as pd
from scipy.optimize import root
from SteamStream import EvaporatorSteam

def get_entrainment_ratio(mix_psia, actuating_steam_psia, vapor_psia):
    """
    a function to help solve for the entrainment ratio mu_o
    mix_psia is the pressure of the mixture psia
    actuating_steam_psia is the pressure of the actuating steam (high pressure) psia
    vapor_psia is the pressure of the vapors psia
    mu_o will be solved for with scipy.optimize
    """
    mix_steam = EvaporatorSteam(P_psia=mix_psia)
    vapors = EvaporatorSteam(P_psia=vapor_psia)

    t_m = mix_steam.sat_temp_deg_F
    t_o = vapors.sat_temp_deg_F

    A = (144 / (t_m - t_o))
    B = np.log10(actuating_steam_psia) - np.log10(mix_psia)
    C = 0.0056 * (t_o - 212)
    right_side = A * (B - C)

    # create sub function for scipy
    def _solve_for(mu_o):
        left_side = (mu_o + 1) ** 2
        return left_side - right_side # get to zero
    
    sol = root(_solve_for, 1)
    return sol.x # solves in about 0.25 ms, fast

entrainment_ratio = get_entrainment_ratio(34.7, 250, 26.8)

print(f"Entrainment Ratio {entrainment_ratio}")

# hugot test examples table 32.12
calandria_pressures = np.array([34.7, 29.7, 24.7, 19.7])
vapor_pressures = np.array([26.8, 22.4, 18.2, 15.3])
act_steam_pressures = np.array([250, 300, 350, 400, 640])

entrainment_ratios = {
    act_steam_pressure: [
        get_entrainment_ratio(cal_pressure, act_steam_pressure, vapor_pressure)[0]
        for cal_pressure, vapor_pressure in zip(calandria_pressures, vapor_pressures)
    ]
    for act_steam_pressure in act_steam_pressures
}

entrainment_ratio_table = pd.DataFrame(
    entrainment_ratios,
    index=pd.MultiIndex.from_arrays(
        [calandria_pressures, vapor_pressures],
        names=["calandria_psia", "vapor_psia"],
    ),
)
entrainment_ratio_table.columns.name = "act_steam_psia"

print(entrainment_ratio_table)

# This file is still a work in progress.