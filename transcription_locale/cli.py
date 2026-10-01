"""Ligne de commande : transcrire, calibrer le seuil, regenerer, installer les modeles.

Une transcription produit, a cote du premier fichier audio (ou de --sortie) :
    BASE.16k.wav          audio converti, garde pour recalculer les locuteurs
    BASE.segments.json    texte brut, garde pour ne pas retranscrire
    BASE.txt, .srt, .json resultat, avec les locuteurs
Les commandes seuils et locuteurs reprennent BASE sans retranscrire.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from . import __version__
from .audio import ErreurAudio, duree, lire_wav_16k, preparer
from .diarisation import SEUIL_DEFAUT, ErreurDiarisation, diariser
from .fusion import attribuer, nombre_de_locuteurs, parts_de_parole, regrouper_tours
from .modeles import ErreurModele, chemins_modeles, dossier_modeles
from .sorties import ecrire_resultats, ecrire_segments, horodatage, lire_segments
from .transcription import LANGUE_DEFAUT, MODELE_DEFAUT, ErreurTranscription, transcrire

APERCU_TOURS = 8
APERCU_CARACTERES = 100
ERREURS = (ErreurAudio, ErreurDiarisation, ErreurModele, ErreurTranscription)


class ErreurUsage(Exception):
    """Fichiers de travail manquants ou option incoherente."""


def info(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def fichiers_de_travail(base: str) -> tuple[str, str]:
    return f"{base}.16k.wav", f"{base}.segments.json"


def base_par_defaut(premier_fichier: str) -> str:
    return os.path.splitext(premier_fichier)[0]


def lire_seuils(texte: str) -> list[float]:
    try:
        seuils = [float(v) for v in texte.split(",") if v.strip()]
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"seuils attendus sous la forme 0.9,1.0,1.1 : {texte}") from e
    if not seuils or any(s <= 0 for s in seuils):
        raise argparse.ArgumentTypeError(f"seuils strictement positifs attendus : {texte}")
    return seuils


def entier_positif(texte: str) -> int:
    valeur = int(texte)
    if valeur < 1:
        raise argparse.ArgumentTypeError("un nombre de locuteurs vaut au moins 1")
    return valeur


def reel_positif(texte: str) -> float:
    valeur = float(texte)
    if valeur <= 0:
        raise argparse.ArgumentTypeError("le seuil est strictement positif")
    return valeur


def exiger(base: str) -> tuple[str, str]:
    wav, segments = fichiers_de_travail(base)
    for chemin in (wav, segments):
        if not os.path.isfile(chemin):
            raise ErreurUsage(f"{chemin} introuvable : lancer d'abord la commande transcrire")
    return wav, segments


def conseil_un_seul_locuteur(base: str, nb_trouve: int, nb_impose: Optional[int]) -> Optional[str]:
    """Piste a suivre quand toutes les voix ont ete fondues en une seule."""
    if nb_trouve > 1 or nb_impose:
        return None
    return (f"Un seul locuteur trouvé. Si plusieurs personnes parlent, comparer les seuils : "
            f"transcription-locale seuils {base}")


def generer(base: str, wav: str, segments_json: str, seuil: float,
            nb_locuteurs: Optional[int]) -> list[str]:
    segments = lire_segments(segments_json)
    passages = diariser(lire_wav_16k(wav), seuil, nb_locuteurs)
    repliques = attribuer(segments, passages)
    nb_trouve = nombre_de_locuteurs(repliques)
    info(f"{nb_trouve} locuteurs, {len(regrouper_tours(repliques))} tours de parole")
    conseil = conseil_un_seul_locuteur(base, nb_trouve, nb_locuteurs)
    if conseil:
        info(conseil)
    # un nombre de locuteurs impose remplace le seuil : le resultat ne le mentionne pas
    return ecrire_resultats(base, wav, None if nb_locuteurs else seuil, repliques=repliques)


def commande_transcrire(args: argparse.Namespace) -> int:
    base = args.sortie or base_par_defaut(args.fichiers[0])
    wav, segments_json = fichiers_de_travail(base)
    info(f"Conversion en 16 kHz mono : {wav}")
    preparer(args.fichiers, wav)
    info(f"Transcription de {horodatage(duree(wav))} d'audio avec {args.modele}")
    debut = time.monotonic()
    segments = transcrire(wav, args.modele, args.langue)
    ecrire_segments(segments_json, wav, args.modele, segments)
    info(f"{len(segments)} segments en {horodatage(time.monotonic() - debut)}")
    if args.sans_locuteurs:
        ecrits = ecrire_resultats(base, wav, None, segments=segments)
    else:
        ecrits = generer(base, wav, segments_json, args.seuil, args.nb_locuteurs)
    print("\n".join(ecrits))
    return 0


def commande_seuils(args: argparse.Namespace) -> int:
    wav, segments_json = exiger(args.base)
    segments = lire_segments(segments_json)
    echantillons = lire_wav_16k(wav)
    for seuil in args.valeurs:
        repliques = attribuer(segments, diariser(echantillons, seuil, progression=False))
        tours = regrouper_tours(repliques)
        parts = ", ".join(f"{nom} {part:.0%}" for nom, part in parts_de_parole(repliques))
        print(f"\n=== seuil {seuil} : {nombre_de_locuteurs(repliques)} locuteurs, "
              f"{len(tours)} tours | parole : {parts}")
        for t in tours[:APERCU_TOURS]:
            print(f"  [{horodatage(t.debut)}] {t.locuteur} : {t.texte[:APERCU_CARACTERES]}")
    return 0


def commande_locuteurs(args: argparse.Namespace) -> int:
    wav, segments_json = exiger(args.base)
    print("\n".join(generer(args.base, wav, segments_json, args.seuil, args.nb_locuteurs)))
    return 0


def commande_modeles(_args: argparse.Namespace) -> int:
    for chemin in chemins_modeles():
        print(chemin)
    info(f"Modèles de séparation des voix prêts dans {dossier_modeles()}")
    return 0


def ajouter_options_locuteurs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seuil", type=reel_positif, default=SEUIL_DEFAUT,
                        help=f"seuil de regroupement des voix (défaut {SEUIL_DEFAUT}) ; "
                             "plus haut, moins de locuteurs")
    parser.add_argument("--nb-locuteurs", type=entier_positif, metavar="N",
                        help="impose le nombre de locuteurs (le seuil est alors ignoré)")


def construire_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcription-locale",
        description="Transcription et séparation des voix en local, sur Mac Apple Silicon.",
        epilog="Rien ne quitte la machine, hormis le téléchargement des modèles au premier lancement.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commandes = parser.add_subparsers(dest="commande", required=True, metavar="commande")

    p = commandes.add_parser("transcrire", help="transcrit un enregistrement et sépare les voix")
    p.add_argument("fichiers", nargs="+", metavar="audio",
                   help="fichier audio ; plusieurs fichiers sont mis bout à bout dans l'ordre")
    p.add_argument("-o", "--sortie", metavar="BASE",
                   help="chemin des fichiers produits, sans extension (défaut : nom du premier fichier)")
    p.add_argument("--modele", default=MODELE_DEFAUT, help=f"modèle Whisper MLX (défaut {MODELE_DEFAUT})")
    p.add_argument("--langue", default=LANGUE_DEFAUT, help=f"langue parlée (défaut {LANGUE_DEFAUT})")
    p.add_argument("--sans-locuteurs", action="store_true", help="texte seul, sans séparer les voix")
    ajouter_options_locuteurs(p)
    p.set_defaults(action=commande_transcrire)

    p = commandes.add_parser("seuils", help="compare plusieurs seuils sans retranscrire")
    p.add_argument("base", help="BASE d'une transcription déjà faite")
    p.add_argument("--valeurs", type=lire_seuils, default=lire_seuils("0.9,1.0,1.1,1.2,1.3"),
                   help="seuils à comparer (défaut 0.9,1.0,1.1,1.2,1.3)")
    p.set_defaults(action=commande_seuils)

    p = commandes.add_parser("locuteurs", help="régénère le résultat avec un autre seuil")
    p.add_argument("base", help="BASE d'une transcription déjà faite")
    ajouter_options_locuteurs(p)
    p.set_defaults(action=commande_locuteurs)

    p = commandes.add_parser("modeles", help="télécharge et vérifie les modèles de séparation des voix")
    p.set_defaults(action=commande_modeles)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = construire_parser().parse_args(argv)
    try:
        return args.action(args)
    except (ErreurUsage, *ERREURS) as e:
        print(f"transcription-locale : {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
