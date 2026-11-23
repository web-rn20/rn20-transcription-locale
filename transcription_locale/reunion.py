"""Enregistrement de reunion en un clic, sans logiciel tiers.

La commande raccourci pose une fois pour toutes l'application ~/Applications/Reunion.app,
epinglee au Dock. Elle ne la reconstruit pas si elle existe deja : macOS rattache
l'autorisation d'enregistrer a la signature de l'application, une application refaite
perdrait cette autorisation.

La commande reunion (lancee par l'icone du Dock) bascule :
    aucun enregistreur actif     -> demarre l'enregistreur (module enregistreur)
    enregistrement en cours      -> l'arrete, la transcription suit
    transcription en cours       -> l'enregistreur le rappelle par une notification
    transcription prete ou echec -> ferme l'ancien enregistreur et en demarre un nouveau

Ce module ne depend pas de PyObjC : la partie macOS vit dans enregistreur.py et badge.py.
Aucun audio ne quitte la machine.
"""
from __future__ import annotations

import datetime
import fcntl
import os
import pathlib
import platform
import plistlib
import signal
import subprocess
import sys
import textwrap
import time
import unicodedata
from typing import Optional
from urllib.parse import quote

TITRE = "Réunion"
ID_APP = "digital.rn20.reunion"
MODULE_ENREGISTREUR = "transcription_locale.enregistreur"
MACOS_MINIMUM = (15, 0)
LARGEUR_MENU = 40
DELAI_FERMETURE = 3.0
DELAI_DEMARRAGE = 20.0  # imports PyObjC compris
EXTENSION_AUDIO = ".m4a"
USAGE_MICRO = "Réunion enregistre votre micro pendant une visio, pour la transcrire sur ce Mac."


class ErreurReunion(Exception):
    """macOS trop ancien, application introuvable ou enregistreur injoignable."""


# --- emplacements -------------------------------------------------------------------------

def dossier_enregistrements() -> pathlib.Path:
    return pathlib.Path.home() / "Movies" / "Reunions"


def chemin_app() -> pathlib.Path:
    return pathlib.Path.home() / "Applications" / f"{TITRE}.app"


def dossier_journaux() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Logs" / "transcription-locale"


def dossier_etat() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Application Support" / "transcription-locale"


def fichier_pid() -> pathlib.Path:
    """Ecrit par l'enregistreur une fois pret a recevoir le signal du Dock."""
    return dossier_etat() / "reunion.pid"


def fichier_verrou() -> pathlib.Path:
    return dossier_etat() / "bascule.lock"


# --- fonctions pures ------------------------------------------------------------------------

def nom_enregistrement(moment: datetime.datetime) -> str:
    return moment.strftime("Reunion %Y-%m-%d %H-%M-%S") + ".mov"


def duree_lisible(secondes: float) -> str:
    minutes, s = divmod(int(secondes), 60)
    heures, minutes = divmod(minutes, 60)
    return f"{heures} h {minutes:02d} min" if heures else f"{minutes} min {s:02d} s"


def chrono(secondes: float) -> str:
    """Duree courte pour la pilule de la barre des menus : 0:42, 12:04, 1:02:04."""
    minutes, s = divmod(int(secondes), 60)
    heures, minutes = divmod(minutes, 60)
    return f"{heures}:{minutes:02d}:{s:02d}" if heures else f"{minutes}:{s:02d}"


def decouper(texte: str, largeur: int = LARGEUR_MENU) -> list[str]:
    """Lignes courtes pour le menu de la barre d'etat, qui sinon s'etire jusqu'au bord de l'ecran."""
    return textwrap.wrap(texte, largeur) or [""]


def version_suffisante(version: str, minimum: tuple[int, int] = MACOS_MINIMUM) -> bool:
    morceaux = [int(m) for m in version.split(".")[:2] if m.isdigit()]
    return tuple(morceaux + [0] * (2 - len(morceaux))) >= minimum


def chaine_applescript(texte: str) -> str:
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def script_applet(python: str) -> str:
    """AppleScript de l'icone du Dock : bascule, et affiche l'erreur si la commande echoue.

    La commande transcription-locale du PATH passe en premier : l'application n'est jamais
    refaite (elle perdrait son autorisation), elle ne doit donc pas dependre d'un interpreteur
    fige. Le Python de l'installation ne sert que de secours.
    """
    shell = ('export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"; '
             'if command -v transcription-locale >/dev/null 2>&1; '
             'then exec transcription-locale reunion; else exec ')
    commande = (f'{chaine_applescript(shell)} & quoted form of {chaine_applescript(python)} & '
                f'" -m transcription_locale reunion; fi"')
    return "\n".join([
        "on run",
        "\ttry",
        f"\t\tdo shell script {commande}",
        "\ton error erreur",  # pas "message" : mot reserve de display alert
        f"\t\tdisplay alert {chaine_applescript(TITRE)} message erreur as critical",
        "\tend try",
        "end run",
        "",
    ])


