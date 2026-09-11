# Streamlit trial app: full factory material & energy balance walkthrough,
# following the same pipeline as main.py:
#   Mill Floor -> Clarification -> Juice Heating -> Pan Floor -> Evaporation
#   -> Steam & Exhaust Summary -> Download
#
# Run with:  streamlit run streamlit_app.py

import io

import time
from datetime import datetime
import matplotlib
matplotlib.use("Agg")  # headless backend, required before pyplot is imported anywhere
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from MillFloor import MillFloor
from Clarification import Clarification
from clarification_diagram import _collect_streams
from excel_export import new_workbook
from SugarStream import SugarStream
from SteamStream import SteamStream, EvaporatorSteam
from JuiceHeater import JuiceHeaterShellTube
from JuiceHeatingStation import JuiceHeatingStation
from Pan import Pan
from Centrifugal import Centrifugal
from Crystallizer_and_Reheater import Crystallizer, Reheater
from ThreeBoilingDoubleMagma import ThreeBoilingDoubleMagma
from FourBoilingDoubleMagma import FourBoilingDoubleMagma
from TwoBoiling import TwoBoiling
from ThreeBoiling import ThreeBoiling
from pan_floor_streamlit_table import (
    COLUMNS as PAN_FLOOR_TABLE_COLUMNS,
    three_boiling_rows, four_boiling_rows, two_boiling_rows,
    three_boiling_single_magma_rows, steam_consumption_table,
    massecuite_summary_table,
)
from PreEvaporator import PreEvaporator
from EvaporatorSet import sets_to_excel
from multi_effect_solver_scipy import solve_evaporator_sets_scipy
from multi_effect_solver_vers_2 import solve_evaporator_sets
from evaporator_streamlit_tables import (
    pre_evaporator_streams_table, pre_evaporator_performance_table,
    evap_set_summary_table, evap_set_summary_metrics_table,
    evap_set_effect_flows_table, evap_set_effect_conditions_table,
    evap_set_energy_balance_table, evap_set_condenser_table, evap_set_condensate_table,
)
from Deaerator import Deaerator
from MillTurbines import MillTurbines
from CanePrepTurbines import CanePrepTurbines
from AuxillaryTurbines import AuxillaryTurbines
from turbine_diagram import _group_info as _turbine_group_info
from Boiler import Boiler
from boiler_streamlit_tables import (
    boiler_parameters_table, boiler_streams_table, boiler_fuel_table, boiler_performance_table,
)
from CoolingTowerSystem import CoolingTowerSystem
from cooling_tower_streamlit_tables import (
    cooling_tower_streams_table, cooling_tower_condenser_table, cooling_tower_balance_table,
)
from condensate_balance import CondensateBalance, CondensateDemand
from condensate_utils import flash_condensate
from steam_summary_excel import steam_summary_to_excel

st.set_page_config(page_title="Factory Balance Trial", layout="wide")
st.title("Cane Sugar Factory Material & Energy Balance")
st.caption("Trial Streamlit walkthrough: Mill Floor → Clarification → Juice Heating → "
           "Pan Floor → Evaporation → Steam & Exhaust Summary.")
st.caption("Version 0.1")
st.caption("Creator: Cody Eaves")

# ============================================================================
# SOLVE CACHE
#
# Every input widget on every tab always renders and always reflects its
# current value (Streamlit reruns the whole script top-to-bottom on any
# interaction — that part is unavoidable). What used to be unconditional here
# is the EXPENSIVE part: constructing MillFloor/Clarification/JuiceHeating
# Station/the boiling-scheme solver/the evaporator-set solver/turbines/
# Boiler/CoolingTowerSystem/CondensateBalance, all of which re-ran on every
# single keystroke anywhere in the app. That's what made editing one cell
# take 10+ seconds once the plant was solved once.
#
# SOLVED is the one place all of that lives. Nothing in the block below is
# recomputed unless solve_clicked is True (the global "Solve Entire Plant"
# button below); every tab's display section reads its stage's result back
# out of SOLVED, so edits in between clicks just re-render cached results —
# fast — and the pipeline only actually re-solves when you ask it to.
# ============================================================================
if "solved" not in st.session_state:
    st.session_state.solved = {}
SOLVED = st.session_state.solved

if "solve_gen" not in st.session_state:
    st.session_state.solve_gen = 0

# PFD figures are kept out of SOLVED on purpose: SOLVED entries are wiped/rebuilt
# every time their pipeline stage re-solves, but generating a PFD is the slow part
# (that's why it got pulled out of the solve path in the first place — see the
# "Check Process Flow Diagrams" tab), so a diagram should only regenerate when its
# own button is clicked, not on every re-solve of its station.
if "pfd_cache" not in st.session_state:
    st.session_state.pfd_cache = {}
PFD_CACHE = st.session_state.pfd_cache


def should_resolve(stage_key):
    """True exactly once per click of "Solve Entire Plant", per pipeline stage.

    Every tab below is its own st.fragment so that editing one tab's widgets only
    reruns that tab, not the whole app — but a fragment rerun does NOT re-execute
    the rest of the script, so a plain `solve_clicked = st.button(...)` variable
    read from inside a fragment would go stale: it would keep reading True on every
    later fragment-only rerun after the button was clicked once, silently re-solving
    that one tab on every subsequent edit. st.session_state isn't subject to that —
    it's read fresh on every call, fragment or not — so instead each stage compares
    a shared click-generation counter (bumped once per real button click) against
    the generation it last solved for. Call mark_resolved(stage_key) once the
    attempt (success or failure) is done, so the same generation isn't re-attempted
    on the next unrelated edit.
    """
    return SOLVED.get(f"_gen_{stage_key}") != st.session_state.solve_gen


def mark_resolved(stage_key):
    SOLVED[f"_gen_{stage_key}"] = st.session_state.solve_gen

STEAM_TYPES = ["Exhaust", "V1", "V2", "V3", "V4"]
WATER_LB_PER_GAL = 8.33045


def resolve_cj():
    """Clarified juice as it exists right now: post juice-heating if that stage has
    ever solved successfully, otherwise straight from Clarification. Tabs after Juice
    Heating call this themselves rather than reading a plain `cj` variable that only
    Juice Heating's own fragment reassigns — each tab fragment is its own function
    now, so that reassignment wouldn't otherwise be visible outside it."""
    cj_after_heat = SOLVED.get("cj_after_heat")
    return cj_after_heat if cj_after_heat is not None else clar.clarified_juice_stream


def parse_floats(s):
    if s is None:
        return []
    return [float(v) for v in str(s).replace(";", ",").split(",") if v.strip() != ""]


def vapor_dist_editor(grade, demand, consumers, key, default_pcts=None):
    """Render a '% of V{grade} demand' distribution editor across the given
    consumer names (evaporator sets, plus 'Pre-Evaporator' for grade 1).
    Returns (share_fn, dataframe) — share_fn(consumer_name) -> lb/hr.

    An evaporator set can only supply V{grade} if it has at least `grade`
    effects (effect k's own vapor feeds header V{k}; the last effect never
    bleeds, its vapor goes to the condenser) — see EvaporatorSet.build_effects.
    """
    col = f"% of V{grade} demand"
    st.markdown(f"**V{grade} Vapor Bleed Distribution** — total V{grade} demand "
                f"(heaters + pans): {demand:,.0f} lb/hr")
    if demand <= 0:
        st.caption(f"No V{grade} demand from heaters or pans.")
        return (lambda cname: 0.0), pd.DataFrame(columns=["Consumer", col])
    if not consumers:
        st.warning(f"V{grade} demand of {demand:,.0f} lb/hr exists but nothing can supply it — "
                    + ("activate the Pre-Evaporator or " if grade == 1 else "")
                    + f"add/edit an evaporator set with at least {grade} effect(s).")
        return (lambda cname: 0.0), pd.DataFrame(columns=["Consumer", col])

    default_pcts = default_pcts or {}
    pcts = [default_pcts.get(c, 0.0) for c in consumers]
    if sum(pcts) <= 0:
        pcts = [100.0 / len(consumers)] * len(consumers)
    df = st.data_editor(
        pd.DataFrame({"Consumer": consumers, col: pcts}),
        hide_index=True, use_container_width=True, num_rows="fixed", key=key,
        disabled=["Consumer"],
    )
    pct_sum = df[col].sum()
    if pct_sum <= 0:
        st.warning(f"V{grade} distribution percentages sum to 0 — no V{grade} will be bled off.")
    elif abs(pct_sum - 100) > 0.01:
        st.caption(f"Percentages sum to {pct_sum:.1f}%, not 100% — normalizing proportionally.")

    def share(cname):
        s = df[col].sum()
        if s <= 0:
            return 0.0
        row = df[df["Consumer"] == cname]
        if row.empty:
            return 0.0
        return float(row[col].iloc[0]) / s * demand

    return share, df


def pan_editor(key, defaults):
    df = pd.DataFrame(defaults)
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, num_rows="fixed", key=key,
        column_config={"Steam Type": st.column_config.SelectboxColumn(options=STEAM_TYPES)},
    )
    pans = {}
    for _, row in edited.iterrows():
        pans[row["Grade"]] = Pan(
            feed_streams=None,
            heating_surface_ft2=float(row["Heating Surface (ft²)"]),
            inches_vacuum=float(row["Vacuum (in Hg)"]),
            supersaturation=float(row["Supersaturation"]),
            head_ft=float(row["Head (ft)"]),
            masse_brix=float(row["Masse Brix"]),
            ml_purity=float(row["Mother Liquor Purity"]),
            calandria_pressure_psia=float(row["Calandria (psia)"]),
            heat_loss_factor=float(row["Heat Loss Factor"]),
            steam_type=STEAM_TYPES.index(row["Steam Type"]),
            name=f"{row['Grade']} Pans",
        )
    return pans


def cen_editor(key, defaults):
    df = pd.DataFrame(defaults)
    edited = st.data_editor(df, hide_index=True, use_container_width=True, num_rows="fixed", key=key)
    cens = {}
    for _, row in edited.iterrows():
        cens[row["Grade"]] = Centrifugal(
            massecuite=None, massecuite_flow_lb_hr=0,
            target_molasses_brix=float(row["Molasses Brix Out"]),
            purity_rise=float(row["Purity Rise"]),
            sugar_purity=float(row["Sugar Purity"]),
            sugar_moisture=float(row["Sugar Moisture"]),
            sugar_temp=float(row["Sugar Temp"]),
            molasses_temp=float(row["Molasses Temp"]),
            name=f"{row['Grade']} Centrifugals",
        )
    return cens


def turbine_group_table(group):
    """One row per turbine unit + a TOTAL row — reuses turbine_diagram's own
    duck-typed adapter (also used for the PFD table and Excel export) so the
    numbers always match what's drawn/exported."""
    info = _turbine_group_info(group)
    df = pd.DataFrame(info["rows"] + [info["total"]], columns=info["headers"])
    for col in df.columns[1:]:
        df[col] = df[col].map(lambda v: f"{v:,.4f}" if isinstance(v, float) else v)
    return df


# ============================================================================
# SIDEBAR — MILL FLOOR + CLARIFICATION
# ============================================================================
with st.sidebar:
    solve_clicked = st.button("🔄 Solve Entire Plant", type="primary", use_container_width=True)    
    st.header("Mill Floor Inputs")
    st.subheader("Cane & Mills")
    cane_tpd = st.number_input("Cane throughput (TPD)", value=19000.0, step=100.0)
    cane_pol_pct = st.number_input("Cane pol (%)", value=13.5, step=0.1)
    cane_fiber_pct = st.number_input("Cane fiber (%)", value=14.0, step=0.1)
    number_of_mills = st.number_input("Number of mills", value=6, min_value=2, max_value=8, step=1)
    mill_1_fiber_rise_load_fraction = st.number_input(
        "Mill 1 fiber rise load fraction", value=0.35, step=0.01, format="%.2f"
    )

    st.subheader("Imbibition & Juice")
    imbibition_pct_on_cane = st.number_input("Imbibition (% on cane)", value=30.0, step=0.5)
    juice_temp_F = st.number_input("Juice temperature (°F)", value=90.0, step=1.0)
    mix_juice_purity = st.number_input("Mixed juice purity (%)", value=88.0, step=0.1)

    st.subheader("Bagasse")
    bagasse_pol_pct = st.number_input("Bagasse pol (%)", value=2.1, step=0.1)
    last_roll_purity = st.number_input("Last roll juice purity (%)", value=72.0, step=0.5)
    bagasse_moisture_pct = st.number_input("Bagasse moisture (%)", value=49.5, step=0.5)
    bagasse_ash_pct = st.number_input("Bagasse ash (%)", value=5.0, step=0.5)

    st.header("Clarification Inputs")
    filter_wash_water_pct_on_cane = st.number_input("Filter wash water (% on cane)", value=5.0, step=0.5)
    filter_cake_pct_on_cane = st.number_input("Filter cake (% on cane)", value=5.0, step=0.5)
    filter_cake_pol_pct = st.number_input("Filter cake pol (%)", value=2.4, step=0.1)
    clarified_juice_purity = st.number_input("Clarified juice purity (%)", value=88.5, step=0.1)
    limed_juice_cold_temp_f = st.number_input("Limed juice cold temp (°F)", value=95.0, step=1.0)
    limed_juice_hot_temp_f = st.number_input("Limed juice hot temp (°F)", value=220.0, step=1.0)
    clarified_juice_temp_f = st.number_input("Clarified juice temp (°F)", value=205.0, step=1.0)
    lime_lb_per_ton_cane = st.number_input("Lime dose (lb/ton cane)", value=1.3, step=0.1)
    lime_baume = st.number_input("Milk of lime (°Baumé)", value=10.0, step=0.5)
    polymer_conc_ppm = st.number_input("Polymer concentration (ppm)", value=5000.0, step=100.0)
    polymer_lb_per_ton_cane = st.number_input(
        "Polymer dose (lb/ton cane)", value=0.045, step=0.005, format="%.3f"
    )
    clarifier_underflow_pct_cane = st.number_input("Clarifier underflow (% on cane)", value=20.0, step=0.5)

    
