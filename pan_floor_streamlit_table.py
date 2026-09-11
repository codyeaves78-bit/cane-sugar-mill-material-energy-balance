# Flat "Section / Stream / ... / Entering-Leaving-Internal" row builders for the
# Pan Floor tab's Streamlit output table. Mirrors the station breakdown used by
# each scheme's to_excel() (see pan_floor_excel.py), but emits row dicts with the
# richer stream-table column set instead of writing to an Excel sheet.

import pandas as pd

from SugarStream import SugarStream
from Massecuite import predict_mother_liquor_purity

COLUMNS = [
    "Section", "Stream", "Entering, Leaving, Internal", "Flow lb/hr", "Pol %", "Brix %",
    "Purity", "Pol lb/hr", "Brix lb/hr", "Cu Ft./hr", "Specific Gravity", "Temperature",
    "Crystal Content (Massecuite Only)", "Predicted ML Purity (Birkett, Massecuite Only)",
]

STEAM_TYPE_LABELS = {0: "Exhaust", 1: "V1", 2: "V2", 3: "V3", 4: "V4"}

ENTERING = "Entering"
LEAVING = "Leaving"
INTERNAL = "Internal"


def combine_streams(streams):
    """Mass-weighted combination of streams with the same solids (brix/purity
    blended by mass balance, temperature blended by flow). Used for summary rows
    like a combined 'Remelt' where the model keeps the underlying streams separate."""
    streams = [s for s in streams if s.flow_lb_per_hr > 0]
    if not streams:
        return SugarStream(brix=0, purity=0, flow_lb_per_hr=0, temp_deg_F=0)
    total_flow = sum(s.flow_lb_per_hr for s in streams)
    total_solids = sum(s.solids_flow for s in streams)
    total_pol = sum(s.pol_flow for s in streams)
    combined = SugarStream.copy(streams[0])
    combined.flow_lb_per_hr = total_flow
    combined.brix = total_solids / total_flow * 100
    combined.purity = total_pol / total_solids * 100 if total_solids else 0
    combined.temp_deg_F = sum(s.flow_lb_per_hr * s.temp_deg_F for s in streams) / total_flow
    return combined


def stream_row(section, name, tag, s):
    return {
        "Section": section, "Stream": name,
        "Flow lb/hr": s.flow_lb_per_hr, "Pol %": s.pol, "Brix %": s.brix,
        "Purity": s.purity, "Pol lb/hr": s.pol_flow, "Brix lb/hr": s.solids_flow,
        "Cu Ft./hr": s.cu_ft_hr, "Specific Gravity": s.specific_gravity,
        "Temperature": s.temp_deg_F, "Crystal Content (Massecuite Only)": None,
        "Predicted ML Purity (Birkett, Massecuite Only)": None,
        "Entering, Leaving, Internal": tag,
    }


def water_row(section, name, tag, flow_lb_hr, temp_deg_F=None):
    return {
        "Section": section, "Stream": name,
        "Flow lb/hr": flow_lb_hr, "Pol %": None, "Brix %": 0.0,
        "Purity": None, "Pol lb/hr": 0.0, "Brix lb/hr": 0.0,
        "Cu Ft./hr": flow_lb_hr / 62.4 if flow_lb_hr else 0.0,
        "Specific Gravity": 1.0,
        "Temperature": temp_deg_F, "Crystal Content (Massecuite Only)": None,
        "Predicted ML Purity (Birkett, Massecuite Only)": None,
        "Entering, Leaving, Internal": tag,
    }

def vapor_row(section, name, tag, flow_lb_hr, temp_deg_F=None):
    return {
        "Section": section, "Stream": name,
        "Flow lb/hr": flow_lb_hr, "Pol %": None, "Brix %": 0.0,
        "Purity": None, "Pol lb/hr": 0.0, "Brix lb/hr": 0.0,
        "Cu Ft./hr": None,
        "Specific Gravity": None,
        "Temperature": temp_deg_F, "Crystal Content (Massecuite Only)": None,
        "Predicted ML Purity (Birkett, Massecuite Only)": None,
        "Entering, Leaving, Internal": tag,
    }


