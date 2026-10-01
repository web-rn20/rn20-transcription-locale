"""Modeles de separation des voix : telechargement verifie et emplacement local.

Les modeles viennent des publications du projet sherpa-onnx sur GitHub, sans
compte. Chaque fichier est verifie par son empreinte SHA-256 avant usage.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass

VARIABLE_DOSSIER = "TRANSCRIPTION_LOCALE_MODELES"
DEPOT = "https://github.com/k2-fsa/sherpa-onnx/releases/download"


@dataclass(frozen=True)
class Modele:
    nom: str
    url: str
    sha256: str
    fichier: str  # chemin du modele dans le dossier, une fois installe
    archive: bool = False


SEGMENTATION = Modele(
    nom="segmentation pyannote 3.0 (MIT)",
    url=f"{DEPOT}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    sha256="24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
    fichier="sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
    archive=True,
)
# "recongition" : coquille d'origine dans le nom de la publication sherpa-onnx
EMPREINTE = Modele(
    nom="empreinte vocale NVIDIA NeMo TitaNet large (CC-BY-4.0)",
    url=f"{DEPOT}/speaker-recongition-models/nemo_en_titanet_large.onnx",
    sha256="d51abcf31717ef28162f26acb9d44dd4127c3d44c9b8624f699f3425daca8e77",
    fichier="nemo_en_titanet_large.onnx",
)
MODELES = (SEGMENTATION, EMPREINTE)


class ErreurModele(Exception):
    """Telechargement impossible, empreinte inattendue ou archive suspecte."""


def dossier_modeles() -> str:
    defaut = os.path.join(os.path.expanduser("~"), ".cache", "rn20-transcription-locale")
    return os.environ.get(VARIABLE_DOSSIER) or defaut


def sha256(chemin: str) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(url: str, cible: str, empreinte: str) -> None:
    """Telecharge url dans cible, et refuse le fichier si l'empreinte differe."""
    provisoire = cible + ".partiel"
    try:
        with urllib.request.urlopen(url, timeout=60) as reponse, open(provisoire, "wb") as f:
            shutil.copyfileobj(reponse, f, length=1 << 20)
    except OSError as e:
        raise ErreurModele(f"telechargement impossible : {url} ({e})") from e
    obtenue = sha256(provisoire)
    if obtenue != empreinte:
        os.remove(provisoire)
        raise ErreurModele(f"empreinte inattendue pour {url} : {obtenue}")
    os.replace(provisoire, cible)


def extraire(archive: str, dossier: str) -> None:
    """Extrait une archive tar en refusant tout chemin qui sortirait du dossier."""
    racine = os.path.realpath(dossier)
    with tarfile.open(archive) as tar:
        for membre in tar.getmembers():
            destination = os.path.realpath(os.path.join(dossier, membre.name))
            if os.path.commonpath([racine, destination]) != racine or membre.issym() or membre.islnk():
                raise ErreurModele(f"archive refusee, entree suspecte : {membre.name}")
        if sys.version_info >= (3, 12):
            tar.extractall(dossier, filter="data")
        else:
            tar.extractall(dossier)


def installer(modele: Modele, dossier: str) -> str:
    """Chemin du modele, apres l'avoir telecharge et verifie s'il manque."""
    chemin = os.path.join(dossier, modele.fichier)
    if os.path.isfile(chemin):
        return chemin
    os.makedirs(dossier, exist_ok=True)
    print(f"Téléchargement du modèle : {modele.nom}", file=sys.stderr, flush=True)
    if modele.archive:
        with tempfile.TemporaryDirectory(dir=dossier) as tmp:
            archive = os.path.join(tmp, os.path.basename(modele.url))
            telecharger(modele.url, archive, modele.sha256)
            extraire(archive, dossier)
    else:
        telecharger(modele.url, chemin, modele.sha256)
    if not os.path.isfile(chemin):
        raise ErreurModele(f"{modele.fichier} absent apres installation")
    return chemin


def chemins_modeles() -> tuple[str, str]:
    """(segmentation, empreinte) : chemins locaux, telecharges au premier usage."""
    dossier = dossier_modeles()
    return installer(SEGMENTATION, dossier), installer(EMPREINTE, dossier)