st.divider()
psia_col, psig_col = st.columns([1, 3])
with psia_col:
    fabrication_exhaust_psia = st.number_input(
        "Fabrication exhaust pressure (psia)", value=30.0, step=1.0,
        help="Default steam supply pressure for the juice heaters and the pre-evaporator.",
    )
with psig_col:
    st.caption("psig equivalent")
    st.markdown(
        f"<div style='font-size:1.1rem; padding-top:0.25rem;'>{fabrication_exhaust_psia - 14.696:.2f}</div>",
        unsafe_allow_html=True,
    )


if solve_clicked:
    st.session_state.solve_gen += 1
st.caption(
    "Every input on every tab is always live and editable, but nothing recomputes until you "
    "click **Solve Entire Plant** — edit whatever you need across as many tabs as you like, "
    "then solve once."
)

# ============================================================================
# MILL FLOOR + CLARIFICATION — first stage of the pipeline. Only (re)solved
# when the global button above is clicked; otherwise we just read back
# whatever was cached from the last successful solve.
# ============================================================================
if solve_clicked:
    try:
        mills = MillFloor(
            cane_tpd=cane_tpd,
            cane_pol_pct=cane_pol_pct,
            cane_fiber_pct=cane_fiber_pct,
            imbibition_pct_on_cane=imbibition_pct_on_cane,
            bagasse_pol_pct=bagasse_pol_pct,
            last_roll_purity=last_roll_purity,
            bagasse_moisture_pct=bagasse_moisture_pct,
            bagasse_ash_pct=bagasse_ash_pct,
            mix_juice_purity=mix_juice_purity,
            number_of_mills=int(number_of_mills),
            juice_temp_F=juice_temp_F,
            mill_1_fiber_rise_load_fraction=mill_1_fiber_rise_load_fraction,
            name="Mill Floor",
        )

        clar = Clarification(
            mixed_juice_stream=mills.mixed_juice_stream,
            cane_tpd=mills.cane_tpd,
            filter_wash_water_pct_on_cane=filter_wash_water_pct_on_cane,
            filter_cake_pct_on_cane=filter_cake_pct_on_cane,
            filter_cake_pol_pct=filter_cake_pol_pct,
            clarified_juice_purity=clarified_juice_purity,
            limed_juice_cold_temp_f=limed_juice_cold_temp_f,
            limed_juice_hot_temp_f=limed_juice_hot_temp_f,
            clarified_juice_temp_f=clarified_juice_temp_f,
            lime_lb_per_ton_cane=lime_lb_per_ton_cane,
            lime_baume=lime_baume,
            polymer_conc_ppm=polymer_conc_ppm,
            polymer_lb_per_ton_cane=polymer_lb_per_ton_cane,
            clarifier_underflow_pct_cane=clarifier_underflow_pct_cane,
            name="Clarification",
        )

       # mills_fig = mills.generate_pfd(show=False)
       # clar_fig = clar.generate_pfd(show=False, include_table=False)
       # plt.close(mills_fig)
       # plt.close(clar_fig)

        SOLVED["mills"] = mills
        SOLVED["clar"] = clar
       # SOLVED["mills_pfd"] = mills_fig
       # SOLVED["clar_pfd"] = clar_fig
        SOLVED["mill_clar_error"] = None
    except Exception as exc:
        SOLVED["mills"] = None
        SOLVED["clar"] = None
        SOLVED["mill_clar_error"] = str(exc)

mills = SOLVED.get("mills")
clar = SOLVED.get("clar")

if mills is None or clar is None:
    if SOLVED.get("mill_clar_error"):
        st.error(f"Balance failed to solve: {SOLVED['mill_clar_error']}")
    st.info("Set your inputs in the sidebar and click **Solve Entire Plant** above to solve the "
            "mill floor and clarification balance, which unlocks the rest of the plant.")
    st.stop()

mj = mills.mixed_juice_stream
bag = mills.bagasse_stream
cj = clar.clarified_juice_stream


(tab_mill, tab_clar, tab_heat, tab_pan, tab_evap, tab_steam, tab_turb, tab_cool,
 tab_cond, tab_dl, tab_pfd) = st.tabs([
    "Mill Floor", "Clarification", "Juice Heating", "Pan Floor",
    "Evaporation", "Exhaust Summary", "Turbines & Boiler", "Cooling Tower",
    "Condensate Balance", "Download", "Check Process Flow Diagrams"
])

# ============================================================================
# MILL FLOOR TAB
# ============================================================================
@st.fragment
def render_tab_mill():
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mill extraction", f"{mills.mill_extraction_pct:.2f}%")
    c2.metric("Mixed juice flow", f"{mj.flow_lb_per_hr:,.0f} lb/hr")
    c3.metric("Mixed juice brix / purity", f"{mj.brix:.2f}% / {mj.purity:.1f}%")
    c4.metric("Bagasse flow", f"{bag.flowrate_lb_hr / 2000 * 24:,.0f} TPD")

    st.subheader("Stream Table (TPH)")
    rows, in_tot, out_tot = mills._stream_table_rows()
    diff = [i - o for i, o in zip(in_tot, out_tot)]
    cols = ["Stream", "Dir", "Flow (TPH)", "Pol (TPH)", "Brix (TPH)", "Fiber (TPH)", "Water (TPH)"]
    df = pd.DataFrame(rows, columns=cols)
    totals_df = pd.DataFrame(
        [["Total In", "", *in_tot], ["Total Out", "", *out_tot], ["Difference", "", *diff]],
        columns=cols,
    )
    st.dataframe(pd.concat([df, totals_df], ignore_index=True), use_container_width=True, hide_index=True)

    st.subheader("Per-Mill Maceration Balance (TPD)")
    mb_df = pd.DataFrame(mills.mill_balances)
    st.dataframe(mb_df, use_container_width=True, hide_index=True)

    st.subheader("Balance Check")
    bal = mills.balance_check
    bal_df = pd.DataFrame(bal).T.reset_index().rename(columns={"index": "Quantity"})
    st.dataframe(bal_df, use_container_width=True, hide_index=True)


with tab_mill:
    render_tab_mill()
# ============================================================================
# CLARIFICATION TAB
# ============================================================================
@st.fragment
def render_tab_clar():
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clarified juice flow", f"{cj.flow_lb_per_hr:,.0f} lb/hr")
    c2.metric("Clarified juice brix / purity", f"{cj.brix:.2f}% / {cj.purity:.1f}%")
    c3.metric("Flash vapor", f"{clar.flash_vapor_pct:.3f}%")
    c4.metric("Filter cake pol loss", f"{clar.filter_cake_pol_lb_per_day:,.0f} lb/day")

    st.subheader("Stream Table (tags match the diagram)")
    stream_cols = ["#", "Stream", "Dir", "lb/hr", "GPM", "Brix lb/hr", "Pol lb/hr",
                   "Brix %", "Pol %", "Purity %", "% on Cane", "°F"]
    st.dataframe(pd.DataFrame(_collect_streams(clar), columns=stream_cols),
                 use_container_width=True, hide_index=True)

    st.subheader("Balance Check")
    bal = clar.balance_check
    bal_df = pd.DataFrame(bal).T.reset_index().rename(columns={"index": "Quantity"})
    st.dataframe(bal_df, use_container_width=True, hide_index=True)


with tab_clar:
    render_tab_clar()
# ============================================================================
# JUICE HEATING TAB
# ============================================================================
DEFAULT_V1_PSIA = 21 # PSIA


def heater_perf_row(h):
    return {
        "Heater": h.name,
        "Steam Type": STEAM_TYPES[h.steam_type],
        "Steam Pressure (psia)": f"{h.hot_stream.P:,.2f}",
        "Steam Temp (°F)": f"{h.hot_stream.T:,.2f}",
        "Steam hfg (BTU/lb)": f"{h.hot_stream.h_fg:,.2f}",
        "Steam Flow (lb/hr)": f"{h.steam_required_lb_per_hr:,.2f}",
        "U (Btu/hr·ft²·°F)": f"{h.U:,.2f}",
        "Area Installed (ft²)": f"{h.installed_area_ft2:,.2f}",
        "Area Required (ft²)": f"{h.required_area_ft2:,.2f}",
        "Juice Flow In (lb/hr)": f"{h.cold_stream.flow_lb_per_hr:,.2f}",
        "Juice Temp In (°F)": f"{h.cold_stream.temp_deg_F:,.2f}",
        "Juice Temp Out (°F)": f"{h.juice_out_temp_degF:,.2f}",
        "Juice cp (Btu/lb·°F)": f"{h.cold_stream.cp_btu_per_lb_deg_F:,.2f}",
        "Duty (MM BTU/hr)": f"{h.Q_btu_per_hr / 10**6:,.2f}",
        "LMTD (deg F)": f"{h.LMTD_degF:,.2f}", # forgot the name here
    }


@st.fragment
def render_tab_heat():
    st.subheader("Juice Heating Station")
    juice_T_out = clar.limed_juice_hot_temp_f
    cold_juice = clar.limed_juice_cold_stream

    mode = st.radio("Flow arrangement", ["parallel", "series"], horizontal=True)
    heater_rows = [
        {"Group": "V1 Heaters", "Steam Type": "V1", "Steam Pressure (psia)": float(DEFAULT_V1_PSIA),
         "U (Btu/hr·ft²·°F)": 200.0, "Area (ft²)": 11000.0},
        {"Group": "Exhaust Heaters", "Steam Type": "Exhaust", "Steam Pressure (psia)": float(fabrication_exhaust_psia),
         "U (Btu/hr·ft²·°F)": 200.0, "Area (ft²)": 5000.0},
    ]
    if mode == "parallel":
        heater_defaults = pd.DataFrame([{**heater_rows[0], "Split %": 75.0},
                                         {**heater_rows[1], "Split %": 25.0}])
    else:
        heater_defaults = pd.DataFrame(heater_rows)

    st.markdown("###### Input Table")
    heater_df = st.data_editor(
        heater_defaults, hide_index=True, use_container_width=True, num_rows="fixed",
        column_config={"Steam Type": st.column_config.SelectboxColumn(options=STEAM_TYPES)},
        key=f"heater_editor_{mode}",
    )

    if mode == "series":
        t1, t2 = st.columns(2)
        primary_temp_out = t1.number_input(
            f"{heater_df.iloc[0]['Group']} exit temp (°F)", value=180.0, step=1.0,
            key="primary_temp_out",
        )
        t2.number_input(
            f"{heater_df.iloc[1]['Group']} exit temp (°F) 🔒", value=float(juice_T_out), step=1.0,
            disabled=True, help="Fixed to the sidebar's \"Limed juice hot temp (°F)\" input.",
            key="secondary_temp_out",
        )
        temp_outs = [primary_temp_out, juice_T_out]
    else:
        temp_outs = [juice_T_out] * len(heater_df)

    st.divider()
    st.subheader("Clarified Juice Heater")
    st.markdown("###### Input Section")
    cj_cols = st.columns(5)
    cjh_steam_type = cj_cols[0].selectbox("Steam type", ["Exhaust", "V1"], key="cjh_steam_type")
    cjh_temp = cj_cols[1].number_input("Juice out temp (°F)", value=225.0, step=1.0)
    cjh_U = cj_cols[2].number_input("U (Btu/hr·ft²·°F)", value=185.0, step=5.0)
    cjh_area = cj_cols[3].number_input("Area (ft²)", value=6000.0, step=500.0)
    cjh_default_psia = float(DEFAULT_V1_PSIA) if cjh_steam_type == "V1" else float(fabrication_exhaust_psia)
    cjh_psia = cj_cols[4].number_input("Steam pressure (psia)", value=cjh_default_psia,
                                        step=1.0, key=f"cjh_psia_{cjh_steam_type}")

    if should_resolve("heat"):
        mark_resolved("heat")
        try:
            heater_objs = [
                JuiceHeaterShellTube(
                    cold_stream=cold_juice,
                    hot_stream=SteamStream(x=1, P=row["Steam Pressure (psia)"]),
                    name=row["Group"],
                    juice_out_temp_degF=temp_outs[i],
                    U_btu_per_ft2_degF=row["U (Btu/hr·ft²·°F)"],
                    installed_area_ft2=row["Area (ft²)"],
                    steam_type=STEAM_TYPES.index(row["Steam Type"]),
                )
                for i, (_, row) in enumerate(heater_df.iterrows())
            ]
            split_pcts = list(heater_df["Split %"]) if mode == "parallel" else None
            juice_heaters = JuiceHeatingStation(
                cold_stream=cold_juice, heaters=heater_objs, mode=mode,
                split_pcts=split_pcts,
                name="Parallel Juice Heating Station" if mode == "parallel" else "Series Juice Heating Station",
            )

            clar_juice_colder = SugarStream.copy(cj)
            clar_juice_heater = JuiceHeaterShellTube(
                cold_stream=clar_juice_colder,
                hot_stream=SteamStream(x=1, P=cjh_psia),
                name="Clarified Juice Heater",
                juice_out_temp_degF=cjh_temp,
                U_btu_per_ft2_degF=cjh_U,
                installed_area_ft2=cjh_area,
                steam_type=STEAM_TYPES.index(cjh_steam_type),
            )
            # Rebind to a fresh copy rather than mutating clar.clarified_juice_stream in place —
            # that object is cached in st.session_state.solved, so an in-place write here would
            # compound on every re-solve (each solve's "juice in" would already sit at last
            # solve's "juice out"), collapsing this heater's duty to zero after the first click.
            cj_after_heat = SugarStream.copy(cj)
            cj_after_heat.temp_deg_F = clar_juice_heater.juice_out_temp_degF

           # heaters_fig = juice_heaters.generate_pfd(show=False)
           # cjh_fig = clar_juice_heater.generate_pfd(show=False)
           # plt.close(heaters_fig)
           # plt.close(cjh_fig)

            SOLVED["juice_heaters"] = juice_heaters
            SOLVED["clar_juice_heater"] = clar_juice_heater
            SOLVED["cj_after_heat"] = cj_after_heat
            SOLVED["cjh_steam_type"] = cjh_steam_type
           # SOLVED["heaters_pfd"] = heaters_fig
           # SOLVED["cjh_pfd"] = cjh_fig
            SOLVED["heat_ok"] = True
            SOLVED["heat_error"] = None
        except Exception as exc:
            SOLVED["juice_heaters"] = None
            SOLVED["clar_juice_heater"] = None
            SOLVED["cj_after_heat"] = None
            SOLVED["heat_ok"] = False
            SOLVED["heat_error"] = str(exc)

    juice_heaters = SOLVED.get("juice_heaters")
    clar_juice_heater = SOLVED.get("clar_juice_heater")
    heat_ok = SOLVED.get("heat_ok", False)

    if heat_ok:
        # Named cj_display, not cj: this function never reads the module-level `cj`
        # (Juice Heating starts from `cold_juice`/`clar.clarified_juice_stream`), but a
        # local variable named `cj` here would still shadow the global for pyflakes'
        # (and Python's) purposes and risk an UnboundLocalError-style footgun later.
        cj_display = SOLVED["cj_after_heat"]

        st.markdown("**Juice Heater performance**")
        heater_perf_df = pd.DataFrame(
            [heater_perf_row(h) for h in juice_heaters.heaters]
        ).set_index("Heater").T
        st.dataframe(heater_perf_df, use_container_width=True, height="content")

        st.markdown(
            """<style>
            .st-key-heater_steam_metrics [data-testid="stMetricValue"] { font-size: 1.1rem; }
            .st-key-heater_steam_metrics [data-testid="stMetricLabel"] { font-size: 0.8rem; }
            </style>""",
            unsafe_allow_html=True,
        )
        with st.container(key="heater_steam_metrics"):
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Juice out", f"{juice_heaters.juice_out.flow_lb_per_hr:,.0f} lb/hr")
            c2.metric("Exhaust", f"{juice_heaters.total_exhaust_steam_lb_hr:,.0f} lb/hr")
            c3.metric("V1", f"{juice_heaters.total_V1_steam_lb_hr:,.0f} lb/hr")
            c4.metric("V2", f"{juice_heaters.total_V2_steam_lb_hr:,.0f} lb/hr")
            c5.metric("V3", f"{juice_heaters.total_V3_steam_lb_hr:,.0f} lb/hr")
            c6.metric("V4", f"{juice_heaters.total_V4_steam_lb_hr:,.0f} lb/hr")

        st.markdown("**Clarified Juice Heater performance**")
        clar_juice_perf_df = pd.DataFrame(
            [heater_perf_row(clar_juice_heater)]
        ).set_index("Heater").T
        st.dataframe(clar_juice_perf_df, use_container_width=True, height="content")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Flow out", f"{clar_juice_heater.juice_out.flow_lb_per_hr:,.0f} lb/hr")
        c2.metric("Temp in", f"{clar_juice_heater.cold_stream.temp_deg_F:.1f} °F")
        c3.metric("Temp out", f"{cj_display.temp_deg_F:.1f} °F")
        c4.metric(f"Steam required ({SOLVED.get('cjh_steam_type', cjh_steam_type)})",
                  f"{clar_juice_heater.steam_required_lb_per_hr:,.0f} lb/hr")

       # st.pyplot(SOLVED["heaters_pfd"], use_container_width=True)
        # st.pyplot(SOLVED["cjh_pfd"], use_container_width=True)
    elif SOLVED.get("heat_error"):
        st.error(f"Juice heating failed to solve: {SOLVED['heat_error']}")
    else:
        st.info("Click **Solve Entire Plant** above to compute the juice heating station.")


