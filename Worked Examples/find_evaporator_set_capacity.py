import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so this runs standalone from any cwd

from EvaporatorSet import EvaporatorSetSciPy, EvaporatorSet
from SteamStream import EvaporatorSteam
from SugarStream import SugarStream
from scipy.optimize import root

juice = SugarStream(
    brix=13.0,
    purity=87,
    flow_lb_per_hr=1_000_000,
    temp_deg_F=225,
    pressure_psia=45,
    level_ft=0
)

steam = EvaporatorSteam(P_psia=(33))

def get_u_rat(juice_flow):
    juice.flow_lb_per_hr=juice_flow
    evaps = EvaporatorSetSciPy(
    juice_in=juice,
    supply_steam=steam,
    last_effect_pressure_psia=2.4,
    target_brix_out=65,
    effect_areas_ft2=[25000, 25000, 25000, 25000],
    vapor_bleeds=[0, 0, 0],
)
    evaps.adjust_pressure_profile_scipy()
    #evaps.neat_display()
    return evaps.U_ratio_avg, evaps.juice_in.flow_lb_per_hr

flow = 1000000
for i in range(30):
    rat, flow = get_u_rat(flow)
    flow /= rat ** (0.5)
    if i == 29:
        print(f"this set can handle: {flow:,.0f} lb/hr juice")

