"""Transcription avec MLX-Whisper, sur le GPU d'un Mac Apple Silicon."""
from __future__ import annotations

import os
import re
from typing import Optional

from .fusion import Segment

MODELE_DEFAUT = "mlx-community/whisper-large-v3-mlx"
LANGUE_DEFAUT = "fr"


# Generiques de sous-titrage appris par Whisper, qu'il recite sur les silences. Retires
# seulement quand ils forment une phrase entiere en fin de segment : une phrase qui parle
# de sous-titres au milieu d'une autre n'est pas touchee.
HALLUCINATIONS = re.compile(
    r"(?:^|(?<=[.!?]))\s*sous-titr(?:age|es|é)[^.!?]*?"
    r"(?:\bST'? ?\d+|amara(?:\.org)?|soustitreur(?:\.com)?|radio-canada|soci[ée]t[ée] radio)"
    r"[^.!?]*[.!?]?\s*$",
    re.IGNORECASE)


def sans_hallucinations(texte: str) -> str:
    if not HALLUCINATIONS.search(texte):
        return texte
    return re.sub(r"\s{2,}", " ", HALLUCINATIONS.sub("", texte)).strip()


class ErreurTranscription(Exception):
    """MLX indisponible sur cette machine, ou transcription en echec."""


# Version figee du modele par defaut : le depot Hugging Face peut changer, pas ce que
# l'outil telecharge. Chaque fichier est verifie par son empreinte SHA-256 apres
# telechargement, comme les modeles de separation des voix (voir modeles.py).
REVISION_WHISPER = "49e6aa286ad60c14352c404340ded53710378a11"
EMPREINTES_WHISPER = {
    "config.json": "34982ce6ae286095000f82ae9583b3431639e8b092bf60c961f203745e6500e3",
    "weights.npz": "05ff791ce3630fae47e7c51004e9666204d786246ec07cac6110af768099b40d",
}


def dossier_whisper(modele: str = MODELE_DEFAUT, telecharger: bool = False) -> Optional[str]:
    """Dossier local du modele (version figee pour le modele par defaut), telecharge s'il
    le faut et si telecharger est vrai. None s'il manque et qu'on ne telecharge pas."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        raise ErreurTranscription("huggingface_hub est absent : réinstaller l'outil.") from e
    revision = REVISION_WHISPER if modele == MODELE_DEFAUT else None
    try:
        return snapshot_download(modele, revision=revision, local_files_only=not telecharger)
    except Exception as e:  # absent du cache, reseau, disque plein, depot indisponible
        if not telecharger:
            return None
        raise ErreurTranscription(f"téléchargement du modèle Whisper impossible : {e}") from e


def fichiers_whisper_complets(dossier: str) -> bool:
    """Les fichiers attendus sont la, en entier : un telechargement interrompu laisse un
    dossier sans les poids. Pour le modele par defaut, le cache de Hugging Face nomme
    chaque gros fichier d'apres son empreinte, ce qui se verifie sans le relire."""
    for nom, empreinte in EMPREINTES_WHISPER.items():
        chemin = os.path.join(dossier, nom)
        if not os.path.isfile(chemin):
            return False
        if nom == "weights.npz" and os.path.basename(os.path.realpath(chemin)) != empreinte:
            return False
    return True


def whisper_en_cache(modele: str = MODELE_DEFAUT) -> bool:
    """Le modele Whisper est-il deja sur le disque, complet ? Sans reseau."""
    try:
        dossier = dossier_whisper(modele)
    except ErreurTranscription:
        return False
    if dossier is None:
        return False
    if modele != MODELE_DEFAUT:
        return any(os.path.isfile(os.path.join(dossier, n)) for n in ("weights.npz", "weights.safetensors"))
    return fichiers_whisper_complets(dossier)


def verifier_whisper(dossier: str) -> None:
    """Empreinte SHA-256 de chaque fichier du modele par defaut, relu en entier."""
    from .modeles import sha256

    for nom, attendue in EMPREINTES_WHISPER.items():
        chemin = os.path.join(dossier, nom)
        if not os.path.isfile(chemin):
            raise ErreurTranscription(f"modèle Whisper incomplet : {nom} manque dans {dossier}")
        obtenue = sha256(chemin)
        if obtenue != attendue:
            raise ErreurTranscription(
                f"empreinte inattendue pour {nom} du modèle Whisper : {obtenue}. Supprimer "
                f"{os.path.dirname(os.path.dirname(dossier))} puis relancer "
                f"transcription-locale modeles.")


def preparer_whisper(modele: str = MODELE_DEFAUT) -> str:
    """Telecharge le modele Whisper s'il manque (environ 3 Go, progression affichee), le
    verifie et renvoie son dossier. La transcription lit ensuite ce dossier, hors ligne."""
    dossier = dossier_whisper(modele, telecharger=True)
    if modele == MODELE_DEFAUT:
        verifier_whisper(dossier)
    return dossier


def transcrire(wav: str, modele: str = MODELE_DEFAUT, langue: str = LANGUE_DEFAUT) -> list[Segment]:
    """Segments de texte d'un WAV 16 kHz mono.

    Le modele Whisper est telecharge depuis Hugging Face au premier lancement (version
    figee, verifiee), puis reste en cache. condition_on_previous_text=False evite qu'une erreur de
    transcription se propage et boucle sur les longs enregistrements.
    """
    try:
        import mlx_whisper
    except ImportError as e:
        raise ErreurTranscription(
            "mlx-whisper est absent. Il ne s'installe que sur un Mac Apple Silicon "
            "(voir le README).") from e
    # le dossier local de la version figee, jamais le depot en ligne a sa derniere version
    chemin = dossier_whisper(modele)
    if chemin is None or (modele == MODELE_DEFAUT and not fichiers_whisper_complets(chemin)):
        chemin = preparer_whisper(modele)
    resultat = mlx_whisper.transcribe(
        wav, path_or_hf_repo=chemin, language=langue,
        condition_on_previous_text=False, verbose=False)
    segments = []
    for s in resultat["segments"]:
        texte = sans_hallucinations(s["text"].strip())
        if texte:
            segments.append(Segment(float(s["start"]), float(s["end"]), texte))
    return segments