def info_app(info: dict) -> dict:
    """Info.plist de l'applet : un identifiant et un nom, pour que macOS affiche Reunion
    (et non "applet") dans ses demandes d'autorisation et ses reglages."""
    info = dict(info)
    info.pop("CFBundleIconName", None)  # sinon macOS prefere l'icone d'Assets.car
    info["CFBundleIdentifier"] = ID_APP
    info["CFBundleName"] = TITRE
    info["CFBundleDisplayName"] = TITRE
    info["NSMicrophoneUsageDescription"] = USAGE_MICRO
    return info


def commande_extraction(video: str, audio: str, nb_pistes: int) -> list[str]:
    """ffmpeg : le son seul, sans la video. Plusieurs pistes (ordinateur et micro separes)
    sont mixees en une, pour que personne ne manque a la transcription."""
    debut = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", video, "-vn"]
    if nb_pistes <= 1:
        return debut + ["-c:a", "copy", audio]
    return debut + ["-filter_complex", f"amix=inputs={nb_pistes}:normalize=0",
                    "-c:a", "aac", "-b:a", "160k", audio]


def urls_dock(app: pathlib.Path) -> list[str]:
    """URL de l'application telle que le Dock peut l'enregistrer (accents composes ou non)."""
    urls = []
    for forme in ("NFC", "NFD"):
        chemin = unicodedata.normalize(forme, str(app))
        urls.append("file://" + quote(chemin) + "/")
    return urls


def dock_contient(persistent_apps: str, app: pathlib.Path) -> bool:
    return any(url in persistent_apps for url in urls_dock(app))


def entree_dock(app: pathlib.Path) -> str:
    return ("<dict><key>tile-data</key><dict><key>file-data</key><dict>"
            f"<key>_CFURLString</key><string>{urls_dock(app)[0]}</string>"
            "<key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>")


# --- systeme --------------------------------------------------------------------------------

def verifier_macos() -> None:
    version = platform.mac_ver()[0]
    if sys.platform != "darwin" or not version_suffisante(version):
        raise ErreurReunion(f"l'enregistrement des réunions demande macOS 15 ou plus récent "
                            f"(trouvé : {version or sys.platform})")


def notifier(message: str) -> None:
    subprocess.run(["osascript", "-e", "on run argv",
                    "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                    "-e", "end run", message, TITRE], capture_output=True)


def environnement() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin")
    return env


def enregistreur_actif() -> Optional[int]:
    """PID de l'enregistreur s'il tourne. Un fichier PID perime (redemarrage, plantage,
    PID repris par un autre programme) est ignore."""
    try:
        pid = int(fichier_pid().read_text().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return None
    commande = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                              capture_output=True, text=True).stdout
    return pid if MODULE_ENREGISTREUR in commande else None


def lancer_enregistreur(delai: float = DELAI_DEMARRAGE) -> bool:
    """Enregistreur detache, puis attente qu'il soit pret (fichier PID ecrit). Faux si
    l'attente depasse le delai : il demarre encore, ou il a echoue (voir reunion.log)."""
    journaux = dossier_journaux()
    journaux.mkdir(parents=True, exist_ok=True)
    try:
        with open(journaux / "reunion.log", "a", encoding="utf-8") as sortie:
            processus = subprocess.Popen(
                [sys.executable, "-m", MODULE_ENREGISTREUR], stdin=subprocess.DEVNULL,
                stdout=sortie, stderr=subprocess.STDOUT, start_new_session=True,
                env=environnement())
    except OSError as e:
        raise ErreurReunion(f"lancement de l'enregistreur impossible : {e}") from e
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if enregistreur_actif() == processus.pid:
            return True
        if processus.poll() is not None:
            raise ErreurReunion(f"l'enregistreur s'est arrêté au démarrage : voir "
                                f"{journaux / 'reunion.log'}")
        time.sleep(0.1)
    return False


def attendre_fin(pid: int, delai: float = DELAI_FERMETURE) -> bool:
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.1)
    return False


def basculer() -> str:
    """Un seul clic a la fois : un double clic attend la fin du premier, qui a laisse
    l'enregistreur pret a recevoir le signal. Jamais deux enregistreurs en meme temps."""
    verifier_macos()
    dossier_etat().mkdir(parents=True, exist_ok=True)
    with open(fichier_verrou(), "w") as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        pid = enregistreur_actif()
        if pid is None:
            return ("Démarrage de l'enregistrement." if lancer_enregistreur()
                    else "Démarrage en cours.")
        os.kill(pid, signal.SIGUSR1)
        # l'enregistreur se ferme s'il n'avait plus rien a faire (transcription prete ou echec)
        if attendre_fin(pid):
            return ("Démarrage d'un nouvel enregistrement." if lancer_enregistreur()
                    else "Démarrage en cours.")
        return "Demande transmise à l'enregistreur en cours."


# --- installation ---------------------------------------------------------------------------

def app_en_place(app: pathlib.Path) -> bool:
    """L'application existe et porte deja notre identifiant : on n'y touche plus."""
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            return plistlib.load(f).get("CFBundleIdentifier") == ID_APP
    except (OSError, plistlib.InvalidFileException):
        return False


def preparer_app(app: pathlib.Path) -> None:
    """Icone du paquet, identifiant et nom, puis signature ad hoc.

    osacompile range aussi une icone dans Assets.car, que macOS prefere a applet.icns :
    on la retire, avec la cle CFBundleIconName qui la designe.
    """
    from importlib.resources import files

    ressources = app / "Contents" / "Resources"
    (ressources / "applet.icns").write_bytes(
        files("transcription_locale").joinpath("ressources", "reunion.icns").read_bytes())
    (ressources / "Assets.car").unlink(missing_ok=True)
    info_plist = app / "Contents" / "Info.plist"
    with open(info_plist, "rb") as f:
        info = plistlib.load(f)
    with open(info_plist, "wb") as f:
        plistlib.dump(info_app(info), f)
    signature = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)],
                               capture_output=True, text=True)
    if signature.returncode != 0:
        # sans signature valide, macOS ne retient pas l'autorisation : refaire au prochain passage
        (app / "Contents" / "Info.plist").unlink(missing_ok=True)
        raise ErreurReunion(f"signature de {app} impossible : {signature.stderr.strip()}")
    subprocess.run(["touch", str(app)], capture_output=True)


