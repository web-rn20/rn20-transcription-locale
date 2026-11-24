"""Commande verifier : ce qu'il faut pour transcrire et pour Reunion, et comment le reparer.

Rien n'est installe ni telecharge ici : chaque point est constate, et ce qui manque est
donne avec la commande qui le repare. Les autorisations de macOS (enregistrement de l'ecran,
micro, notifications) ne se lisent pas depuis le Terminal : l'essai de 10 secondes de
Reunion les verifie.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from . import __version__


@dataclass(frozen=True)
class Point:
    nom: str
    ok: bool
    detail: str = ""
    remede: str = ""
    requis: bool = True  # un point non requis manquant n'empeche pas de transcrire


def chemin_outils() -> str:
    return os.pathsep.join(["/opt/homebrew/bin", "/usr/local/bin",
                            os.path.expanduser("~/.local/bin"), os.environ.get("PATH", "")])


def trouver(programme: str) -> Optional[str]:
    return shutil.which(programme, path=chemin_outils())


def swiftc_present() -> bool:
    try:
        return subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True).returncode == 0
    except OSError:
        return False


def dans_le_dock(app) -> bool:
    from .reunion import dock_contient

    try:
        actuelles = subprocess.run(["defaults", "read", "com.apple.dock", "persistent-apps"],
                                   capture_output=True, text=True).stdout
    except OSError:
        return False
    return dock_contient(actuelles, app)


def points(machine: str, version_macos: str, programme: Callable[[str], Optional[str]],
           swiftc: bool, app_ok: bool, dock: bool, whisper: bool, voix: bool,
           mises_a_jour: bool) -> list[Point]:
    """Fonction pure : la liste des points, d'apres ce qui a ete constate."""
    from .reunion import MACOS_MINIMUM, version_suffisante

    minimum = ".".join(str(n) for n in MACOS_MINIMUM)
    return [
        Point("Mac Apple Silicon", machine == "arm64", machine,
              "L'outil demande un Mac M1 ou plus récent."),
        Point(f"macOS {minimum} ou plus récent", version_suffisante(version_macos),
              f"macOS {version_macos or '?'}",
              "Mettre à jour macOS : Réglages > Général > Mise à jour de logiciels.",
              requis=False),
        Point("ffmpeg", bool(programme("ffmpeg") and programme("ffprobe")), "",
              "brew install ffmpeg"),
        Point("Outils de développement d'Apple", swiftc,
              "compilent l'application Réunion", "xcode-select --install", requis=False),
        Point("Application Réunion", app_ok, "~/Applications/Réunion.app",
              "transcription-locale raccourci", requis=False),
        Point("Réunion dans le Dock", dock, "", "transcription-locale raccourci", requis=False),
        Point("Modèle Whisper", whisper, "environ 3 Go, téléchargé une fois",
              "transcription-locale modeles"),
        Point("Modèles de séparation des voix", voix, "environ 110 Mo",
              "transcription-locale modeles"),
        Point("Mises à jour au clic", True,
              "activées" if mises_a_jour else
              "désactivées (transcription-locale raccourci --mises-a-jour pour les activer)",
              requis=False),
    ]


def constater() -> list[Point]:
    from . import mises_a_jour
    from .modeles import modeles_presents
    from .reunion import app_en_place, chemin_app
    from .transcription import whisper_en_cache

    app = chemin_app()
    return points(platform.machine(), platform.mac_ver()[0] if sys.platform == "darwin" else "",
                  trouver, swiftc_present(), app_en_place(app), dans_le_dock(app),
                  whisper_en_cache(), modeles_presents(), mises_a_jour.activees())


def rapport(liste: list[Point]) -> tuple[str, bool]:
    """(texte affiche, tout ce qui est requis est en place)."""
    lignes = [f"transcription-locale {__version__}", ""]
    for p in liste:
        detail = f" ({p.detail})" if p.detail else ""
        suite = "" if p.ok else (" : à faire" if p.requis else " : pour Réunion")
        lignes.append(f"  {'✓' if p.ok else '✗'} {p.nom}{detail}{suite}")
        if not p.ok and p.remede:
            lignes.append(f"      → {p.remede}")
    lignes += ["", "Les autorisations de macOS (enregistrement de l'écran, micro, notifications) "
               "se vérifient avec l'essai de 10 secondes, proposé au premier clic sur Réunion, "
               "puis dans le menu du badge vert ou gris."]
    return "\n".join(lignes), all(p.ok for p in liste if p.requis)
