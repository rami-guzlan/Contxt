"""Build a one-page webinar flyer (HTML) from webinar.json. Standard library only."""
import html
import json
import sys

with open(sys.argv[1] if len(sys.argv) > 1 else "webinar.json", encoding="utf-8") as handle:
    spec = json.load(handle)
points = "".join(f"<li>{html.escape(p)}</li>" for p in spec.get("points", [])[:3])
page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(spec["title"])}</title>
<style>
body {{ font-family: Inter, system-ui, sans-serif; margin: 0; color: #1d1d1b; }}
header {{ background: #1F4E79; color: #fff; padding: 48px 56px; }}
header p {{ color: #F28C28; font-weight: 700; letter-spacing: .04em; margin: 0 0 12px; }}
h1 {{ font-size: 40px; margin: 0; line-height: 1.15; }}
main {{ padding: 40px 56px; background: #E7E6E3; min-height: 60vh; }}
li {{ margin: 0 0 12px; font-size: 18px; }}
a {{ color: #1F4E79; font-weight: 700; }}
</style></head><body>
<header><p>BRIGHTMILL WEBINAR</p><h1>{html.escape(spec["title"])}</h1></header>
<main>
<p><strong>{html.escape(spec["date"])}, {html.escape(spec["time"])} Eastern</strong></p>
<p>With {html.escape(spec["guest"])}, {html.escape(spec["guest_role"])}</p>
<h2>What you will take back to your plant</h2><ul>{points}</ul>
<p>Register: <a href="{html.escape(spec["link"])}">{html.escape(spec["link"])}</a></p>
</main></body></html>"""
with open("one-pager.html", "w", encoding="utf-8") as handle:
    handle.write(page)
print("Wrote one-pager.html")
