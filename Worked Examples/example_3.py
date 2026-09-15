"""
Example 3 -- Louisiana factory, 22,000 short tons cane/day (24 hours/day).

Run from any directory: python "Worked Examples/example_3.py"
Use --details for station neat_display reports; default prints the balance and
preliminary equipment recommendations. Importing this file does not run it.

Basis inherited from example_1.py, example_2.py and main.py:
* Two equal 11,000 TPD tandems, six mills and two knife sets per tandem.
* Cane: 13.5% pol, 14.5% fiber; 30% imbibition; bagasse 49.5% moisture.
* Shared clarification; limed juice heating in series: V2, 90 -> 170 F;
  V1, 170 -> 220 F. Clarified juice leaves at 205 F, purity 86.5.
* Two equal PARALLEL Pres take all clarified juice, each half the V1 demand.
  Their combined juice feeds four PARALLEL stations, 25% each: two quads,
  two triples. All first calandrias use 22 psig exhaust, not Pre vapor.
* V1 = 9.425 psig: Pres supply secondary heaters and A/B/grain pans.
  V2 = -2.007 psig: effect 2 of all four sets supplies primary heaters and C pans.
  No external V1 bleed from the four sets; their V1 feeds their own effect 2.
* Design mode: solve REQUIRED surface at imposed common vapor pressures,
  using the repository Dessin correlation, K=18,000, 2-ft liquid head.
  Shared headers use the triple profile; quad tail splits the remaining drop.
  See hugot_profiles() for source and the common-header design adaptation.
  This is not a capacity prediction for an existing installed set.
* Syrup 63 Brix; three-boiling double-magma recycles from example_2.
* Factory live header: 250 psig saturated. Process exhaust: 22 psig.
* Dedicated cogen supply: 600 psig, 400 F SUPERHEAT ABOVE SATURATION.
  Assume a topping/backpressure turbine: all discharge goes to 250 psig,
  no condensing tail or additional extraction. 5 MW gross electrical,
  75% isentropic efficiency, 96% generator efficiency (auxiliaries excluded).
  CogenTurbine has no generator-loss input, so pass 5000/0.96 kW equivalent.
  Desuperheat its discharge before crediting saturated 250-psig steam.
* Six 600-hp fan drives plus two 300-hp pumps; 40% turbine efficiency.
  Mill and knife drives 50%; no inlet throttling loss assumed.
* Exhaust distribution loss 5%; live distribution loss 2%; jets/steam-outs
  25,000 lb/hr. Any excess exhaust is reported, never clipped out of balance.
* DA at 10 psig, return water 205 F, vent 1% of DA steam; solve DA duty
  simultaneously with boiler feed demand. Use actual 22-psig inlet enthalpy
  after throttling, not the Deaerator class's saturated-10-psig inlet shortcut.
* Boiler blowdown 3% of feedwater. Efficiencies: LP 65%, HP 70%, GCV basis.
  One shared bagasse pool: allocate to the HP boiler first, then LP boilers.
  Desuperheater spray comes from a separately metered 205 F clean-condensate
  supply; report it explicitly, outside DA/boiler feed. Pump work neglected.
* No claim of full site water/electrical closure: return-water sourcing,
  crystallizer/reheater utility loops, and auxiliary electrical loads remain
  outside this example. Condenser cooling loop is included, as in main.py.

Sizing is a preliminary process-duty estimate, not a vendor selection. 20%
margin is an EXAMPLE assumption, not a design standard. Pres/sets retain their
calculated effective surface for the balance; recommendations add margin.
Pan U, cycles, vessel fill, retention times and nominal machine capacities
are editable assumptions below, not manufacturer ratings. No mill roll
geometry, relief sizing, pump head or motor power is inferred from flow alone.
"""
import argparse
import math
import sys
from copy import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scipy.optimize import brentq
from MillFloor import MillFloor
from Clarification import Clarification
from SugarStream import SugarStream
from SteamStream import SteamStream, EvaporatorSteam
from JuiceHeater import JuiceHeaterShellTube
from Pan import Pan
from Centrifugal import Centrifugal
from Crystallizer_and_Reheater import Crystallizer, Reheater
from ThreeBoilingDoubleMagma import ThreeBoilingDoubleMagma
from PreEvaporator import PreEvaporator
from EvaporatorSet import EvaporatorSetSciPy
from MillTurbines import MillTurbines
from CanePrepTurbines import CanePrepTurbines
from AuxillaryTurbines import AuxillaryTurbines
from CogenTurbine import CogenTurbine
from Boiler import Boiler
from CoolingTowerSystem import CoolingTowerSystem
from evaporator_functions import calculate_U_dessin
from sugar_stream_properties import bpe_total, get_latent_heat, sat_steam_temp

