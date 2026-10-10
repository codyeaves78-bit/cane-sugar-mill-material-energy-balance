"""LMTD graph for the WaterCooler class: how the driving force behaves and
where the 300 ft2 limit lands."""
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brentq
from water_cooler import WaterCooler

P = dict(T_ci=90, T_hi=205, gpm_h=75, psia_h=70, psia_c=70, U=250)
T_CO, T_HO = 130.0, 110.0
AREA = 300.0


def mk(T_co, T_ho):
    return WaterCooler(T_co=T_co, T_ho=T_ho, **P)


def safe(fn, *a):
    """Return fn(*a) or nan/inf when the state is outside the exchanger envelope."""
    try:
        return fn(*a)
    except Exception:
        return np.nan


lmtd_at = lambda T_co, T_ho: safe(lambda c, h: mk(c, h).lmtd, T_co, T_ho)
area_at = lambda T_co, T_ho: safe(lambda c, h: mk(c, h).heating_surface_ft2, T_co, T_ho)
duty_at = lambda T_co, T_ho: safe(lambda c, h: mk(c, h).duty_btu_hr, T_co, T_ho)

# terminal deltas for the design point
d1 = P["T_hi"] - T_CO
d2 = T_HO - P["T_ci"]
print(f"Design point  T_co={T_CO:.0f} F, T_ho={T_HO:.0f} F")
print(f"  delta_1 = T_hi - T_co = {d1:.1f} F")
print(f"  delta_2 = T_ho - T_ci = {d2:.1f} F")
print(f"  LMTD = {lmtd_at(T_CO, T_HO):.2f} F   (arithmetic mean would be {(d1+d2)/2:.2f} F)")


def max_T_ho(T_co, area=AREA):
    """Coolest hot-side outlet reachable within `area` ft2, cold outlet fixed."""
    f = lambda t: area_at(T_co, t) - area
    lo, hi = 91.0, 204.99          # IAPWS97 region 1 bound is 273.16 K = 32.00 F
    if f(lo) <= 0:
        return lo
    return brentq(f, lo, hi)


T_co_grid = np.linspace(95, 200, 300)
T_ho_grid = np.linspace(95, 200, 300)
CO, HO = np.meshgrid(T_co_grid, T_ho_grid)

LMTD = np.vectorize(lmtd_at)(CO, HO)
AREA_M = np.vectorize(area_at)(CO, HO)
# invalid where the exchanger is infeasible (countercurrent deltas must be > 0)
BAD = ~np.isfinite(LMTD)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))

# ---- left: LMTD curves, one per hot-side outlet ----
for h in (100, 110, 120, 130, 150):
    y = np.array([lmtd_at(t, h) for t in T_co_grid])
    ax1.plot(T_co_grid, y, lw=2, label=f"T_ho = {h} F")
    d = lmtd_at(T_CO, h)
    if np.isfinite(d):
        ax1.plot(T_CO, d, "o", color=f"C{(h-100)//10}", ms=8, mec="k", mew=1)
ax1.axvline(T_CO, ls=":", color="k", lw=1.2)
ax1.text(T_CO + 1, ax1.get_ylim()[1] * 0.95, "design T_co = 130 F",
         rotation=90, va="top", fontsize=8)
ax1.set_xlabel("Cold water outlet, T_co (°F)")
ax1.set_ylabel("LMTD (°F)")
ax1.set_title("LMTD vs cold water outlet temperature\n(countercurrent, T_hi = 205 F, T_ci = 90 F)")
ax1.grid(alpha=.3)
ax1.legend(title="hot water outlet", loc="best")

# ---- right: LMTD field with the 300 ft2 limit overlaid ----
Lm = np.ma.masked_where(BAD, LMTD)
cf = ax2.contourf(CO, HO, Lm, levels=40, cmap="viridis")
ax2.contour(CO, HO, np.ma.masked_where(BAD, AREA_M), levels=[AREA],
            colors="white", linewidths=2.5, linestyles="--")
ax2.plot([], [], "w--", lw=2.5, label=f"{AREA:.0f} ft² limit")
ax2.plot(T_CO, T_HO, "*", color="red", ms=18, mec="k", mew=0.8, label="design point")

# pinch lines: countercurrent needs T_co < T_hi and T_ho > T_ci
ax2.axvline(P["T_hi"], color="w", lw=1, alpha=.6)
ax2.axhline(P["T_ci"], color="w", lw=1, alpha=.6)
ax2.text(P["T_hi"] - 1, 195, "T_co = T_hi (pinch)", rotation=90,
         va="top", ha="right", color="w", fontsize=8)
ax2.text(196, P["T_ci"] + 2, "T_ho = T_ci (pinch)", va="bottom", ha="right",
         color="w", fontsize=8)

# the 300 ft2 limit at the design cold outlet
x_lim = np.linspace(95, 200, 200)
y_lim = np.array([max_T_ho(x) for x in x_lim])
ax2.plot(x_lim, y_lim, color="red", lw=2.5, label="coolest T_ho @ 300 ft²")
ax2.plot(T_CO, max_T_ho(T_CO), "o", color="red", ms=9, mec="k", mew=1)

ax2.set_xlabel("Cold water outlet, T_co (°F)")
ax2.set_ylabel("Hot water outlet, T_ho (°F)")
ax2.set_title("LMTD field (°F) with the 300 ft² feasibility limit")
ax2.legend(loc="lower right", fontsize=9)
fig.colorbar(cf, ax=ax2, label="LMTD (°F)")

fig.suptitle(f"Water cooler LMTD — 75 gpm hot, 205→110 F, 70 psia, "
             f"U = {P['U']:.0f} BTU/(ft²·h·°F)", fontsize=12)
fig.tight_layout()
plt.show()
