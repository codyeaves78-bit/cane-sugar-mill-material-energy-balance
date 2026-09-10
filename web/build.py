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
       .replace("/*__APP_JS__*/", read("src/app.js")))

(WEB / "index.html").write_text(out, encoding="utf-8")
print(f"Wrote web/index.html ({len(out):,} bytes)")
