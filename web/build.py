# Assembles web/index.html (the single-file deliverable) from web/template.html
# and the individual source files in web/src/. Kept as a trivial string-replace
# in pure Python (no Node/bundler) so it runs anywhere this repo's Python
# environment runs. Run from repo root: python web/build.py

from pathlib import Path

WEB = Path(__file__).parent

def read(rel):
    return (WEB / rel).read_text(encoding="utf-8")

template = read("template.html")
out = (template
       .replace("/*__APP_CSS__*/", read("src/app.css"))
       .replace("/*__IAPWS97_JS__*/", read("src/iapws97.js"))
       .replace("/*__STEAM_STREAM_JS__*/", read("src/steam_stream.js"))
       .replace("/*__SUGAR_STREAM_JS__*/", read("src/sugar_stream.js"))
       .replace("/*__BAGASSE_JS__*/", read("src/bagasse.js"))
       .replace("/*__MILL_FLOOR_JS__*/", read("src/mill_floor.js"))
       .replace("/*__CLARIFICATION_JS__*/", read("src/clarification.js"))
       .replace("/*__BOILER_JS__*/", read("src/boiler.js"))
       .replace("/*__TURBINE_JS__*/", read("src/turbine.js"))
       .replace("/*__COGEN_TURBINE_JS__*/", read("src/cogen_turbine.js"))
       .replace("/*__MILL_TURBINES_JS__*/", read("src/mill_turbines.js"))
       .replace("/*__CANE_PREP_TURBINES_JS__*/", read("src/cane_prep_turbines.js"))
       .replace("/*__AUXILLARY_TURBINES_JS__*/", read("src/auxillary_turbines.js"))
       .replace("/*__DEAERATOR_JS__*/", read("src/deaerator.js"))
       .replace("/*__CONDENSATE_UTILS_JS__*/", read("src/condensate_utils.js"))
       .replace("/*__JUICE_HEATER_JS__*/", read("src/juice_heater.js"))
       .replace("/*__JUICE_HEATING_STATION_JS__*/", read("src/juice_heating_station.js"))
       .replace("/*__APP_JS__*/", read("src/app.js")))

(WEB / "index.html").write_text(out, encoding="utf-8")
print(f"Wrote web/index.html ({len(out):,} bytes)")
