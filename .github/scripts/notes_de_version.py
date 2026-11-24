"""Verifie qu'une etiquette vX.Y.Z correspond a la version du paquet et au journal des
versions, puis ecrit sur la sortie standard les notes de cette version (la section du
CHANGELOG). Code de sortie 1, avec la raison, si l'un des trois ne concorde pas.

Usage : python3 .github/scripts/notes_de_version.py v0.4.1 [racine du depot]
"""
import pathlib
import re
import sys


def notes(etiquette: str, racine: pathlib.Path) -> str:
    trouve = re.fullmatch(r"v(\d+\.\d+\.\d+)", etiquette)
    if not trouve:
        raise ValueError(f"étiquette {etiquette!r} : attendu vX.Y.Z")
    numero = trouve.group(1)
    init = (racine / "transcription_locale" / "__init__.py").read_text(encoding="utf-8")
    version = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    if not version or version.group(1) != numero:
        raise ValueError(f"__version__ vaut {version.group(1) if version else '?'}, "
                         f"l'étiquette {etiquette}")
    journal = (racine / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(rf"^## {re.escape(numero)} \(.*?\)\n(.*?)(?=^## |\Z)", journal, re.M | re.S)
    if not section or not section.group(1).strip():
        raise ValueError(f"CHANGELOG.md n'a pas de section « ## {numero} (date) »")
    return section.group(1).strip() + "\n"


if __name__ == "__main__":
    racine = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(".")
    try:
        sys.stdout.write(notes(sys.argv[1], racine))
    except (ValueError, OSError, IndexError) as e:
        print(f"release refusée : {e}", file=sys.stderr)
        sys.exit(1)