def creer_app(app: pathlib.Path) -> None:
    app.parent.mkdir(parents=True, exist_ok=True)
    compilation = subprocess.run(["osacompile", "-o", str(app), "-e", script_applet(sys.executable)],
                                 capture_output=True, text=True)
    if compilation.returncode != 0:
        raise ErreurReunion(f"création de {app} impossible : {compilation.stderr.strip()}")
    preparer_app(app)


def installer(dock: bool = True, reconstruire: bool = False) -> list[str]:
    """Cree l'application Reunion et l'epingle au Dock. Relancable sans risque."""
    verifier_macos()
    faits = []
    dossier_enregistrements().mkdir(parents=True, exist_ok=True)
    faits.append(f"Enregistrements : {dossier_enregistrements()}")

    app = chemin_app()
    reconstruit = not app_en_place(app) or reconstruire
    if reconstruit:
        creer_app(app)
        faits.append(f"Application : {app}")
    else:
        faits.append(f"Application déjà en place, autorisations conservées : {app}")

    if dock:
        actuelles = subprocess.run(["defaults", "read", "com.apple.dock", "persistent-apps"],
                                   capture_output=True, text=True).stdout
        if dock_contient(actuelles, app):
            faits.append("Déjà dans le Dock")
        else:
            ajout = subprocess.run(["defaults", "write", "com.apple.dock", "persistent-apps",
                                    "-array-add", entree_dock(app)], capture_output=True, text=True)
            if ajout.returncode != 0:
                raise ErreurReunion(f"ajout au Dock impossible : {ajout.stderr.strip()}")
            faits.append("Ajoutée au Dock")
        if not dock_contient(actuelles, app) or reconstruit:
            subprocess.run(["killall", "Dock"], capture_output=True)  # recharge aussi l'icone
    return faits


# --- apres l'enregistrement (processus detache, lance par l'enregistreur) --------------------

def nombre_de_pistes_audio(video: pathlib.Path) -> int:
    sonde = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                            "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, env=environnement())
    return len(sonde.stdout.split()) if sonde.returncode == 0 else 1


def extraire_audio(video: pathlib.Path) -> pathlib.Path:
    """Garde le seul son : ScreenCaptureKit impose une piste video (l'ecran en vignette),
    qui n'a rien a faire sur le disque. En cas d'echec, on transcrit la video telle quelle."""
    audio = video.with_suffix(EXTENSION_AUDIO)
    try:
        pistes = nombre_de_pistes_audio(video)
        print(f"{pistes} piste(s) audio dans {video.name}", file=sys.stderr)
        copie = subprocess.run(commande_extraction(str(video), str(audio), pistes),
                               capture_output=True, text=True, env=environnement())
        erreur = copie.stderr.strip()
        reussi = copie.returncode == 0 and audio.is_file() and audio.stat().st_size > 0
    except OSError as e:  # ffmpeg ou ffprobe absent
        erreur, reussi = f"{e} (brew install ffmpeg)", False
    if reussi:
        video.unlink()
        return audio
    print(f"extraction du son impossible, transcription de {video.name} : {erreur}",
          file=sys.stderr)
    audio.unlink(missing_ok=True)
    return video


def apres_enregistrement(video: str) -> int:
    from .cli import main

    audio = extraire_audio(pathlib.Path(video))
    return main(["transcrire", str(audio)])


if __name__ == "__main__":
    sys.exit(apres_enregistrement(sys.argv[1]))
