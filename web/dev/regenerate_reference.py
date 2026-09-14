# Regenerates web/dev/reference.json and web/dev/reference.js from the
# Python `iapws` package. Run this after changing gen_reference.py's test
# grid, then re-run the validation harness (see PROGRESS.md).
import subprocess
import sys

subprocess.run([sys.executable, "web/dev/gen_reference.py"], check=True)
subprocess.run([sys.executable, "web/dev/json_to_js.py"], check=True)
