# Cane Sugar Factory Material and Energy Balance (Python OOP) — User Guide

Each class can stand alone and run calculations, provided you've cloned the repo and installed the requirements.

The general import format is `from XXX import XXX` — the filename and class name are usually identical:

```python
from SugarStream import SugarStream
```

There are some exceptions, where the class name differs from the filename:

```python
from SteamStream import EvaporatorSteam
```

Until the worked examples are finished, the best reference for everything is `main.py`.

---

## Foundations

Four classes make up the foundation everything else is built on: `SugarStream` and `SteamStream`/`EvaporatorSteam` for streams, and `Massecuite` for pan work. Learn these and the equipment classes read easily, since they're mostly assemblies of streams.

- **`SugarStream`** — any water–sugar–non-sugar mixture (juice, syrup, molasses, massecuite, magma).
- **`SteamStream`** — high-accuracy steam/water, wraps IAPWS97. Use when you want precision.
- **`EvaporatorSteam`** — fast steam properties from correlations. Use for trial-and-error loops.
- **`Massecuite`** — boiling-point rise, crystal content, and temperature solves for vacuum pans and crystallizers.

---

## SugarStream

`SugarStream` covers every water–sugar–non-sugar mixture in the factory: juice, syrup, molasses, massecuite, and magma. There is a dedicated `Massecuite` class for pan material and energy balances, but `SugarStream` gives you the basic properties engineers typically look for.

```python
>>> from SugarStream import SugarStream
>>> my_stream = SugarStream(brix=14, purity=90, flow_lb_per_hr=100, temp_deg_F=225, pressure_psia=50, level_ft=2)
>>> my_stream.display_properties()
stream_id: 2.00
brix: 14.00
purity: 90.00
flow_lb_per_hr: 100.00
temp_deg_F: 225.00
pressure_psia: 50.00
level_ft: 2.00
pol: 12.60
boiling_point_elevation_deg_F: 1.69
cp_btu_per_lb_deg_F: 0.92
specific_gravity: 1.05
cu_ft_hr: 1.52
latent_heat_btu_per_lb: 924.15
vapor_saturation_temp_deg_F: 280.98
solids_flow: 14.00
pol_flow: 12.60
```

You can change a property, such as brix, and the dependent properties recalculate:

```python
>>> my_stream.brix = 95
>>> my_stream.display_properties()
stream_id: 2.00
brix: 95.00
purity: 90.00
flow_lb_per_hr: 100.00
temp_deg_F: 225.00
pressure_psia: 50.00
level_ft: 2.00
pol: 85.50
boiling_point_elevation_deg_F: 82.07
cp_btu_per_lb_deg_F: 0.46
specific_gravity: 1.52
cu_ft_hr: 1.06
latent_heat_btu_per_lb: 924.15
vapor_saturation_temp_deg_F: 280.98
solids_flow: 95.00
pol_flow: 85.50
```

Note how the dependent properties changed — `pol`, `solids_flow`, `pol_flow`, and others. Keep that in mind when running your own calculations.

You can also return the properties as a dictionary:

```python
>>> my_stream.brix = 65  # note that I changed brix here
>>> my_stream.properties()
{'stream_id': 2, 'brix': 65, 'purity': 90, 'flow_lb_per_hr': 100, 'temp_deg_F': 225, 'pressure_psia': 50, 'level_ft': 2, 'pol': 58.5, 'boiling_point_elevation_deg_F': 8.923810142857143, 'cp_btu_per_lb_deg_F': 0.62876, 'specific_gravity': 1.3158810906176885, 'cu_ft_hr': 1.2178639194608702, 'latent_heat_btu_per_lb': np.float64(924.1472739021877), 'vapor_saturation_temp_deg_F': np.float64(280.9818423397531), 'solids_flow': 65.0, 'pol_flow': 58.5}
```

### Helper methods

Beyond reading and setting properties, `SugarStream` has a few methods that handle common factory transformations.

**`evaporate(new_brix, new_temp)`** — transforms the stream in place to a new brix, conserving solids and recomputing the flow. Handy for turning clarified juice into syrup for pan-floor calcs. Purity is unchanged (evaporation removes only water):

```python
>>> cj = SugarStream(brix=14, purity=90, flow_lb_per_hr=1_500_000, temp_deg_F=210)
>>> cj.evaporate(new_brix=65, new_temp=140)
>>> repr(cj)
'SugarStream(brix=65.00, purity=90.00, flow=323,076.92 lb/hr, temp=140.00°F, pressure=14.70 psia, level=0.0 ft)'
>>> cj.solids_flow          # solids conserved: 14% of 1,500,000 = 210,000
210000.0
```

**`copy(stream, **overrides)`** — a classmethod that clones a stream, optionally overriding any parameter. Useful for branching a stream without disturbing the original:

```python
>>> syrup2 = SugarStream.copy(cj, brix=68, purity=88)
>>> repr(syrup2)
'SugarStream(brix=68.00, purity=88.00, flow=323,076.92 lb/hr, temp=140.00°F, pressure=14.70 psia, level=0.0 ft)'
```

**`current_temp_to_bpe_plus_vapor_temp()`** — sets the stream's temperature to its vapor saturation temperature plus boiling-point elevation, i.e. the temperature it would actually boil at given its pressure and brix. Convenient inside evaporator calculations:

```python
>>> v = SugarStream(brix=60, purity=85, flow_lb_per_hr=100_000, pressure_psia=10, level_ft=1)
>>> v.current_temp_to_bpe_plus_vapor_temp()
>>> round(v.temp_deg_F, 2)   # sat 193.16 °F + bpe 7.70 °F
200.86
```

---

## SteamStream and EvaporatorSteam

Two steam classes, for two different needs. `SteamStream` wraps IAPWS97 for accuracy; `EvaporatorSteam` uses fast correlations for speed inside iterative loops. Pick based on whether you're after precision or throughput.

### SteamStream

`SteamStream` is a powerful, highly accurate class that wraps the IAPWS97 object from `iapws` in unit conversions, so you can use it the same way you'd use IAPWS97 directly — but in US customary units. Give it any two inputs that IAPWS97 accepts:

```python
>>> from SteamStream import SteamStream
>>> my_steam = SteamStream(T=350, P=50)  # any 2 inputs that work with IAPWS97 work here
>>> my_steam.properties()
{'stream_id': 1,
 'flow_lb_per_hr': 0,
 'T': 349.9999999999999,
 'P': 50.0,
 'h': np.float64(1210.2039776365916),
 's': np.float64(1.705277415909871),
 'x': 1,
 'v': np.float64(9.427310020194167),
 'rho': np.float64(0.10607479735554552),
 'h_fg': np.float64(924.0066546909492),
 'is_superheated': 'YES! Steam is superheated. T=350.00 °F > saturation temp 280.99 °F at P=50.00 psia.'}
```

`properties()` gives you a dictionary to do what you wish with. For a cleaner display — including a units legend — use `display_properties()`:

```python
>>> my_steam.display_properties()
Units: T(°F), P(psia), h(BTU/lb), s(BTU/lb·°R), v(ft³/lb), rho(lb/ft³), h_fg(BTU/lb)
stream_id: 1.00
flow_lb_per_hr: 0.00
T: 350.00
P: 50.00
h: 1,210.20
s: 1.71
x: 1.00
v: 9.43
rho: 0.11
h_fg: 924.01
is_superheated: YES! Steam is superheated. T=350.00 °F > saturation temp 280.99 °F at P=50.00 psia.
```

You can specify a flow when constructing the object:

```python
>>> my_other_steam = SteamStream(x=1, P=500, flow_lb_per_hr=1000)
>>> my_other_steam.display_properties()
Units: T(°F), P(psia), h(BTU/lb), s(BTU/lb·°R), v(ft³/lb), rho(lb/ft³), h_fg(BTU/lb)
stream_id: 2.00
flow_lb_per_hr: 1,000.00
T: 467.05
P: 500.00
h: 1,205.02
s: 1.46
x: 1.00
v: 0.93
rho: 1.08
h_fg: 755.48
is_superheated: NO! Steam is not superheated. T=467.05 °F <= saturation temp 467.05 °F at P=500.00 psia.
```

Flow can be set directly:

```python
>>> my_other_steam.flow_lb_per_hr = 2000
>>> my_other_steam.display_properties()
Units: T(°F), P(psia), h(BTU/lb), s(BTU/lb·°R), v(ft³/lb), rho(lb/ft³), h_fg(BTU/lb)
stream_id: 2.00
flow_lb_per_hr: 2,000.00
T: 467.05
P: 500.00
h: 1,205.02
s: 1.46
x: 1.00
v: 0.93
rho: 1.08
h_fg: 755.48
is_superheated: NO! Steam is not superheated. T=467.05 °F <= saturation temp 467.05 °F at P=500.00 psia.
```

The state properties, however, can't be set directly — use `update()` with two arguments instead. The steam state is solved from two independent properties via IAPWS97, so changing one means re-solving with a fresh pair. Flow is just a multiplier on that state, which is why it can be assigned on its own:

```python
>>> my_other_steam.update(T=750, P=550)
>>> my_other_steam.display_properties()
Units: T(°F), P(psia), h(BTU/lb), s(BTU/lb·°R), v(ft³/lb), rho(lb/ft³), h_fg(BTU/lb)
stream_id: 2.00
flow_lb_per_hr: 2,000.00
T: 750.00
P: 550.00
h: 1,382.37
s: 1.62
x: 1.00
v: 1.24
rho: 0.81
h_fg: 743.61
is_superheated: YES! Steam is superheated. T=750.00 °F > saturation temp 476.98 °F at P=550.00 psia.
```

### EvaporatorSteam

`EvaporatorSteam` is the fast counterpart to `SteamStream`. Instead of IAPWS97, it uses the pressure correlations from `sugar_stream_properties.py` for saturation temperature and latent heat. It's built for evaporator trial-and-error calculations where a full IAPWS97 solve on every iteration would be wasteful — the accuracy tradeoff is small, and it's valid for roughly 1–60 psia.

It takes a pressure and an optional flow:

```python
>>> from SteamStream import EvaporatorSteam
>>> evap = EvaporatorSteam(P_psia=30, flow_lb_per_hr=1000)
>>> evap.display_properties()
Units: T(°F), P(psia), h_fg(BTU/lb)
P_psia: 30.00
flow_lb_per_hr: 1,000.00
sat_temp_deg_F: 250.31
h_fg: 945.27
```

Pressure can be changed directly, and the saturation temperature and latent heat follow:

```python
>>> evap.P_psia = 8
>>> evap.display_properties()
Units: T(°F), P(psia), h_fg(BTU/lb)
P_psia: 8.00
flow_lb_per_hr: 1,000.00
sat_temp_deg_F: 182.80
h_fg: 987.91
```

Like the other classes, it returns a dictionary via `properties()`:

```python
>>> evap.properties()
{'P_psia': 8, 'flow_lb_per_hr': 1000, 'sat_temp_deg_F': 182.79906858782903, 'h_fg': 987.9105787358312}
```

**When to use which:** reach for `SteamStream` when you need superheat, entropy, or high accuracy, or when working with boiler/turbine steam. Reach for `EvaporatorSteam` when you're iterating a multiple-effect evaporator and only need saturation temperature and latent heat at low pressures — it's dramatically faster per call.

---

## Massecuite

`Massecuite` handles the material and energy balance for a massecuite in a vacuum pan or crystallizer: boiling-point rise (BPR), crystal content, mother-liquor properties, and the temperature solve. The BPR regression is sourced from Birkett fig. 12.14, as presented in his Nicholls class notes; below 60 mother-liquor purity is extrapolated, so treat low-purity results with caution.

It runs in one of **two modes**, and you must give exactly one of `supersaturation` or `temp_F`:

- **Boiling mode** (`supersaturation` given) — the massecuite is boiling in a pan. Its temperature is solved from the vapor-space vacuum, the static head, and the BPR regression. All boiling properties apply (water boiling point and BPR at both surface and head). Requires `head_ft`.
- **Set-temperature mode** (`temp_F` given) — the massecuite is off-boiling in a crystallizer, reheater, or in transport, and its temperature is imposed by heat exchange. `massecuite_temp` returns your `temp_F` directly; the boiling-solve properties are unavailable, since BPR-based supersaturation only means something at boiling equilibrium.

### Boiling mode