def massecuite_row(section, name, tag, masse, flow_lb_hr):
    """masse is a Massecuite instance (Pan/Centrifugal/Crystallizer/Reheater's
    massecuite object); flow_lb_hr comes from the owning unit's own flow property
    since these Massecuite instances aren't built with flow_lb_hr set."""
    return {
        "Section": section, "Stream": name,
        "Flow lb/hr": flow_lb_hr,
        "Pol %": masse.masse_purity * masse.masse_brix / 100,
        "Brix %": masse.masse_brix, "Purity": masse.masse_purity,
        "Pol lb/hr": flow_lb_hr * masse.masse_purity * masse.masse_brix / 10000,
        "Brix lb/hr": flow_lb_hr * masse.masse_brix / 100,
        "Cu Ft./hr": flow_lb_hr / masse.density, "Specific Gravity": masse.density / 62.4,
        "Temperature": masse.massecuite_temp,
        "Crystal Content (Massecuite Only)": masse.crystal_content,
        "Predicted ML Purity (Birkett, Massecuite Only)": predict_mother_liquor_purity(masse.masse_purity),
        "Entering, Leaving, Internal": tag,
    }


def _grade(name, suffix):
    """'A1 Pans' -> 'A1', 'C Centrifugals' -> 'C' — for terse row labels."""
    return name[:-len(suffix)].strip() if name.endswith(suffix) else name


def _pan_rows(section, pan, feed_names):
    grade = _grade(pan.name, "Pans")
    rows = [stream_row(section, n, ENTERING, f) for n, f in zip(feed_names, pan.feed_streams)]
    rows.append(massecuite_row(section, f"{grade} Massecuite", LEAVING,
                                pan.massecuite, pan.massecuite_flow_lb_hr))
    # Vapor leaves at the vapor-space (surface) condition, not the massecuite's own
    # boiling point at head depth — water_bp_surface, not water_bp_at_head.
    vapor_temp = pan.massecuite.water_bp_surface
    rows.append(vapor_row(section, "Vapors", LEAVING, pan.water_evaporated_lb_hr, vapor_temp))
    return rows


def _overall_rows(pan_floor, sugar_rows):
    """sugar_rows: [(label, stream), ...] — the raw sugar product(s) leaving the floor."""
    section = "Overall"
    # _final_molasses_out (final centrifugal molasses net of any C top-off recycled back
    # to the C pans) is only present on schemes with the top-off feature; fall back to the
    # raw centrifugal output for schemes (e.g. FourBoilingDoubleMagma) that lack it.
    final_molasses = getattr(pan_floor, "_final_molasses_out", pan_floor.C_centrifugals.molasses_stream)
    pans = pan_floor._pans
    total_vapor = sum(p.water_evaporated_lb_hr for p in pans)
    vapor_temp = (sum(p.water_evaporated_lb_hr * p.massecuite.water_bp_surface for p in pans)
                  / total_vapor if total_vapor else 0)

    rows = [stream_row(section, "Syrup From Evaporators", ENTERING, pan_floor.syrup)]
    rows.append(water_row(section, "Total Water", ENTERING, pan_floor.total_water.flow_lb_per_hr))
    rows += [stream_row(section, label, LEAVING, s) for label, s in sugar_rows]
    rows.append(stream_row(section, "Final Molasses", LEAVING, final_molasses))
    rows.append(water_row(section, "Vapors", LEAVING, total_vapor, vapor_temp))
    return rows


def _cen_rows(section, cen):
    grade = _grade(cen.name, "Centrifugals")
    rows = [
        massecuite_row(section, f"{grade} Massecuite", ENTERING,
                        cen.massecuite, cen.massecuite_flow_lb_hr),
        water_row(section, "Wash Water", ENTERING, cen.wash_water_lb_hr),
        stream_row(section, f"{grade} Sugar", LEAVING, cen.sugar_stream),
        stream_row(section, f"{grade} Molasses", LEAVING, cen.molasses_stream),
    ]
    return rows


def _dil_rows(section, undiluted, diluted, label):
    water = diluted.flow_lb_per_hr - undiluted.flow_lb_per_hr
    return [
        stream_row(section, f"{label} (undiluted)", ENTERING, undiluted),
        water_row(section, "Dilution Water", ENTERING, water),
        stream_row(section, f"{label} (diluted)", LEAVING, diluted),
    ]


def _magma_rows(section, sugar, magma, label):
    water = magma.flow_lb_per_hr - sugar.flow_lb_per_hr
    return [
        stream_row(section, f"{label} Sugar", ENTERING, sugar),
        water_row(section, "Mingler Water", ENTERING, water),
        stream_row(section, f"{label} Magma", LEAVING, magma),
    ]