ATM = 14.696
CANE_TPD = 22_000
SCALE = CANE_TPD / 13_000
LIVE_PSIA = 250 + ATM
HP_PSIA = 600 + ATM
EXHAUST_PSIA = 22 + ATM
LAST_EFFECT_PSIA = 2.4


def hugot_profiles(supply_psia, last_psia):
    """Hugot, 3rd ed. (1986), ch.32, p.579, Table 32.23.

    Triple drop weights: 11,10,9 /30; quad: 11,10.3,9.7,9 /40.
    Source: https://archive.org/stream/HandbookOfCaneSugarEngineering-hogot/
            HandbookOfCaneSugarEngineering-hogot_djvu.txt
    DESIGN ADAPTATION: common V1/V2 are the lower triple values. The quad
    keeps those headers, then splits its remaining drop in ratio 9.7:9.
    Thus the constrained quad is not Hugot's unmodified four-effect profile.
    """
    if not supply_psia > last_psia > 0:
        raise ValueError('Supply pressure must exceed positive final pressure')
    drop = supply_psia - last_psia
    triple = [supply_psia - 11/30*drop, supply_psia - 21/30*drop, last_psia]
    quad_reference = [supply_psia - fraction*drop for fraction in (11/40,21.3/40,31/40)] + [last_psia]
    quad_common = triple[:2] + [triple[1] - (triple[1]-last_psia)*9.7/18.7, last_psia]
    return triple, quad_reference, quad_common


TRIPLE_PROFILE, QUAD_REFERENCE_PROFILE, QUAD_PROFILE = hugot_profiles(EXHAUST_PSIA, LAST_EFFECT_PSIA)
V1_PSIA, V2_PSIA = TRIPLE_PROFILE[:2]
MARGIN = 1.20
GENERATOR_EFFICIENCY = 0.96
BLOWDOWN_FRACTION = 0.03
SPRAY_TEMP_F = 205


def require_close(name, actual, expected, rtol=1e-5, atol=0.1):
    if not math.isclose(actual, expected, rel_tol=rtol, abs_tol=atol):
        raise RuntimeError(f"{name}: {actual:,.6f} != {expected:,.6f}")


def positive(name, value):
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name}: expected finite positive value, got {value}")
    return value


