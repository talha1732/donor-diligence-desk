"""Build self-contained report.html and slides.html at the repo root.

  python docs/report/build.py

Sources: docs/report/report.src.html and slides.src.html. Placeholders:
  {{img:name.webp}}      -> data URI of docs/report/img/name.webp
  {{svg:name.svg}}       -> inline SVG from docs/report/
  {{reveal_css}} {{reveal_theme_css}} {{reveal_js}} -> vendored reveal.js 5.2.0 (MIT)
Everything is embedded so the files open by double-click on any computer, offline.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DRAFT = "--draft" in sys.argv
MIME = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _img(match: re.Match) -> str:
    path = HERE / "img" / match.group(1)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{MIME[path.suffix.lower()]};base64,{data}"


def _svg(match: re.Match) -> str:
    svg = (HERE / match.group(1)).read_text(encoding="utf-8")
    return re.sub(r"<\?xml[^>]*\?>", "", svg).strip()


def build(src: str, out: str) -> None:
    html = (HERE / src).read_text(encoding="utf-8")
    html = re.sub(r"\{\{img:([^}|]+)\}\}", _img, html)
    html = re.sub(r"\{\{svg:([^}]+)\}\}", _svg, html)
    vendor = HERE / "vendor"
    html = html.replace("{{reveal_css}}", (vendor / "reveal.css").read_text(encoding="utf-8"))
    html = html.replace("{{reveal_theme_css}}", (vendor / "white.css").read_text(encoding="utf-8"))
    html = html.replace("{{reveal_js}}", (vendor / "reveal.js").read_text(encoding="utf-8"))
    if DRAFT:
        html = re.sub(r"\{\{TODO:([^}]+)\}\}", r'<div style="background:#fff3c4;border:2px dashed #b88a00;padding:10px;margin:10px 0">PENDING: \1</div>', html)
    left = re.findall(r"\{\{[^}]+\}\}", html)
    if left:
        raise SystemExit(f"{src}: unresolved placeholders {left[:5]}")
    if "—" in html:
        raise SystemExit(f"{src}: contains an em dash (style rule)")
    (ROOT / out).write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html.encode('utf-8')) / 1e6:.1f} MB)")


if __name__ == "__main__":
    for src, out in (("report.src.html", "report.html"), ("slides.src.html", "slides.html")):
        if (HERE / src).exists():
            build(src, out)