```python
>>> from Massecuite import Massecuite
>>> masse = Massecuite(ml_purity=70, masse_purity=90, masse_brix=92,
...                    inches_vacuum=23.5, supersaturation=1.2, head_ft=2,
...                    flow_lb_hr=500_000)
>>> masse.display_properties()
Units: T(°F), BPR(°F), density(lb/ft³), flow(lb/hr), purity/brix/yield(%)
  ml_purity                    : 70.000
  masse_purity                 : 90.000
  masse_brix                   : 92.000
  crystal_content_pct          : 61.333
  mother_liquor_brix           : 79.310
  crystal_yield_pct_brix_pct   : 66.667
  density_lb_ft3               : 93.208
  massecuite_temp              : 181.263
  sat_bpr                      : 19.998
  inches_vacuum                : 23.500
  vapor_pressure_psia          : 3.154
  supersaturation              : 1.200
  head_ft                      : 2.000
  water_bp_surface             : 143.356
  massecuite_temp_surf         : 165.235
  bpr_at_surface               : 21.879
  water_bp_at_head             : 157.265
  bpr_at_head                  : 23.998
  flow_lb_hr                   : 500000.000
  solids_flow                  : 460000.000
  pol_flow                     : 414000.000
```

A few things worth understanding in that output:

- **Surface vs. head.** The pan reports two conditions. At the *surface* there's no liquid head, so the water boils lower and the massecuite sits cooler. At the *head* (here 2 ft down), static head raises the local pressure, the water boils hotter, and so does the massecuite. The `_surf` and `_at_head` properties let you see both.
- **`massecuite_temp`** is the head temperature — the meaningful one for the bulk of the massecuite.
- **Composition** (`crystal_content_pct`, `mother_liquor_brix`, `crystal_yield_pct_brix_pct`) comes straight from the purities and brix, independent of the temperature solve.
- **Flow properties** (`solids_flow`, `pol_flow`, `cu_ft_hr`) only appear when you pass `flow_lb_hr`.

The solves are cached — the iteration runs once per instance, on first access, then the results are reused.

### Set-temperature mode, and copy()

`copy()` clones a massecuite and lets you override inputs. Overriding `temp_F` switches the copy to set-temperature mode (dropping the old supersaturation); overriding `supersaturation` switches back. This models a massecuite leaving the pan and entering a crystallizer cleanly:

```python
>>> cryst = masse.copy(temp_F=120, ml_purity=64)
>>> cryst.display_properties()
Units: T(°F), BPR(°F), density(lb/ft³), flow(lb/hr), purity/brix/yield(%)
  ml_purity                    : 64.000
  masse_purity                 : 90.000
  masse_brix                   : 92.000
  crystal_content_pct          : 66.444
  mother_liquor_brix           : 76.159
  crystal_yield_pct_brix_pct   : 72.222
  density_lb_ft3               : 93.208
  massecuite_temp              : 120.000
  sat_bpr                      : 14.150
  flow_lb_hr                   : 500000.000
  solids_flow                  : 460000.000
  pol_flow                     : 414000.000
```

Notice the boiling-only rows (`vapor_pressure_psia`, `water_bp_surface`, `bpr_at_head`, and so on) are gone — in set-temperature mode those aren't defined, and reaching for them raises a clear error telling you to `copy(supersaturation=...)` if the massecuite is back in a pan. Because the copy runs back through the constructor, validation re-runs and it solves fresh, with no stale cached results carried over.

---

## Bagasse

`Bagasse` is a stream class like `SugarStream`, just for the fibrous solid leaving the last mill instead of a liquid. Give it a proximate analysis (moisture, brix, pol, ash — all as % of wet weight) and a flow, and it derives fiber content and gross calorific value (GCV):

```python
>>> from Bagasse import Bagasse
>>> b = Bagasse(
...     moisture_pct=49.0,
...     brix_pct=1.2,
...     pol_pct=0.8,
...     ash_pct=4.0,
...     flowrate_lb_hr=125_000,
... )
>>> b.neat_display()
========================================
           BAGASSE PROPERTIES
========================================
  Flowrate             125,000.00  lb/hr
----------------------------------------
  Fiber                     49.80  %
  Moisture                  49.00  %
  Brix                       1.20  %
  Pol                        0.80  %
  Ash                        4.00  %  (assumed part of fiber)
----------------------------------------
  GCV                     3945.18  BTU/lb
========================================
```

A couple of things worth knowing:

- **`fiber_pct`** is a calculated number, not a lab input: `100 - moisture_pct - brix_pct`. `pol_pct` and `ash_pct` aren't subtracted out — pol is treated as part of brix (dissolved solids), and ash is left inside the fiber fraction (hence the `(assumed part of fiber)` note on `neat_display()`). Note that in reality, I am not saying ash is literally a part of fiber, but something needed to be nested in something else to make the typical lab numbers work out (pol, moisture, last roll purity). I do not, nor do I know any LA mills that record ash % bagasse independent of the other values on the manufacturing report. 
- **`gcv`** is a moisture/ash/brix-penalized correlation — more moisture, ash, or entrained brix all pull the calorific value down from the bone-dry-fiber ceiling (`19605 - 196.05*M - 196.05*A - 31.14*B`, converted from kJ/kg to BTU/lb by the trailing `0.4299` factor).
- Unlike `SugarStream`, this class only ships `neat_display()` — there's no `properties()`/`display_properties()` dict export and no `__repr__`, so if you need the values programmatically, read the attributes/properties (`b.fiber_pct`, `b.gcv`, etc.) directly. This is because this stream is only meant to be used in the Boiler class, there is not much utility for it otherwise. 

---
# Equipment Classes

## JuiceHeaterShellTube

This class represents a heat exchanger. It was originally intended for shell-and-tube calculations (tube velocity, pressure drop, number of passes), but that scope was dropped as outside the project, though the name is still intact. Instead it does the basic heat-exchanger balance, `Q = U * A * LMTD`, and works for either type — plate or shell-and-tube.

With the stream classes above under your belt, `JuiceHeaterShellTube` is intuitive: hand it a cold `SugarStream` and a hot `SteamStream`, plus the design parameters. `steam_type` tags which steam source feeds the heater — `0` for exhaust, `1`–`4` for vapor bleeds V1 through V4.

```python
>>> from JuiceHeater import JuiceHeaterShellTube
>>> heater = JuiceHeaterShellTube(
...     cold_stream=SugarStream(brix=14, purity=90, temp_deg_F=90, pressure_psia=40, level_ft=0, flow_lb_per_hr=100),
...     hot_stream=SteamStream(x=1, P=30),
...     name="Juice Heater",
...     juice_out_temp_degF=220,
...     U_btu_per_ft2_degF=185,
...     installed_area_ft2=6000,
...     steam_type=0,   # 0 = exhaust, 1–4 = vapor bleeds V1–V4
... )
>>> heater.properties()
{'name': 'Juice Heater',
 'U': 185,
 'cold_stream': SugarStream(brix=14.00, purity=90.00, flow=100.00 lb/hr, temp=90.00°F, pressure=40.00 psia, level=0.0 ft),
 'hot_stream': SteamStream(T=250.30°F, P=30.00 psia, h=1164.14 BTU/lb, x=1),
 'juice_out_temp_degF': 220,
 'installed_area_ft2': 6000,
 'steam_type': 0,
 'juice_out': SugarStream(brix=14.00, purity=90.00, flow=100.00 lb/hr, temp=220.00°F, pressure=40.00 psia, level=0.0 ft),
 'cold_delta_T': 130,
 'Q_btu_per_hr': 11923.807999999999,
 'LMTD_degF': np.float64(78.03739510075035),
 'required_area_ft2': np.float64(0.8259247522678584),
 'steam_required_lb_per_hr': np.float64(12.614946467763332),
 'is_steam_hot_enough': 'YES'}
```

Please note that `steam_type` doesn't actually do anything within the heater class itself, but rather serves a more important role in `main.py` (or any full factory balance `.py` file): being able to work with the `Evaporator` and `EvaporatorSet` classes to automate the V1–V4 bleed quantities needed, rather than manually inputting bleed quantities. You can even wrap your balance in a loop to update the heater class steam pressure and feed that output back to the `EvaporatorSet`, but we'll cover that later.

From here on, some of the equipment objects are packaged with `neat_display()`, `to_excel()`, & `generate_pfd()`. 

```python
>>> heater.neat_display()
==============================================================
                JUICE HEATER  —  JUICE HEATER
==============================================================

  DESIGN PARAMETERS
--------------------------------------------------------------
  Overall HT Coeff. (U)                     185.0 BTU/ft²·°F
  Juice Outlet Temperature                          220.0 °F
  Installed Area                                   6,000 ft²

  INLET CONDITIONS
--------------------------------------------------------------
  Juice Inlet Temperature                            90.0 °F
  Juice Flow Rate                                  100 lb/hr
  Juice Brix                                        14.0 °Bx
  Juice Purity                                        90.0 %
  Steam Temperature                                 250.3 °F

  HEAT TRANSFER RESULTS
--------------------------------------------------------------
  Juice Temperature Rise (ΔT)                       130.0 °F
  LMTD                                               78.0 °F
  Heat Duty (Q)                                11,924 BTU/hr
  Required Area                                        1 ft²
  Steam Required                                    13 lb/hr
  Steam Hot Enough?                                      YES

==============================================================
```

`generate_pfd()` returns a matplotlib figure of the process flow diagram:

```python
>>> heater.generate_pfd()
<Figure size 1050x958 with 2 Axes>
```

<img width="1050" height="958" alt="Juice heater PFD" src="https://github.com/user-attachments/assets/ba3d8ef7-dcce-43cf-88d4-527ec2f58115" />

By default `generate_pfd()` has `show=True`, which opens a window — fine interactively, but in a script or headless environment pass `save_path="pfd.png"` (or set a non-interactive matplotlib backend) so it doesn't block.

`to_excel()` writes the results into a workbook:

```python
>>> from excel_export import new_workbook
>>> wb = new_workbook()
>>> heater.to_excel(wb)
>>> wb.save("juice_heater.xlsx")
>>> print("Saved juice_heater.xlsx")
Saved juice_heater.xlsx
```

The workbook is saved in the current working directory. Check out `JuiceHeater.py` and run it to see the workbook.

---

## Evaporator

`Evaporator` models a single Robert vessel in the evaporator station: a juice-side `SugarStream` coming in, a calandria-side `EvaporatorSteam` (or `SteamStream`) supplying the heat, and the vessel's area and vapor-space pressure. It solves how much water flashes/evaporates off the juice, what brix the juice leaves at, and how the calculated heat-transfer coefficient stacks up against a Dessin's-method estimate.

Unlike `JuiceHeaterShellTube`, the outlet streams aren't recomputed automatically on every access — call `solve()` once you're happy with the inputs, and it pushes the results into `juice_side_out` and `vapor_out`:

```python
>>> from SugarStream import SugarStream
>>> from SteamStream import EvaporatorSteam
>>> from Evaporator import Evaporator
>>> clear_juice = SugarStream(brix=14, purity=90, flow_lb_per_hr=1_000_000, temp_deg_F=225, pressure_psia=60, level_ft=0)
>>> exhaust_steam = EvaporatorSteam(P_psia=30, flow_lb_per_hr=100_000)
>>> evaporator = Evaporator(
...     juice_side_in=clear_juice,
...     calandria_side=exhaust_steam,
...     area_ft2=25_000,
...     liquid_level_ft=2,
...     dessin_coefficient=18000,
...     vapor_pressure_psia=25,
... )
>>> evaporator.solve()
>>> evaporator.display_properties()
Units: T(°F), P(psia), h_fg(BTU/lb)
juice_side_in: SugarStream(brix=14.00, purity=90.00, flow=1,000,000.00 lb/hr, temp=225.00°F, pressure=60.00 psia, level=0.0 ft)
calandria_side: EvaporatorSteam(P_psia=30.00, flow_lb_per_hr=100,000.00)
area_ft2: 25,000.00
dessin_coefficient: 18,000.00
vapor_pressure_psia: 25.00
liquid_level_ft: 2.00
juice_side_out: SugarStream(brix=15.27, purity=90.00, flow=916,932.68 lb/hr, temp=241.82°F, pressure=25.00 psia, level=2.0 ft)
vapor_out: EvaporatorSteam(P_psia=25.00, flow_lb_per_hr=83,067.32)
vapor_bleed: EvaporatorSteam(P_psia=25.00, flow_lb_per_hr=0.00)
heat_duty_btu_per_hr: 94,526,921.13
lbs_evaporated_per_hr: 83,083.82
heat_from_flash: -15,426,312.33
heat_available_for_evaporation: 79,100,608.81
brix_out: 15.27
delta_T_juice_steam: 8.50
dessin_U: 539.21
heat_xfer_U: 445.04
U_ratio: 0.83
bpe_juice: 1.77
vapor_temperature: 240.05
condensate_out: 100,000.00

 Juice In details: 
 ...
 Material and Energy Balance

Entering: 100,000.00 lb/hr * 945.27 BTU/lb = 94,526,921.13 BTU/hr
Plus: 1,000,000.00 lb/hr * 0.92 BTU/lb * (-16.82°F) = -15,426,312.33 BTU/hr
Available for Evaporation: 94,526,921.13 + -15,426,312.33 = 79,100,608.81 BTU/hr
```