def size_pre(feed, vapor):
    # Match PreEvaporator's input-Brix BPE basis, including its head convention.
    # This preserves the existing model rather than silently changing a class.
    supply = EvaporatorSteam(P_psia=EXHAUST_PSIA)
    out_brix = 100 * feed.solids_flow / (feed.flow_lb_per_hr - vapor)
    if not feed.brix < out_brix < 63:
        raise RuntimeError("Pre vapor demand is incompatible with the juice feed")
    hfg = get_latent_heat(V1_PSIA)
    liquid_t = sat_steam_temp(V1_PSIA) + bpe_total(2, feed.brix, V1_PSIA)
    duty = feed.flow_lb_per_hr * feed.cp_btu_per_lb_deg_F * (liquid_t - feed.temp_deg_F) + vapor * hfg
    u = calculate_U_dessin(out_brix, supply.sat_temp_deg_F, hfg, 18000)
    area = duty / (u * positive("Pre temperature driving force", supply.sat_temp_deg_F - liquid_t))
    pre = PreEvaporator(feed, supply, vapor, positive("Pre area", area))
    pre.solve(max_iter=200)
    # Inverse polynomial P(T) has finite error: refine area using the actual model.
    def residual(a):
        pre.area_ft2 = a
        pre.solve(max_iter=200)
        return pre.vapor_pressure_psia - V1_PSIA
    pre.area_ft2 = brentq(residual, area * 0.8, area * 1.2, xtol=1e-7)
    pre.solve(max_iter=200)
    require_close("Pre V1 pressure", pre.vapor_pressure_psia, V1_PSIA, atol=1e-5)
    require_close("Pre material", feed.flow_lb_per_hr, pre.juice_out.flow_lb_per_hr + vapor)
    require_close("Pre solids", feed.solids_flow, pre.juice_out.solids_flow)
    return pre


def size_set(name, feed, n, v2_bleed):
    interior = (QUAD_PROFILE if n == 4 else TRIPLE_PROFILE)[:-1]
    evap = EvaporatorSetSciPy(
        juice_in=feed, supply_steam=EvaporatorSteam(P_psia=EXHAUST_PSIA),
        last_effect_pressure_psia=LAST_EFFECT_PSIA, target_brix_out=63,
        effect_areas_ft2=[20000.] * n, vapor_bleeds=[0., v2_bleed] + [0.] * (n - 2),
        dessin_coefficient=18000, liquid_level_ft=2,
        injection_water_temp_F=90, condenser_leg_temp_drop_F=8,
        name=name,
    )
    evap.manually_set_pressures(interior)
    # At fixed feed/pressures/duty, A_required = A_trial * U_calc / U_Dessin.
    for i, body in enumerate(evap.evaporator_list):
        area = positive(f"{name} effect {i+1} area", body.area_ft2 * body.U_ratio)
        evap.effect_areas_ft2[i] = body.area_ft2 = area
    evap.manually_set_pressures(interior)
    require_close(f"{name} syrup Brix", evap.evaporator_list[-1].juice_side_out.brix, 63, atol=0.0002)
    previous_p = EXHAUST_PSIA
    for i, body in enumerate(evap.evaporator_list):
        positive(f"{name} E{i+1} juice", body.juice_side_out.flow_lb_per_hr)
        positive(f"{name} E{i+1} steam", body.calandria_side.flow_lb_per_hr)
        if not previous_p > body.vapor_pressure_psia > 0:
            raise RuntimeError(f"{name}: vapor pressures must decrease")
        previous_p = body.vapor_pressure_psia
        require_close(f"{name} E{i+1} U ratio", body.U_ratio, 1., atol=0.0001)
        require_close(f"{name} E{i+1} solids", body.juice_side_in.solids_flow, body.juice_side_out.solids_flow)
        if body.lbs_evaporated_per_hr < body.vapor_bleed.flow_lb_per_hr:
            raise RuntimeError(f"{name}: bleed exceeds generated vapor")
    return evap