def _magma_split_rows(section, magma, destinations):
    """destinations: [(label, stream), ...] whose flows sum to magma's flow."""
    return [stream_row(section, label, INTERNAL, s) for label, s in destinations]


def _remelt_rows(section, magma_to_rmlt, remelt, label):
    water = remelt.flow_lb_per_hr - magma_to_rmlt.flow_lb_per_hr
    return [
        stream_row(section, f"{label} Magma (to Remelt)", ENTERING, magma_to_rmlt),
        water_row(section, "Remelt Water", ENTERING, water),
        stream_row(section, f"{label} Remelt", LEAVING, remelt),
    ]


def _heatx_rows(section, unit):
    return [
        massecuite_row(section, "Massecuite Entering", ENTERING,
                        unit.massecuite_in, unit.massecuite_flow_lb_hr),
        massecuite_row(section, "Massecuite Leaving", LEAVING,
                        unit.massecuite_out, unit.massecuite_flow_lb_hr),
    ]


# ---------------------------------------------------------------------------
# Three Boiling Double Magma
# ---------------------------------------------------------------------------

def three_boiling_rows(tb) -> list:
    a_sugar = tb.A_centrifugals.sugar_stream
    combined_remelt = combine_streams([tb._b_remelt, tb._c_remelt])
    combined_magma_to_rmlt = combine_streams([tb._b_magma_to_rmlt, tb._c_magma_to_rmlt])

    rows = _overall_rows(tb, [("A Sugar", a_sugar)])

    rows += _remelt_rows("Remelt Station", combined_magma_to_rmlt, combined_remelt, "B+C")

    rows.append(stream_row("Syrup Tanks", "Syrup From Evaporators", ENTERING, tb.syrup))
    rows.append(stream_row("Syrup Tanks", "Remelt", ENTERING, combined_remelt))
    rows.append(stream_row("Syrup Tanks", "Syrup Remelt Blend", LEAVING, tb.syrup_as_fed))

    rows.append(stream_row("Syrup Distribution", "Syrup to A Pans", INTERNAL,
                            _scaled(tb.syrup_as_fed, tb.syrup_to_A_pans_pct)))
    rows.append(stream_row("Syrup Distribution", "Syrup to Grain Pans", INTERNAL,
                            _scaled(tb.syrup_as_fed, tb.syrup_to_grain_pct)))

    rows += _pan_rows("A Station - Pans", tb.A_pans, ["Syrup", "B Magma", "A Molasses Top-off"])
    rows += _cen_rows("A Station - Centrifugals", tb.A_centrifugals)
    rows += _dil_rows("A Station - A Molasses Dilution", tb.A_centrifugals.molasses_stream,
                       tb._a_mol_diluted, "A Molasses")
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to A Pans", INTERNAL,
                            _scaled(tb._a_mol_diluted, tb.a_mol_top_off_pct)))
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to B Pans", INTERNAL,
                            _scaled(tb._a_mol_diluted, tb.a_mol_B_pans_pct)))
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to Grain", INTERNAL,
                            _scaled(tb._a_mol_diluted, tb.a_mol_to_grain_pct)))

    rows += _pan_rows("B Station - Pans", tb.B_pans, ["C Magma", "A Molasses", "B Molasses Top-off"])
    rows += _cen_rows("B Station - Centrifugals", tb.B_centrifugals)
    rows += _magma_rows("B Station - B Mingler", tb.B_centrifugals.sugar_stream, tb._b_magma, "B")
    rows += _magma_split_rows("B Station - B Magma Distribution", tb._b_magma, [
        ("B Magma to A Footing", tb._b_magma_A_pans),
        ("B Magma to Remelt", tb._b_magma_to_rmlt),
    ])
    rows += _dil_rows("B Station - Molasses Dilution", tb.B_centrifugals.molasses_stream,
                       tb._b_mol_diluted, "B Molasses")
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses to Grain", INTERNAL,
                            _scaled(tb._b_mol_diluted, tb.b_mol_to_grain_pct)))
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses to C Pans", INTERNAL,
                            _scaled(tb._b_mol_diluted, tb.b_mol_C_pans_pct)))
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses Top-off (to B Pans)", INTERNAL,
                            _scaled(tb._b_mol_diluted, tb.b_mol_top_off_pct)))

    rows += _pan_rows("Grain Pans", tb.grain_pans, ["Syrup", "A Molasses", "B Molasses"])

    rows += _pan_rows("C Station - Pans", tb.C_pans, ["Grain Massecuite", "B Molasses", "C Molasses Top-off"])
    rows += _heatx_rows("C Station - Crystallizers", tb.C_crystallizers)
    rows += _heatx_rows("C Station - Reheater", tb.C_reheaters)
    rows += _cen_rows("C Station - Centrifugals", tb.C_centrifugals)
    rows += _dil_rows("C Station - C Molasses Top-off Dilution", tb._c_mol_top_off_non_dilute,
                       tb._c_mol_top_off, "C Molasses Top-off")
    rows += _magma_rows("C Station - C Mingler", tb.C_centrifugals.sugar_stream, tb._c_magma, "C")
    rows += _magma_split_rows("C Station - C Magma Distribution", tb._c_magma, [
        ("C Magma to B Footing", tb._c_magma_B_pans),
        ("C Magma to Remelt", tb._c_magma_to_rmlt),
    ])
    return rows