A few things worth knowing:

- **`heat_duty_btu_per_hr`** is just calandria steam flow × its latent heat.
- **`heat_from_flash`** accounts for the juice entering above (or below) the temperature it settles at on the outlet side. It's negative in this example because the juice is actually *heating up* (225°F in → 241.82°F out, since the outlet is pinned to the lower vapor-space pressure's saturation point), so it subtracts from the heat available for evaporation rather than adding to it — watch the sign, don't assume it's always a bonus.
- **`brix_out`** and `juice_side_out` are solved from the lbs evaporated, not assumed — change an input (steam flow, area, vapor pressure) and call `solve()` again to update them; nothing recalculates until you do.
- **`U_ratio`** (`heat_xfer_U / dessin_U`) is the sanity check on vessel performance: near 1.0 says the calculated coefficient matches what Dessin's correlation expects for this brix and ΔT; well below 1.0 (0.83 here) flags scaling, fouling, or an area/duty mismatch worth a second look.
- **`vapor_bleed`** lets you pull a bleed stream off this effect (e.g. to feed a `JuiceHeaterShellTube`), but setting it doesn't touch the balance by itself — `EvaporatorSet` is what nets the bleed out of `lbs_evaporated_per_hr` before forwarding vapor to the next effect. Set it directly and it's on you to account for it downstream.

`Evaporator` has no `neat_display()` — `display_properties()` (above) is the full report, including both streams and the balance walk-through. Multiple `Evaporator` instances get chained by `EvaporatorSet` / `multi_effect_solver_vers_2` for the full multi-effect station; see `main.py` for that pattern.
---

## Pan

`Pan` runs the full material and energy balance for a vacuum pan — one or more feed `SugarStream`s in, a boiling massecuite out, sized against a calandria and vapor-space condition. It builds its own internal `Massecuite` from the feeds, so you don't hand it one directly.

```python
>>> from SugarStream import SugarStream
>>> from Pan import Pan
>>> syrup   = SugarStream(brix=80, purity=88, flow_lb_per_hr=250_000, temp_deg_F=144, pressure_psia=14.7, level_ft=0)
>>> footing = SugarStream(brix=88, purity=92, flow_lb_per_hr=50_000, temp_deg_F=150, pressure_psia=14.7, level_ft=0)
>>> pan = Pan(
...     feed_streams=[syrup, footing],
...     heating_surface_ft2=22_000,
...     inches_vacuum=26.5,
...     supersaturation=1.2,
...     head_ft=2,
...     masse_brix=96,
...     ml_purity=70,
...     calandria_pressure_psia=21.696,   # V1 steam (7 psig)
...     heat_loss_factor=0.05,
... )
```

Note what you give it and what it derives:

- **`ml_purity`** (mother liquor purity) is a direct input — pull it from lab analysis or process knowledge.
- **`masse_purity`** is *not* an input. It's a property, derived live from the pol/solids balance across `feed_streams`: `Σ(flow×purity×brix) / Σ(flow×brix)`. Add, remove, or reweight feed streams and it updates automatically.
- **`calandria_pressure_psia`** drives `calandria_T_sat_F` and `h_fg_calandria` live through an internal `EvaporatorSteam` — change the attribute after construction (e.g. once you know the actual measured header pressure) and every heat-transfer result downstream recalculates, no re-instantiation needed. `pan.neat_display()` below shows this in the "single-pass U refinement" idea from `Pan.py`'s own `__main__` block.

`pan.neat_display()`:

```
===========================================================
  Pan  |  21.70 psia steam  |  22,000 ft²  |  26.5 inHg vacuum
===========================================================

  -------------------------------------------------------
  FEED
  -------------------------------------------------------
  Total feed flow                          300,000.0  lb/hr
  Feed solids                              244,000.0  lb/hr
  Feed temperature                             145.0  °F

  -------------------------------------------------------
  MASSECUITE
  -------------------------------------------------------
  Massecuite flow                          254,166.7  lb/hr
  Massecuite brix                               96.0  %
  Massecuite purity                             88.7  %
  Mother liquor purity                          70.0  %
  Crystal content                               59.9  %
  Mother liquor brix                            90.0  %

  -------------------------------------------------------
  EVAPORATION
  -------------------------------------------------------
  Water evaporated                          45,833.3  lb/hr
  Massecuite temp                              163.0  °F
  Vapor pressure                                 1.7  psia
  BPR at head                                   21.6  °F

  -------------------------------------------------------
  ENERGY BALANCE
  -------------------------------------------------------
  Sensible heat                          2,285,707.4  BTU/hr
  Evaporation heat                      46,979,010.1  BTU/hr
  Heat loss                              2,463,235.9  BTU/hr
  Total duty                            51,727,953.5  BTU/hr

  -------------------------------------------------------
  STEAM & HEAT TRANSFER
  -------------------------------------------------------
  Calandria pressure                            21.7  psia
  Calandria T_sat                              232.3  °F
  h_fg calandria                               957.1  BTU/lb
  Steam flow                                54,046.5  lb/hr
  Steam/evaporation ratio                        1.2  lb/lb
  dT (calandria - masse)                        69.3  °F
  U (back-calc)                                 33.9  BTU/hr·ft²·°F

===========================================================
```

`U_btu_hr_ft2_F` is *back-calculated* (`Q / (A × ΔT)`), not looked up — it's a diagnostic on how the pan is actually performing given the current calandria pressure, not a design input. Update `calandria_pressure_psia` to the real header pressure and re-read it any time without touching anything else:

```python
>>> pan.calandria_pressure_psia = 20.5   # actual measured V1 header pressure
>>> pan.U_btu_hr_ft2_F
35.5   # up from 33.9 at the original 21.696 psia assumption
```

**One gotcha worth knowing before you rely on it:** `crys_yld_frac_brix` is computed once in `__init__` from `masse_purity` and `ml_purity` at that moment, and stored as a plain attribute — it does **not** recompute if you mutate a feed stream's brix or purity afterward, even though `masse_purity` itself is a live property and will show the new value. If you change feed composition after building the `Pan`, `crys_yld_frac_brix` is stale until you rebuild the `Pan` instance. `properties()`/`display_properties()` (a flat dict/printout of everything above, without the section headers) are also available if `neat_display()`'s formatting isn't what you want. That is because it is meant to be fed into one of the boiling schemes and it handles the rebuild. To handle this manually, simply press the up arrow key (in a terminal) until the prompt for your pan class reappears, from there adjust the parameters you want, then repeat the `neat_display()` method. If you customize your own Pan Floor balances, generally you will nest building of the Pan class in a loop for iterative solving, this will rebuild the Pan class automatically in python.

`Pan` has no `to_excel()` or `generate_pfd()`.

---

## Centrifugal

`Centrifugal` takes a massecuite off the pan (or crystallizer/reheater) and splits it into sugar and molasses — the SJM (Sugar/Juice/Molasses) purity balance. Hand it a `Massecuite` instance plus the flow reaching the centrifugal (`pan.massecuite_flow_lb_hr`, or the crystallizer/reheater's `massecuite_out` flow if it's gone through those first):

```python
>>> from Massecuite import Massecuite
>>> from Centrifugal import Centrifugal
>>> masse_A = Massecuite(ml_purity=70, masse_purity=90, masse_brix=92,
...                      inches_vacuum=23.5, supersaturation=1.2, head_ft=2)
>>> cent_A = Centrifugal(
...     massecuite=masse_A,
...     massecuite_flow_lb_hr=226_630,
...     target_molasses_brix=78.0,
...     purity_rise=1.1,   # molasses purity = ml_purity + rise = 71.1%
...     sugar_purity=99.5,
...     sugar_moisture=0.5,
... )
>>> cent_A.neat_display()
```

```
═══════════════════════════════════════════════════════════
  Centrifugal  |  J=90.0%  S=99.5%  M=71.1%
═══════════════════════════════════════════════════════════

  ───────────────────────────────────────────────────────
  MASSECUITE FEED
  ───────────────────────────────────────────────────────
  Massecuite flow                          226,630.0  lb/hr
  Massecuite solids                        208,499.6  lb/hr
  Massecuite brix                               92.0  %
  Massecuite purity (J)                         90.0  %
  Mother liquor purity                          70.0  %
  Pol in                                   187,649.6  lb/hr

  ───────────────────────────────────────────────────────
  SUGAR PRODUCT
  ───────────────────────────────────────────────────────
  Sugar solids (dry)                       138,755.0  lb/hr
  Sugar flow (wet)                         139,452.3  lb/hr
  Sugar brix                                    99.5  %
  Sugar purity (S)                              99.5  %
  Sugar pol %                                   99.0  %
  Sugar moisture                                 0.5  %
  Moisture lb/hr                               697.3  lb/hr
  Pol to sugar                             138,061.2  lb/hr

  ───────────────────────────────────────────────────────
  MOLASSES
  ───────────────────────────────────────────────────────
  Molasses flow                             89,416.1  lb/hr
  Molasses solids                           69,744.6  lb/hr
  Molasses brix                                 78.0  %
  Molasses purity (M)                           71.1  %
  Purity rise                                    1.1  %
  Pol to molasses                           49,588.4  lb/hr
  Molasses density                              11.6  lb/gal
  Molasses flow                                128.5  gal/min

  ───────────────────────────────────────────────────────
  WASH WATER & YIELD
  ───────────────────────────────────────────────────────
  Wash water required                        2,238.4  lb/hr
  Crystal yield (% brix)                        65.4  %
  Crystal yield (% masse)                       60.2  %

═══════════════════════════════════════════════════════════
```

Two things worth flagging before you trust the numbers:

- **`purity_rise` drives the whole molasses side, not a two-step crystal-loss model.** The module's own header comment describes a more elaborate SJM derivation — an "ideal split" at the mother-liquor purity, then a second pass where dissolved crystal (`crystal_loss_pct`) raises the molasses purity. That's *not* what's implemented: there's no `crystal_loss_pct` parameter or crystal-loss step in the code at all. What actually runs is a single-pass SJM balance where you specify `molasses_purity = ml_purity + purity_rise` directly — `purity_rise` is your one dial for "how much higher than mother-liquor purity does the molasses end up," lumping crystal loss, wash dilution, and everything else into one number you set from experience.
- **`target_molasses_brix` back-calculates wash water**, not the other way around — pick a target brix, and `wash_water_lb_hr` is solved to hit it. If the target is *higher* than the molasses would naturally sit at with zero wash water, `wash_water_lb_hr` raises a `ValueError` telling you to lower the target (you can't un-add water that's already there).

`molasses_stream` hands you a ready-made `SugarStream` for feeding straight into the next lower pan grade (e.g. A molasses → B pan feed):

```python
>>> next_grade_feed = cent_A.molasses_stream
```

`properties()` and `display_properties()` are also available for a flat dict/printout without the section headers. `Centrifugal` has no `to_excel()` or `generate_pfd()`.

---

## Crystallizer

`Crystallizer` and `Reheater` (below) share a module — both are non-contact water heat exchangers for low-grade (C) massecuite between the pan and the centrifugals, and both conserve massecuite mass flow (nothing mixes in or out, unlike the pan or centrifugal). `Crystallizer` cools the massecuite with cold water after it drops from the pan, driving further crystal growth as the mother liquor exhausts:

```python
>>> from Massecuite import Massecuite
>>> from Crystallizer_and_Reheater import Crystallizer, Reheater
>>> c_masse = Massecuite(ml_purity=33, masse_purity=54, masse_brix=95.5,
...                      inches_vacuum=26.5, supersaturation=1.2, head_ft=2)
>>> crys = Crystallizer(c_masse, 100_000,
...                     masse_temp_out_deg_F=120, ml_purity_out=30,
...                     water_temp_in_deg_F=85, water_temp_out_deg_F=105,
...                     name='C Crystallizer')
>>> crys.neat_display()
=== C Crystallizer ===
  Massecuite : 100,000 lb/hr, 173.0 → 120.0 °F
  ML purity  : 33.0 → 30.0 %   crystal content 29.9 → 32.7 %  (+2,810 lb/hr crystal)
  Duty       : 2,417,070 BTU/hr removed
  Cooling water: 120,854 lb/hr (242 gpm), 85 → 105 °F
```

A few things to know:

