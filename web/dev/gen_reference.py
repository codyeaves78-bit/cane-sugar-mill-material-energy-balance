# Generates reference IAPWS-97 property values using the Python `iapws`
# package this project already depends on, spanning the pressure/temperature
# envelope this mill actually operates in (roughly 1-950 psia, up to 800 F).
# validate.mjs loads these and checks web/src/iapws97.js against them.
#
# Run from repo root: python web/dev/gen_reference.py

import json
from iapws import IAPWS97

MPA_PER_PSIA = 0.00689476
K_OFFSET = 273.15

def f_to_k(f):
    return (f - 32) * 5 / 9 + K_OFFSET

def psia_to_mpa(psia):
    return psia * MPA_PER_PSIA

cases = []

# --- TP: compressed liquid and superheated vapor over the full pressure range
pressures_psia = [2, 5, 10, 14.696, 20, 30, 45, 60, 90, 120, 165, 180, 200, 250,
                   300, 400, 500, 600, 750, 900]
for p_psia in pressures_psia:
    p_mpa = psia_to_mpa(p_psia)
    sat = IAPWS97(P=p_mpa, x=1)
    tsat_f = (sat.T - K_OFFSET) * 9 / 5 + 32
    # subcooled liquid well below saturation
    for dt in [-150, -50, -10]:
        t_f = max(35, tsat_f + dt)
        t_k = f_to_k(t_f)
        st = IAPWS97(T=t_k, P=p_mpa)
        cases.append({"kind": "TP", "T": t_k, "P": p_mpa,
                      "h": st.h, "s": st.s, "v": st.v})
    # superheated well above saturation
    for dsh in [1, 25, 100, 300, 500]:
        t_k = f_to_k(tsat_f + dsh)
        st = IAPWS97(T=t_k, P=p_mpa)
        cases.append({"kind": "TP", "T": t_k, "P": p_mpa,
                      "h": st.h, "s": st.s, "v": st.v})

# --- Px: saturation dome at various qualities
for p_psia in pressures_psia:
    p_mpa = psia_to_mpa(p_psia)
    for x in [0.0, 0.25, 0.5, 0.75, 1.0]:
        st = IAPWS97(P=p_mpa, x=x)
        cases.append({"kind": "Px", "P": p_mpa, "x": x,
                      "T": st.T, "h": st.h, "s": st.s, "v": st.v})

# --- Ph and Ps: feed back h/s from known TP and Px states (covers
# subcooled liquid, superheated vapor, and two-phase wet steam -- exactly
# what Turbine.h_out_isentropic and SteamStream(P=.., h=..) hit in practice)
for p_psia in pressures_psia:
    p_mpa = psia_to_mpa(p_psia)
    sat = IAPWS97(P=p_mpa, x=1)
    tsat_f = (sat.T - K_OFFSET) * 9 / 5 + 32
    probe_temps_f = [max(35, tsat_f - 100), tsat_f, tsat_f + 5, tsat_f + 150, tsat_f + 400]
    probe_x = [0.2, 0.6, 0.9]
    for t_f in probe_temps_f:
        st = IAPWS97(T=f_to_k(t_f), P=p_mpa)
        cases.append({"kind": "Ph", "P": p_mpa, "h": st.h,
                      "T": st.T, "s": st.s, "v": st.v})
        cases.append({"kind": "Ps", "P": p_mpa, "s": st.s,
                      "T": st.T, "h": st.h, "v": st.v})
    for x in probe_x:
        st = IAPWS97(P=p_mpa, x=x)
        cases.append({"kind": "Ph", "P": p_mpa, "h": st.h,
                      "T": st.T, "s": st.s, "v": st.v, "x_expected": x})
        cases.append({"kind": "Ps", "P": p_mpa, "s": st.s,
                      "T": st.T, "h": st.h, "v": st.v, "x_expected": x})

with open("web/dev/reference.json", "w") as f:
    json.dump(cases, f, indent=1)

print(f"Wrote {len(cases)} reference cases to web/dev/reference.json")