# ---------------------------------------------------------------------------
# Three Boiling (Single Magma)
# ---------------------------------------------------------------------------

def three_boiling_single_magma_rows(tb) -> list:
    a_sugar = tb.A_centrifugals.sugar_stream
    b_sugar = tb.B_centrifugals.sugar_stream

    rows = _overall_rows(tb, [("A Sugar", a_sugar), ("B Sugar", b_sugar)])

    rows += _remelt_rows("Remelt Station", tb._c_magma_to_rmlt, tb._c_remelt, "C")

    rows.append(stream_row("Syrup Tanks", "Syrup From Evaporators", ENTERING, tb.syrup))
    rows.append(stream_row("Syrup Tanks", "Remelt", ENTERING, tb._c_remelt))
    rows.append(stream_row("Syrup Tanks", "Syrup Remelt Blend", LEAVING, tb.syrup_as_fed))

    rows.append(stream_row("Syrup Distribution", "Syrup to A Pans", INTERNAL,
                            _scaled(tb.syrup_as_fed, tb.syrup_to_A_pans_pct)))
    rows.append(stream_row("Syrup Distribution", "Syrup to Grain Pans", INTERNAL,
                            _scaled(tb.syrup_as_fed, tb.syrup_to_grain_pct)))

    rows += _pan_rows("A Station - Pans", tb.A_pans, ["Syrup", "C Magma (A Footing)", "A Molasses Top-off"])
    rows += _cen_rows("A Station - Centrifugals", tb.A_centrifugals)
    rows += _dil_rows("A Station - A Molasses Dilution", tb.A_centrifugals.molasses_stream,
                       tb._a_mol_diluted, "A Molasses")
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses Top-off", INTERNAL,
                            _scaled(tb._a_mol_diluted, tb.a_mol_top_off_pct)))
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to B Pans", INTERNAL,
                            _scaled(tb._a_mol_diluted, tb.a_mol_B_pans_pct)))
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to Grain", INTERNAL,
                            _scaled(tb._a_mol_diluted, tb.a_mol_to_grain_pct)))

    rows += _pan_rows("B Station - Pans", tb.B_pans, ["C Magma (B Footing)", "A Molasses", "B Molasses Top-off"])
    rows += _cen_rows("B Station - Centrifugals", tb.B_centrifugals)
    rows += _dil_rows("B Station - Molasses Dilution", tb.B_centrifugals.molasses_stream,
                       tb._b_mol_diluted, "B Molasses")
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses to Grain", INTERNAL,
                            _scaled(tb._b_mol_diluted, tb.b_mol_to_grain_pct)))
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses to C Pans", INTERNAL,
                            _scaled(tb._b_mol_diluted, tb.b_mol_C_pans_pct)))
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses Top-off (to B Pans)", INTERNAL,
                            _scaled(tb._b_mol_diluted, tb.b_mol_top_off_pct)))

    rows += _pan_rows("Grain Pans", tb.grain_pans, ["Syrup", "A Molasses", "B Molasses"])

    rows += _pan_rows("C Station - Pans", tb.C_pans, ["Grain Massecuite", "B Molasses", "C Molasses Top-off"])
    rows += _heatx_rows("C Station - Crystallizers", tb.C_crystallizers)
    rows += _heatx_rows("C Station - Reheater", tb.C_reheaters)
    rows += _cen_rows("C Station - Centrifugals", tb.C_centrifugals)
    rows += _dil_rows("C Station - C Molasses Top-off Dilution", tb._c_mol_top_off_non_dilute,
                       tb._c_mol_top_off, "C Molasses Top-off")
    rows += _magma_rows("C Station - C Mingler", tb.C_centrifugals.sugar_stream, tb._c_magma, "C")
    rows += _magma_split_rows("C Station - C Magma Distribution", tb._c_magma, [
        ("C Magma to A Footing", tb._c_magma_A_pans),
        ("C Magma to B Footing", tb._c_magma_B_pans),
        ("C Magma to Remelt", tb._c_magma_to_rmlt),
    ])
    return rows