- **`massecuite_in` must already be a solved `Massecuite`** — boiling mode straight off a pan, or set-temperature mode from a prior unit. `masse_temp_in_deg_F` just reads `massecuite_in.massecuite_temp`, whichever mode produced it.
- **`ml_purity_out` is optional** — leave it `None` and the mother liquor purity carries through unchanged; set it lower to model the exhaustion (further crystal growth) that cooling actually causes, as in the example above (33 → 30).
- **The heat balance is sensible-only** — heat of crystallization is neglected as small, per the module's own comment. Don't expect it to reconcile against a rigorous crystallization-energy balance.
- **`massecuite_out`** is a *new* set-temperature-mode `Massecuite` (via `.copy()`), ready to feed the `Reheater` or `Centrifugal` directly — it doesn't mutate `massecuite_in`.
- Construction raises a `ValueError` immediately if `water_temp_out_deg_F <= water_temp_in_deg_F` — cooling water has to leave hotter than it enters, or the inputs are physically wrong.

`Crystallizer` has `properties()` and `neat_display()`, but no `display_properties()`, `to_excel()`, or `generate_pfd()`.

---

## Reheater

`Reheater` is `Crystallizer`'s mirror image: it warms the cooled, exhausted massecuite back up with hot water before the centrifugals, to cut viscosity for spinning. Hot water rather than steam avoids local overheating that would redissolve crystal, so mother liquor purity is assumed unchanged by default:

```python
>>> reheat = Reheater(crys.massecuite_out, 100_000,
...                   masse_temp_out_deg_F=130,
...                   water_temp_in_deg_F=150, water_temp_out_deg_F=135,
...                   name='C Reheater')
>>> reheat.neat_display()
=== C Reheater ===
  Massecuite : 100,000 lb/hr, 120.0 → 130.0 °F
  Duty       : 456,252 BTU/hr added
  Hot water  : 30,417 lb/hr (61 gpm), 150 → 135 °F

>>> reheat.massecuite_out
Massecuite(ml_purity=30, masse_purity=54, masse_brix=95.5, temp_F=130)
```

Same shape as `Crystallizer`, flipped:

- **`water_temp_in_deg_F` must exceed `water_temp_out_deg_F`** (hot water supply cooler than its return is backwards) — construction raises `ValueError` otherwise.
- **`ml_purity_out`** defaults to unchanged, same as `Crystallizer`; the class docstring's rationale is that reheating with hot water (rather than steam) avoids the local overheating that would redissolve crystal in the first place, which is why "unchanged" is the default rather than the exception. You can still pass a value slightly above the inlet purity if you want to model some redissolution happening anyway.
- **`massecuite_out`** feeds straight into `Centrifugal`'s `massecuite=` argument — see `crys.massecuite_out` → `reheat` → `reheat.massecuite_out` → `Centrifugal(...)` chained in `Crystallizer_and_Reheater.py`'s own `__main__` block.

Same method set as `Crystallizer`: `properties()` and `neat_display()`, no `display_properties()`, `to_excel()`, or `generate_pfd()`.

---

## Condenser

`Condenser` models a barometric condenser — the injection-water spray that condenses vapor pulled off the last evaporator effect or a vacuum pan, using cold water rather than a surface exchanger. Give it a vapor stream with a flow set (either `EvaporatorSteam` or `SteamStream` — it duck-types between them) and the injection water's supply temperature:

```python
>>> from SteamStream import EvaporatorSteam
>>> from Condenser import Condenser
>>> vapor = EvaporatorSteam(P_psia=14.696 - 26.5 * 0.491154, flow_lb_per_hr=50_000)  # 26.5 inHg vacuum
>>> cond = Condenser(vapor, water_inlet_temp_F=75, water_outlet_temp_drop_F=5)
>>> cond.neat_display()
Condenser Summary:
  Vapor Saturation Temp (°F): 119.68
  Vapor h_fg (BTU/lb): 1,025.00
  Vapor Flow (lb/hr): 50,000.00
  Heat Load (BTU/hr): 51,499,829.24
  Injection Water Inlet (°F): 75.00
  Water Outlet Temp (°F): 114.68
  Injection Water Flow (lb/hr): 1,297,773.94
  Total Outlet Flow (lb/hr): 1,347,773.94
```

Key assumption, straight from the module comment: **the outlet water/condensate mixture is assumed to leave at (vapor saturation temp − `water_outlet_temp_drop_F`)** — perfect mixing, no sub-cooling beyond that fixed approach. `water_outlet_temp_drop_F` defaults to 5°F and is *your* approach-temperature assumption, not something solved for.

`injection_water_flow_lb_hr` raises `ValueError` if the water inlet temperature is at or above the vapor's (drop-adjusted) saturation temperature — there's no physical solution if the injection water can't absorb the heat.

`Condenser` has `properties()`, `display_properties()`, and `neat_display()`.

---

## CoolingTower

`CoolingTower` is the leanest class in the project — a bare-bones evaporative cooling-tower balance with no `properties()`, `display_properties()`, `neat_display()`, or even a custom `__repr__`. Read its attributes and properties directly:

```python
>>> from CoolingTower import CoolingTower
>>> tower = CoolingTower(
...     hot_water_temp=105,
...     hot_water_lb_hr=1_500_000,
...     cool_water_temp=85,
...     percent_blowdown=3,
... )
>>> tower.blowdown_lb_hr
45000.0
>>> tower.evaporated
29100.0
>>> tower.cool_water_lb_hr
1425900.0
>>> tower.cool_water_gpm
2863.2530120481924
```

How the balance works, in order:

1. **`blowdown_lb_hr`** — `hot_water_lb_hr × percent_blowdown / 100`.
2. **`water_to_tower`** — hot return flow minus blowdown.
3. **`evaporated`** — heat rejected (`water_to_tower × (hot_water_temp − cool_water_temp)`, Cp assumed 1.0) divided by a flat **1,000 BTU/lb** latent heat approximation, noted directly in the code (`# about 1000 btu / lb evaporated`) rather than pulled from a steam table — a deliberately simple stand-in, not IAPWS-grade.
4. **`cool_water_lb_hr`** — what's left after evaporation losses (`water_to_tower − evaporated`) — this is the flow returning to the process, *not* `hot_water_lb_hr`; makeup water to replace blowdown and evaporation isn't modeled by this class at all.

For a fuller system model — makeup water, blended delivery temperature to multiple condensers — see `CoolingTowerSystem.py`, which wraps a `CoolingTower` instance internally (`self.tower`) rather than duplicating its math.

---

## Boiler

`Boiler` turns a `Bagasse` stream into a steam-availability number: given the bagasse's GCV, a thermal efficiency, and the boiler's operating pressure/superheat/feed-water temperature, it tells you how much steam that fuel can raise. It doesn't model combustion or drum internals — it's a fuel-to-steam energy balance, one `SteamStream` in (feed water) and one out (steam), scaled by GCV and efficiency.

```python
>>> from Boiler import Boiler
>>> from Bagasse import Bagasse
>>> b = Boiler(
...     bagasse=Bagasse(moisture_pct=49.0, brix_pct=3.2, pol_pct=1.8, ash_pct=4.0, flowrate_lb_hr=100_000),
...     efficiency=68,
...     pressure_psig=600,
...     deg_superheat=150,
...     feed_water_temp=230,
...     capacity=650_000,
...     name='Boiler 1',
... )
>>> b.neat_display()
==================================================
                BOILER — Boiler 1
==================================================
                --- Parameters ---
  Efficiency                     68.0  %
  Pressure                      600.0  psig  (614.696 psia)
  Feed Water Temp               230.0  °F
  Superheat                     150.0  °F above sat
--------------------------------------------------
                --- Feed Water ---
  Temperature                  230.00  °F
  Enthalpy                     199.63  BTU/lb
--------------------------------------------------
                --- Steam Out ---
  Temperature                  638.86  °F
  Enthalpy                    1313.31  BTU/lb
  Condition                Superheated
--------------------------------------------------
               --- Performance ---
  Heat to make 1 lb steam     1113.67  BTU/lb steam
  Steam/Bagasse Ratio           2.393  lb/lb
  Steam Available from Bagasse  239,255.0  lb/hr
Rated Steam Capacity: 650,000
==================================================
```

A few things worth knowing:

- **`feed_water_stream`** and **`steam_stream`** are `SteamStream` properties, not stored streams — they're rebuilt from `psia`/`feed_wat_temp`/`deg_sh` every time you read them, so changing pressure or superheat on the fly and re-reading them (or calling `neat_display()` again) picks up the new state with no manual resolve.
- **`deg_superheat=0`** (the default) gives you saturated steam (`x=1`); anything above 0 adds that many degrees above the saturation temperature at `psia`.
- **`steam_available_per_lb_bagasse`** is `bagasse.gcv * efficiency/100 / btu_for_1_lb` — GCV converted to usable heat by efficiency, divided by the enthalpy rise needed to make 1 lb of the boiler's steam. Multiply by the bagasse flow and you get `steam_availabe_lb_hr` (note the missing `l` — that's the actual attribute name, not a typo you're allowed to "fix" without checking every caller).
- **`capacity`** is purely informational — a rated-capacity number you pass in for the `neat_display()`/`to_excel()` footer; nothing in the class checks the computed steam availability against it.

`Boiler` has no `properties()`/`display_properties()` or `generate_pfd()` — `neat_display()` above is the full report. `to_excel()` writes parameters, the feed water/steam streams, the bagasse fuel breakdown, and performance onto their own sheet.

---

## Turbine

`Turbine` is an isentropic steam turbine with an efficiency correction, wrapping IAPWS97 directly (not `SteamStream`) for the isentropic expansion step so it can solve on entropy at the outlet pressure. Give it an inlet `SteamStream`, the exhaust (back) pressure, an isentropic efficiency, and the mechanical HP it needs to deliver — it back-solves the steam flow required to make that HP.

```python
>>> from SteamStream import SteamStream
>>> from Turbine import Turbine
>>> live_steam = SteamStream(T=750, P=600)
>>> turbine = Turbine(inlet_steam=live_steam, outlet_pressure_psia=30,
...                   isentropic_efficiency=0.75, hp_demand=5000, name="Turbo-Alternator")
>>> turbine.neat_display()
==============================================================
                 TURBINE  —  TURBO-ALTERNATOR
==============================================================
      |   psia    |  temp °F   | enthalpy BTU/lb  |  quality
------+-----------+------------+------------------+-----------
   IN |     600.0 |      750.0 |         1,379.77 | Superheat
  OUT |      30.0 |      264.4 |         1,171.42 | Superheat
==============================================================
Steam Rate: 12.22 lb/HP-hr  |  HP: 5,000  |  Flow: 61,077 lb/hr  |  Eff: 75.0%
Exhaust for Process: 61,529 lb/hr  |  Desuperheater Water: 452 lb/hr
==============================================================
```

The solve, in order: expand isentropically (`s_out = s_in`) to `outlet_pressure_psia` for `h_out_isentropic`, apply the efficiency correction for the actual `h_out_actual`, get `work_per_lb = h_in - h_out_actual`, then `steam_flow_lb_hr = hp_demand * 2545 / work_per_lb` (2545 BTU/hr per mechanical HP). `exhaust_steam` is the resulting `SteamStream` at `(outlet_pressure_psia, h_out_actual)`.

A few things worth knowing:

- **`isentropic_efficiency` is a fraction here (0–1), not a percent** — construction raises `ValueError` outside that range. This is the opposite convention from the turbine *group* classes below (`CanePrepTurbines`, `MillTurbines`, `AuxillaryTurbines`), which take efficiency as a percent (e.g. `50` for 50%) and divide by 100 before handing it to `Turbine` — don't double-convert if you're building `Turbine` objects directly.
- **`exhaust_steam.x` can land above, at, or below 1.0** — superheated, exactly saturated, or wet — depending on the pressure drop and efficiency. Always check `x` before assuming a condition; the class doesn't clamp it for you.
- **`exhaust_available`** is what's actually usable downstream, and it branches on that quality: exactly saturated (`x=1`) returns the flow as-is; **superheated** adds a `desuperheating_water_temp` (default 212°F) water injection to knock it down to saturation, and the *returned* flow includes that added water (452 lb/hr in the example above, on top of the 61,077 lb/hr turbine exhaust); **wet** (`x<1`) returns only the dry fraction (`exhaust_steam.flow_lb_per_hr * x`) — the moisture is treated as separated out before the flow reaches process equipment.
- **`steam_rate`** (lb steam/HP-hr) is the standard turbine performance metric — lower is better (less steam per unit of work).

`Turbine` has `properties()`, `display_properties()`, and `neat_display()`. No `to_excel()` or `generate_pfd()` on its own — those live one level up, on the turbine *group* classes (see Equipment Management Classes below), which wrap a list of `Turbine` instances and report them together.

---

## Deaerator

`Deaerator` is a straightforward energy and mass balance: incoming feedwater is heated to saturation at the deaerator's operating pressure by condensing live steam, with a percentage of that steam lost to atmospheric vent.

