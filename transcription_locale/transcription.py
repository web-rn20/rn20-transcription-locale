"""Transcription avec MLX-Whisper, sur le GPU d'un Mac Apple Silicon."""
from __future__ import annotations

from .fusion import Segment

MODELE_DEFAUT = "mlx-community/whisper-large-v3-mlx"
LANGUE_DEFAUT = "fr"


class ErreurTranscription(Exception):
    """MLX indisponible sur cette machine, ou transcription en echec."""


def transcrire(wav: str, modele: str = MODELE_DEFAUT, langue: str = LANGUE_DEFAUT) -> list[Segment]:
    """Segments de texte d'un WAV 16 kHz mono.

    Le modele Whisper est telecharge depuis Hugging Face au premier lancement,
    puis reste en cache. condition_on_previous_text=False evite qu'une erreur de
    transcription se propage et boucle sur les longs enregistrements.
    """
    try:
        import mlx_whisper
    except ImportError as e:
        raise ErreurTranscription(
            "mlx-whisper est absent. Il ne s'installe que sur un Mac Apple Silicon "
            "(voir le README).") from e
    resultat = mlx_whisper.transcribe(
        wav, path_or_hf_repo=modele, language=langue,
        condition_on_previous_text=False, verbose=False)
    segments = []
    for s in resultat["segments"]:
        texte = s["text"].strip()
        if texte:
            segments.append(Segment(float(s["start"]), float(s["end"]), texte))
    return segments
