"""Preparation de l'audio avec ffmpeg : conversion en WAV 16 kHz mono, assemblage.

ffmpeg est appele comme programme externe ; il n'est pas embarque.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from typing import Sequence

FREQUENCE = 16_000
OPTIONS_SORTIE = ["-ac", "1", "-ar", str(FREQUENCE), "-c:a", "pcm_s16le"]


class ErreurAudio(Exception):
    """Fichier audio introuvable ou illisible, ou ffmpeg absent."""


def verifier_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise ErreurAudio("ffmpeg introuvable. Sur Mac : brew install ffmpeg")


def liste_concat(entrees: Sequence[str]) -> str:
    """Contenu d'une liste pour le demultiplexeur concat de ffmpeg.

    Les chemins sont absolus et leurs apostrophes echappees.
    """
    lignes = []
    for e in entrees:
        chemin = os.path.abspath(e).replace("'", "'\\''")
        lignes.append(f"file '{chemin}'")
    return "\n".join(lignes) + "\n"


def commande_conversion(entrees: Sequence[str], cible: str, liste: str = "") -> list[str]:
    """Commande ffmpeg : une entree convertie, ou plusieurs mises bout a bout."""
    base = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if len(entrees) == 1:
        return base + ["-i", entrees[0]] + OPTIONS_SORTIE + [cible]
    return base + ["-f", "concat", "-safe", "0", "-i", liste] + OPTIONS_SORTIE + [cible]


def preparer(entrees: Sequence[str], cible: str) -> str:
    """Convertit une ou plusieurs pistes en un seul WAV 16 kHz mono, 16 bits.

    Plusieurs entrees sont mises bout a bout dans l'ordre donne : c'est le cas
    d'une session que l'enregistreur a coupee en plusieurs fichiers. Elles doivent
    alors venir du meme appareil (meme format).
    """
    if not entrees:
        raise ErreurAudio("aucun fichier audio")
    for e in entrees:
        if not os.path.isfile(e):
            raise ErreurAudio(f"{e} : fichier introuvable")
        if os.path.abspath(e) == os.path.abspath(cible):
            raise ErreurAudio(f"{e} : le fichier converti ecraserait l'entree, choisir une autre sortie")
    verifier_ffmpeg()
    with tempfile.TemporaryDirectory() as dossier:
        liste = ""
        if len(entrees) > 1:
            liste = os.path.join(dossier, "liste.txt")
            with open(liste, "w", encoding="utf-8") as f:
                f.write(liste_concat(entrees))
        resultat = subprocess.run(commande_conversion(entrees, cible, liste),
                                  capture_output=True, text=True)
    if resultat.returncode != 0:
        detail = (resultat.stderr.strip().splitlines() or ["erreur inconnue"])[-1]
        raise ErreurAudio(f"ffmpeg n'a pas pu convertir l'audio : {detail}")
    return cible


def lire_wav_16k(chemin: str):
    """Echantillons d'un WAV 16 kHz mono 16 bits, en flottants entre -1 et 1."""
    import numpy as np

    try:
        with wave.open(chemin, "rb") as w:
            format_ok = (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, FREQUENCE, 2)
            donnees = w.readframes(w.getnframes())
    except (FileNotFoundError, wave.Error) as e:
        raise ErreurAudio(f"{chemin} : WAV illisible ({e})") from e
    if not format_ok:
        raise ErreurAudio(f"{chemin} : WAV attendu en 16 kHz mono 16 bits")
    return np.frombuffer(donnees, dtype=np.int16).astype(np.float32) / 32768.0


def duree(chemin: str) -> float:
    """Duree d'un WAV, en secondes."""
    with wave.open(chemin, "rb") as w:
        return w.getnframes() / w.getframerate()
