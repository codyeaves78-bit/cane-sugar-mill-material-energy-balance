import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brentq
from water_cooler import WaterCooler

P = dict(T_ci=90, T_hi=205, gpm_h=75, psia_h=70, psia_c=70, U=250)
T_HO = 110
AREA = 300.0

def mk(T_co, T_ho=T_HO):
    return WaterCooler(T_co=T_co, T_ho=T_ho, **P)

def area_at(T_co, T_ho):
    try:
        return mk(T_co, T_ho).heating_surface_ft2
    except Exception:
        return np.inf

def gpm_at(T_co, T_ho):
    try:
        return mk(T_co, T_ho).gpm_c
    except Exception:
        return np.nan

def max_T_ho(T_co, area=AREA):
    """Hottest-side outlet reachable within `area` ft2 (cold outlet fixed)."""
    f = lambda t: area_at(T_co, t) - area
    lo, hi = 91.0, 204.99          # IAPWS97 region 1 bound is 273.16 K = 32.00 F
    if f(lo) <= 0:                 # even 91 F outlet needs more than `area`
        return lo
    return brentq(f, lo, hi)

T_co = np.arange(95, 200.1, 1.0)
area = np.array([area_at(t, T_HO) for t in T_co])
gpm  = np.array([gpm_at(t, T_HO) for t in T_co])
tho  = np.array([max_T_ho(t) for t in T_co])

# ---------- table ----------
base = mk(130)
rows = [("Cold water in, T_ci", "90.0", "F"),
        ("Cold water out, T_co", "130.0", "F"),
        ("Hot water in, T_hi", "205.0", "F"),
        ("Hot water out, T_ho", "110.0", "F"),
        ("Hot water flow", "75.0", "US gal/min"),
        ("Hot mass flow", f"{base.lb_hr_h:,.0f}", "lb/hr"),
        ("Heat duty", f"{base.duty_btu_hr:,.0f}", "BTU/hr"),
        ("Countercurrent LMTD", f"{base.lmtd:,.1f}", "F"),
        ("Cold water flow", f"{base.gpm_c:,.1f}", "US gal/min"),
        ("Cold mass flow", f"{base.lb_hr_c:,.0f}", "lb/hr"),
        ("Surface REQUIRED", f"{base.heating_surface_ft2:,.1f}", "ft2"),
        ("Surface AVAILABLE", f"{AREA:,.0f}", "ft2"),
        ("Shortfall", f"{base.heating_surface_ft2 - AREA:,.1f}", "ft2")]
w = max(len(r[0]) for r in rows)
print(f"{'Property':<{w}}  {'Value':>12}  Units")
print("-"*(w+22))
for n,v,u in rows: print(f"{n:<{w}}  {v:>12}  {u}")

lim = mk(130, max_T_ho(130))
print(f"\nWith 300 ft2: best hot outlet = {max_T_ho(130):.1f} F "
      f"(vs 110 F target), duty {lim.duty_btu_hr:,.0f} BTU/hr, cold water {lim.gpm_c:,.1f} gpm")

# ---------- graph ----------
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 9), sharex=True,
                              gridspec_kw=dict(height_ratios=[2, 1]))
ax.plot(T_co, area, lw=2, color="tab:red", label="Surface required (ft$^2$)")
ax.axhline(AREA, ls="--", color="k", lw=1.5, label=f"Available = {AREA:.0f} ft$^2$")
ax.axvline(130, ls=":", color="tab:blue", lw=1.5, label="Design point T_co = 130 F")
ax.plot(130, base.heating_surface_ft2, "o", color="tab:blue", ms=7)
ax.set_ylabel("Surface required (ft$^2$)")
ax.set_ylim(0, max(np.nanmax(area), AREA) * 1.1)
ax.grid(alpha=.3); ax.legend(loc="best")

axb = ax.twinx()
axb.plot(T_co, gpm, lw=2, color="tab:green", label="Cold water flow (gpm)")
axb.plot(130, base.gpm_c, "o", color="tab:green", ms=7)
axb.set_ylabel("Cold water flow (US gal/min)", color="tab:green")
axb.tick_params(axis="y", labelcolor="tab:green")
ax.set_title("Water cooler (75 gpm hot, 205$\\to$110 F) vs cold water outlet temperature\n"
             f"U = {P['U']:.0f} BTU/(ft$^2$·h·F), 70 psia both sides", fontsize=11)

ax2.plot(T_co, tho, lw=2, color="tab:purple", label="Best achievable T_ho @ 300 ft$^2$")
ax2.axhline(T_HO, ls="--", color="k", lw=1.5, label="Target T_ho = 110 F")
ax2.plot(130, max_T_ho(130), "o", color="tab:purple", ms=7)
ax2.set_xlabel("Cold water outlet temperature, T_co (F)")
ax2.set_ylabel("Hot outlet, T_ho (F)")
ax2.grid(alpha=.3); ax2.legend(loc="best")

fig.tight_layout()
plt.show()