# ---------------------------------------------------------------------------
# Four Boiling Double Magma
# ---------------------------------------------------------------------------

def four_boiling_rows(fb) -> list:
    a1_sugar = fb.A1_centrifugals.sugar_stream
    a2_sugar = fb.A2_centrifugals.sugar_stream
    combined_remelt = combine_streams([fb._b_remelt, fb._c_remelt])
    combined_magma_to_rmlt = combine_streams([fb._b_magma_to_rmlt, fb._c_magma_to_rmlt])

    rows = _overall_rows(fb, [("A1 Sugar", a1_sugar), ("A2 Sugar", a2_sugar)])

    rows += _remelt_rows("Remelt Station", combined_magma_to_rmlt, combined_remelt, "B+C")

    rows.append(stream_row("Syrup Tanks", "Syrup From Evaporators", ENTERING, fb.syrup))
    rows.append(stream_row("Syrup Tanks", "Remelt", ENTERING, combined_remelt))
    rows.append(stream_row("Syrup Tanks", "Syrup Remelt Blend", LEAVING, fb.syrup_as_fed))

    rows.append(stream_row("Syrup Distribution", "Syrup to A1 Pans", INTERNAL,
                            _scaled(fb.syrup_as_fed, fb.syrup_to_A1_pans_pct)))
    rows.append(stream_row("Syrup Distribution", "Syrup to A2 Pans", INTERNAL,
                            _scaled(fb.syrup_as_fed, fb.syrup_to_A2_pans_pct)))
    rows.append(stream_row("Syrup Distribution", "Syrup to Grain Pans", INTERNAL,
                            _scaled(fb.syrup_as_fed, fb.syrup_to_grain_pct)))

    rows += _pan_rows("A1 Station - Pans", fb.A1_pans, ["Syrup", "B Magma A1 Footing"])
    rows += _cen_rows("A1 Station - Centrifugals", fb.A1_centrifugals)
    rows += _dil_rows("A1 Station - A1 Molasses Dilution", fb.A1_centrifugals.molasses_stream,
                       fb._a1_mol_diluted, "A1 Molasses")
    rows.append(stream_row("A1 Station - A1 Molasses Distribution", "A1 Molasses to A2", INTERNAL,
                            _scaled(fb._a1_mol_diluted, fb.a1_mol_to_A2_pct)))
    rows.append(stream_row("A1 Station - A1 Molasses Distribution", "A1 Molasses to Grain", INTERNAL,
                            _scaled(fb._a1_mol_diluted, fb.a1_mol_to_grain_pct)))
    rows.append(stream_row("A1 Station - A1 Molasses Distribution", "A1 Molasses to B", INTERNAL,
                            _scaled(fb._a1_mol_diluted, fb.a1_mol_to_B_pct)))

    rows += _pan_rows("A2 Station - Pans", fb.A2_pans, ["Syrup", "A1 Molasses", "B Magma A2 Footing"])
    rows += _cen_rows("A2 Station - Centrifugals", fb.A2_centrifugals)
    rows += _dil_rows("A2 Station - A2 Molasses Dilution", fb.A2_centrifugals.molasses_stream,
                       fb._a2_mol_diluted, "A2 Molasses")
    rows.append(stream_row("A2 Station - A2 Molasses Distribution", "A2 Molasses to Grain", INTERNAL,
                            _scaled(fb._a2_mol_diluted, fb.a2_mol_to_grain_pct)))
    rows.append(stream_row("A2 Station - A2 Molasses Distribution", "A2 Molasses to B", INTERNAL,
                            _scaled(fb._a2_mol_diluted, fb.a2_mol_to_B_pct)))

    rows += _pan_rows("B Station - Pans", fb.B_pans, ["A2 Molasses to B", "C Magma B Footing", "A1 Molasses to B"])
    rows += _cen_rows("B Station - Centrifugals", fb.B_centrifugals)
    rows += _magma_rows("B Station - B Mingler", fb.B_centrifugals.sugar_stream, fb._b_magma, "B")
    rows += _magma_split_rows("B Station - B Magma Distribution", fb._b_magma, [
        ("B Magma to A1 Footing", fb._b_magma_A1_footing),
        ("B Magma to A2 Footing", fb._b_magma_A2_footing),
        ("B Magma to Remelt", fb._b_magma_to_rmlt),
    ])
    rows += _dil_rows("B Station - Molasses Dilution", fb.B_centrifugals.molasses_stream,
                       fb._b_mol_diluted, "B Molasses")
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses to Grain", INTERNAL,
                            _scaled(fb._b_mol_diluted, fb.b_mol_to_grain_pct)))
    rows.append(stream_row("B Station - B Molasses Distribution", "B Molasses to C Pans", INTERNAL,
                            _scaled(fb._b_mol_diluted, fb.b_mol_to_C_pct)))

    rows += _pan_rows("Grain Pans", fb.grain_pans,
                       ["Syrup", "A1 Molasses", "A2 Molasses", "B Molasses"])

    rows += _pan_rows("C Station - Pans", fb.C_pans, ["Grain Massecuite", "B Molasses"])
    rows += _heatx_rows("C Station - Crystallizers", fb.C_crystallizers)
    rows += _heatx_rows("C Station - Reheater", fb.C_reheaters)
    rows += _cen_rows("C Station - Centrifugals", fb.C_centrifugals)
    rows += _magma_rows("C Station - C Mingler", fb.C_centrifugals.sugar_stream, fb._c_magma, "C")
    rows += _magma_split_rows("C Station - C Magma Distribution", fb._c_magma, [
        ("C Magma to B Footing", fb._c_magma_B_footing),
        ("C Magma to Remelt", fb._c_magma_to_rmlt),
    ])
    return rows