```python
>>> from Deaerator import Deaerator
>>> da = Deaerator(deaerator_psig=10, water_in_deg_F=205, water_in_lb_hr=800_000, vent_pct=1.0)
>>> da.display_properties()

===========================================================
  Deaerator  |  24.70 psia  |  T_sat = 239.4 degF
===========================================================

  ENTERING
  Feedwater flow                                  800,000.00  lb/hr
  Feedwater temperature                               205.00  degF
  Feedwater enthalpy                                  173.13  BTU/lb
  Steam flow (total)                               29,432.12  lb/hr
  Steam enthalpy                                    1,160.31  BTU/lb
  Steam h_fg                                          952.49  BTU/lb

  LEAVING
  Deaerated water flow                            829,137.80  lb/hr
  Water out temperature                               239.36  degF
  Water out enthalpy                                  207.82  BTU/lb
  Vent flow                                           294.32  lb/hr
  Vent pct                                              1.00  %

  Net (In - Out):                                    -0.0000  lb/hr
===========================================================
```

**`steam_flow_lb_hr`** is solved from the sensible heat needed to bring `water_in_lb_hr` up to saturation (`Q_sens = water_in × (h_sat − h_feedwater)`), divided by the steam's `h_fg`, then grossed up for vent loss: `steam_net / (1 − vent_pct/100)`. `water_out_flow_lb_hr` is everything that came in minus what left as vent — `water_in + steam_flow − vent_flow`.

`steam_in`, `water_in`, `water_out`, and `vent` each hand you a ready-made `SteamStream` (state + flow) if you want to wire the deaerator into a condensate/feedwater balance rather than reading the scalar properties. `Deaerator` has no `neat_display()` — `display_properties()` above is the full report — plus `generate_pfd()` and `to_excel()` (streams table, energy/mass balance, and the PFD on one sheet).

---

## PreEvaporator

`PreEvaporator` models a single-effect pre-evaporator the way `Evaporator` doesn't: here the **vapor bleed is the fixed, known input** (you've decided how much vapor you want to pull off for juice heaters or pans), and the class iterates to find the vapor-space pressure — and hence the juice's boiling temperature — that's consistent with the available heating surface and the Dessin U. It mirrors Birkett's pre-evaporator method, and its typical job is supplying `juice_in` to an `EvaporatorSet` after the bleed has already been taken.

```python
>>> from SugarStream import SugarStream
>>> from SteamStream import EvaporatorSteam
>>> from PreEvaporator import PreEvaporator
>>> juice = SugarStream(brix=12, purity=90, flow_lb_per_hr=1_000_000, temp_deg_F=225, pressure_psia=60, level_ft=0)
>>> steam = EvaporatorSteam(P_psia=34.7, flow_lb_per_hr=0)
>>> pre = PreEvaporator(juice_in=juice, supply_steam=steam, vapor_bleed_lb_per_hr=120_000,
...                     area_ft2=20_000, liquid_level_ft=2, dessin_coefficient=18000)
>>> pre.display_properties()
  Juice in:          500.000 tph @ 12.00 brix, 225.00 °F
  Juice out:         440.000 tph @ 13.64 brix, 247.28 °F
  Vapor bleed:       60.000 tph
  Vapor pressure:    27.6590 psia  (12.9630 psig)
  Vapor temp:        245.6976 °F
  Calandria temp:    258.7573 °F
  Exhaust required:  143,136.01 lb/hr  (71.568 tph)
  Heat duty:         134,488,503 BTU/hr
  Heating surface:   20,000 ft²
  U dessin:          585.8596 BTU/hr·ft²·°F
```

A few things worth knowing:

- **The juice-side mass balance is fixed at construction**, before any iteration: `juice_out_flow_lb_per_hr = juice_in.flow − vapor_bleed_lb_per_hr`, brix out from conserved solids. Only the *temperature* side (vapor pressure, calandria ΔT, exhaust steam demand) is solved iteratively.
- **`solve()` runs automatically in `__init__`** for a fixed 20 iterations, no convergence tolerance check — unlike `Evaporator`, where you call `.solve()` yourself. If you change an input afterward (area, bleed, supply steam), call `.solve()` again to re-converge.
- **`supply_steam.flow_lb_per_hr` gets overwritten** by the solve (`exhaust_required_lb_per_hr`) — whatever flow you passed in at construction is just a starting value.
- **`clean_condensate`** nets out flash loss on the fresh exhaust supply via `condensate_utils.flash_condensate()`, same convention used by `EvaporatorSet`/`JuiceHeatingStation`/the pan-floor classes.
- **`U_ratio`** (`U_calc / U_dessin`) reads ~1.0 by construction here, since the solve pins the calandria ΔT to make Dessin U and heat-transfer U agree — it's not an independent sanity check the way it is on `Evaporator`, where area and duty come from separate inputs.

`PreEvaporator` has no `neat_display()` — `display_properties()` above is the full report — plus `generate_pfd()` and `to_excel()`.

---

# Equipment Management Classes

The equipment classes above each model one physical unit. The classes in this section wire several of those units together into a station or an entire section of the factory: they build the individual `Pan`/`Centrifugal`/`Evaporator`/`Turbine`/`JuiceHeaterShellTube` objects internally (usually from *configuration templates* you hand in with feed streams left as placeholders), run whatever iteration the recycle streams require, and then report the whole assembly with one `neat_display()`/`to_excel()`/`generate_pfd()`. `main.py` is still the best single reference for how they all chain together into a full factory balance; `examples.py` shows a compact mill-floor run.

## MillFloor

`MillFloor` is the cane-milling-train material balance: cane and imbibition water in, mixed juice and bagasse out, plus a per-mill maceration table for pump sizing. Everything solves in `__init__` — no `solve()` call needed.

```python
>>> from MillFloor import MillFloor
>>> mill = MillFloor(
...     cane_tpd=17_000, cane_pol_pct=13.5, cane_fiber_pct=14.0,
...     imbibition_pct_on_cane=25.0, bagasse_pol_pct=1.8, last_roll_purity=72.0,
...     bagasse_moisture_pct=49.0, mix_juice_purity=88.0, number_of_mills=6, juice_temp_F=90.0,
... )
>>> mill
MillFloor(cane=17,000 TPD, pol=13.5%, fiber=14.0%, extraction=96.15%, mills=6)
>>> mill.mixed_juice_stream
SugarStream(brix=15.34, purity=88.00, flow=1,361,898.63 lb/hr, temp=90.00°F, pressure=14.70 psia, level=0.0 ft)
```

Key outputs: **`mixed_juice_stream`** (a `SugarStream`, ready to feed `Clarification`), **`bagasse_stream`** (a `Bagasse`, ready to feed `Boiler`), **`mill_extraction_pct`**, **`imbibition_gpm`**, and **`mill_balances`** — a list of per-mill dicts (bagasse in/out, maceration liquid in and its source, juice out and its destination) driven by `mill_1_fiber_rise_load_fraction`, the fraction of the total cane→bagasse fiber-% rise that Mill 1 absorbs in one step. Print that table on its own with `display_mill_balances()`:

```
Per-Mill Maceration Balance
------  ----------------  ----------------  ----------------------  ----------------  --------------------------
Mill    Bagasse In (TPD)  Liquid In (TPD)   Liquid In Source        Bagasse Out (TPD)  Juice Out (TPD) / Dest
------  ----------------  ----------------  ----------------------  ----------------  --------------------------
1       17,000.0          0.0               None                    9,127.5           7,872.5  ->  To process
2       9,127.5           7,130.7           Mill 3 maceration       7,788.0           8,470.3  ->  To process
3       7,788.0           6,134.1           Mill 4 maceration       6,791.3           7,130.7  ->  Mill 2 maceration
4       6,791.3           5,363.5           Mill 5 maceration       6,020.7           6,134.1  ->  Mill 3 maceration
5       6,020.7           4,750.0           Mill 6 maceration       5,407.2           5,363.5  ->  Mill 4 maceration
6       5,407.2           4,250.0           Imbibition              4,907.2           4,750.0  ->  Mill 5 maceration
------  ----------------  ----------------  ----------------------  ----------------  --------------------------
```

Note the counter-current logic in the "Source"/"Dest" columns: each mill's maceration liquid comes from the *next* mill down the train (imbibition water only enters at the last mill), and juice from mills 3+ feeds back as maceration to the mill *before* it — only mills 1 and 2's juice actually goes "To process." `balance_check` gives you a total/pol/brix/fiber/water in-vs-out reconciliation dict, mirroring the pattern used by `Clarification` below. `generate_pfd()` and `to_excel()` are also available.

---

## Clarification

`Clarification` runs the clarifier + rotary vacuum filter material balance for a single-clarifier station, taking `MillFloor`'s `mixed_juice_stream` straight in.

```python
>>> from Clarification import Clarification
>>> clar = Clarification(
...     mixed_juice_stream=mill.mixed_juice_stream, cane_tpd=mill.cane_tpd,
...     filter_wash_water_pct_on_cane=8.0, filter_cake_pct_on_cane=6.0, filter_cake_pol_pct=2.0,
...     clarified_juice_purity=90.0, limed_juice_hot_temp_f=220.0,
... )
>>> clar
Clarification(cane=17,000 TPD, CJ brix=14.53%, purity=90.0%, flow=1,393,081 lb/hr)
>>> clar.flash_vapor_pct
0.754
>>> clar.filter_cake_pol_lb_per_day
40800
```

The internal balance runs lime, milk-of-lime dilution, polymer/flocculant, rotary-filter wash water, flash-tank vapor loss (limed juice flashing down to 212°F before the clarifier), and the clarifier underflow — all as lb/hr streams stored in the **`streams`** dict, keyed by stream name, each with flow/brix/pol/purity/specific gravity/GPM/% on cane. **`clarified_juice_stream`** is the `SugarStream` output (feeds an `Evaporator`/`EvaporatorSet` next); **`limed_juice_cold_stream`** is exposed separately since it's the usual cold-side feed into `JuiceHeatingStation`. `balance_check` totals every "In"/"Out"-tagged stream in `streams` (flow, brix-lb/hr, pol-lb/hr) for a reconciliation check.

