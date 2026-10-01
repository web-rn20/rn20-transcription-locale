"""Fusion du texte et des voix : chaque segment de texte recoit un locuteur.

Module pur, sans dependance : il ne manipule que des intervalles de temps.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Segment:
    """Morceau de texte transcrit, en secondes depuis le debut de l'audio."""

    debut: float
    fin: float
    texte: str


@dataclass(frozen=True)
class Passage:
    """Intervalle ou la diarisation entend un locuteur (numero brut du moteur)."""

    debut: float
    fin: float
    locuteur: int


@dataclass(frozen=True)
class Replique:
    """Segment de texte attribue a un locuteur nomme ("Locuteur 1", ...)."""

    debut: float
    fin: float
    locuteur: str
    texte: str


def locuteur_du_segment(segment: Segment, passages: list[Passage]) -> Optional[int]:
    """Locuteur qui chevauche le plus le segment.

    Sans aucun chevauchement, on prend le passage le plus proche du milieu du
    segment. None si la diarisation n'a rien entendu.
    """
    meilleur, recouvrement_max = None, 0.0
    for p in passages:
        recouvrement = min(segment.fin, p.fin) - max(segment.debut, p.debut)
        if recouvrement > recouvrement_max:
            meilleur, recouvrement_max = p.locuteur, recouvrement
    if meilleur is not None:
        return meilleur

    milieu = (segment.debut + segment.fin) / 2
    meilleur, distance_min = None, float("inf")
    for p in passages:
        distance = 0.0 if p.debut <= milieu <= p.fin else min(abs(milieu - p.debut), abs(milieu - p.fin))
        if distance < distance_min:
            meilleur, distance_min = p.locuteur, distance
    return meilleur


def attribuer(segments: list[Segment], passages: list[Passage]) -> list[Replique]:
    """Attribue un locuteur a chaque segment.

    Les locuteurs sont renommes "Locuteur 1", "Locuteur 2"... dans l'ordre ou ils
    prennent la parole pour la premiere fois. Sans passage, tout va au locuteur 1.
    """
    noms: dict[Optional[int], str] = {}
    repliques = []
    for s in segments:
        brut = locuteur_du_segment(s, passages)
        if brut not in noms:
            noms[brut] = f"Locuteur {len(noms) + 1}"
        repliques.append(Replique(s.debut, s.fin, noms[brut], s.texte))
    return repliques


def regrouper_tours(repliques: list[Replique]) -> list[Replique]:
    """Fusionne les repliques consecutives d'un meme locuteur en tours de parole."""
    tours: list[Replique] = []
    for r in repliques:
        if tours and tours[-1].locuteur == r.locuteur:
            precedent = tours[-1]
            tours[-1] = replace(precedent, fin=r.fin, texte=f"{precedent.texte} {r.texte}")
        else:
            tours.append(r)
    return tours


def parts_de_parole(repliques: list[Replique]) -> list[tuple[str, float]]:
    """Part du temps de parole de chaque locuteur, de la plus grande a la plus petite."""
    durees: dict[str, float] = {}
    for r in repliques:
        durees[r.locuteur] = durees.get(r.locuteur, 0.0) + (r.fin - r.debut)
    total = sum(durees.values()) or 1.0
    return sorted(((nom, d / total) for nom, d in durees.items()), key=lambda x: -x[1])


def nombre_de_locuteurs(repliques: list[Replique]) -> int:
    return len({r.locuteur for r in repliques})