def make_pan_floor(syrup):
    V1_psia, V2_psia = V1_PSIA, V2_PSIA
    pan_floor = ThreeBoilingDoubleMagma(
        syrup=syrup,
        A_pans=Pan(
            feed_streams=None, heating_surface_ft2=12000 * SCALE, inches_vacuum=23.5,
            supersaturation=1.2, head_ft=2, masse_brix=92, ml_purity=70, # mother liquor purity
            calandria_pressure_psia=V1_psia, heat_loss_factor=0.02,
            name='A Pans', steam_type=1 # meaning V1
            ),
        A_centrifugals=Centrifugal(
            massecuite=None, massecuite_flow_lb_hr=0, # master object updates this flow
            target_molasses_brix=82, purity_rise=2, molasses_temp=145,
            sugar_moisture=0.35, sugar_purity=99.4, sugar_temp=150,
            name="A Centrifugals"),
        B_pans=Pan(
            feed_streams=None, heating_surface_ft2=5000 * SCALE, inches_vacuum=25,
            supersaturation=1.2, head_ft=2, masse_brix=94, ml_purity=48,
            calandria_pressure_psia=V1_psia, heat_loss_factor=0.05,
            name='B Pans', steam_type=1
            ),
        B_centrifugals=Centrifugal(
            massecuite=None, massecuite_flow_lb_hr=0, target_molasses_brix=82, purity_rise=2,
            sugar_moisture=5, sugar_purity=90, sugar_temp=150, molasses_temp=145,
            name="B Centrifugals"
        ),
        grain_pans=Pan(
            feed_streams=None, heating_surface_ft2=2000 * SCALE, inches_vacuum=25.5,
            supersaturation=1.2, head_ft=2, masse_brix=88, ml_purity=39,
            calandria_pressure_psia=V1_psia, heat_loss_factor=0.05,
            name='Grain Pans', steam_type=1
        ),
        C_pans=Pan(
            feed_streams=None, heating_surface_ft2=5000 * SCALE, inches_vacuum=26.5,
            supersaturation=1.2, head_ft=2, masse_brix=95.5, ml_purity=33,
            calandria_pressure_psia=V2_psia, heat_loss_factor=0.05,
            name='C Pans', steam_type=2 # meaning V2
        ),
        C_centrifugals=Centrifugal(
            massecuite=None, massecuite_flow_lb_hr=0, target_molasses_brix=82, purity_rise=4,
            sugar_moisture=5, sugar_purity=82, sugar_temp=150, molasses_temp=145,
            name="C Centrifugals"
        ),
        C_crystallizers=Crystallizer(
            massecuite_in=None, massecuite_flow_lb_hr=0,
            masse_temp_out_deg_F=120, ml_purity_out=30,
            water_temp_in_deg_F=85, water_temp_out_deg_F=105,
            name="C Crystallizers"
        ),
        C_reheaters=Reheater(
            massecuite_in=None, massecuite_flow_lb_hr=0,
            masse_temp_out_deg_F=130,
            water_temp_in_deg_F=150, water_temp_out_deg_F=135,
            name="C Reheaters"
        ),
        c_magma_brix=90,
        c_magma_remelt_pct=20,
        b_magma_brix=90,
        b_magma_remelt_pct=20,
        syrup_to_grain_pct=2,
        a_mol_to_grain_pct=10,
        b_mol_to_grain_pct=20,
        a_mol_top_off_pct=0,
        b_mol_top_off_pct=0,
        c_mol_top_off_pct=0,
        b_remelt_brix=60,
        c_remelt_brix=60,
        a_mol_dilution_brix=70,
        b_mol_dilution_brix=70,
        injection_water_temp_F=90,
        iterations=100,
        condenser_leg_temp_drop_F=8
    )
    return pan_floor