`neat_display()` prints the full stream table grouped by In/Out/Internal; `generate_pfd()` and `to_excel()` are also available (the Excel sheet includes a numbered stream table matching the PFD's tags).

---

## JuiceHeatingStation

`JuiceHeatingStation` arranges a group of `JuiceHeaterShellTube` units in **series** or **parallel** and solves the train — the heat-transfer math itself still lives entirely in `JuiceHeaterShellTube`; this class only wires the cold streams together (chained outlet→inlet for series, a flow split for parallel) and reports the whole station.

The `heaters` argument is a list of `JuiceHeaterShellTube` objects used purely as **configuration templates** — their `cold_stream` gets replaced internally; `hot_stream`, `juice_out_temp_degF`, `U`, `installed_area_ft2`, and `name` are kept:

```python
>>> from JuiceHeater import JuiceHeaterShellTube
>>> from JuiceHeatingStation import JuiceHeatingStation
>>> juice = SugarStream(brix=15, purity=88, flow_lb_per_hr=1_400_000, temp_deg_F=95, pressure_psia=14.7, level_ft=0)
>>> primary = JuiceHeaterShellTube(cold_stream=juice, hot_stream=SteamStream(x=1, P=19), steam_type=1,
...                                name='Primary Heaters', juice_out_temp_degF=180,
...                                U_btu_per_ft2_degF=220, installed_area_ft2=8000)
>>> secondary = JuiceHeaterShellTube(cold_stream=juice, hot_stream=SteamStream(x=1, P=30), steam_type=0,
...                                  name='Secondary Heaters', juice_out_temp_degF=220,
...                                  U_btu_per_ft2_degF=220, installed_area_ft2=8000)
>>> ser = JuiceHeatingStation(cold_stream=juice, heaters=[primary, secondary],
...                           mode='series', name='Juice Heaters - Series')
>>> ser.neat_display()
===================================================================================================================
                                         JUICE HEATERS - SERIES  -  SERIES
===================================================================================================================
  Heater                    Juice lb/hr   T in F  T out F   LMTD F    Duty BTU/hr      U   Req ft2  Inst ft2 Steam psia  Steam lb/hr
-------------------------------------------------------------------------------------------------------------------
  Primary Heaters             1,400,000     95.0    180.0     80.3    108,475,640    220     6,137     8,000       19.0      112,796
  Secondary Heaters           1,400,000    180.0    220.0     47.5     51,047,360    220     4,882     8,000       30.0       54,006
-------------------------------------------------------------------------------------------------------------------
  TOTAL                                                               159,523,000                                            166,802

  Hot juice out: 1,400,000 lb/hr @ 220.0 F  (15.00 Bx, 88.0 purity)
-------------------------------------------------------------------------------------------------------------------
  Clean condensate (Exhaust steam heaters) :       51,874 lb/hr
  Dirty condensate (V1-V4 steam heaters)   :      111,261 lb/hr
  Total condensate                         :      163,134 lb/hr
===================================================================================================================
```

For `mode='parallel'`, `cold_stream` is split across the heaters by `split_pcts` (defaults to an equal split; must sum to 100), each solved independently, then recombined at the mass-weighted blend temperature.

**`set_steam_pressure(steam_type, P)`** is the hook `main.py` uses to close the loop with `EvaporatorSet`/`EvaporatorSetSciPy`: it re-pressures every heater on a given `steam_type` (0=Exhaust, 1–4=V1–V4) — keeping the same quality if the steam was saturated, or the same temperature if it was superheated — then resolves the whole station. It raises `ValueError` if no heater in the station uses that `steam_type`.

Totals: `total_steam_lb_hr`, per-bleed `total_exhaust_steam_lb_hr`/`total_V1_steam_lb_hr` ... `total_V4_steam_lb_hr`, `total_duty_btu_hr`, and `clean_condensate`/`dirty_condensate` (post-flash, same `condensate_utils.flash_condensate()` convention used everywhere else). `generate_pfd()` (series or parallel layout) and `to_excel()` are also available.

---

## EvaporatorSet

`EvaporatorSet` chains multiple `Evaporator` instances into a rigorous multi-effect station. Where a single `Evaporator` needs you to hand it a vapor-space pressure and just tells you what happens, `EvaporatorSet` **solves for** the supply steam flow needed to hit a target syrup brix, and the vapor-pressure profile across effects needed to equalize heat-transfer performance (U_calc/U_dessin) between them.

```python
>>> from SugarStream import SugarStream
>>> from SteamStream import EvaporatorSteam
>>> from EvaporatorSet import EvaporatorSet
>>> from evaporator_functions import convert_inHg_vacuum_to_psia, convert_psig_to_psia
>>> juice = SugarStream(brix=12, purity=90, flow_lb_per_hr=200_000, temp_deg_F=225, pressure_psia=60, level_ft=0)
>>> steam = EvaporatorSteam(P_psia=convert_psig_to_psia(20), flow_lb_per_hr=0)
>>> evap_set = EvaporatorSet(
...     juice_in=juice, supply_steam=steam,
...     last_effect_pressure_psia=convert_inHg_vacuum_to_psia(26),
...     target_brix_out=60, effect_areas_ft2=[4800, 4800, 4800], name='Triple Effect',
... )
>>> evap_set.adjust_pressure_profile()   # required — see gotcha below
>>> evap_set.neat_display()
===============================================================
  Triple Effect
===============================================================
  Juice In     :      200,000 lb/hr  |   12.00 brix  |   225.0 deg F
  Syrup Out    :       40,000 lb/hr  |   60.00 brix  |   140.5 deg F
  Steam Req'd  :       53,826 lb/hr  |   34.70 psia -  20.00 psig  |   258.8 deg F
  Last Eff Vac :  26.00 inHg
  Avg U Ratio  :  0.905
```

(`neat_display()` continues with a full per-effect table — flows, brix, temperatures, vapor/calandria conditions, U calc vs. Dessin — an energy-balance walk-through per effect, the last-effect condenser, and the condensate return; see the example above for the general shape.)

A few things worth knowing:

- **Construction alone doesn't converge the balance.** `__init__` builds each `Evaporator` at an initial guessed pressure profile (`pressure_profile_initial`) and a shortcut steam-flow estimate, and solves each one *once* at those starting conditions — it does **not** iterate to hit `target_brix_out` or equalize U ratios. You always call `adjust_pressure_profile()` (or `adjust_pressure_profile_scipy()` on the SciPy variant) right after construction, exactly as every docstring example and the `__main__` block do.
- **`adjust_pressure_profile()`** is a fixed-point loop: it nudges each effect's vapor pressure by `(average_U_ratio / this_effect's_U_ratio) ** 0.1` per pass, calling `solve_for_steam()` (a secant-method search on the supply steam flow) after every pressure change, until the U-ratio spread (`stdev`) falls below `0.0001` or 100 iterations pass. `manually_set_pressures()` lets you bypass this and pin a pressure profile directly, for testing.
- **`EvaporatorSetSciPy`** (also defined in `EvaporatorSet.py`) is a subclass swapping that hand-rolled loop for `scipy.optimize.root` via `adjust_pressure_profile_scipy()` — same target (equal U_ratio across effects, brix on target), tighter convergence, and it's what `multi_effect_solver_scipy.py`/`multi_effect_solver_vers_2.py` build internally. Prefer it unless you have a reason not to.
- **`vapor_bleeds`** is a list, one entry per effect (first effect first) — a nonzero entry pulls that much vapor off as a `vapor_bleed` stream (e.g. to a `JuiceHeaterShellTube`) *before* the remainder flows on to feed the next effect's calandria.
- **A `PreEvaporator` chains in front of an `EvaporatorSet`** by passing `pre.juice_out` as `juice_in` — see the class docstring for a full worked example, and `generate_pfd(pre_evap=pre)` to draw both on one figure.
- **`condenser`** is a live `Condenser` property built from the last effect's vapor (net of any last-effect bleed); **`clean_condensate`**/**`dirty_condensate`** split effect 1 (fresh exhaust) from effects 2+ (inter-effect vapor), same `flash_condensate()` convention as elsewhere.
- **`check_material_balance()`** and **`check_energy_balance()`** are standalone diagnostic prints (not part of `neat_display()`) that flag any effect whose in/out flows or energy don't reconcile within a small tolerance — useful after you've been poking at inputs manually.

`sets_to_excel(evap_sets, workbook)` (a module-level function, not a method) writes several solved `EvaporatorSet`s onto **one shared sheet** — used together with `solve_evaporator_sets`/`solve_evaporator_sets_scipy` below, which hand you back a list of sets. `show_me_evaporator_details()` prints every effect's full `display_properties()` back-to-back; `show_brix_list_actual()` is a quick one-line-per-effect brix check.

---

## FourBoilingDoubleMagma, ThreeBoilingDoubleMagma, TwoBoiling, ThreeBoiling

These are the full pan-floor boiling schemes — the "management" layer over `Pan`, `Centrifugal`, `Crystallizer`, and `Reheater`, the same way `EvaporatorSet` sits over `Evaporator`. You hand each one syrup plus one `Pan`/`Centrifugal`/`Crystallizer`/`Reheater` object **per station**, used purely as a configuration template (feed streams / massecuite left as `None`/`0` placeholders — you don't need to define inlet streams yourself); the class rebuilds each unit internally, wired to the streams the scheme actually produces.

Why rebuilding is necessary: these floors are **recycle loops**. C magma feeds back to foot the A (or B) pans; A/B molasses feed the grain pans; grain massecuite feeds the C pans; remelted magma feeds back into the syrup itself. None of that can be solved in one pass, so `_solve()` runs a fixed number of iterations (`iterations=`, default 15–20 depending on the class) rebuilding every station each pass from the previous pass's outputs, until the recycle streams settle. There's no convergence *check* — just a fixed iteration count, so if you push these to extreme inputs, bump `iterations` up and re-inspect rather than trusting the default blindly.

**TwoBoiling** — the simplest scheme, two product streams (A sugar, C final molasses), no B stage:
Syrup + C-magma footing + top-off A molasses → **A pans** → **A centrifugals** → A sugar (final product) + A molasses. A molasses splits three ways: top-off back to A pans, to the grain pans, and to the C pans. Syrup + A molasses → **grain pans** → grain massecuite + remaining A molasses + syrup + top-off C molasses → **C pans** → **C crystallizers** → **C reheaters** → **C centrifugals** → C magma (mingled from C sugar) splits to A-pan footing and remelt (remelt rejoins the syrup feed) + C final molasses (terminal product, leaves the floor, net of whatever's diverted back as top-off — see **Molasses top-off** below).

**ThreeBoilingDoubleMagma** — adds a B stage between A and C, "double magma" meaning both B and C magma get re-mingled and recycled (footing + remelt) rather than going straight to product:
Syrup → **A pans** (footed by B magma) → **A centrifugals** → A sugar (final product) + A molasses (→ B pans, grain, top-off). **B pans** (footed by C magma, fed by A molasses + top-off B molasses) → **B centrifugals** → B magma (→ A footing + remelt) + B molasses (→ grain, C pans, top-off back to B pans). Grain massecuite + B molasses + top-off C molasses → **C pans** → crystallizer → reheater → **C centrifugals** → C magma (→ B footing + remelt) + C final molasses (terminal product, net of whatever's diverted back as top-off).

**FourBoilingDoubleMagma** — splits the A stage into **A1** and **A2** pans (two independently-run product streams, `A1_centrifugals.sugar_stream` and `A2_centrifugals.sugar_stream`), both footed off B magma:
Syrup splits to A1 pans, A2 pans, and grain. **A1 pans** → **A1 centrifugals** → A1 sugar + A1 molasses, which splits to A2 pans, grain, and B pans. **A2 pans** (fed by syrup + A1 molasses + B-magma footing) → **A2 centrifugals** → A2 sugar + A2 molasses, split to grain and B pans. **B pans** (fed by A1 molasses + A2 molasses + C-magma footing) → **B centrifugals** → B magma (→ A1 + A2 footings, remelt) + B molasses (→ grain, C pans). Grain + B molasses → **C pans** → crystallizer → reheater → **C centrifugals** → C magma (→ B footing + remelt) + C final molasses.

```python
>>> from FourBoilingDoubleMagma import FourBoilingDoubleMagma
>>> pan_floor = FourBoilingDoubleMagma(syrup=..., A1_pans=..., A2_pans=..., B_pans=..., C_pans=...,
...                                     grain_pans=..., A1_centrifugals=..., A2_centrifugals=...,
...                                     B_centrifugals=..., C_centrifugals=..., ...)  # see FourBoilingDoubleMagma.py __main__
>>> pan_floor.neat_display()
===================================================================================================================
                                FOUR BOILING DOUBLE MAGMA - COMPLETE FLOOR BALANCE
===================================================================================================================

-------------------------------------------------------------------------------------------------------------------
  OVERALL FLOOR BALANCE
-------------------------------------------------------------------------------------------------------------------
  (Feed = Evaporator syrup + Wash Water; Products = A1+A2 sugar + C final molasses)

  Stream                           Flow (lb/hr)  Solids (lb/hr) Pol (lb/hr)   Water (lb/hr)  Brix%   Pur%     ft3/hr

  ENTERING
    Syrup From Evaporators               100,000        65,000        57,850        35,000   65.0   89.0      1,218
    Wash and Dilution Water               24,678             0             0        24,678    0.0    0.0        395

  LEAVING
    A1 Product Sugar                      36,126        36,053        35,945            72   99.8   99.7        373
    A2 Product Sugar                      19,116        19,078        18,944            38   99.8   99.3        198
    Total Raw Sugar                       55,241        55,131        54,889           110      -      -          -
    C Final Molasses                      12,035         9,869         2,961         2,166   82.0   30.0        135
    Evaporated (all pans)                 57,401             0             0        57,401      -      -          -
-------------------------------------------------------------------------------------------------------------------
    Total Entering                       124,678        65,000        57,850        59,678      -      -          -
    Total Leaving                        124,678        65,000        57,850        59,678      -      -          -
-------------------------------------------------------------------------------------------------------------------
  Pol% Recovered in Raw Sugar (A1+A2 / feed):    94.88 %
```

Every scheme shares the same properties for wiring into the rest of the factory: **`pan_condensers`** (a `[(name, Condenser)]` list, one barometric condenser per pan — feed straight into `CoolingTowerSystem`), **`total_exhaust_steam_lb_hr`**/**`total_V1_steam_lb_hr`**...**`total_V4_steam_lb_hr`** (summed across every pan, by `steam_type`), **`clean_condensate`**/**`dirty_condensate`**, and **`total_water`** (fresh water added: centrifugal wash + magma minglers + remelt/dilution water — everything not drawn on the PFD). `generate_pfd()` and `to_excel()` are on all three, and as of the latest update so is a full station-by-station `neat_display()` — **`TwoBoiling`'s** was added to match its two `*DoubleMagma` siblings, same shape (per-station `ENTERING`/`LEAVING` tables, pan-vapor-condenser table, condensate return), trimmed to the two-stage flow: no B stage, no magma tables (neither `*DoubleMagma` class prints those to the console either — that detail is `to_excel()`-only for all three).

`TwoBoiling` also picked up **`properties()`**/**`display_properties()`** — a flat dict (and its one-line-per-metric printout) of the top-level floor balance: syrup in, A sugar out, C final molasses out, total evaporated, pol% recovered, steam demand by `steam_type`, and clean/dirty condensate. Neither `ThreeBoilingDoubleMagma` nor `FourBoilingDoubleMagma` has these yet — for those two, read the station attributes directly (`pan_floor.A_centrifugals.sugar_stream`, etc.) or use `neat_display()`'s full report.

```python
>>> from TwoBoiling import TwoBoiling
>>> pan_floor = TwoBoiling(syrup=..., A_pans=..., C_pans=..., grain_pans=...,
...                        A_centrifugals=..., C_centrifugals=..., ...)  # see TwoBoiling.py __main__
>>> pan_floor.neat_display()
===================================================================================================================
                                       TWO BOILING - COMPLETE FLOOR BALANCE