with tab_heat:
    render_tab_heat()
# ============================================================================
# PAN FLOOR TAB
# ============================================================================
pan_ok = False
pan_floor = None
syrup_brix = 65.0

@st.fragment
def render_tab_pan():
    st.subheader("Pan Floor")
    scheme = st.radio(
        "Boiling scheme",
        ["FBDM (Four Boiling Double Magma)", "TBDM (Three Boiling Double Magma)",
         "3B (Three Boiling - Single Magma)", "2B (Two Boiling)"],
        horizontal=True,
    )
    is_fbdm = scheme.startswith("FBDM")
    is_tbdm = scheme.startswith("TBDM")
    is_3b = scheme.startswith("3B")
    is_2b = scheme.startswith("2B")
    scheme_key = "FBDM" if is_fbdm else ("TBDM" if is_tbdm else ("3B" if is_3b else "2B"))

    cj = resolve_cj()
    syrup_brix = st.number_input("Syrup brix", value=65.0, step=0.5, key="syrup_brix")
    syrup_lb_hr = cj.flow_lb_per_hr * cj.brix / syrup_brix
    syrup = SugarStream.copy(cj)
    syrup.flow_lb_per_hr = syrup_lb_hr
    syrup.brix = syrup_brix
    st.caption(f"Syrup feed: {syrup_lb_hr:,.0f} lb/hr @ {syrup_brix:.1f} Bx "
               f"(from clarified juice @ {cj.brix:.2f} Bx)")

    st.markdown("**Global pan floor settings**")
    ad1, ad2, ad3, ad4, ad5, ad6 = st.columns(6)
    pf_injection_water_temp_F = ad1.number_input("Injection water temp (°F)", value=90.0, step=1.0,
                                                  key="pf_inj_water")
    pf_condenser_leg_temp_drop_F = ad2.number_input("Condenser leg ΔT (°F)", value=5.0, step=0.5,
                                                     key="pf_cond_leg")
    pf_c_magma_brix = ad3.number_input("C magma brix", value=92.0, step=0.5, key="pf_c_magma_brix")
    pf_c_remelt_brix = ad4.number_input("C remelt brix", value=65.0, step=0.5, key="pf_c_remelt_brix")
    if not is_2b and not is_3b:
        pf_b_magma_brix = ad5.number_input("B magma brix", value=92.0, step=0.5, key="pf_b_magma_brix")
        pf_b_remelt_brix = ad6.number_input("B remelt brix", value=65.0, step=0.5, key="pf_b_remelt_brix")
    else:
        pf_b_magma_brix = pf_b_remelt_brix = None

    st.markdown("**Pans**")
    if is_fbdm:
        pan_defaults = [
            dict(Grade="A1", **{"Heating Surface (ft²)": 16000.0, "Vacuum (in Hg)": 23.5, "Supersaturation": 1.2,
                                 "Head (ft)": 2.0, "Masse Brix": 92.0, "Mother Liquor Purity": 75.0,
                                 "Calandria (psia)": 21.696, "Heat Loss Factor": 0.02, "Steam Type": "V1"}),
            dict(Grade="A2", **{"Heating Surface (ft²)": 6000.0, "Vacuum (in Hg)": 23.5, "Supersaturation": 1.2,
                                 "Head (ft)": 2.0, "Masse Brix": 92.0, "Mother Liquor Purity": 70.0,
                                 "Calandria (psia)": 21.696, "Heat Loss Factor": 0.02, "Steam Type": "V1"}),
            dict(Grade="B", **{"Heating Surface (ft²)": 7500.0, "Vacuum (in Hg)": 25.0, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 94.0, "Mother Liquor Purity": 52.0,
                                "Calandria (psia)": 29.696, "Heat Loss Factor": 0.05, "Steam Type": "Exhaust"}),
            dict(Grade="Grain", **{"Heating Surface (ft²)": 3000.0, "Vacuum (in Hg)": 25.5, "Supersaturation": 1.2,
                                    "Head (ft)": 2.0, "Masse Brix": 88.0, "Mother Liquor Purity": 45.0,
                                    "Calandria (psia)": 29.696, "Heat Loss Factor": 0.05, "Steam Type": "Exhaust"}),
            dict(Grade="C", **{"Heating Surface (ft²)": 12000.0, "Vacuum (in Hg)": 26.5, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 95.5, "Mother Liquor Purity": 33.0,
                                "Calandria (psia)": 21.696, "Heat Loss Factor": 0.05, "Steam Type": "V1"}),
        ]
        cen_defaults = [
            dict(Grade="A1", **{"Molasses Brix Out": 80.0, "Purity Rise": 0.0, "Sugar Purity": 99.7,
                                 "Sugar Moisture": 0.2, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
            dict(Grade="A2", **{"Molasses Brix Out": 80.0, "Purity Rise": 0.0, "Sugar Purity": 99.3,
                                 "Sugar Moisture": 0.2, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
            dict(Grade="B", **{"Molasses Brix Out": 82.0, "Purity Rise": 0.0, "Sugar Purity": 92.0,
                                "Sugar Moisture": 5.0, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
            dict(Grade="C", **{"Molasses Brix Out": 82.0, "Purity Rise": 0.0, "Sugar Purity": 82.0,
                                "Sugar Moisture": 5.0, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
        ]
    elif is_tbdm or is_3b:
        pan_defaults = [
            dict(Grade="A", **{"Heating Surface (ft²)": 22500.0, "Vacuum (in Hg)": 23.5, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 92.0, "Mother Liquor Purity": 73.0,
                                "Calandria (psia)": 21.696, "Heat Loss Factor": 0.02, "Steam Type": "V1"}),
            dict(Grade="B", **{"Heating Surface (ft²)": 7500.0, "Vacuum (in Hg)": 25.0, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 94.0, "Mother Liquor Purity": 53.0,
                                "Calandria (psia)": 29.696, "Heat Loss Factor": 0.05, "Steam Type": "Exhaust"}),
            dict(Grade="Grain", **{"Heating Surface (ft²)": 3000.0, "Vacuum (in Hg)": 25.5, "Supersaturation": 1.2,
                                    "Head (ft)": 2.0, "Masse Brix": 88.0, "Mother Liquor Purity": 45.0,
                                    "Calandria (psia)": 29.696, "Heat Loss Factor": 0.05, "Steam Type": "Exhaust"}),
            dict(Grade="C", **{"Heating Surface (ft²)": 12000.0, "Vacuum (in Hg)": 26.5, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 95.5, "Mother Liquor Purity": 33.0,
                                "Calandria (psia)": 21.696, "Heat Loss Factor": 0.05, "Steam Type": "V1"}),
        ]
        cen_defaults = [
            dict(Grade="A", **{"Molasses Brix Out": 80.0, "Purity Rise": 0.0, "Sugar Purity": 99.7,
                                "Sugar Moisture": 0.2, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
            dict(Grade="B", **{"Molasses Brix Out": 82.0, "Purity Rise": 0.0, "Sugar Purity": 92.0,
                                "Sugar Moisture": 5.0, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
            dict(Grade="C", **{"Molasses Brix Out": 82.0, "Purity Rise": 0.0, "Sugar Purity": 82.0,
                                "Sugar Moisture": 5.0, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
        ]
    else:  # Two Boiling — no B pans/centrifugals
        pan_defaults = [
            dict(Grade="A", **{"Heating Surface (ft²)": 22500.0, "Vacuum (in Hg)": 23.5, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 92.0, "Mother Liquor Purity": 55.0,
                                "Calandria (psia)": 21.696, "Heat Loss Factor": 0.02, "Steam Type": "V1"}),
            dict(Grade="Grain", **{"Heating Surface (ft²)": 3000.0, "Vacuum (in Hg)": 25.5, "Supersaturation": 1.2,
                                    "Head (ft)": 2.0, "Masse Brix": 88.0, "Mother Liquor Purity": 45.0,
                                    "Calandria (psia)": 29.696, "Heat Loss Factor": 0.05, "Steam Type": "Exhaust"}),
            dict(Grade="C", **{"Heating Surface (ft²)": 12000.0, "Vacuum (in Hg)": 26.5, "Supersaturation": 1.2,
                                "Head (ft)": 2.0, "Masse Brix": 95.5, "Mother Liquor Purity": 30.0,
                                "Calandria (psia)": 21.696, "Heat Loss Factor": 0.05, "Steam Type": "V1"}),
        ]
        cen_defaults = [
            dict(Grade="A", **{"Molasses Brix Out": 80.0, "Purity Rise": 0.0, "Sugar Purity": 99.4,
                                "Sugar Moisture": 0.3, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
            dict(Grade="C", **{"Molasses Brix Out": 78.0, "Purity Rise": 0.0, "Sugar Purity": 78.0,
                                "Sugar Moisture": 5.0, "Sugar Temp": 150.0, "Molasses Temp": 145.0}),
        ]

    pans = pan_editor(f"pan_editor_{scheme_key}", pan_defaults)
    st.markdown("**Centrifugals**")
    cens = cen_editor(f"cen_editor_{scheme_key}", cen_defaults)

    st.markdown("**C Crystallizer / Reheater** (low-grade cooling train)")
    cc1, cc2, cc3 = st.columns(3)
    cryst_temp_out = cc1.number_input("Crystallizer masse out (°F)", value=120.0, step=1.0)
    cryst_ml_purity_out = cc2.number_input("Crystallizer Mother Liquor Purity out (%)", value=30.0, step=1.0)
    reheat_temp_out = cc3.number_input("Reheater masse out (°F)", value=140.0, step=1.0)
    st.caption("Cooling water fixed 85→105°F, reheat water fixed 150→135°F.")

    C_crystallizers = Crystallizer(
        massecuite_in=None, massecuite_flow_lb_hr=0, masse_temp_out_deg_F=cryst_temp_out,
        ml_purity_out=cryst_ml_purity_out, water_temp_in_deg_F=85, water_temp_out_deg_F=105,
        name="C Crystallizers",
    )
    C_reheaters = Reheater(
        massecuite_in=None, massecuite_flow_lb_hr=0, masse_temp_out_deg_F=reheat_temp_out,
        water_temp_in_deg_F=150, water_temp_out_deg_F=135, name="C Reheaters",
    )

    PAN_SOLVER_ITERATIONS = 20

    st.markdown("**Split fractions**")
    if is_fbdm:
        s1, s2, s3, s4 = st.columns(4)
        syrup_to_A1 = s1.number_input("Syrup to A1 pans (%)", value=75.0)
        syrup_to_A2 = s2.number_input("Syrup to A2 pans (%)", value=20.0)
        a1_to_A2 = s3.number_input("A1 mol to A2 (%)", value=80.0)
        a1_to_grain = s4.number_input("A1 mol to grain (%)", value=3.0)
        s5, s6, s7, s8 = st.columns(4)
        a2_to_grain = s5.number_input("A2 mol to grain (%)", value=0.0)
        b_to_grain = s6.number_input("B mol to grain (%)", value=10.0)
        b_A1_footing = s7.number_input("B magma A1 footing (%)", value=40.0)
        b_A2_footing = s8.number_input("B magma A2 footing (%)", value=40.0)
        s9, s10 = st.columns(2)
        c_B_footing = s9.number_input("C magma B footing (%)", value=80.0)
    elif is_tbdm:
        s1, s2, s3, s4 = st.columns(4)
        c_remelt = s1.number_input("C magma remelt (%)", value=20.0)
        b_remelt = s2.number_input("B magma remelt (%)", value=20.0)
        syrup_grain = s3.number_input("Syrup to grain (%)", value=1.0)
        a_to_grain = s4.number_input("A mol to grain (%)", value=3.0)
        s5, s6, s7, s8 = st.columns(4)
        b_to_grain = s5.number_input("B mol to grain (%)", value=10.0)
        a_top_off = s6.number_input("A mol top-off (%)", value=0.0)
        b_top_off = s7.number_input("B mol top-off (%)", value=0.0)
        c_top_off = s8.number_input("C mol top-off (%)", value=0.0)
        if b_top_off or c_top_off:
            st.caption("Molasses top-off recycles already-boiled molasses back through its own pan — "
                       "usually undesirable, since the extra pass raises color.")
    elif is_3b:
        s1, s2, s3, s4 = st.columns(4)
        c_magma_A_footing = s1.number_input("C magma A footing (%)", value=40.0)
        c_magma_B_footing = s2.number_input("C magma B footing (%)", value=40.0)
        syrup_grain = s3.number_input("Syrup to grain (%)", value=1.0)
        a_to_grain = s4.number_input("A mol to grain (%)", value=3.0)
        s5, s6, s7, s8 = st.columns(4)
        b_to_grain = s5.number_input("B mol to grain (%)", value=10.0)
        a_top_off = s6.number_input("A mol top-off (%)", value=0.0)
        b_top_off = s7.number_input("B mol top-off (%)", value=0.0)
        c_top_off = s8.number_input("C mol top-off (%)", value=0.0)
        st.caption(f"C magma remainder to remelt: {max(100.0 - c_magma_A_footing - c_magma_B_footing, 0.0):.1f}%")
        if b_top_off or c_top_off:
            st.caption("Molasses top-off recycles already-boiled molasses back through its own pan — "
                       "usually undesirable, since the extra pass raises color.")
    else:  # Two Boiling
        s1, s2, s3, s4 = st.columns(4)
        c_remelt = s1.number_input("C magma remelt (%)", value=20.0)
        syrup_grain = s2.number_input("Syrup to grain (%)", value=1.0)
        syrup_to_C = s3.number_input("Syrup to C pans (%)", value=5.0)
        a_to_grain = s4.number_input("A mol to grain (%)", value=3.0)
        s5, s6 = st.columns(2)
        a_top_off = s5.number_input("A mol top-off (%)", value=30.0)
        c_top_off = s6.number_input("C mol top-off (%)", value=0.0)
        if c_top_off:
            st.caption("Molasses top-off recycles already-boiled molasses back through its own pan — "
                       "usually undesirable, since the extra pass raises color.")

    if should_resolve("pan"):
        mark_resolved("pan")
        try:
            if is_fbdm:
                pan_floor = FourBoilingDoubleMagma(
                    syrup=syrup,
                    A1_pans=pans["A1"], A2_pans=pans["A2"], B_pans=pans["B"], C_pans=pans["C"],
                    grain_pans=pans["Grain"],
                    A1_centrifugals=cens["A1"], A2_centrifugals=cens["A2"], B_centrifugals=cens["B"],
                    C_centrifugals=cens["C"],
                    C_crystallizers=C_crystallizers, C_reheaters=C_reheaters,
                    syrup_to_A1_pans_pct=syrup_to_A1, syrup_to_A2_pans_pct=syrup_to_A2,
                    a1_mol_to_A2_pct=a1_to_A2, a1_mol_to_grain_pct=a1_to_grain, a2_mol_to_grain_pct=a2_to_grain,
                    b_mol_to_grain_pct=b_to_grain, b_magma_A1_footing_pct=b_A1_footing,
                    b_magma_A2_footing_pct=b_A2_footing, c_magma_B_footing_pct=c_B_footing,
                    b_magma_brix=pf_b_magma_brix, c_magma_brix=pf_c_magma_brix,
                    b_remelt_brix=pf_b_remelt_brix, c_remelt_brix=pf_c_remelt_brix,
                    injection_water_temp_F=pf_injection_water_temp_F,
                    condenser_leg_temp_drop_F=pf_condenser_leg_temp_drop_F,
                    iterations=PAN_SOLVER_ITERATIONS,
                )
            elif is_tbdm:
                pan_floor = ThreeBoilingDoubleMagma(
                    syrup=syrup,
                    A_pans=pans["A"], B_pans=pans["B"], C_pans=pans["C"], grain_pans=pans["Grain"],
                    A_centrifugals=cens["A"], B_centrifugals=cens["B"], C_centrifugals=cens["C"],
                    C_crystallizers=C_crystallizers, C_reheaters=C_reheaters,
                    c_magma_remelt_pct=c_remelt, b_magma_remelt_pct=b_remelt, syrup_to_grain_pct=syrup_grain,
                    a_mol_to_grain_pct=a_to_grain, b_mol_to_grain_pct=b_to_grain, a_mol_top_off_pct=a_top_off,
                    b_mol_top_off_pct=b_top_off, c_mol_top_off_pct=c_top_off,
                    b_magma_brix=pf_b_magma_brix, c_magma_brix=pf_c_magma_brix,
                    b_remelt_brix=pf_b_remelt_brix, c_remelt_brix=pf_c_remelt_brix,
                    injection_water_temp_F=pf_injection_water_temp_F,
                    condenser_leg_temp_drop_F=pf_condenser_leg_temp_drop_F,
                    iterations=PAN_SOLVER_ITERATIONS,
                )
            elif is_3b:
                pan_floor = ThreeBoiling(
                    syrup=syrup,
                    A_pans=pans["A"], B_pans=pans["B"], C_pans=pans["C"], grain_pans=pans["Grain"],
                    A_centrifugals=cens["A"], B_centrifugals=cens["B"], C_centrifugals=cens["C"],
                    C_crystallizers=C_crystallizers, C_reheaters=C_reheaters,
                    c_magma_A_footing_pct=c_magma_A_footing, c_magma_B_footing_pct=c_magma_B_footing,
                    syrup_to_grain_pct=syrup_grain, a_mol_to_grain_pct=a_to_grain,
                    b_mol_to_grain_pct=b_to_grain, a_mol_top_off_pct=a_top_off,
                    b_mol_top_off_pct=b_top_off, c_mol_top_off_pct=c_top_off,
                    c_magma_brix=pf_c_magma_brix, c_remelt_brix=pf_c_remelt_brix,
                    injection_water_temp_F=pf_injection_water_temp_F,
                    condenser_leg_temp_drop_F=pf_condenser_leg_temp_drop_F,
                    iterations=PAN_SOLVER_ITERATIONS,
                )
            else:  # Two Boiling
                pan_floor = TwoBoiling(
                    syrup=syrup,
                    A_pans=pans["A"], C_pans=pans["C"], grain_pans=pans["Grain"],
                    A_centrifugals=cens["A"], C_centrifugals=cens["C"],
                    C_crystallizers=C_crystallizers, C_reheaters=C_reheaters,
                    c_magma_remelt_pct=c_remelt, syrup_to_grain_pct=syrup_grain, syrup_to_C_pct=syrup_to_C,
                    a_mol_to_grain_pct=a_to_grain, a_mol_top_off_pct=a_top_off, c_mol_top_off_pct=c_top_off,
                    c_magma_brix=pf_c_magma_brix, c_remelt_brix=pf_c_remelt_brix,
                    injection_water_temp_F=pf_injection_water_temp_F,
                    condenser_leg_temp_drop_F=pf_condenser_leg_temp_drop_F,
                    iterations=PAN_SOLVER_ITERATIONS,
                )
           # pan_fig = pan_floor.generate_pfd(show=False)
           # plt.close(pan_fig)

            SOLVED["pan_floor"] = pan_floor
           # SOLVED["pan_pfd"] = pan_fig
            SOLVED["pan_scheme"] = scheme_key
            SOLVED["pan_ok"] = True
            SOLVED["pan_error"] = None
        except Exception as exc:
            SOLVED["pan_floor"] = None
            SOLVED["pan_ok"] = False
            SOLVED["pan_error"] = str(exc)

    pan_floor = SOLVED.get("pan_floor")
    pan_ok = SOLVED.get("pan_ok", False)

    if pan_ok and SOLVED.get("pan_scheme") != scheme_key:
        st.info(f"Last solved as **{SOLVED.get('pan_scheme')}** — the boiling scheme above has "
                f"since changed to **{scheme_key}**. Click **Solve Entire Plant** to re-solve.")
    elif pan_ok:
        st.divider()

        raw_sugar = pan_floor.total_raw_sugar
        # _final_molasses_out nets out any C top-off recycled back into the C pans; only
        # present on schemes with the top-off feature (not FourBoilingDoubleMagma).
        final_molasses = getattr(pan_floor, "_final_molasses_out", pan_floor.C_centrifugals.molasses_stream)
        final_molasses_gal_per_day = final_molasses.flow_lb_per_hr * 24 / (WATER_LB_PER_GAL * final_molasses.specific_gravity)
        st.markdown(
            """<style>
            .st-key-pan_floor_summary_metrics [data-testid="stMetricValue"] { font-size: 1.1rem; }
            .st-key-pan_floor_summary_metrics [data-testid="stMetricLabel"] { font-size: 0.8rem; }
            .st-key-pan_floor_summary_metrics [data-testid="stMetricDelta"] { font-size: 0.8rem; }
            </style>""",
            unsafe_allow_html=True,
        )
        with st.container(key="pan_floor_summary_metrics"):
            m1, m2, m3 = st.columns(3)
            m1.metric("Entering Syrup", f"{pan_floor.syrup.flow_lb_per_hr:,.0f} lb/hr",
                      f"{pan_floor.syrup.brix:.2f} brix, {pan_floor.syrup.purity:.2f} purity",
                      delta_color="off", delta_arrow="off")
            m2.metric("Total Raw Sugar", f"{raw_sugar.flow_lb_per_hr:,.0f} lb/hr    |    {raw_sugar.flow_lb_per_hr*24:,.0f} lb/day",
                      f"{raw_sugar.pol:.2f} pol, {raw_sugar.purity:.2f} purity",
                      delta_color="off", delta_arrow="off")
            m3.metric("Total Final Molasses", f"{final_molasses.flow_lb_per_hr:,.0f} lb/hr  |  {final_molasses_gal_per_day:,.0f} Gal per day",
                      f"{final_molasses.brix:.2f} brix, {final_molasses.purity:.2f} purity",
                      delta_color="off", delta_arrow="off")

        st.markdown("**Massecuite Summary**")
        st.dataframe(massecuite_summary_table(pan_floor, mills.cane_tpd),
                     use_container_width=True, height="content")

        st.markdown("**Steam Consumption Table**")
        st.dataframe(steam_consumption_table(pan_floor), use_container_width=True, height="content")

        st.markdown("**Pan Floor Output Table**")
        if is_fbdm:
            pan_floor_rows = four_boiling_rows(pan_floor)
        elif is_tbdm:
            pan_floor_rows = three_boiling_rows(pan_floor)
        elif is_3b:
            pan_floor_rows = three_boiling_single_magma_rows(pan_floor)
        else:
            pan_floor_rows = two_boiling_rows(pan_floor)
        pan_floor_df = pd.DataFrame(pan_floor_rows, columns=PAN_FLOOR_TABLE_COLUMNS)

        SECTION_PALETTE = [
            "#e3f2fd", "#e8f5e9", "#fff8e1", "#f3e5f5", "#fbe9e7",
            "#e0f2f1", "#fce4ec", "#ede7f6", "#f1f8e9", "#e0f7fa",
            "#fff3e0", "#f9fbe7", "#efebe9", "#eceff1",
        ]
        section_order = list(dict.fromkeys(pan_floor_df["Section"]))
        section_colors = {s: SECTION_PALETTE[i % len(SECTION_PALETTE)] for i, s in enumerate(section_order)}

        def _section_row_style(row):
            color = section_colors.get(row["Section"])
            style = f"background-color: {color}; color: #1b1b1b" if color else ""
            return [style] * len(row)

        st.dataframe(
            pan_floor_df.style.apply(_section_row_style, axis=1),
            column_config={
                col: st.column_config.NumberColumn(format="%,.2f")
                for col in [
                    "Flow lb/hr", "Pol %", "Brix %", "Purity", "Pol lb/hr", "Brix lb/hr",
                    "Cu Ft./hr", "Specific Gravity", "Temperature",
                    "Crystal Content (Massecuite Only)",
                    "Predicted ML Purity (Birkett, Massecuite Only)",
                ]
            },
            use_container_width=True, hide_index=True, height="content",
        )

       # st.pyplot(SOLVED["pan_pfd"], use_container_width=True)
    elif SOLVED.get("pan_error"):
        st.error(f"Pan floor failed to solve: {SOLVED['pan_error']}")
    else:
        st.info("Click **Solve Entire Plant** above to compute the pan floor balance.")


with tab_pan:
    render_tab_pan()
# ============================================================================
# EVAPORATION TAB — Pre + N sets, each independently on/off
# ============================================================================
@st.fragment
def render_tab_evap():
    st.subheader("Evaporation Station")
    # Re-derive every upstream value from the cache rather than trusting a plain
    # variable left over from the Juice Heating / Pan Floor tabs' own code — each
    # tab is its own fragment now, so that carry-over no longer happens reliably.
    heat_ok = SOLVED.get("heat_ok", False)
    pan_ok = SOLVED.get("pan_ok", False)
    juice_heaters = SOLVED.get("juice_heaters")
    clar_juice_heater = SOLVED.get("clar_juice_heater")
    pan_floor = SOLVED.get("pan_floor")
    cj = resolve_cj()
    if not (heat_ok and pan_ok):
        st.warning("Solve Juice Heating and Pan Floor first (see their tabs for errors) — "
                   "the V1 vapor demand comes from both.")
    else:
        st.markdown("**Pre-Evaporator**")
        pe1, pe2, pe3, pe4 = st.columns(4)
        pre_active = pe1.checkbox("Pre-Evaporator active", value=True)
        pre_area = pe2.number_input("Pre area (ft²)", value=35000.0, step=1000.0, disabled=not pre_active)
        pre_dessin = pe3.number_input("Pre Dessin coefficient", value=18000.0, step=500.0, disabled=not pre_active)
        pre_level = pe4.number_input("Pre liquid level (ft)", value=2.0, step=0.5, disabled=not pre_active)

        st.markdown("**Evaporator Sets** — add/remove rows, each row is one set. Effect *k*'s own vapor "
                    "feeds header V*k* (effect 1 → V1, effect 2 → V2, ...); the last effect never bleeds "
                    "(its vapor goes to the condenser), so an N-effect set can supply V1..V(N-1).")
        set_defaults = pd.DataFrame([
            {"Active": True, "Name": "Set 1 (4-eff 25k ft²)",
             "Effect Areas (ft², comma-sep)": "25000,25000,25000,25000",
             "Supply Steam (psia)": float(fabrication_exhaust_psia), "Last Effect (psia)": 2.4,
             "Dessin Coeff": 18000.0, "Liquid Level (ft)": 2.0},
            {"Active": True, "Name": "Set 2 (4-eff 12k ft²)",
             "Effect Areas (ft², comma-sep)": "12000,12000,12000,12000",
             "Supply Steam (psia)": float(fabrication_exhaust_psia), "Last Effect (psia)": 2.4,
             "Dessin Coeff": 18000.0, "Liquid Level (ft)": 2.0},
            {"Active": True, "Name": "Set 3 (3-eff 11-9k ft²)",
             "Effect Areas (ft², comma-sep)": "11000,9000,9000",
             "Supply Steam (psia)": 20.0, "Last Effect (psia)": 2.4,
             "Dessin Coeff": 18000.0, "Liquid Level (ft)": 2.0},
        ])
        sets_df = st.data_editor(
            set_defaults, hide_index=True, use_container_width=True, num_rows="dynamic", key="evap_set_editor",
            column_config={"Active": st.column_config.CheckboxColumn()},
        )

        st.markdown("**Station-wide defaults**")
        d1, d2, d3 = st.columns(3)
        # Defaults mirror the Pan Floor tab's own widgets by reading them out of
        # st.session_state (via their explicit keys) rather than a plain variable —
        # Pan Floor is its own fragment now, so its local variables aren't visible here.
        target_brix_out = d1.number_input(
            "Target syrup brix", value=float(st.session_state.get("syrup_brix", 65.0)), step=0.5,
        )
        evap_injection_water_temp_F = d2.number_input(
            "Injection water temp (°F)",
            value=float(st.session_state.get("pf_inj_water", 90.0)), step=1.0,
            help="Matches the Pan Floor tab's value by default — condenser makeup water temp.",
        )
        evap_condenser_leg_temp_drop_F = d3.number_input(
            "Condenser leg ΔT (°F)",
            value=float(st.session_state.get("pf_cond_leg", 5.0)), step=0.5,
        )

        active_sets = sets_df[sets_df["Active"]].reset_index(drop=True)

        # Effect count per active set — needed up front to know which sets are
        # even eligible to supply V2/V3/V4 (a set needs >= grade effects).
        # Lenient here (bad input just drops the set from eligibility); the
        # real validation with a clear error happens in the solve step below.
        n_eff_by_name = {}
        for _, row in active_sets.iterrows():
            try:
                n_eff_by_name[row["Name"]] = len(parse_floats(row["Effect Areas (ft², comma-sep)"]))
            except Exception:
                n_eff_by_name[row["Name"]] = 0

        v1_consumers = (["Pre-Evaporator"] if pre_active else []) + \
            [n for n in active_sets["Name"] if n_eff_by_name.get(n, 0) >= 1]
        v2_consumers = [n for n in active_sets["Name"] if n_eff_by_name.get(n, 0) >= 2]
        v3_consumers = [n for n in active_sets["Name"] if n_eff_by_name.get(n, 0) >= 3]
        v4_consumers = [n for n in active_sets["Name"] if n_eff_by_name.get(n, 0) >= 4]

        clar_juice_heater_v1_lb_hr = (
            clar_juice_heater.steam_required_lb_per_hr if clar_juice_heater.steam_type == 1 else 0.0
        )
        v1_demand = juice_heaters.total_V1_steam_lb_hr + pan_floor.total_V1_steam_lb_hr + clar_juice_heater_v1_lb_hr
        v2_demand = juice_heaters.total_V2_steam_lb_hr + pan_floor.total_V2_steam_lb_hr
        v3_demand = juice_heaters.total_V3_steam_lb_hr + pan_floor.total_V3_steam_lb_hr
        v4_demand = juice_heaters.total_V4_steam_lb_hr + pan_floor.total_V4_steam_lb_hr

        st.markdown("**Vapor Bleed Distribution** — only eligible consumers are listed for each grade "
                    "(effect *k* of a set can only supply V*k*); this splits each grade's total demand "
                    "(heaters + pans) across the Pre-Evaporator (V1 only) and the matching effect of "
                    "each evaporator set.")
        v1_default_pcts = {"Pre-Evaporator": 80.0}
        for cname in v1_consumers:
            if "Set 1" in cname:
                v1_default_pcts[cname] = 13.0
            elif "Set 2" in cname:
                v1_default_pcts[cname] = 7.0
        v1_share, v1_dist_df = vapor_dist_editor(1, v1_demand, v1_consumers, "v1_dist_editor", v1_default_pcts)
        st.markdown(f"{"-"*270} % total {v1_dist_df.iloc[:,1].sum()}")
        v2_share, v2_dist_df = vapor_dist_editor(2, v2_demand, v2_consumers, "v2_dist_editor")
        st.markdown(f"{"-"*270} % total {v2_dist_df.iloc[:,1].sum()}")
        v3_share, v3_dist_df = vapor_dist_editor(3, v3_demand, v3_consumers, "v3_dist_editor")
        st.markdown(f"{"-"*270} % total {v3_dist_df.iloc[:,1].sum()}")
        v4_share, v4_dist_df = vapor_dist_editor(4, v4_demand, v4_consumers, "v4_dist_editor")
        st.markdown(f"{"-"*270} % total {v4_dist_df.iloc[:,1].sum()}")
        share_by_grade = {1: v1_share, 2: v2_share, 3: v3_share, 4: v4_share}

        if active_sets.empty:
            st.warning("No evaporator sets active — station will not be solved.")

        if should_resolve("evap"):
            mark_resolved("evap")
            try:
                if pre_active:
                    pre_bleed = v1_share("Pre-Evaporator")
                    pre_3 = PreEvaporator(
                        juice_in=SugarStream.copy(cj),
                        supply_steam=EvaporatorSteam(P_psia=fabrication_exhaust_psia),
                        vapor_bleed_lb_per_hr=pre_bleed,
                        area_ft2=pre_area,
                        liquid_level_ft=pre_level,
                        dessin_coefficient=pre_dessin,
                    )
                    juice_to_sets = SugarStream.copy(pre_3.juice_out)
                else:
                    pre_3 = None
                    juice_to_sets = SugarStream.copy(cj)

                set_configs = []
                for _, row in active_sets.iterrows():
                    areas = parse_floats(row["Effect Areas (ft², comma-sep)"])
                    n_eff = len(areas)
                    if n_eff < 1:
                        raise ValueError(f"{row['Name']}: at least one effect area required")
                    # bleeds[k] (0-indexed) is drawn off effect k+1, feeding header V(k+1).
                    # The last effect never bleeds (its vapor goes to the condenser).
                    bleeds = [share_by_grade[k + 1](row["Name"]) if (k + 1) in share_by_grade else 0.0
                              for k in range(n_eff - 1)]
                    set_configs.append({
                        "name": row["Name"],
                        "effect_areas_ft2": areas,
                        "supply_steam_psia": row["Supply Steam (psia)"],
                        "last_effect_psia": row["Last Effect (psia)"],
                        "vapor_bleeds": bleeds,
                        "dessin_coefficient": row["Dessin Coeff"],
                        "liquid_level_ft": row["Liquid Level (ft)"],
                    })

                if set_configs:
                    evap_station = solve_evaporator_sets_scipy(
                        juice_brix=juice_to_sets.brix,
                        juice_purity=juice_to_sets.purity,
                        juice_flow_lb_per_hr=juice_to_sets.flow_lb_per_hr,
                        juice_temp_deg_F=juice_to_sets.temp_deg_F,
                        juice_pressure_psia=40,
                        target_brix_out=target_brix_out,
                        injection_water_temp_F=evap_injection_water_temp_F,
                        condenser_leg_temp_drop_F=evap_condenser_leg_temp_drop_F,
                        set_configs=set_configs,
                        verbose=False,
                    )
                else:
                    evap_station = []

                v1_delivered = sum(v1_share(c) for c in v1_consumers)
                v2_delivered = sum(v2_share(c) for c in v2_consumers)
                v3_delivered = sum(v3_share(c) for c in v3_consumers)
                v4_delivered = sum(v4_share(c) for c in v4_consumers)

                #pre_fig = None
                #if pre_3 is not None:
                   # pre_fig = pre_3.generate_pfd(show=False)
                   # plt.close(pre_fig)
                #evap_figs = {}
                #for evap in evap_station:
                    #ef = evap.generate_pfd(show=False, pre_evap=pre_3)
                    #plt.close(ef)
                    #evap_figs[evap.name] = ef

                SOLVED["pre_3"] = pre_3
                SOLVED["evap_station"] = evap_station
                #SOLVED["pre_pfd"] = pre_fig
               # SOLVED["evap_pfds"] = evap_figs
                SOLVED["v1_demand"] = v1_demand
                SOLVED["v2_demand"] = v2_demand
                SOLVED["v3_demand"] = v3_demand
                SOLVED["v4_demand"] = v4_demand
                SOLVED["v1_delivered"] = v1_delivered
                SOLVED["v2_delivered"] = v2_delivered
                SOLVED["v3_delivered"] = v3_delivered
                SOLVED["v4_delivered"] = v4_delivered
                SOLVED["evap_ok"] = True
                SOLVED["evap_error"] = None
            except Exception as exc:
                SOLVED["pre_3"] = None
                SOLVED["evap_station"] = []
                SOLVED["evap_ok"] = False
                SOLVED["evap_error"] = str(exc)

        pre_3 = SOLVED.get("pre_3")
        evap_station = SOLVED.get("evap_station", [])
        evap_ok = SOLVED.get("evap_ok", False)
        v1_delivered = SOLVED.get("v1_delivered", 0.0)
        v2_delivered = SOLVED.get("v2_delivered", 0.0)
        v3_delivered = SOLVED.get("v3_delivered", 0.0)
        v4_delivered = SOLVED.get("v4_delivered", 0.0)

        if SOLVED.get("evap_error"):
            st.error(f"Evaporation failed to solve: {SOLVED['evap_error']}")
        elif not evap_ok:
            st.info("Click **Solve Entire Plant** above to compute the evaporation station.")

        if evap_ok:
            st.divider()
            vapor_summary_df = pd.DataFrame(
                [["V1", v1_demand, v1_delivered], ["V2", v2_demand, v2_delivered],
                 ["V3", v3_demand, v3_delivered], ["V4", v4_demand, v4_delivered]],
                columns=["Grade", "Demand (lb/hr)", "Delivered (lb/hr)"],
            )
            st.dataframe(vapor_summary_df, hide_index=True, use_container_width=True)

            if pre_3 is not None:
                st.markdown(f"**Pre-Evaporator** — {pre_3.vapor_bleed_lb_per_hr:,.0f} lb/hr bleed, "
                            f"{pre_3.exhaust_required_lb_per_hr:,.0f} lb/hr exhaust, "
                            f"U ratio {pre_3.U_ratio:.3f}")
                # st.pyplot(SOLVED.get("pre_pfd"), use_container_width=True)

                st.markdown("**Pre-Evaporator — Streams**")
                st.dataframe(pre_evaporator_streams_table(pre_3), hide_index=True,
                             use_container_width=True)
                st.markdown("**Pre-Evaporator — Performance**")
                st.dataframe(pre_evaporator_performance_table(pre_3), hide_index=True,
                             use_container_width=True)

            evap_figs = SOLVED.get("evap_pfds", {})
            for evap in evap_station:
                syrup_out = evap.evaporator_list[-1].juice_side_out
                st.markdown(f"**{evap.name}** — steam {evap.supply_steam.flow_lb_per_hr:,.0f} lb/hr, "
                            f"syrup out {syrup_out.flow_lb_per_hr:,.0f} lb/hr @ {syrup_out.brix:.1f} Bx, "
                            f"U ratio {evap.U_ratio_avg:.3f}")
                if evap.name in evap_figs:
                    st.pyplot(evap_figs[evap.name], use_container_width=True)

                st.markdown(f"**{evap.name} — Summary**")
                st.dataframe(evap_set_summary_table(evap), hide_index=True, use_container_width=True)
                st.dataframe(evap_set_summary_metrics_table(evap), hide_index=True, use_container_width=True)

                st.markdown(f"**{evap.name} — Effect Flows**")
                st.dataframe(evap_set_effect_flows_table(evap), use_container_width=True)

                st.markdown(f"**{evap.name} — Effect Conditions**")
                st.dataframe(evap_set_effect_conditions_table(evap), use_container_width=True)

                st.markdown(f"**{evap.name} — Energy Balance Per Effect**")
                st.dataframe(evap_set_energy_balance_table(evap), hide_index=True, use_container_width=True)

                st.markdown(f"**{evap.name} — Last Effect Condenser**")
                st.dataframe(evap_set_condenser_table(evap), hide_index=True, use_container_width=True)

                st.markdown(f"**{evap.name} — Condensate Return**")
                st.dataframe(evap_set_condensate_table(evap), hide_index=True, use_container_width=True)

            if evap_station:
                summary_rows = [
                    (evap.name, evap.supply_steam.flow_lb_per_hr,
                     evap.evaporator_list[-1].juice_side_out.flow_lb_per_hr,
                     evap.evaporator_list[-1].juice_side_out.brix, evap.U_ratio_avg,
                     evap.clean_condensate, evap.dirty_condensate)
                    for evap in evap_station
                ]
                st.dataframe(
                    pd.DataFrame(summary_rows, columns=["Set", "Steam (lb/hr)", "Syrup Out (lb/hr)",
                                                         "Syrup Brix", "U Ratio", "Clean Condensate",
                                                         "Dirty Condensate"]),
                    use_container_width=True, hide_index=True,
                )


with tab_evap:
    render_tab_evap()
# ============================================================================
# STEAM & EXHAUST SUMMARY TAB
# ============================================================================
@st.fragment
def render_tab_steam():
    st.subheader("Steam & Exhaust Summary")
    # Re-derive every upstream value from the cache — Juice Heating, Pan Floor, and
    # Evaporation are each their own fragment now, so their plain variables from a
    # prior tab's own run aren't reliably visible here.
    evap_ok = SOLVED.get("evap_ok", False)
    pre_3 = SOLVED.get("pre_3")
    evap_station = SOLVED.get("evap_station", [])
    pan_floor = SOLVED.get("pan_floor")
    juice_heaters = SOLVED.get("juice_heaters")
    clar_juice_heater = SOLVED.get("clar_juice_heater")
    if not evap_ok:
        st.info("Solve Evaporation first (see its tab) to compute the exhaust steam summary.")
    else:
        st.markdown("**Deaerator**")
        dz1, dz2, dz3, dz4 = st.columns(4)
        with dz1:
            da_psia_col, da_psig_col = st.columns([3, 1])
            with da_psia_col:
                da_psia = st.number_input("Deaerator pressure (psia)", value=24.7, step=1.0)
            with da_psig_col:
                da_psig = da_psia - 14.696
                st.caption("psig")
                st.markdown(
                    f"<div style='font-size:1.1rem; padding-top:0.25rem;'>{da_psig:.1f}</div>",
                    unsafe_allow_html=True,
                )
        da_water_temp = dz2.number_input("Water in temp (°F)", value=200.0, step=5.0)
        da_water_flow = dz3.number_input("Water in flow (lb/hr)", value=800000.0, step=10000.0)
        da_vent_pct = dz4.number_input("Vent (%)", value=4.0, step=0.5)
        exh_losses_pct = st.number_input("Exhaust losses (% of subtotal)", value=5.0, step=0.5)

        if should_resolve("steam"):
            mark_resolved("steam")
            try:
                da = Deaerator(deaerator_psig=da_psig, water_in_deg_F=da_water_temp,
                                water_in_lb_hr=da_water_flow, vent_pct=da_vent_pct)

                exhaust_for_Pre = pre_3.supply_steam.flow_lb_per_hr if pre_3 is not None else 0.0
                exhaust_for_evaporators = sum(evap.supply_steam.flow_lb_per_hr for evap in evap_station)
                exhaust_for_pans = pan_floor.total_exhaust_steam_lb_hr
                clar_juice_heater_exhaust_lb_hr = (
                    clar_juice_heater.steam_required_lb_per_hr if clar_juice_heater.steam_type == 0 else 0.0
                )
                exhaust_for_heaters = juice_heaters.total_exhaust_steam_lb_hr + clar_juice_heater_exhaust_lb_hr
                exhaust_for_da = da.steam_flow_lb_hr
                subtotal_exh = (exhaust_for_Pre + exhaust_for_evaporators + exhaust_for_pans
                                 + exhaust_for_heaters + exhaust_for_da)
                total_exhaust_required = subtotal_exh * (1 + exh_losses_pct / 100)

                exh_dict = {
                    "Exhaust for Pre": exhaust_for_Pre,
                    "Exhaust for Evaporators": exhaust_for_evaporators,
                    "Exhaust for Pans": exhaust_for_pans,
                    "Exhaust for Heaters": exhaust_for_heaters,
                    "Exhaust for Deaerator": exhaust_for_da,
                    "Exhaust Losses": subtotal_exh * exh_losses_pct / 100,
                    "Total Exhaust Required": total_exhaust_required,
                }

                SOLVED["da"] = da
                SOLVED["exh_dict"] = exh_dict
                SOLVED["total_exhaust_required"] = total_exhaust_required
                SOLVED["vapor_check"] = (
                    SOLVED.get("v1_demand", 0.0), SOLVED.get("v1_delivered", 0.0),
                    SOLVED.get("v2_demand", 0.0), SOLVED.get("v2_delivered", 0.0),
                    SOLVED.get("v3_demand", 0.0), SOLVED.get("v3_delivered", 0.0),
                    SOLVED.get("v4_demand", 0.0), SOLVED.get("v4_delivered", 0.0),
                )
                SOLVED["steam_ok"] = True
                SOLVED["steam_error"] = None
            except Exception as exc:
                SOLVED["da"] = None
                SOLVED["steam_ok"] = False
                SOLVED["steam_error"] = str(exc)

        da = SOLVED.get("da")
        exh_dict = SOLVED.get("exh_dict", {})
        total_exhaust_required = SOLVED.get("total_exhaust_required", 0.0)
        steam_ok = SOLVED.get("steam_ok", False)

        if steam_ok:
            st.dataframe(pd.DataFrame(exh_dict.items(), columns=["Item", "lb/hr"]),
                         hide_index=True, use_container_width=True)

            st.markdown("**Vapor Bleed Demand vs. Delivered** (set on the Evaporation tab)")
            vc_v1d, vc_v1x, vc_v2d, vc_v2x, vc_v3d, vc_v3x, vc_v4d, vc_v4x = SOLVED["vapor_check"]
            vapor_check_df = pd.DataFrame(
                [["V1", vc_v1d, vc_v1x], ["V2", vc_v2d, vc_v2x],
                 ["V3", vc_v3d, vc_v3x], ["V4", vc_v4d, vc_v4x]],
                columns=["Grade", "Demand (lb/hr)", "Delivered (lb/hr)"],
            )
            st.dataframe(vapor_check_df, hide_index=True, use_container_width=True)

            st.caption("See the Turbines & Boiler tab for live steam demand, exhaust availability, and "
                       "makeup steam, which build on the exhaust total computed here.")
        elif SOLVED.get("steam_error"):
            st.error(f"Exhaust summary failed to solve: {SOLVED['steam_error']}")
        else:
            st.info("Click **Solve Entire Plant** above to compute the exhaust steam summary.")


with tab_steam:
    render_tab_steam()
# ============================================================================
# TURBINES & BOILER TAB
# ============================================================================
@st.fragment
def render_tab_turb():
    st.subheader("Turbine Steam Demand & Boiler Room")
    steam_ok = SOLVED.get("steam_ok", False)
    da = SOLVED.get("da")
    total_exhaust_required = SOLVED.get("total_exhaust_required", 0.0)
    if not steam_ok:
        st.warning("Solve the Exhaust Summary tab first — makeup steam needs the total exhaust required.")
    else:
        tons_fiber_hr = mills.cane_fiber_pct / 100 * mills.cane_tph
        st.caption(f"Fiber rate from Mill Floor: {tons_fiber_hr:,.1f} ton fiber/hr")

        st.markdown("**Live Steam Generation** — the boiler header condition used as the enthalpy "
                    "source for every turbine group below (throttled to each group's own inlet "
                    "pressure, matching SMSC_Balance.py's approach).")
        lg1, lg2, lg3 = st.columns(3)
        live_gen_psig = lg1.number_input("Live steam generated (psig)", value=185.0, step=5.0)
        live_gen_superheat = lg2.number_input("Superheat (°F above sat., 0 = saturated)", value=0.0, step=5.0)
        live_gen_quality = lg3.number_input("Quality (used if superheat = 0)", value=1.0, step=0.01,
                                             min_value=0.0, max_value=1.0, format="%.2f")
        live_gen_psia = live_gen_psig + 14.696
        live_steam_sat = SteamStream(P=live_gen_psia, x=1)
        if live_gen_superheat > 0:
            live_steam_gen = SteamStream(P=live_gen_psia, T=live_steam_sat.T + live_gen_superheat)
        else:
            live_steam_gen = SteamStream(P=live_gen_psia, x=live_gen_quality)

        def _group_steam(psig):
            return SteamStream(P=psig + 14.696, h=live_steam_gen.h)

        st.markdown("**Cane Prep (Knife) Turbines**")
        kg1, kg2 = st.columns(2)
        knf_live_psig = kg1.number_input("Knife live steam (psig)", value=165.0, step=5.0, key="knf_live")
        knf_exh_psig = kg2.number_input("Knife exhaust (psig)", value=16.0, step=1.0, key="knf_exh")
        knf_defaults = pd.DataFrame([
            {"Name": "Knife 1", "HP per Ton Fiber/hr": 16.0, "Isentropic Eff (%)": 50.0},
            {"Name": "Knife 2", "HP per Ton Fiber/hr": 16.0, "Isentropic Eff (%)": 50.0},
            {"Name": "Knife 3", "HP per Ton Fiber/hr": 16.0, "Isentropic Eff (%)": 50.0},
        ])
        knf_df = st.data_editor(knf_defaults, hide_index=True, use_container_width=True,
                                 num_rows="dynamic", key="knf_editor")

        st.markdown("**Mill Turbines**")
        mg1, mg2 = st.columns(2)
        mill_live_psig = mg1.number_input("Mill live steam (psig)", value=170.0, step=5.0, key="mill_live")
        mill_exh_psig = mg2.number_input("Mill exhaust (psig)", value=15.0, step=1.0, key="mill_exh")
        mill_hp_defaults = [18.0, 16.0, 16.0, 16.0, 16.0, 18.0]
        mill_defaults = pd.DataFrame([
            {"HP per Ton Fiber/hr": mill_hp_defaults[i] if i < len(mill_hp_defaults) else 16.0,
             "Isentropic Eff (%)": 50.0}
            for i in range(mills.number_of_mills)
        ])
        mill_df = st.data_editor(mill_defaults, hide_index=True, use_container_width=True,
                                  num_rows="dynamic", key="mill_trb_editor")

        st.markdown("**Auxiliary Turbines** (fans, pumps, misc.)")
        ag1, ag2, ag3 = st.columns(3)
        aux_group_name = ag1.text_input("Group name", value="Fan and Pump Turbines")
        aux_live_psig = ag2.number_input("Aux live steam (psig)", value=170.0, step=5.0, key="aux_live")
        aux_exh_psig = ag3.number_input("Aux exhaust (psig)", value=16.0, step=1.0, key="aux_exh")
        aux_defaults = pd.DataFrame([
            {"Name": "ID 123", "HP": 750.0, "Isentropic Eff (%)": 50.0},
            {"Name": "ID 4", "HP": 235.0, "Isentropic Eff (%)": 50.0},
            {"Name": "ID 5", "HP": 400.0, "Isentropic Eff (%)": 50.0},
            {"Name": "ID 6", "HP": 795.0, "Isentropic Eff (%)": 50.0},
            {"Name": "ID 7", "HP": 1200.0, "Isentropic Eff (%)": 50.0},
            {"Name": "FD 7", "HP": 233.0, "Isentropic Eff (%)": 50.0},
            {"Name": "ID 8", "HP": 1300.0, "Isentropic Eff (%)": 50.0},
            {"Name": "FD 8", "HP": 350.0, "Isentropic Eff (%)": 50.0},
            {"Name": "BFW 1", "HP": 400.0, "Isentropic Eff (%)": 50.0},
            {"Name": "BFW 2", "HP": 400.0, "Isentropic Eff (%)": 50.0},
            {"Name": "BFW 3", "HP": 400.0, "Isentropic Eff (%)": 50.0},
            {"Name": "JCE 1", "HP": 400.0, "Isentropic Eff (%)": 50.0},
        ])
        aux_df = st.data_editor(aux_defaults, hide_index=True, use_container_width=True,
                                 num_rows="dynamic", key="aux_trb_editor")

        st.markdown("**Losses & Jets**")
        lj1, lj2 = st.columns(2)
        live_steam_jets_lb_hr = lj1.number_input("Live steam for jets (lb/hr)", value=25000.0, step=1000.0)
        live_steam_loss_pct = lj2.number_input("Live steam losses (% of subtotal)", value=2.0, step=0.5)

        st.markdown("**Boiler Room**")
        b1, b2, b3, b4 = st.columns(4)
        blr_efficiency = b1.number_input("Boiler efficiency (%)", value=60.0, step=1.0)
        blr_pressure_psig = b2.number_input("Boiler pressure (psig)", value=float(live_gen_psig), step=5.0)
        blr_superheat = b3.number_input("Boiler superheat (°F)", value=float(live_gen_superheat), step=5.0)
        blr_capacity = b4.number_input("Boiler capacity (lb/hr, 0 = unlimited)", value=900000.0, step=10000.0)
        b5, b6 = st.columns(2)
        use_da_fw_temp = b5.checkbox("Feedwater temp = Deaerator water out", value=True)
        manual_fw_temp = b6.number_input("Feedwater temp (°F, used if unchecked)", value=230.0, step=5.0,
                                          disabled=use_da_fw_temp)

        if should_resolve("turb"):
            mark_resolved("turb")
            try:
                knf_trbs = CanePrepTurbines(
                    name_list=list(knf_df["Name"]),
                    hp_ton_fiber_hr=list(knf_df["HP per Ton Fiber/hr"]),
                    isentropic_efficiency=list(knf_df["Isentropic Eff (%)"]),
                    live_steam_object=_group_steam(knf_live_psig),
                    exhaust_psia=knf_exh_psig + 14.696,
                    tons_fiber_hr=tons_fiber_hr,
                )
                mill_trbs = MillTurbines(
                    hp_ton_fiber_hr=list(mill_df["HP per Ton Fiber/hr"]),
                    isentropic_efficiency=list(mill_df["Isentropic Eff (%)"]),
                    live_steam_object=_group_steam(mill_live_psig),
                    exhaust_psia=mill_exh_psig + 14.696,
                    tons_fiber_hr=tons_fiber_hr,
                )
                misc_trbs = AuxillaryTurbines(
                    group_name=aux_group_name,
                    name_list=list(aux_df["Name"]),
                    hp_list=list(aux_df["HP"]),
                    isentropic_efficiency=list(aux_df["Isentropic Eff (%)"]),
                    live_steam_object=_group_steam(aux_live_psig),
                    exhaust_psia=aux_exh_psig + 14.696,
                )

                live_steam_subtotal = (knf_trbs.total_inlet_flow_lb_hr + mill_trbs.total_inlet_flow_lb_hr
                                        + misc_trbs.total_inlet_flow_lb_hr + live_steam_jets_lb_hr)
                live_steam_loss_lb_hr = live_steam_subtotal * live_steam_loss_pct / 100
                live_steam_total_lb_hr = live_steam_subtotal + live_steam_loss_lb_hr
                exhaust_available = (knf_trbs.total_exhaust_available_lb_hr + mill_trbs.total_exhaust_available_lb_hr
                                      + misc_trbs.total_exhaust_available_lb_hr)
                makeup_steam = max(total_exhaust_required - exhaust_available, 0.0)

                live_steam_dict = {
                    "Cane Prep Turbines": knf_trbs.total_inlet_flow_lb_hr,
                    "Mill Turbines": mill_trbs.total_inlet_flow_lb_hr,
                    "Fan and Pump Turbines": misc_trbs.total_inlet_flow_lb_hr,
                    "Steam Jets": live_steam_jets_lb_hr,
                    "Live Steam Losses": live_steam_loss_lb_hr,
                    "Total Live Steam": live_steam_total_lb_hr,
                }

                fw_temp = da.water_out.T if (use_da_fw_temp and da is not None) else manual_fw_temp
                blrs = Boiler(
                    bagasse=mills.bagasse_stream,
                    efficiency=blr_efficiency,
                    pressure_psig=blr_pressure_psig,
                    deg_superheat=blr_superheat,
                    feed_water_temp=fw_temp,
                    capacity=blr_capacity,
                    name="All Boilers",
                )

               # knf_fig = knf_trbs.generate_pfd(show=False)
               # mill_fig = mill_trbs.generate_pfd(show=False)
               # misc_fig = misc_trbs.generate_pfd(show=False)
               # plt.close(knf_fig)
               # plt.close(mill_fig)
               # plt.close(misc_fig)

                SOLVED["knf_trbs"] = knf_trbs
                SOLVED["mill_trbs"] = mill_trbs
                SOLVED["misc_trbs"] = misc_trbs
                SOLVED["blrs"] = blrs
               # SOLVED["knf_pfd"] = knf_fig
               # SOLVED["mill_pfd"] = mill_fig
               # SOLVED["misc_pfd"] = misc_fig
                SOLVED["live_steam_dict"] = live_steam_dict
                SOLVED["live_steam_total_lb_hr"] = live_steam_total_lb_hr
                SOLVED["exhaust_available"] = exhaust_available
                SOLVED["makeup_steam"] = makeup_steam
                SOLVED["aux_group_name"] = aux_group_name
                SOLVED["turb_ok"] = True
                SOLVED["turb_error"] = None
            except Exception as exc:
                SOLVED["turb_ok"] = False
                SOLVED["turb_error"] = str(exc)

        knf_trbs = SOLVED.get("knf_trbs")
        mill_trbs = SOLVED.get("mill_trbs")
        misc_trbs = SOLVED.get("misc_trbs")
        blrs = SOLVED.get("blrs")
        live_steam_dict = SOLVED.get("live_steam_dict", {})
        exhaust_available = SOLVED.get("exhaust_available", 0.0)
        makeup_steam = SOLVED.get("makeup_steam", 0.0)
        turb_ok = SOLVED.get("turb_ok", False)

        if turb_ok:
            live_steam_total_lb_hr = SOLVED["live_steam_total_lb_hr"]
            cached_aux_group_name = SOLVED.get("aux_group_name", aux_group_name)

            st.dataframe(pd.DataFrame(live_steam_dict.items(), columns=["Item", "lb/hr"]),
                         hide_index=True, use_container_width=True)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Live Steam Demand", f"{live_steam_total_lb_hr:,.0f} lb/hr")
            c2.metric("Exhaust Required", f"{total_exhaust_required:,.0f} lb/hr")
            c3.metric("Exhaust Available from Turbines", f"{exhaust_available:,.0f} lb/hr")
            c4.metric("Makeup Required", f"{makeup_steam:,.0f} lb/hr")

            c1, c2 = st.columns(2)
            c1.metric("Steam Available from Bagasse", f"{blrs.steam_availabe_lb_hr:,.0f} lb/hr")
            c2.metric("Live Steam Demand vs. Available",
                      f"{live_steam_total_lb_hr:,.0f} / {blrs.steam_availabe_lb_hr:,.0f} lb/hr")

            st.markdown("**Boiler — Parameters**")
            st.dataframe(boiler_parameters_table(blrs), hide_index=True, use_container_width=True)
            st.markdown("**Boiler — Feed Water / Steam**")
            st.dataframe(boiler_streams_table(blrs), hide_index=True, use_container_width=True)
            st.markdown("**Boiler — Bagasse Fuel**")
            st.dataframe(boiler_fuel_table(blrs), hide_index=True, use_container_width=True)
            st.markdown("**Boiler — Performance**")
            st.dataframe(boiler_performance_table(blrs), hide_index=True, use_container_width=True)

            st.markdown("**Cane Prep (Knife) Turbines — Output**")
            st.dataframe(turbine_group_table(knf_trbs), hide_index=True, use_container_width=True)
            # st.pyplot(SOLVED["knf_pfd"], use_container_width=True)

            st.markdown("**Mill Turbines — Output**")
            st.dataframe(turbine_group_table(mill_trbs), hide_index=True, use_container_width=True)
            # st.pyplot(SOLVED["mill_pfd"], use_container_width=True)

            st.markdown(f"**{cached_aux_group_name} — Output**")
            st.dataframe(turbine_group_table(misc_trbs), hide_index=True, use_container_width=True)
            # st.pyplot(SOLVED["misc_pfd"], use_container_width=True)
        elif SOLVED.get("turb_error"):
            st.error(f"Turbines/Boiler failed to solve: {SOLVED['turb_error']}")
        else:
            st.info("Click **Solve Entire Plant** above to compute turbines and the boiler room.")


with tab_turb:
    render_tab_turb()
# ============================================================================
# COOLING TOWER TAB
# ============================================================================
@st.fragment
def render_tab_cool():
    st.subheader("Cooling Tower System")
    pan_ok = SOLVED.get("pan_ok", False)
    evap_ok = SOLVED.get("evap_ok", False)
    pan_floor = SOLVED.get("pan_floor")
    evap_station = SOLVED.get("evap_station", [])
    if not (pan_ok and evap_ok):
        st.warning("Solve Pan Floor and Evaporation first — the cooling tower collects every "
                   "condenser from both.")
    else:
        ct1, ct2, ct3, ct4 = st.columns(4)
        ct_cool_water_temp = ct1.number_input("Cool water temp (°F)", value=85.0, step=1.0)
        ct_pct_blowdown = ct2.number_input("Blowdown (%)", value=10.0, step=1.0)
        ct_makeup_water_temp = ct3.number_input("Makeup water temp (°F)", value=70.0, step=1.0)
        ct_iterations = int(ct4.number_input("Solver iterations", value=20, step=1, key="ct_iterations"))

        if should_resolve("cool"):
            mark_resolved("cool")
            try:
                condenser_list = list(pan_floor.pan_condensers)
                for evap in evap_station:
                    condenser_list.append(evap.condenser)

                ctwrs = CoolingTowerSystem(
                    condensers=condenser_list,
                    cool_water_temp_F=ct_cool_water_temp,
                    percent_blowdown=ct_pct_blowdown,
                    makeup_water_temp_F=ct_makeup_water_temp,
                    iterations=ct_iterations,
                    name="Cooling Tower System",
                )
               # ctwrs_fig = ctwrs.generate_pfd(show=False)
               # plt.close(ctwrs_fig)

                SOLVED["ctwrs"] = ctwrs
               # SOLVED["ctwrs_pfd"] = ctwrs_fig
                SOLVED["cool_ok"] = True
                SOLVED["cool_error"] = None
            except Exception as exc:
                SOLVED["ctwrs"] = None
                SOLVED["cool_ok"] = False
                SOLVED["cool_error"] = str(exc)

        ctwrs = SOLVED.get("ctwrs")
        cool_ok = SOLVED.get("cool_ok", False)

        if cool_ok:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Vapor Condensed", f"{ctwrs.total_vapor_lb_hr:,.0f} lb/hr")
            c2.metric("Injection Water Demand", f"{ctwrs.total_injection_water_lb_hr:,.0f} lb/hr")
            c3.metric("Delivered Water Temp", f"{ctwrs.delivered_water_temp_F:.1f} °F")
            c4.metric("Makeup Required", f"{ctwrs.makeup_lb_hr:,.0f} lb/hr")

            c1, c2, c3 = st.columns(3)
            c1.metric("Evaporation Loss", f"{ctwrs.evaporated_lb_hr:,.0f} lb/hr")
            c2.metric("Blowdown", f"{ctwrs.blowdown_lb_hr:,.0f} lb/hr")
            c3.metric("Surplus", f"{ctwrs.surplus_lb_hr:,.0f} lb/hr")

            st.markdown("**System Streams**")
            st.dataframe(cooling_tower_streams_table(ctwrs), hide_index=True, use_container_width=True)

            st.markdown(f"**Condenser Inventory** ({len(ctwrs.condensers)} condensers)")
            st.dataframe(cooling_tower_condenser_table(ctwrs), hide_index=True, use_container_width=True)

            st.markdown("**Hot Water Return / Cooling Tower / System Balance**")
            st.dataframe(cooling_tower_balance_table(ctwrs), hide_index=True, use_container_width=True)

            st.subheader("Balance Check")
            bal_df = pd.DataFrame([ctwrs.balance_check])
            st.dataframe(bal_df, use_container_width=True, hide_index=True)
        elif SOLVED.get("cool_error"):
            st.error(f"Cooling tower failed to solve: {SOLVED['cool_error']}")
        else:
            st.info("Click **Solve Entire Plant** above to compute the cooling tower system.")


with tab_cool:
    render_tab_cool()
# ============================================================================
# CONDENSATE BALANCE TAB
# ============================================================================
@st.fragment
def render_tab_cond():
    st.subheader("Condensate Balance")
    heat_ok = SOLVED.get("heat_ok", False)
    pan_ok = SOLVED.get("pan_ok", False)
    evap_ok = SOLVED.get("evap_ok", False)
    steam_ok = SOLVED.get("steam_ok", False)
    cool_ok = SOLVED.get("cool_ok", False)
    juice_heaters = SOLVED.get("juice_heaters")
    clar_juice_heater = SOLVED.get("clar_juice_heater")
    pan_floor = SOLVED.get("pan_floor")
    pre_3 = SOLVED.get("pre_3")
    evap_station = SOLVED.get("evap_station", [])
    da = SOLVED.get("da")
    ctwrs = SOLVED.get("ctwrs")
    if not (heat_ok and pan_ok and evap_ok and steam_ok and cool_ok):
        st.warning("Solve Juice Heating, Pan Floor, Evaporation, Exhaust Summary, and Cooling Tower "
                   "first — condensate supply and water demand both draw from those sections.")
    else:
        clar_juice_heater_condensate = flash_condensate(
            clar_juice_heater.steam_required_lb_per_hr, clar_juice_heater.hot_stream.T)
        clar_juice_heater_label = f"Clarified Juice Heater ({STEAM_TYPES[clar_juice_heater.steam_type]})"

        clean_condensate_dict = {
            "Pre-Evaporator": pre_3.clean_condensate if pre_3 is not None else 0.0,
            "Evaporator Sets (Effect 1s)": sum(evap.clean_condensate for evap in evap_station),
            "Pan Floor - Exhaust Pans": pan_floor.clean_condensate,
            "Juice Heaters - Exhaust Station": juice_heaters.clean_condensate,
            **({clar_juice_heater_label: clar_juice_heater_condensate}
               if clar_juice_heater.steam_type == 0 else {}),
        }
        dirty_condensate_dict = {
            "Evaporator Sets (Effects 2+)": sum(evap.dirty_condensate for evap in evap_station),
            "Pan Floor - V1-V4 Pans": pan_floor.dirty_condensate,
            "Juice Heaters - V1-V4 Station": juice_heaters.dirty_condensate,
            **({clar_juice_heater_label: clar_juice_heater_condensate}
               if clar_juice_heater.steam_type != 0 else {}),
        }

        st.markdown("**Available Condensate**")
        avail_df = pd.DataFrame(
            list(clean_condensate_dict.items()) + list(dirty_condensate_dict.items()),
            columns=["Source", "lb/hr"],
        )
        avail_df.insert(1, "Type", ["Clean"] * len(clean_condensate_dict) + ["Dirty"] * len(dirty_condensate_dict))
        st.dataframe(avail_df, hide_index=True, use_container_width=True)

        # Wash water differs by boiling scheme — collect whichever centrifugals exist.
        # Use the scheme pan_floor was ACTUALLY solved with (not the live radio widget,
        # which may have been changed since without a re-solve yet) so this always matches
        # the real type of the cached pan_floor object.
        solved_pan_scheme = SOLVED.get("pan_scheme")
        if solved_pan_scheme == "FBDM":
            cent_wash_water_lb_hr = (pan_floor.A1_centrifugals.wash_water_lb_hr
                                      + pan_floor.A2_centrifugals.wash_water_lb_hr
                                      + pan_floor.B_centrifugals.wash_water_lb_hr
                                      + pan_floor.C_centrifugals.wash_water_lb_hr)
        elif solved_pan_scheme in ("TBDM", "3B"):
            cent_wash_water_lb_hr = (pan_floor.A_centrifugals.wash_water_lb_hr
                                      + pan_floor.B_centrifugals.wash_water_lb_hr
                                      + pan_floor.C_centrifugals.wash_water_lb_hr)
        else:
            cent_wash_water_lb_hr = (pan_floor.A_centrifugals.wash_water_lb_hr
                                      + pan_floor.C_centrifugals.wash_water_lb_hr)
        pan_dilution_water_lb_hr = pan_floor.total_water.flow_lb_per_hr - cent_wash_water_lb_hr

        filter_wash_water_lb_hr = clar.filter_wash_water_lb_hr

        st.markdown("**Water Demand — input table** (flow, target temp, and method are all editable)")
        demand_defaults = pd.DataFrame([
            {"Demand": "Boiler Feed Water", "Flow (lb/hr)": da.water_in_lb_hr,
             "Target Temp (°F)": da.water_in_deg_F, "Method": "blended"},
            {"Demand": "Imbibition", "Flow (lb/hr)": mills.imbibition_lb_hr,
             "Target Temp (°F)": 150.0, "Method": "blended"},
            {"Demand": "Wash Water - Centrifugals", "Flow (lb/hr)": cent_wash_water_lb_hr,
             "Target Temp (°F)": 180.0, "Method": "cooled"},
            {"Demand": "Dilution Water - Pans/Molasses/Remelt", "Flow (lb/hr)": pan_dilution_water_lb_hr,
             "Target Temp (°F)": 150.0, "Method": "blended"},
            {"Demand": "Mud Filter Wash Water", "Flow (lb/hr)": filter_wash_water_lb_hr,
             "Target Temp (°F)": 180.0, "Method": "blended"},
        ])
        demand_df = st.data_editor(
            demand_defaults, hide_index=True, use_container_width=True, num_rows="fixed",
            key="condensate_demand_editor", disabled=["Demand"],
            column_config={"Method": st.column_config.SelectboxColumn(options=["blended", "cooled"])},
        )

        gt1, gt2 = st.columns(2)
        well_water_temp_F = gt1.number_input(
            "Well water temp (°F)", value=float(ctwrs.makeup_water_temp_F) if ctwrs.makeup_water_temp_F
            else 70.0, step=1.0,
        )
        combined_condensate_temp_F = gt2.number_input("Combined condensate temp (°F)", value=210.0, step=5.0)

        if should_resolve("cond"):
            mark_resolved("cond")
            try:
                demand_notes = {
                    "Boiler Feed Water": "Recommend usage of clean condensate, make up with minimal dirty "
                                          "condensate or well water",
                }
                condensate_demands = [
                    CondensateDemand(row["Demand"], flow_lb_hr=row["Flow (lb/hr)"],
                                      temp_F=row["Target Temp (°F)"], method=row["Method"],
                                      note=demand_notes.get(row["Demand"], ""))
                    for _, row in demand_df.iterrows()
                ]

                condensate_balance = CondensateBalance(
                    clean_condensate_dict, dirty_condensate_dict, condensate_demands,
                    well_water_temp_F=well_water_temp_F,
                    combined_condensate_temp_F=combined_condensate_temp_F,
                    name="Condensate Balance",
                )
                SOLVED["condensate_balance"] = condensate_balance
                SOLVED["cond_ok"] = True
                SOLVED["cond_error"] = None
            except Exception as exc:
                SOLVED["condensate_balance"] = None
                SOLVED["cond_ok"] = False
                SOLVED["cond_error"] = str(exc)

        condensate_balance = SOLVED.get("condensate_balance")
        cond_ok = SOLVED.get("cond_ok", False)

        if cond_ok:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Condensate Available", f"{condensate_balance.total_condensate_available_lb_hr:,.0f} lb/hr")
            c2.metric("Total Water Demand", f"{condensate_balance.total_water_demand_lb_hr:,.0f} lb/hr")
            c3.metric("Condensate Required", f"{condensate_balance.total_condensate_required_lb_hr:,.0f} lb/hr")
            c4.metric("Well Water Required", f"{condensate_balance.total_well_water_required_lb_hr:,.0f} lb/hr")

            st.markdown("**Demand Detail**")
            demand_rows = [
                (d.name, d.flow_lb_hr, d.temp_F, d.method, d.condensate_flow_lb_hr,
                 d.well_water_flow_lb_hr, d.condensate_pct, d.warning)
                for d in condensate_balance.demands
            ]
            st.dataframe(
                pd.DataFrame(demand_rows, columns=["Demand", "Flow (lb/hr)", "Target Temp (°F)", "Method",
                                                    "Condensate (lb/hr)", "Well Water (lb/hr)",
                                                    "Condensate %", "Warning"]),
                hide_index=True, use_container_width=True,
            )
        elif SOLVED.get("cond_error"):
            st.error(f"Condensate balance failed to solve: {SOLVED['cond_error']}")
        else:
            st.info("Click **Solve Entire Plant** above to compute the condensate balance.")


with tab_cond:
    render_tab_cond()
# ============================================================================
# DOWNLOAD TAB
# ============================================================================
@st.fragment
def render_tab_dl():
    st.write("Export everything solved so far to a styled Excel workbook.")
    heat_ok = SOLVED.get("heat_ok", False)
    pan_ok = SOLVED.get("pan_ok", False)
    evap_ok = SOLVED.get("evap_ok", False)
    steam_ok = SOLVED.get("steam_ok", False)
    turb_ok = SOLVED.get("turb_ok", False)
    cool_ok = SOLVED.get("cool_ok", False)
    cond_ok = SOLVED.get("cond_ok", False)
    juice_heaters = SOLVED.get("juice_heaters")
    clar_juice_heater = SOLVED.get("clar_juice_heater")
    pan_floor = SOLVED.get("pan_floor")
    pre_3 = SOLVED.get("pre_3")
    evap_station = SOLVED.get("evap_station", [])
    da = SOLVED.get("da")
    knf_trbs = SOLVED.get("knf_trbs")
    mill_trbs = SOLVED.get("mill_trbs")
    misc_trbs = SOLVED.get("misc_trbs")
    blrs = SOLVED.get("blrs")
    live_steam_dict = SOLVED.get("live_steam_dict", {})
    exh_dict = SOLVED.get("exh_dict", {})
    exhaust_available = SOLVED.get("exhaust_available", 0.0)
    makeup_steam = SOLVED.get("makeup_steam", 0.0)
    ctwrs = SOLVED.get("ctwrs")
    condensate_balance = SOLVED.get("condensate_balance")
    if st.button("Build workbook", use_container_width=True):
        wb = new_workbook()
        mills.to_excel(wb)
        clar.to_excel(wb)
        if heat_ok:
            juice_heaters.to_excel(wb)
            clar_juice_heater.to_excel(wb)
        if pan_ok:
            pan_floor.to_excel(wb)
        if evap_ok:
            if pre_3 is not None:
                pre_3.to_excel(wb)
            if evap_station:
                sets_to_excel(evap_station, workbook=wb)
        if steam_ok:
            da.to_excel(wb)
        if turb_ok:
            knf_trbs.to_excel(wb)
            mill_trbs.to_excel(wb)
            misc_trbs.to_excel(wb)
            blrs.to_excel(wb)
            steam_summary_to_excel(
                wb, live_steam_dict, exh_dict,
                exhaust_available_lb_hr=exhaust_available,
                makeup_steam_lb_hr=makeup_steam,
                steam_available_lb_hr=blrs.steam_availabe_lb_hr,
            )
        if cool_ok:
            ctwrs.to_excel(wb)
        if cond_ok:
            condensate_balance.to_excel(wb)
        buf = io.BytesIO()
        wb.save(buf)
        st.session_state["workbook_bytes"] = buf.getvalue()

    st.caption(
        "Included when solved: Mill Floor, Clarification, Juice Heating, Pan Floor, "
        "Pre-Evaporator + Evaporator Sets, Deaerator, Turbines (Knife/Mill/Auxiliary), "
        "Boiler, Steam Summary, Cooling Tower, Condensate Balance — the same sections "
        "main.py and SMSC_Balance.py write to their workbooks."
    )

    if "workbook_bytes" in st.session_state:
        now = datetime.now()
        formatted_dt = now.strftime("%Y%m%d-%H%M%S")
        prefix = st.text_input(label='File Name Prefix Input: ', value='Factory')
        excel_filename = f"{prefix}_{formatted_dt}.xlsx"
        st.download_button(
            "Download Excel workbook",
            data=st.session_state["workbook_bytes"],
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

with tab_dl:
    render_tab_dl()
# ============================================================================
# PROCESS FLOW DIAGRAMS TAB — on-demand PFD generation, one button per station.
# ============================================================================
def _pfd_button(label, state_key, fig_fn, available, unavailable_msg):
    st.markdown(f"**{label}**")
    if not available:
        st.caption(unavailable_msg)
        st.divider()
        return
    if st.button(f"Generate {label} PFD", key=f"pfd_btn_{state_key}"):
        old_fig = PFD_CACHE.get(state_key)
        if old_fig is not None:
            plt.close(old_fig)
        try:
            PFD_CACHE[state_key] = fig_fn()
            PFD_CACHE[f"{state_key}_error"] = None
        except Exception as exc:
            PFD_CACHE[state_key] = None
            PFD_CACHE[f"{state_key}_error"] = str(exc)
    if PFD_CACHE.get(f"{state_key}_error"):
        st.error(f"Failed to generate PFD: {PFD_CACHE[f'{state_key}_error']}")
    elif PFD_CACHE.get(state_key) is not None:
        st.pyplot(PFD_CACHE[state_key], use_container_width=True)
    st.divider()


@st.fragment
def render_tab_pfd():
    st.subheader("Process Flow Diagrams")
    st.caption(
        "Drawing a PFD is the slow part of solving a station, so it's opt-in here — click a "
        "button to render that station's diagram from its last successful solve. Diagrams do "
        "not refresh automatically on re-solve; re-click a button to update its picture."
    )

    mills = SOLVED.get("mills")
    clar = SOLVED.get("clar")
    juice_heaters = SOLVED.get("juice_heaters")
    clar_juice_heater = SOLVED.get("clar_juice_heater")
    pan_floor = SOLVED.get("pan_floor")
    pre_3 = SOLVED.get("pre_3")
    evap_station = SOLVED.get("evap_station", [])
    da = SOLVED.get("da")
    knf_trbs = SOLVED.get("knf_trbs")
    mill_trbs = SOLVED.get("mill_trbs")
    misc_trbs = SOLVED.get("misc_trbs")
    ctwrs = SOLVED.get("ctwrs")

    _pfd_button("Mill Floor", "mills", lambda: mills.generate_pfd(show=False),
                mills is not None, "Click Solve Entire Plant above first.")
    _pfd_button("Clarification", "clar", lambda: clar.generate_pfd(show=False, include_table=False),
                clar is not None, "Click Solve Entire Plant above first.")
    _pfd_button("Juice Heating Station", "juice_heaters", lambda: juice_heaters.generate_pfd(show=False),
                juice_heaters is not None, "Solve Juice Heating first (see its tab).")
    _pfd_button("Clarified Juice Heater", "clar_juice_heater",
                lambda: clar_juice_heater.generate_pfd(show=False),
                clar_juice_heater is not None, "Solve Juice Heating first (see its tab).")
    _pfd_button("Pan Floor", "pan_floor", lambda: pan_floor.generate_pfd(show=False),
                pan_floor is not None, "Solve the Pan Floor first (see its tab).")
    _pfd_button("Pre-Evaporator", "pre_3", lambda: pre_3.generate_pfd(show=False),
                pre_3 is not None, "Solve Evaporation with the Pre-Evaporator active first (see its tab).")

    st.markdown("**Evaporator Sets**")
    if not evap_station:
        st.caption("Solve Evaporation first (see its tab).")
    else:
        for evap in evap_station:
            _pfd_button(evap.name, f"evap_{evap.name}",
                        lambda evap=evap: evap.generate_pfd(show=False, pre_evap=pre_3),
                        True, "")

    _pfd_button("Deaerator", "da", lambda: da.generate_pfd(show=False),
                da is not None, "Solve the Exhaust Summary tab first.")
    _pfd_button("Cane Prep (Knife) Turbines", "knf_trbs", lambda: knf_trbs.generate_pfd(show=False),
                knf_trbs is not None, "Solve the Turbines & Boiler tab first.")
    _pfd_button("Mill Turbines", "mill_trbs", lambda: mill_trbs.generate_pfd(show=False),
                mill_trbs is not None, "Solve the Turbines & Boiler tab first.")
    _pfd_button("Auxiliary Turbines", "misc_trbs", lambda: misc_trbs.generate_pfd(show=False),
                misc_trbs is not None, "Solve the Turbines & Boiler tab first.")
    _pfd_button("Cooling Tower System", "ctwrs", lambda: ctwrs.generate_pfd(show=False),
                ctwrs is not None, "Solve the Cooling Tower tab first.")


with tab_pfd:
    render_tab_pfd()
