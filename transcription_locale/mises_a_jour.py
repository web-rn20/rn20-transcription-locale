"""Mise a jour au clic, optionnelle : desactivee par defaut.

Activee par transcription-locale raccourci --mises-a-jour, elle fait au plus une fois par
jour une requete vers l'API publique de GitHub pour lire la derniere release du depot. Elle
ne transmet rien d'autre que cette requete : ni audio, ni texte, ni identifiant. Une version
plus recente s'affiche dans le menu de la pilule ; l'installation ne se fait que sur un clic,
et jamais pendant un enregistrement ou une transcription.

Seules les releases sont suivies, jamais la branche principale : une version n'arrive chez
les utilisateurs que si elle a ete publiee. Les etiquettes v* sont protegees sur GitHub.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import __version__
from .reunion import dossier_etat

DEPOT = "web-rn20/rn20-transcription-locale"
API_RELEASE = f"https://api.github.com/repos/{DEPOT}/releases/latest"
SOURCE = f"git+https://github.com/{DEPOT}"
PAQUET = "rn20-transcription-locale"
INTERVALLE = 24 * 3600
DELAI_RESEAU = 5.0
ETIQUETTE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
NOTES_MAX = 300


@dataclass(frozen=True)
class Version:
    etiquette: str
    notes: str = ""

    @property
    def numero(self) -> str:
        return self.etiquette[1:]


# --- emplacements -------------------------------------------------------------------------

def fichier_choix() -> pathlib.Path:
    """Present = mises a jour activees. Absent par defaut."""
    return dossier_etat() / "mises-a-jour-activees"


def fichier_cache() -> pathlib.Path:
    return dossier_etat() / "derniere-release.json"


# --- fonctions pures ------------------------------------------------------------------------

def decoder_etiquette(etiquette: object) -> Optional[tuple[int, int, int]]:
    """Numero d'une etiquette vX.Y.Z, ou None : toute autre valeur venue du reseau est ignoree,
    elle finirait sinon dans une commande d'installation."""
    if not isinstance(etiquette, str):
        return None
    trouve = ETIQUETTE.match(etiquette)
    return tuple(int(n) for n in trouve.groups()) if trouve else None


def plus_recente(etiquette: str, installee: str = __version__) -> bool:
    distante = decoder_etiquette(etiquette)
    locale = decoder_etiquette(f"v{installee}")
    return distante is not None and locale is not None and distante > locale


def lire_release(reponse: dict) -> Optional[Version]:
    """Release publiee et valide, sinon None (brouillon, pre-version, etiquette inattendue)."""
    if reponse.get("draft") or reponse.get("prerelease"):
        return None
    etiquette = reponse.get("tag_name")
    if decoder_etiquette(etiquette) is None:
        return None
    notes = reponse.get("body") if isinstance(reponse.get("body"), str) else ""
    return Version(etiquette, " ".join(notes.split())[:NOTES_MAX])


def commande_installation(version: Version, uv: str) -> list[str]:
    if decoder_etiquette(version.etiquette) is None:  # deja filtre, verifie a nouveau ici
        raise ValueError(f"étiquette de version invalide : {version.etiquette!r}")
    # --reinstall-package : seul le code de l'outil est remplace, en quelques millisecondes.
    # --reinstall reconstruirait tout l'environnement (mlx compris) pendant plusieurs minutes,
    # sous l'enregistreur qui tourne et sous l'icone du Dock qui le relance.
    return [uv, "tool", "install", "--reinstall-package", PAQUET, f"{SOURCE}@{version.etiquette}"]


def cache_frais(cache: dict, maintenant: float, intervalle: float = INTERVALLE) -> bool:
    verifie = cache.get("verifie")
    return isinstance(verifie, (int, float)) and 0 <= maintenant - verifie < intervalle


# --- systeme --------------------------------------------------------------------------------

def activees() -> bool:
    return fichier_choix().is_file()


def choisir(actives: bool) -> None:
    if actives:
        fichier_choix().parent.mkdir(parents=True, exist_ok=True)
        fichier_choix().write_text("Mises à jour au clic activées par transcription-locale "
                                   "raccourci --mises-a-jour.\n", encoding="utf-8")
    else:
        fichier_choix().unlink(missing_ok=True)


def interroger_github() -> dict:
    requete = urllib.request.Request(API_RELEASE, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "rn20-transcription-locale",  # nom generique, aucune donnee personnelle
    })
    with urllib.request.urlopen(requete, timeout=DELAI_RESEAU) as reponse:
        return json.load(reponse)


def disponible(maintenant: Optional[float] = None) -> Optional[Version]:
    """Version plus recente que celle installee, ou None. Ne leve jamais : une verification
    ratee (hors ligne, GitHub indisponible) ne doit pas gener un enregistrement."""
    if not activees():
        return None
    maintenant = time.time() if maintenant is None else maintenant
    try:
        cache = json.loads(fichier_cache().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache, dict):  # fichier abime ou modifie a la main
        cache = {}
    if not cache_frais(cache, maintenant):
        try:
            release = lire_release(interroger_github())
            cache = {"verifie": maintenant,
                     "etiquette": release.etiquette if release else None,
                     "notes": release.notes if release else ""}
        except Exception as e:  # reseau, JSON, limite de GitHub, aucune release (404)
            print(f"vérification des mises à jour impossible : {e}", flush=True)
            # l'echec compte aussi : au plus une requete par jour, meme hors ligne. La
            # derniere version connue reste proposee.
            cache = {**cache, "verifie": maintenant}
        try:
            fichier_cache().parent.mkdir(parents=True, exist_ok=True)
            fichier_cache().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    etiquette = cache.get("etiquette")
    if isinstance(etiquette, str) and plus_recente(etiquette):
        return Version(etiquette, str(cache.get("notes", "")))
    return None


def trouver_uv() -> Optional[str]:
    chemin = os.pathsep.join([str(pathlib.Path.home() / ".local" / "bin"), "/opt/homebrew/bin",
                              "/usr/local/bin", os.environ.get("PATH", "")])
    return shutil.which("uv", path=chemin)