# ---------------------------------------------------------------------------
# Two Boiling
# ---------------------------------------------------------------------------

def two_boiling_rows(twb) -> list:
    a_sugar = twb.A_centrifugals.sugar_stream

    rows = _overall_rows(twb, [("A Sugar", a_sugar)])

    rows += _remelt_rows("Remelt Station", twb._c_magma_to_rmlt, twb._c_remelt, "C")

    rows.append(stream_row("Syrup Tanks", "Syrup From Evaporators", ENTERING, twb.syrup))
    rows.append(stream_row("Syrup Tanks", "Remelt", ENTERING, twb._c_remelt))
    rows.append(stream_row("Syrup Tanks", "Syrup Remelt Blend", LEAVING, twb.syrup_as_fed))

    rows.append(stream_row("Syrup Distribution", "Syrup to A Pans", INTERNAL,
                            _scaled(twb.syrup_as_fed, twb.syrup_to_A_pans_pct)))
    rows.append(stream_row("Syrup Distribution", "Syrup to Grain Pans", INTERNAL,
                            _scaled(twb.syrup_as_fed, twb.syrup_to_grain_pct)))
    rows.append(stream_row("Syrup Distribution", "Syrup to C Pans", INTERNAL,
                            _scaled(twb.syrup_as_fed, twb.syrup_to_C_pct)))

    rows += _pan_rows("A Station - Pans", twb.A_pans, ["Syrup", "C Magma", "A Molasses Top-off"])
    rows += _cen_rows("A Station - Centrifugals", twb.A_centrifugals)
    rows += _dil_rows("A Station - A Molasses Dilution", twb.A_centrifugals.molasses_stream,
                       twb._a_mol_diluted, "A Molasses")
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses Top-off", INTERNAL,
                            _scaled(twb._a_mol_diluted, twb.a_mol_top_off_pct)))
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to Grain", INTERNAL,
                            _scaled(twb._a_mol_diluted, twb.a_mol_to_grain_pct)))
    rows.append(stream_row("A Station - A Molasses Distribution", "A Molasses to C Pans", INTERNAL,
                            _scaled(twb._a_mol_diluted, twb.a_mol_to_C_pans_pct)))

    rows += _pan_rows("Grain Pans", twb.grain_pans, ["Syrup", "A Molasses"])

    rows += _pan_rows("C Station - Pans", twb.C_pans, ["Grain Massecuite", "A Molasses", "Syrup", "C Molasses Top-off"])
    rows += _heatx_rows("C Station - Crystallizers", twb.C_crystallizers)
    rows += _heatx_rows("C Station - Reheater", twb.C_reheaters)
    rows += _cen_rows("C Station - Centrifugals", twb.C_centrifugals)
    rows += _dil_rows("C Station - C Molasses Top-off Dilution", twb._c_mol_top_off_non_dilute,
                       twb._c_mol_top_off, "C Molasses Top-off")
    rows += _magma_rows("C Station - C Mingler", twb.C_centrifugals.sugar_stream, twb._c_magma, "C")
    rows += _magma_split_rows("C Station - C Magma Distribution", twb._c_magma, [
        ("C Magma to A Footing", twb._c_magma_A_pans),
        ("C Magma to Remelt", twb._c_magma_to_rmlt),
    ])
    return rows


