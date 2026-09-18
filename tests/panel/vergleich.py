"""Panel-Render gegen einen git-Stand vergleichen: python tests/panel/vergleich.py [REV] [--zeige N] [--ignoriere REGEX ...]

Rendert `solakon-panel.js` samt Panel- und Entity-Texten aus REV (Standard HEAD) und aus
dem Arbeitsverzeichnis mit render.cjs und vergleicht die Schnappschüsse. `--ignoriere` entfernt Treffer vor dem
Vergleich (für bewusste Änderungen). Exit 0: gleich · 1: abweichend · 2: Umgebung fehlt.
Einrichtung einmalig: npm install --prefix tests/panel
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
REPO = HIER.parent.parent
PANEL = "custom_components/solakon_nulleinspeisung/frontend/solakon-panel.js"
TEXTE = ["custom_components/solakon_nulleinspeisung/frontend",
         "custom_components/solakon_nulleinspeisung/translations"]


def render(panel: Path, ziel: Path, texte: Path = REPO) -> list:
    subprocess.run(["node", str(HIER / "render.cjs"), str(panel), str(ziel), str(texte)],
                   check=True, capture_output=True)
    return json.loads(ziel.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if not (HIER / "node_modules" / "jsdom").exists():
        print("jsdom fehlt: npm install --prefix tests/panel")
        return 2
    rev, zeige, muster = "HEAD", 3, []
    i = 0
    while i < len(argv):
        if argv[i] == "--zeige":
            zeige, i = int(argv[i + 1]), i + 2
        elif argv[i] == "--ignoriere":
            muster.append(re.compile(argv[i + 1])); i += 2
        else:
            rev, i = argv[i], i + 1
    with tempfile.TemporaryDirectory() as tmp:
        alt_js = Path(tmp) / "alt.js"
        alt_js.write_text(subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{PANEL}"],
                                         check=True, capture_output=True, text=True).stdout, encoding="utf-8")
        alt_texte = Path(tmp) / "rev"
        alt_texte.mkdir()
        archiv = subprocess.run(["git", "-C", str(REPO), "archive", rev, *TEXTE], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(alt_texte)], input=archiv, check=True)
        alt = render(alt_js, Path(tmp) / "alt.json", alt_texte)
        neu = render(REPO / PANEL, Path(tmp) / "neu.json")

    def norm(v):
        for r in muster:
            v = r.sub("", v)
        return v

    abweichend = 0
    for (na, va), (nb, vb) in zip(alt, neu):
        if na != nb or norm(va) != norm(vb):
            abweichend += 1
            if abweichend <= zeige:
                print("==", na)
                print("\n".join(list(difflib.unified_diff(norm(va).split("\n"), norm(vb).split("\n"),
                                                          lineterm="", n=1))[2:30]))
    if len(alt) != len(neu):
        print(f"Anzahl Schnappschüsse: {rev} {len(alt)}, Arbeitsstand {len(neu)}")
        abweichend += 1
    print(f"{abweichend} von {len(neu)} Schnappschüssen abweichend ({rev} gegen Arbeitsstand)")
    return 1 if abweichend else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
