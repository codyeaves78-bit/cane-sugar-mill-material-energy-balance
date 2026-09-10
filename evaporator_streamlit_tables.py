# Streamlit table builders for the Evaporation tab, mirroring the sections
# written by PreEvaporator.to_excel() and EvaporatorSet.to_excel() — same
# streams/metrics, rendered as st.dataframe-friendly tables instead of an
# Excel sheet.

import pandas as pd

from evaporator_functions import convert_psia_to_psig, convert_psia_to_inHgVac


def _fmt(df, cols=None):
    cols = cols if cols is not None else df.columns[1:]
    for col in cols:
        df[col] = df[col].map(lambda v: f"{v:,.2f}")
    return df


# ---------------------------------------------------------------------------
# Pre-Evaporator
# ---------------------------------------------------------------------------

def pre_evaporator_streams_table(pre) -> pd.DataFrame:
    rows = [
        ("Juice In", pre.juice_in.flow_lb_per_hr, pre.juice_in.brix, pre.juice_in.temp_deg_F),
        ("Juice Out", pre.juice_out_flow_lb_per_hr, pre.juice_out_brix, pre.liquid_temp_deg_F),
        ("Vapor Bleed", pre.vapor_bleed_lb_per_hr, pre.vapor_pressure_psia, pre.vapor_temp_deg_F),
        ("Exhaust Steam", pre.exhaust_required_lb_per_hr, pre.supply_steam.P_psia,
         pre.supply_steam.sat_temp_deg_F),
    ]
    df = pd.DataFrame(rows, columns=["Stream", "Flow (lb/hr)", "Brix / P (psia)", "Temp (°F)"])
    return _fmt(df)


def pre_evaporator_performance_table(pre) -> pd.DataFrame:
    vap_psig = pre.vapor_pressure_psia - 14.696
    rows = [
        ("Vapor pressure (psia)", pre.vapor_pressure_psia),
        ("Vapor pressure (psig)", vap_psig),
        ("Vapor temp (°F)", pre.vapor_temp_deg_F),
        ("Calandria temp (°F)", pre.supply_steam.sat_temp_deg_F),
        ("Heat duty (BTU/hr)", pre.heat_duty_btu_per_hr),
        ("Heating surface (ft²)", pre.area_ft2),
        ("U Dessin (BTU/hr·ft²·°F)", pre.dessin_U),
        ("U calc (BTU/hr·ft²·°F)", pre.U_calc),
        ("U ratio (calc/Dessin)", pre.U_ratio),
    ]
    df = pd.DataFrame(rows, columns=["Metric", "Value"])
    return _fmt(df)


# ---------------------------------------------------------------------------
# Evaporator Set
# ---------------------------------------------------------------------------

def evap_set_summary_table(evap) -> pd.DataFrame:
    syrup_out = evap.evaporator_list[-1].juice_side_out
    rows = [
        ("Juice In", evap.juice_in.flow_lb_per_hr, evap.juice_in.brix, evap.juice_in.temp_deg_F),
        ("Syrup Out", syrup_out.flow_lb_per_hr, syrup_out.brix, syrup_out.temp_deg_F),
        ("Steam Req'd", evap.supply_steam.flow_lb_per_hr, evap.supply_steam.P_psia,
         evap.supply_steam.sat_temp_deg_F),
    ]
    df = pd.DataFrame(rows, columns=["Stream", "Flow (lb/hr)", "Brix / P (psia)", "Temp (°F)"])
    return _fmt(df)


def evap_set_summary_metrics_table(evap) -> pd.DataFrame:
    rows = [
        ("Steam pressure (psig)", convert_psia_to_psig(evap.supply_steam.P_psia)),
        ("Last effect vacuum (in Hg)", convert_psia_to_inHgVac(evap.last_effect_pressure_psia)),
        ("Avg U ratio (calc/Dessin)", evap.U_ratio_avg),
    ]
    df = pd.DataFrame(rows, columns=["Metric", "Value"])
    return _fmt(df)


def evap_set_effect_flows_table(evap) -> pd.DataFrame:
    ef = evap.evaporator_list
    data = {
        f"Effect {i + 1}": [
            f"{e.juice_side_in.flow_lb_per_hr:,.2f}",
            f"{e.juice_side_out.flow_lb_per_hr:,.2f}",
            f"{e.calandria_side.flow_lb_per_hr:,.2f}",
            f"{e.lbs_evaporated_per_hr:,.2f}",
            f"{e.vapor_bleed.flow_lb_per_hr:,.2f}",
            f"{e.area_ft2:,.2f}",
        ]
        for i, e in enumerate(ef)
    }
    return pd.DataFrame(data, index=["Juice in (lb/hr)", "Syrup out (lb/hr)", "Steam in (lb/hr)",
                                      "Evaporated (lb/hr)", "Vapor bleed (lb/hr)",
                                      "Heating surface (ft²)"])


