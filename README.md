# Cane Sugar Factory Material & Energy Balance

Python tools for calculating first-pass material and energy balances around a
raw cane sugar factory — milling, clarification, multiple-effect evaporation,
pan boiling, and steam/cogeneration — built with Louisiana mills in mind.

Use it as an object-oriented library for your own calculations, or through the
Streamlit app (linked below), which runs online or locally on your own machine.

Built by a sugar mill engineer for sugar mill engineers. It's meant for
screening and first-pass estimates — calibrate against your own plant data
before trusting any single number.

**Requires:** Python 3.12+
Older versions may work, but I haven't tested them.

This repo has two purposes.

## Reason 1
To give other sugar mill engineers easy-to-use Python objects (classes) for material and energy balances — either around a single part of the factory, or chained together for a full-factory calculation.

## Reason 2
To host an easy-to-use Streamlit application covering most of what cane sugar engineers in Louisiana need to calculate. The app is live here: https://cane-sugar-mill-material-energy-balance-fbl69dwu8opxateg3jsgnn.streamlit.app/ You're also welcome to clone the repo and run it locally.

## Installation

### macOS / Linux (bash)

```bash
git clone https://github.com/codyeaves78-bit/cane-sugar-mill-material-energy-balance
cd cane-sugar-mill-material-energy-balance

# create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# install requirements, then launch the app
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Windows (easiest: double-click launcher)

If you don't want to type PowerShell commands, install [Python](https://www.python.org/downloads/)
(check "Add python.exe to PATH" during install) and [Git for Windows](https://git-scm.com/downloads),
then:

```powershell
git clone https://github.com/codyeaves78-bit/cane-sugar-mill-material-energy-balance
```

Open the new `cane-sugar-mill-material-energy-balance` folder and double-click
**`run_windows.bat`**. It creates the virtual environment, installs dependencies, and
launches the app for you — every run after the first just activates the existing venv
and starts Streamlit. Close its window (or press Ctrl+C) to stop the app.

### Windows (PowerShell)

```powershell
git clone https://github.com/codyeaves78-bit/cane-sugar-mill-material-energy-balance
cd cane-sugar-mill-material-energy-balance

# create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# install requirements, then launch the app
pip install -r requirements.txt
streamlit run streamlit_app.py
```

If activation fails with a "running scripts is disabled on this system" error, allow scripts for your user once, then re-run the activate line:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Windows users may also need Git installed first: [git-scm.com/downloads](https://git-scm.com/downloads).

## HTML quick-check tool

The [`html version/`](html%20version/) folder has a single self-contained HTML file
(`cane_factory_balance.html`) that runs the same balance engine entirely client-side —
no install, no server, just open it in a browser. It's meant for quick, offline
sanity checks (sharing a single-file tool is easier than getting someone set up with
Python/Streamlit), not as a replacement for the Streamlit app.

The core calculation modules (Mill Floor, Clarification, Juice Heaters, Pan Floor,
Evaporators, Deaerator, Turbines, Boiler) were validated line-by-line against the
Python classes on matched inputs and match to floating-point precision. It's
deliberately a lighter tool than the Streamlit app, though:

- No Excel export and no process flow diagrams.
- One evaporator train at a fixed effect count, with a single V1-split percentage —
  no dynamic add/remove of trains and no V2–V4 vapor bleed routing across multiple
  consumers.
- Evaporator pressure profiles use a damped fixed-point solver instead of SciPy's
  root-finder (SciPy can't run in a browser), so multi-train configs can drift up to
  roughly 0.01% from the Python/Streamlit numbers; single-train configs match almost
  exactly.
- No separate Clarified Juice Heater station, and the juice heating station is fixed
  at two exhaust-only heaters.
- Pan Floor uses fixed per-scheme input fields rather than editable pan/centrifugal
  tables, and ties each scheme's crystallizer output purity to its C pan's
  mother-liquor purity instead of exposing it independently.

For multi-train evaporation, full vapor-grade routing, Excel export, or PFDs, use the
Streamlit app.

## Documentation
See the [Documentation](documentation/) folder for the User Guide and worked examples.