def steam_and_fuel(mills, process_exhaust):
    live = SteamStream(P=LIVE_PSIA, x=1)
    exhaust = SteamStream(P=EXHAUST_PSIA, x=1)
    hp_sat = SteamStream(P=HP_PSIA, x=1)
    hp_live = SteamStream(P=HP_PSIA, T=hp_sat.T + 400)
    cogen = CogenTurbine(
        inlet_steam=hp_live, outlet_pressure_psia=LIVE_PSIA,
        isentropic_efficiency=0.75, kw_demand=5000 / GENERATOR_EFFICIENCY,
        name='600 -> 250 psig topping turbine',
        desuperheating_water_temp=SPRAY_TEMP_F,
    )
    cogen_in = cogen.steam_flow_lb_hr
    cogen_header = cogen.exhaust_available
    cogen_spray = cogen_header - cogen_in
    positive('Cogen spray water', cogen_spray)
    spray_hp_h = SteamStream(P=LIVE_PSIA, T=SPRAY_TEMP_F).h
    require_close('Cogen desuperheater energy',
                  cogen_in * cogen.h_out_actual + cogen_spray * spray_hp_h,
                  cogen_header * live.h, atol=1.)
    require_close('Cogen electrical output', cogen.kw_output * GENERATOR_EFFICIENCY, 5000)

    groups = []
    for mill in mills:
        fiber_tph = mill.cane_tph * mill.cane_fiber_pct / 100
        groups.extend([
            CanePrepTurbines(hp_ton_fiber_hr=[14, 14], isentropic_efficiency=[50, 50],
                             live_steam_object=live, exhaust_psia=EXHAUST_PSIA, tons_fiber_hr=fiber_tph),
            MillTurbines(hp_ton_fiber_hr=[13, 11, 11, 11, 11, 13], isentropic_efficiency=[50]*6,
                         live_steam_object=live, exhaust_psia=EXHAUST_PSIA, tons_fiber_hr=fiber_tph),
        ])
    groups.append(AuxillaryTurbines(
        group_name='Boiler fans and water pumps',
        name_list=[f'ID fan {i}' for i in range(1, 7)] + ['Water pump 1', 'Water pump 2'],
        hp_list=[600]*6 + [300]*2, isentropic_efficiency=[40]*8,
        live_steam_object=live, exhaust_psia=EXHAUST_PSIA,
    ))
    drive_in = sum(g.total_inlet_flow_lb_hr for g in groups)
    drive_out = sum(g.total_exhaust_available_lb_hr for g in groups)
    # Turbine exhaust_available removes liquid if wet; keep drains visible.
    drive_drains = drive_in - drive_out
    spray_lp_h = SteamStream(P=EXHAUST_PSIA, T=SPRAY_TEMP_F).h
    prds_water_per_lb = (live.h - exhaust.h) / (exhaust.h - spray_lp_h)
    if prds_water_per_lb < 0:
        raise RuntimeError('PRDS inlet is below saturated exhaust enthalpy')

    da_p = 10 + ATM
    fw = SteamStream(P=da_p, x=0)
    incoming_water = SteamStream(T=205, x=0)
    da_vent_h = SteamStream(P=da_p, x=1).h
    vent_fraction = 0.01

    def balance(da_steam):
        exhaust_required = 1.05 * (process_exhaust + da_steam)
        makeup = max(0., exhaust_required - drive_out)
        prds_live = makeup / (1 + prds_water_per_lb)
        live_required = 1.02 * (drive_in + prds_live + 25000)
        lp_boiler = live_required - cogen_header
        if lp_boiler < 0:
            raise RuntimeError('Cogen overfeeds the live header; reduce generation or add an explicit outlet')
        boiler_steam = cogen_in + lp_boiler
        boiler_feed = boiler_steam / (1 - BLOWDOWN_FRACTION)
        da_water_in = boiler_feed - (1 - vent_fraction) * da_steam
        # Exhaust throttling to 10 psig is isenthalpic; vent at DA saturation.
        energy_residual = (da_water_in * incoming_water.h + da_steam * exhaust.h
                           - boiler_feed * fw.h - da_steam * vent_fraction * da_vent_h)
        return dict(da_steam=da_steam, da_water_in=da_water_in, boiler_feed=boiler_feed,
                    exhaust_required=exhaust_required, exhaust_surplus=max(0., drive_out-exhaust_required),
                    prds_live=prds_live, prds_spray=makeup-prds_live, lp_boiler=lp_boiler,
                    live_required=live_required, energy_residual=energy_residual,
                    total_boiler_steam=boiler_steam, da_vent=da_steam*vent_fraction)

    da_steam = brentq(lambda x: balance(x)['energy_residual'], 0., 1_000_000, xtol=1e-7)
    result = balance(da_steam)
    require_close('DA energy residual BTU/hr', result['energy_residual'], 0., atol=1.)
    require_close('250 psig header', result['lp_boiler'] + cogen_header, result['live_required'])
    require_close('22 psig header', drive_out + result['prds_live'] + result['prds_spray'],
                  result['exhaust_required'] + result['exhaust_surplus'])
    require_close('DA mass', result['da_water_in'] + da_steam,
                  result['boiler_feed'] + result['da_vent'])
    bagasse = copy(mills[0].bagasse_stream)
    bagasse.flowrate_lb_hr = sum(m.bagasse_stream.flowrate_lb_hr for m in mills)
    # Boiler instances provide the repository fuel/steam properties. Explicit
    # blowdown energy is added here because Boiler's steam yield omits it.
    hp_boiler = Boiler(bagasse=bagasse, efficiency=70, pressure_psig=600,
                       deg_superheat=400, feed_water_temp=fw.T,
                       capacity=MARGIN*cogen_in, name='Dedicated HP boiler')
    lp_boiler = Boiler(bagasse=bagasse, efficiency=65, pressure_psig=250,
                       deg_superheat=0, feed_water_temp=fw.T,
                       capacity=MARGIN*result['lp_boiler'], name='LP boiler bank')

    def bagasse_needed(boiler, steam):
        bd = steam * BLOWDOWN_FRACTION / (1-BLOWDOWN_FRACTION)
        bd_h = SteamStream(P=boiler.psia, x=0).h
        duty = steam * boiler.btu_for_1_lb + bd * (bd_h-boiler.feed_water_stream.h)
        return duty / (bagasse.gcv * boiler.efficiency / 100)

    hp_fuel = bagasse_needed(hp_boiler, cogen_in)
    lp_fuel = bagasse_needed(lp_boiler, result['lp_boiler'])
    remaining_fuel = bagasse.flowrate_lb_hr - hp_fuel
    # Never feed the whole bagasse pool independently to both boiler systems.
    hp_boiler.bagasse = copy(bagasse)
    hp_boiler.bagasse.flowrate_lb_hr = min(hp_fuel, bagasse.flowrate_lb_hr)
    lp_boiler.bagasse = copy(bagasse)
    lp_boiler.bagasse.flowrate_lb_hr = max(0., remaining_fuel)
    result.update(cogen=cogen, groups=groups, hp_boiler=hp_boiler, lp_boiler_model=lp_boiler,
                  hp_steam=cogen_in, hp_temp=hp_live.T, cogen_header=cogen_header,
                  cogen_spray=cogen_spray, drive_in=drive_in, drive_out=drive_out,
                  drive_drains=drive_drains, hp_fuel=hp_fuel, lp_fuel=lp_fuel,
                  bagasse_available=bagasse.flowrate_lb_hr,
                  bagasse_surplus=bagasse.flowrate_lb_hr-hp_fuel-lp_fuel,
                  hp_fuel_deficit=max(0., hp_fuel-bagasse.flowrate_lb_hr))
    return result


def recommend_equipment(mills, clarifiers, heaters, pres, sets, pans, cooling, steam):
    """Return parallel rows: item, required duty, suggested size, explicit basis."""
    rows = []
    def row(item, duty, size, basis):
        rows.append((item, duty, size, basis))
    def rounded(value, step):
        return math.ceil(value / step) * step

    row('Each milling tandem (2)', f'{CANE_TPD/2/24:,.1f} short ton cane/hr',
        f'{rounded(MARGIN*CANE_TPD/2/24, 25):,.0f} short ton/hr',
        '20% throughput margin; six mills/tandem; roll geometry requires fiber loading and speed')
    for i, heater in enumerate(heaters, 1):
        area = rounded(MARGIN*heater.required_area_ft2, 500)
        row(f'Heater stage {i} ({"V2" if i==1 else "V1"})', f'{heater.required_area_ft2:,.0f}