"""Build index.html: the map template (src/template.html) with the data (data/pa8.geojson) written into it.

Usage: python scripts/render.py
The template's <title>, fonts and styles go into <head>; everything else goes into <body>.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    template = open(os.path.join(ROOT, "src", "template.html"), encoding="utf8").read()
    data = open(os.path.join(ROOT, "data", "pa8.geojson"), encoding="utf8").read()
    assert template.count("/*DATA*/null") == 1, "template must contain the /*DATA*/null placeholder once"
    split = template.index("</style>") + len("</style>")
    head, body = template[:split], template[split:].replace("/*DATA*/null", data)
    page = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        "<meta name=\"description\" content=\"Precinct-level election results, party registration and swing for "
        "Pennsylvania's 8th Congressional District, 2022 to 2026.\">\n"
        "<style>body { margin: 0; } [hidden] { display: none !important; }</style>\n"
        f"{head}\n</head>\n<body>{body}\n</body>\n</html>\n"
    )
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf8").write(page)
    print(f"index.html written ({len(page) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