===================================================================================================================

-------------------------------------------------------------------------------------------------------------------
  OVERALL FLOOR BALANCE
-------------------------------------------------------------------------------------------------------------------
  (Feed = Evaporator syrup + Wash Water; Products = A sugar + C final molasses)

  Stream                           Flow (lb/hr)  Solids (lb/hr) Pol (lb/hr)   Water (lb/hr)  Brix%   Pur%     ft3/hr

  ENTERING
    Syrup From Evaporators               166,666       100,000        78,000        66,666   60.0   78.0      2,077
    Wash and Dilution Water               38,962             0             0        38,962    0.0    0.0        624

  LEAVING
    A Product Sugar                       67,480        67,278        66,874           202   99.7   99.4        698
    C Final Molasses                      39,904        32,722        11,125         7,183   82.0   34.0        449
    Evaporated (all pans)                 98,244             0             0        98,244      -      -          -

-------------------------------------------------------------------------------------------------------------------
    Total Entering                       205,628       100,000        78,000       105,629      -      -          -
    Total Leaving                        205,628       100,000        78,000       105,629      -      -          -
-------------------------------------------------------------------------------------------------------------------
    Net (In - Out)                             0             0             0             0      -      -          -
  Pol% Recovered in Raw Sugar (A sugar / feed):  85.74 %

[... continues with A Pans, A Centrifugals, A Molasses Dilution, Grain Pans, C Pans, C Crystallizers,
     C Reheaters, C Centrifugals, Pan Vapor Condensers, and Condensate Return, same table shapes as the
     FourBoilingDoubleMagma example above ...]

>>> pan_floor.display_properties()
Units: flow(lb/hr), brix/purity/pol(%)
  syrup_flow_lb_hr                  : 166,666.000
  syrup_brix                        : 60.000
  syrup_purity                      : 78.000
  total_water_lb_hr                 : 38,962.377
  a_sugar_flow_lb_hr                : 67,480.438
  a_sugar_brix                      : 99.700
  a_sugar_purity                    : 99.400
  c_final_molasses_flow_lb_hr       : 39,904.344
  c_final_molasses_brix             : 82.000
  c_final_molasses_purity           : 34.000
  total_evaporated_lb_hr            : 98,243.542
  pol_pct_recovered_in_raw_sugar    : 85.737
  total_exhaust_steam_lb_hr         : 113,916.690
  total_V1_steam_lb_hr              : 0.000
  total_V2_steam_lb_hr              : 0.000
  total_V3_steam_lb_hr              : 0.000
  total_V4_steam_lb_hr              : 0.000
  clean_condensate_lb_hr            : 111,502.070
  dirty_condensate_lb_hr            : 0.000
```

**ThreeBoiling** — a non-double-magma, three-stage scheme: a variant of `ThreeBoilingDoubleMagma` with the B magma stage removed. B centrifugal sugar is a terminal product (sent straight to the warehouse alongside A sugar) instead of being remelted into a footing magma, so only C magma exists, split three ways instead of two — `c_magma_A_footing_pct` foots the A pans, `c_magma_B_footing_pct` foots the B pans, and the remainder (`c_magma_remelt_pct`) goes to remelt, back into the syrup feed:
Syrup → **A pans** (footed by C magma) → **A centrifugals** → A sugar (final product) + A molasses (→ B pans, grain, top-off). **B pans** (footed by C magma, fed by A molasses + top-off B molasses) → **B centrifugals** → B sugar (final product, terminal — no B magma stage) + B molasses (→ grain, C pans, top-off back to B pans). Grain massecuite + B molasses + top-off C molasses → **C pans** → crystallizer → reheater → **C centrifugals** → C magma (→ A footing + B footing + remelt) + C final molasses (terminal product, net of whatever's diverted back as top-off).

### Molasses top-off

All three of the schemes above let you recycle a slice of a grade's own molasses straight back into that same grade's pans, instead of passing all of it on to the next lower grade (or, for A, to the grain pans/B pans): `a_mol_top_off_pct`, `b_mol_top_off_pct`, and `c_mol_top_off_pct` (fractions of that grade's molasses, 0–100). `a_mol_top_off_pct` defaults to 30% in every scheme that has an A stage; `b_mol_top_off_pct` and `c_mol_top_off_pct` default to **0% (off)** in `ThreeBoiling`, `ThreeBoilingDoubleMagma`, and `TwoBoiling` — they're opt-in.

- **A and B top-off** draw from the same diluted molasses stream that feeds the next grade (`a_mol_dilution_brix`/`b_mol_dilution_brix`, both default 70 Bx) — the top-off slice is just another split off that stream, back into its own pan as an extra feed.
- **C top-off** works differently, since C molasses is the terminal product rather than feeding a lower grade: `c_mol_top_off_pct` is a fraction of the *undiluted* final C-centrifugal molasses, which then gets diluted separately to `c_mol_top_off_brix` (default 70 Bx) before returning to the C pans. Whatever fraction is recycled this way no longer counts as `C final molasses` — the schemes track this as `_final_molasses_out` (final centrifugal molasses minus the top-off slice), which is what `neat_display()`, `generate_pfd()`, `properties()`/`display_properties()`, and `total_water()` all report. If you're reading the terminal molasses flow directly off the object, use `pan_floor._final_molasses_out`, not `pan_floor.C_centrifugals.molasses_stream` (the latter is the pre-top-off flow).
- **Why you'd use it:** topping off gives a pan more feed volume/boiling capacity when it's running short. **Why you usually wouldn't:** it reruns already-once-boiled (and, for C, already fully exhausted) molasses back through a pan for a second pass, exposing it to more heat and residence time — which raises color. Leave these at 0% unless the pan floor genuinely needs the extra feed and the color hit is acceptable.

---

## CanePrepTurbines, MillTurbines, AuxillaryTurbines

These three classes solve a *group* of `Turbine` objects from parallel lists and report them side by side in one table — cane prep drives (shredder/knives), mill drives, and everything else (ID fans, boiler feed pumps, etc.), respectively. All three share the same shape: build one `Turbine` per entry, expose `.turbines` (the list) plus `total_hp`/`total_inlet_flow_lb_hr`/`total_exhaust_available_lb_hr`, and the same `neat_display()`/`generate_pfd()`/`to_excel()` (the last two both delegate to shared helpers in `turbine_diagram.py`).

They differ only in how HP demand is specified and named:

- **`CanePrepTurbines`** and **`MillTurbines`** take `hp_ton_fiber_hr` (a list of HP-per-ton-fiber-per-hour, one entry per unit) and a single `tons_fiber_hr` — each turbine's `hp_demand` is `hp_ton_fiber_hr[i] * tons_fiber_hr`, so bumping the cane rate rescales every turbine's demand automatically. `CanePrepTurbines` defaults to naming units `Shredder`, `Knife 1`, `Knife 2`, `Knife 3` (override with `name_list`) and skips any unit with `hp_ton_fiber_hr == 0` in the display; `MillTurbines` always names units `Mill 1`, `Mill 2`, ... and shows every one.
- **`AuxillaryTurbines`** takes an explicit `hp_list` instead (no per-ton-fiber scaling) plus a **required** `name_list` and `group_name` — it's for drives whose load doesn't track fiber rate. Units with `hp_list[i] == 0` are skipped in the display, same as `CanePrepTurbines`.

All three require `isentropic_efficiency` as a **list of percents** (e.g. `50` for 50%, matching the count of the HP list) — they divide by 100 before constructing each `Turbine`, so pass percents here even though `Turbine` itself wants a 0–1 fraction.

```python
>>> from AuxillaryTurbines import AuxillaryTurbines
>>> from SteamStream import SteamStream
>>> aux = AuxillaryTurbines(
...     group_name='ID Fan Turbines',
...     name_list=['123 ID Fan', '4 ID Fan', '5 ID Fan', '6 ID Fan', '7 ID Fan', '8 ID Fan'],
...     hp_list=[750, 235, 400, 795, 1200, 1300],
...     isentropic_efficiency=[50, 50, 50, 50, 50, 50],
...     live_steam_object=SteamStream(P=190, x=1),
...     exhaust_psia=32,
... )
>>> aux.neat_display()
============================================================================================================================
                                                      ID Fan Turbines
============================================================================================================================
             |  Inlet Flow  | Exhaust Avail |    HP     | Steam Rate |  Inlet   |  Inlet   |  Outlet  |  Outlet  |  Outlet
    Unit     |    lb/hr     |     lb/hr     |           |  lb/HP-hr  |   psia   | temp °F  |   psia   | temp °F  |  quality
-------------+--------------+---------------+-----------+------------+----------+----------+----------+----------+----------
  123 ID Fan |       28,176 |        27,128 |       750 |      37.57 |    190.0 |    377.5 |     32.0 |    254.0 |  0.9628
    4 ID Fan |        8,829 |         8,500 |       235 |      37.57 |    190.0 |    377.5 |     32.0 |    254.0 |  0.9628
    5 ID Fan |       15,027 |        14,468 |       400 |      37.57 |    190.0 |    377.5 |     32.0 |    254.0 |  0.9628
    6 ID Fan |       29,867 |        28,756 |       795 |      37.57 |    190.0 |    377.5 |     32.0 |    254.0 |  0.9628
    7 ID Fan |       45,082 |        43,405 |     1,200 |      37.57 |    190.0 |    377.5 |     32.0 |    254.0 |  0.9628
    8 ID Fan |       48,839 |        47,022 |     1,300 |      37.57 |    190.0 |    377.5 |     32.0 |    254.0 |  0.9628
-------------+--------------+---------------+-----------+------------+----------+----------+----------+----------+----------
       TOTAL |      175,820 |       169,279 |     4,680 |      37.57 |          |          |          |          |
============================================================================================================================
```

All three turbines in a group share one `live_steam_object` and one `exhaust_psia` — if part of your plant runs on a different steam header, build a separate group for it (`main.py` typically ends up with several `AuxillaryTurbines` groups: ID fans, FD fans, boiler feed pumps, and so on).

---

## CoolingTowerSystem

`CoolingTowerSystem` combines **every barometric condenser in the factory** — each evaporator set's last-effect condenser, plus every pan's condenser from the pan floor — into one shared cooling-tower and makeup-water balance. Each `Condenser` is solved independently wherever it's built (an `EvaporatorSet`, a boiling scheme's `pan_condensers`); this class just gathers them, in the same spirit as the boiling schemes' "streams not shown" water table:

```python
>>> from CoolingTowerSystem import CoolingTowerSystem
>>> cts = CoolingTowerSystem(
...     condensers=(pan_floor.pan_condensers + [(s.name, s.condenser) for s in evap_station]),
...     cool_water_temp_F=90, percent_blowdown=1.0,
... )
>>> cts.neat_display()
```

Set `water_outlet_temp_drop_F=5.0` on `CoolingTowerSystem` to apply one downleg
ΔT to every collected pan and evaporator condenser. Downleg temperature is vapor
saturation temperature minus ΔT (°F); it must remain above injection-water
temperature. Omitting this argument preserves each condenser's existing setting.
The Streamlit **Cooling Tower** section exposes **Condenser downleg ΔT (°F)**,
defaulting to 5°F. Change it and click **Solve Entire Plant** to recalculate.

producing a report shaped like (5-condenser demo from `CoolingTowerSystem.py`'s own `__main__`):

```
COOLING TOWER SYSTEM - COMBINED CONDENSER / TOWER BALANCE
...
  CONDENSER INVENTORY  (5 condensers, delivered injection water @ 88.5 F)
  ...
  Total                             190,000                      194.011     4,808,686     9,656              4,998,686

  HOT WATER RETURN TO TOWER
  Total return                            4,998,686 lb/hr    10,038 GPM  @ 128.9 F mixed

  COOLING TOWER  (128.9 F -> 90 F, blowdown 10.0%)
  Blowdown                                  499,869 lb/hr     1,004 GPM
  Evaporated to atmosphere                  174,905 lb/hr       351 GPM
  Cool water from tower                   4,323,913 lb/hr     8,683 GPM  @ 90 F

  SYSTEM BALANCE
  Cold water demand (condensers)          4,808,686 lb/hr     9,656 GPM
  Cool water available (tower)            4,323,913 lb/hr     8,683 GPM  @ 90 F
  MAKEUP WATER REQUIRED                     484,774 lb/hr       973 GPM  @ 75 F

  Delivered injection water temp (cool + makeup blend): 88.5 F
