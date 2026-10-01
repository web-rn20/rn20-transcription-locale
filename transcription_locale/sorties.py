"""Fichiers produits : texte lisible par tours de parole, sous-titres SRT, JSON.

Module pur, sans dependance.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .fusion import Replique, Segment, nombre_de_locuteurs, regrouper_tours

LARGEUR_FILET = 70


def horodatage(secondes: float) -> str:
    """H:MM:SS, arrondi a la seconde inferieure."""
    s = int(secondes)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def horodatage_srt(secondes: float) -> str:
    """HH:MM:SS,mmm, le format des sous-titres SRT."""
    ms = int(round(secondes * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def texte_lisible(source: str, repliques: list[Replique]) -> str:
    """Transcription par tours de parole, avec l'heure de debut de chaque tour."""
    entete = (f"Transcription : {source}\n"
              f"Locuteurs : {nombre_de_locuteurs(repliques)}\n"
              f"{'=' * LARGEUR_FILET}\n\n")
    corps = "".join(f"[{horodatage(t.debut)}] {t.locuteur} :\n{t.texte}\n\n"
                    for t in regrouper_tours(repliques))
    return entete + corps


def texte_sans_locuteurs(source: str, segments: list[Segment]) -> str:
    entete = f"Transcription : {source}\n{'=' * LARGEUR_FILET}\n\n"
    return entete + "".join(f"[{horodatage(s.debut)}] {s.texte}\n" for s in segments)


def sous_titres(elements: list) -> str:
    """SRT : un sous-titre par segment, prefixe du locuteur s'il est connu."""
    blocs = []
    for i, e in enumerate(elements, 1):
        texte = f"{e.locuteur} : {e.texte}" if isinstance(e, Replique) else e.texte
        blocs.append(f"{i}\n{horodatage_srt(e.debut)} --> {horodatage_srt(e.fin)}\n{texte}\n")
    return "\n".join(blocs)


def resultat_json(source: str, seuil: Optional[float], repliques: list[Replique]) -> dict:
    return {
        "source": source,
        "seuil": seuil,
        "locuteurs": nombre_de_locuteurs(repliques),
        "segments": [
            {"debut": r.debut, "fin": r.fin, "locuteur": r.locuteur, "texte": r.texte}
            for r in repliques
        ],
    }


def ecrire(chemin: str, contenu: str) -> str:
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)
    return chemin


def ecrire_resultats(base: str, source: str, seuil: Optional[float],
                     repliques: Optional[list[Replique]] = None,
                     segments: Optional[list[Segment]] = None) -> list[str]:
    """Ecrit base.txt, base.srt et base.json ; renvoie les chemins ecrits.

    Avec des repliques, la sortie porte les locuteurs ; sinon, seulement le texte.
    """
    nom = os.path.basename(source)
    if repliques is not None:
        txt, srt = texte_lisible(nom, repliques), sous_titres(repliques)
        donnees = resultat_json(nom, seuil, repliques)
    else:
        segments = segments or []
        txt, srt = texte_sans_locuteurs(nom, segments), sous_titres(segments)
        donnees = {"source": nom, "segments": [
            {"debut": s.debut, "fin": s.fin, "texte": s.texte} for s in segments]}
    return [
        ecrire(f"{base}.txt", txt),
        ecrire(f"{base}.srt", srt),
        ecrire(f"{base}.json", json.dumps(donnees, ensure_ascii=False, indent=1) + "\n"),
    ]


def ecrire_segments(chemin: str, source: str, modele: str, segments: list[Segment]) -> str:
    """Cache de la transcription brute, relu par les commandes seuils et locuteurs."""
    donnees = {"source": os.path.basename(source), "modele": modele, "segments": [
        {"debut": s.debut, "fin": s.fin, "texte": s.texte} for s in segments]}
    return ecrire(chemin, json.dumps(donnees, ensure_ascii=False, indent=1) + "\n")


def lire_segments(chemin: str) -> list[Segment]:
    with open(chemin, encoding="utf-8") as f:
        donnees = json.load(f)
    return [Segment(s["debut"], s["fin"], s["texte"]) for s in donnees["segments"]]