def _scaled(stream, pct):
    """A copy of stream scaled to pct% of its flow — for display-only distribution rows."""
    out = SugarStream.copy(stream)
    out.flow_lb_per_hr = stream.flow_lb_per_hr * pct / 100
    return out


def massecuite_summary_table(pan_floor, cane_tpd) -> pd.DataFrame:
    """One column per pan's massecuite (by grade), plus a Total column —
    Cubic Ft / Hr, Cubic Ft / Day, Cubic Ft / Ton Cane. Generic across all three
    schemes since it just walks pan_floor._pans (A/A1/A2/B/Grain/C, whichever exist)."""
    def _col(ft3_hr):
        ft3_day = ft3_hr * 24
        ft3_ton_cane = ft3_day / cane_tpd if cane_tpd else 0.0
        return [f"{ft3_hr:,.2f}", f"{ft3_day:,.2f}", f"{ft3_ton_cane:,.2f}"]

    data = {}
    total_ft3_hr = 0.0
    for pan in pan_floor._pans:
        grade = _grade(pan.name, "Pans")
        ft3_hr = pan.massecuite_flow_lb_hr / pan.massecuite.density
        total_ft3_hr += ft3_hr
        data[f"{grade} Massecuite"] = _col(ft3_hr)
    data["Total"] = _col(total_ft3_hr)
    return pd.DataFrame(data, index=["Cubic Ft / Hr", "Cubic Ft / Day", "Cubic Ft / Ton Cane"])


def steam_consumption_table(pan_floor) -> pd.DataFrame:
    """One column per pan, rows = calandria steam side + vapor side + heat transfer."""
    rows = []
    for pan in pan_floor._pans:
        rows.append({
            "Pan": pan.name,
            "Steam Used (lb/hr)": f"{pan.steam_flow_lb_hr:,.2f}",
            "Steam Type": STEAM_TYPE_LABELS.get(pan.steam_type, str(pan.steam_type)),
            "Steam Pressure (psia)": f"{pan.calandria_pressure_psia:,.2f}",
            "Steam Temp (°F)": f"{pan.calandria_T_sat_F:,.2f}",
            "Steam hfg (BTU/lb)": f"{pan.h_fg_calandria:,.2f}",
            "Massecuite Temp (°F)": f"{pan.massecuite.massecuite_temp:,.2f}",
            "Vapor Evaporated (lb/hr)": f"{pan.water_evaporated_lb_hr:,.2f}",
            "Vapor Temp (°F)": f"{pan.massecuite.water_bp_surface:,.2f}",
            "Vapor Pressure (psia)": f"{pan.massecuite.vapor_pressure_psia:,.2f}",
            "Vapor hfg (BTU/lb)": f"{pan.h_fg_vapor:,.2f}",
            "Heating Surface (ft²)": f"{pan.heating_surface_ft2:,.2f}",
            "U (Btu/hr·ft²·°F)": f"{pan.U_btu_hr_ft2_F:,.2f}",
        })
    return pd.DataFrame(rows).set_index("Pan").T
