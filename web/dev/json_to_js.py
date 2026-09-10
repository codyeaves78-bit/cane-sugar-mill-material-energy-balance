# Wraps reference.json as a plain <script> global so validate.html can load
# it without fetch() (which file:// pages can't do reliably). Run after
# gen_reference.py, or via `python web/dev/regenerate_reference.py` for both.
import json

with open("web/dev/reference.json") as f:
    data = json.load(f)

with open("web/dev/reference.js", "w") as f:
    f.write("window.REFERENCE_CASES = ")
    json.dump(data, f)
    f.write(";")

print(f"Wrote {len(data)} cases to web/dev/reference.js")
