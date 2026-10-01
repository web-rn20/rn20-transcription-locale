"""Separation des voix (qui parle quand) avec sherpa-onnx, sur le CPU."""
from __future__ import annotations

import sys
from typing import Optional

from .fusion import Passage
from .modeles import chemins_modeles

SEUIL_DEFAUT = 1.1
DUREE_MIN_PAROLE = 0.3  # secondes : en dessous, un passage de parole est ignore
DUREE_MIN_SILENCE = 0.5  # secondes : en dessous, deux passages d'une voix sont fusionnes


class ErreurDiarisation(Exception):
    """sherpa-onnx absent ou diarisation en echec."""


def diariser(echantillons, seuil: float = SEUIL_DEFAUT,
             nb_locuteurs: Optional[int] = None, progression: bool = True) -> list[Passage]:
    """Passages de parole et numero de locuteur, tries par heure de debut.

    seuil : distance entre empreintes vocales au-dela de laquelle deux voix sont
    separees. Plus il est haut, moins on obtient de locuteurs.
    nb_locuteurs : impose le nombre de locuteurs ; le seuil est alors ignore.
    """
    try:
        import sherpa_onnx
    except ImportError as e:
        raise ErreurDiarisation("sherpa-onnx est absent (voir le README).") from e
    segmentation, empreinte = chemins_modeles()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=segmentation)),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=empreinte),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=nb_locuteurs if nb_locuteurs else -1, threshold=float(seuil)),
        min_duration_on=DUREE_MIN_PAROLE,
        min_duration_off=DUREE_MIN_SILENCE,
    )
    if not config.validate():
        raise ErreurDiarisation("configuration sherpa-onnx invalide (modeles manquants ?)")
    moteur = sherpa_onnx.OfflineSpeakerDiarization(config)

    palier = [0]

    def afficher(traites: int, total: int, *_args) -> int:
        pourcentage = 100 * traites // max(total, 1)
        if pourcentage >= palier[0] + 20:
            palier[0] = pourcentage - pourcentage % 20
            print(f"  séparation des voix : {palier[0]} %", file=sys.stderr, flush=True)
        return 0

    if progression:
        resultat = moteur.process(echantillons, callback=afficher)
    else:
        resultat = moteur.process(echantillons)
    return [Passage(float(s.start), float(s.end), int(s.speaker))
            for s in resultat.sort_by_start_time()]