def evap_set_effect_conditions_table(evap) -> pd.DataFrame:
    ef = evap.evaporator_list
    data = {
        f"Effect {i + 1}": [
            f"{e.juice_side_in.brix:,.2f}",
            f"{e.juice_side_out.brix:,.2f}",
            f"{e.juice_side_in.temp_deg_F:,.2f}",
            f"{e.juice_side_out.temp_deg_F:,.2f}",
            f"{e.juice_side_in.cp_btu_per_lb_deg_F:,.2f}",
            f"{e.juice_side_out.cp_btu_per_lb_deg_F:,.2f}",
            f"{e.vapor_pressure_psia:,.2f}",
            f"{e.vapor_temperature:,.2f}",
            f"{e.vapor_out.h_fg:,.2f}",
            f"{e.calandria_side.P_psia:,.2f}",
            f"{e.calandria_side.sat_temp_deg_F:,.2f}",
            f"{e.calandria_side.h_fg:,.2f}",
            f"{e.heat_duty_btu_per_hr / 1e6:,.2f}",
            f"{e.calandria_bleed_pec:,.2f}",
            f"{e.heat_loss_percent:,.2f}",
            f"{e.heat_xfer_U:,.2f}",
            f"{e.dessin_U:,.2f}",
        ]
        for i, e in enumerate(ef)
    }
    index = ["Brix in", "Brix out", "Juice temp (°F)", "Syrup temp (°F)", "Juice cp", "Syrup cp",
             "Vapor P (psia)", "Vapor temp (°F)", "Vapor h_fg (BTU/lb)", "Calandria P (psia)",
             "Calandria temp (°F)", "Calandria h_fg (BTU/lb)", "Duty (MM BTU/hr)",
             "Gas bleed (%)", "Heat loss (%)",
             "U calc (BTU/hr·ft²·°F)", "U Dessin (BTU/hr·ft²·°F)"]
    return pd.DataFrame(data, index=index)


def evap_set_energy_balance_table(evap) -> pd.DataFrame:
    ef = evap.evaporator_list
    rows = [
        {
            "Effect": f"Effect {i + 1}",
            "Steam (lb/hr)": f"{e.calandria_side.flow_lb_per_hr:,.2f}",
            "h_fg (BTU/lb)": f"{e.calandria_side.h_fg:,.2f}",
            "Entering (MM BTU/hr)": f"{e.heat_duty_btu_per_hr / 1e6:,.2f}",
            "Heat Loss (MM BTU/hr)": f"{e.heat_loss_btu_per_hr / 1e6:,.2f}",
            "Sensible (MM BTU/hr)": f"{e.heat_from_flash / 1e6:,.2f}",
            "Net for Evap (MM BTU/hr)": f"{e.heat_available_for_evaporation / 1e6:,.2f}",
            "Evaporated (lb/hr)": f"{e.lbs_evaporated_per_hr:,.2f}",
        }
        for i, e in enumerate(ef)
    ]
    return pd.DataFrame(rows)


def evap_set_condenser_table(evap) -> pd.DataFrame:
    cond = evap.condenser
    rows = [
        ("Vapor to condenser (lb/hr)", cond.vapor_flow_lb_hr),
        ("Vapor saturation temp (°F)", cond.vapor_sat_temp_F),
        ("Vapor h_fg (BTU/lb)", cond.vapor_h_fg_btu_lb),
        ("Heat load (BTU/hr)", cond.heat_load_btu_hr),
        ("Injection water in (°F)", evap.injection_water_temp_F),
        ("Water outlet temp (°F)", cond.water_outlet_temp_F),
        ("Injection water flow (lb/hr)", cond.injection_water_flow_lb_hr),
        ("Injection water flow (GPM)", cond.injection_water_flow_lb_hr / 500.4),
        ("Total outlet flow (lb/hr)", cond.total_outlet_flow_lb_hr),
    ]
    df = pd.DataFrame(rows, columns=["Metric", "Value"])
    return _fmt(df)


def evap_set_condensate_table(evap) -> pd.DataFrame:
    rows = [
        ("Clean condensate (lb/hr)", evap.clean_condensate),
        ("Dirty condensate (lb/hr)", evap.dirty_condensate),
        ("Total condensate (lb/hr)", evap.clean_condensate + evap.dirty_condensate),
    ]
    df = pd.DataFrame(rows, columns=["Metric", "Value"])
    return _fmt(df)