```

The mechanics worth understanding:

- **This is a circular dependency, solved by plain iteration.** The delivered injection-water temperature depends on how much makeup is needed, which depends on the condensers' cold-water demand, which depends on the delivered temperature. `_solve()` just loops a fixed `iterations` times (default 15) re-solving every condenser at `delivered_water_temp_F` — no tolerance check, same pattern as the boiling schemes.
- **The condensers you pass in were each solved standalone**, usually at some assumed injection temperature (often 90°F, whatever the owning `EvaporatorSet`/pan floor used). `CoolingTowerSystem` re-solves them at the *actual* delivered temperature once the tower and makeup are accounted for — that's exactly the "ignore this injection water demand, it's re-solved here" note you'll see printed by `EvaporatorSet.neat_display()` and the boiling schemes. **`mismatched_inlets`** lists which condensers arrived at a different temperature than what got delivered, if you want to double check.
- **`makeup_water_temp_F=None`** (the default) means makeup arrives at the tower's own cool-water temperature, so the delivered temp equals `cool_water_temp_F` exactly and the loop above converges in one pass. Give it an actual makeup source temperature (well water, city water) and the delivered temp becomes a mass/heat blend of tower water and makeup — that's what produces the 88.5°F in the example (blended from 90°F tower water and 75°F makeup).
- **`makeup_lb_hr`** is `max(injection demand − cool water from tower, 0)`; if the vapor condensed across the factory actually exceeds what the tower needs to reject, the shortfall goes negative and shows up instead as **`surplus_lb_hr`** (overflow) — the system doesn't need makeup in that case.
- **`tower`** is a live `CoolingTower` property (see the base equipment class) built from the combined hot-water return; **`balance_check`** reconciles the whole system (vapor + makeup in, vs. evaporated + blowdown + surplus out).

`generate_pfd()` and `to_excel()` are both available.

---

# Useful Functions

Beyond the equipment and management classes, a handful of standalone modules do work that doesn't belong to any one unit — condensate/water reconciliation, unit conversions feeding into the evaporator solves, and the multi-set juice-balancing solvers. This section covers the ones worth knowing about if you're assembling your own factory balance the way `main.py` does.

## condensate_utils

The whole project's condensate accounting runs through one function: **`flash_condensate(flow_lb_per_hr, sat_temp_deg_F, flash_temp_F=212.0, h_fg_flash_btu_lb=970.0)`**. Condensate hotter than atmospheric partially flashes to vapor when it's let down to atmospheric pressure on its way back to the boiler feed system; this returns the liquid fraction that survives that flash — `flow − flow*(sat_temp − 212)/970` when `sat_temp > 212°F`, or the full flow unchanged otherwise. Every `clean_condensate`/`dirty_condensate` property you've seen above (`EvaporatorSet`, `JuiceHeatingStation`, `PreEvaporator`, the boiling schemes) is built from this one call, tagged clean (fresh exhaust) vs. dirty (V1–V4 / inter-effect vapor) purely by which `steam_type`/effect it came from — the function itself doesn't know or care about that distinction.

## condensate_balance

`CondensateBalance` (with `CondensateDemand`) takes the `clean_condensate`/`dirty_condensate` totals you've already tallied from the rest of the factory and reconciles them, informationally, against a list of named water-demand locations — boiler feed water, imbibition, wash water, dilution water, and so on.

```python
>>> from condensate_balance import CondensateBalance, CondensateDemand
>>> demands = [
...     CondensateDemand('Boiler Feed Water', flow_lb_hr=800_000, temp_F=227, method='blended',
...                      note="Recommend usage of clean condensate, make up with minimal dirty condensate or well water"),
...     CondensateDemand('Imbibition', flow_lb_hr=1_200_000, temp_F=150, method='blended'),
...     CondensateDemand('Wash Water - Pans', flow_lb_hr=150_000, temp_F=160, method='cooled'),
...     CondensateDemand('Dilution Water - Molasses/Remelt', flow_lb_hr=90_000, temp_F=180, method='blended'),
... ]
>>> cb = CondensateBalance(
...     clean_condensate_dict={'Evap Set - Effect 1': 41_000, 'Pan Floor - Exhaust Pans': 15_000, 'Juice Heaters - Exhaust': 52_000},
...     dirty_condensate_dict={'Evap Set - Effects 2+': 102_000, 'Pan Floor - V1-V4 Pans': 50_000, 'Juice Heaters - V1-V4': 111_000},
...     demands=demands, well_water_temp_F=90, combined_condensate_temp_F=210,
... )
>>> cb.neat_display()
```

```
  CONDENSATE DEMAND
  (combined condensate temp = 210.0 °F, well water temp = 90.0 °F)
------------------------------------------------------------------------------------------
  Location                       Method   Flow lb/hr   Temp F   Cond lb/hr   Well lb/hr   Cond %
------------------------------------------------------------------------------------------
  Boiler Feed Water             blended      800,000    227.0      800,000            0   100.0%
      -> Recommend usage of clean condensate, make up with minimal dirty condensate or well water
      WARNING: Target 227.0 °F is above the condensate temp (210.0 °F) — clamped to 100% condensate.
  Imbibition                    blended    1,200,000    150.0      600,000      600,000    50.0%
  Wash Water - Pans              cooled      150,000    160.0      150,000            0   100.0%
  Dilution Water - Molasses/Remelt  blended       90,000    180.0       67,500       22,500    75.0%
------------------------------------------------------------------------------------------
  TOTAL                                    2,240,000             1,617,500      622,500

  CONDENSATE CHECK  (informational — reconcile against the demand list yourself)
------------------------------------------------------------------------------------------
  Total condensate available                       371,000 lb/hr
  Total condensate required                      1,617,500 lb/hr
  Surplus / (Deficit)                           -1,246,500 lb/hr
```

A few things worth knowing:

- **This does not auto-allocate condensate to demands.** The supply side (clean/dirty totals) and the demand side (condensate/well-water split per location) are computed completely independently and shown side by side — the "Surplus/(Deficit)" line is informational only, telling you whether there's roughly enough condensate to go around; nothing routes an actual lb/hr of clean condensate to a specific demand for you. You reconcile the two by eye and decide routing yourself.
- **Each `CondensateDemand` picks one of two methods.** `'blended'` splits the demand's flow between condensate and well water via a straight linear temperature blend against a single `combined_condensate_temp_F` (one lumped number for the whole balance, not tracked per source) — `cond_frac = (target − well) / (cond − well)`, clamped to [0, 1] with a warning if the target temperature is outside the condensate/well-water range. `'cooled'` means the full flow is condensate by definition (it's cooled via a heat exchanger rather than diluted with well water), so `well_water_flow_lb_hr` is always 0.
- **`note`** on a `CondensateDemand` is a free-text tag only — printed/exported as-is, with no effect on the calculation. Use it the way the example does, to record a routing recommendation for whoever reads the report.

`to_excel()` writes the same supply/demand tables to their own sheet (or appends onto a shared `SheetWriter`).

## multi_effect_solver_vers_2 and multi_effect_solver_scipy

Both modules solve the same problem `EvaporatorSet` doesn't: balancing juice flow **across several parallel evaporator sets** sharing one clarified-juice feed (e.g. two independent triple-effect trains) so every set converges to the same average `U_ratio_avg` — a fair load split, not just "however much juice each train happens to get." Each set's own internal pressure profile is solved via `EvaporatorSetSciPy.adjust_pressure_profile_scipy()` either way; the two modules differ only in how the **outer** juice-split is solved.

```python
>>> from multi_effect_solver_scipy import solve_evaporator_sets_scipy
>>> sets = solve_evaporator_sets_scipy(
...     juice_brix=14, juice_purity=90, juice_flow_lb_per_hr=1_500_000, juice_temp_deg_F=220,
...     set_configs=[
...         {"name": "Set 1 (4-eff 25k ft2)", "effect_areas_ft2": [25000]*4,
...          "supply_steam_psia": 30, "last_effect_psia": 2.4, "vapor_bleeds": [100000, 50000, 50000]},
...         {"name": "Set 2 (4-eff 12k ft2)", "effect_areas_ft2": [12000]*4,
...          "supply_steam_psia": 25, "last_effect_psia": 2.4, "vapor_bleeds": [50000, 20000]},
...         {"name": "Set 3 (3-eff 11-9k ft2)", "effect_areas_ft2": [11000, 9000, 9000],
...          "supply_steam_psia": 16, "last_effect_psia": 2.4, "vapor_bleeds": [50000]},
...     ],
... )

Initial fractions (HS x dP / n_eff):
  Set 1 (4-eff 25k ft2): 0.6315  Set 2 (4-eff 12k ft2): 0.2482  Set 3 (3-eff 11-9k ft2): 0.1203

Converged in 7 evals  (145.2 ms)
  Set 1 (4-eff 25k ft2)    63.40% of juice  (     951,021 lb/hr)  U_ratio_avg=1.142367
  Set 2 (4-eff 12k ft2)    24.70% of juice  (     370,551 lb/hr)  U_ratio_avg=1.142367
  Set 3 (3-eff 11-9k ft2)   11.90% of juice  (     178,428 lb/hr)  U_ratio_avg=1.142367
  total fraction check: 1.000000
```

- **`solve_evaporator_sets` (in `multi_effect_solver_vers_2.py`)** — the one `main.py` actually imports — starts each set at a juice fraction weighted by `(total heating surface / n_effects) × ΔP`, then runs `n_iterations` (default 10) of a **damped fixed-point** update: under-loaded sets (low `U_ratio_avg` relative to the group average) get more juice next pass, over-loaded sets give some away, scaled by a `dampening` exponent (default 0.1–0.2; smaller = more stable, more iterations needed). It always prints verbose per-iteration progress and a full `neat_display()` per set at the end unless you set `verbose=False`.
- **`solve_evaporator_sets_scipy` (in `multi_effect_solver_scipy.py`)** — same seeding logic, but wraps the outer fraction split in `scipy.optimize.root` instead of the damped loop. Per the module's own benchmark note, this is a **package deal**: `root` estimates its Jacobian by nudging each fraction and watching the U-average move, and that only works cleanly because the *inner* per-set solve (`adjust_pressure_profile_scipy`, not the plain `adjust_pressure_profile`) converges to ~1e-10 instead of ~1e-4 — mixing `root` with the old inner solver doesn't converge. Measured ~1.8x faster on a 3-set station in the module's own comparison. Pass `bounded=True` to switch to `scipy.optimize.least_squares` with fraction bounds `(0, 1)`, which is only worth reaching for if the station might otherwise start from a non-physical fraction guess.

Both return `list[EvaporatorSet]` (or `EvaporatorSetSciPy` instances) in `set_configs` order — call `.neat_display()` on any of them individually, or pass the whole list to `sets_to_excel()` (see `EvaporatorSet` above) to write them onto one shared sheet.

## excel_export and steam_summary_excel

Every `to_excel()` method throughout this guide is built on **`excel_export.py`**: `new_workbook()` returns a styled `openpyxl` `Workbook`, and `SheetWriter` is the class every equipment/management class's `to_excel()` uses internally (`title()`, `section()`, `row()`, `table()`, `row_pair()`, `image()`, `page_break()`, `finish()`) to lay its own sheet out consistently. You won't usually touch `SheetWriter` directly — the pattern throughout `main.py` is just:

```python
>>> from excel_export import new_workbook
>>> wb = new_workbook()
>>> boiler.to_excel(wb)
>>> mill.to_excel(wb)
>>> # ... every other unit ...
>>> wb.save("factory_balance.xlsx")
```

— but it's worth knowing about if you want to append a custom section onto an existing sheet: most `to_excel()` methods accept an existing `sheet_writer=` to append onto rather than starting a new sheet (see `EvaporatorSet.to_excel`/`sets_to_excel` for the pattern).

**`steam_summary_excel.steam_summary_to_excel(workbook, live_steam_dict, exh_dict, ...)`** writes the plant-wide live-steam and exhaust-steam demand summary — the same `{label: lb/hr}` dictionaries `main.py` already builds while walking through the boiler, turbine groups, juice heaters, and pans — onto one sheet. Pass `exhaust_available_lb_hr`/`makeup_steam_lb_hr` to also include the exhaust-availability-vs-makeup balance, and `steam_available_lb_hr` (from `Boiler.steam_availabe_lb_hr`, once you've solved it) to include live-steam availability vs. demand.
