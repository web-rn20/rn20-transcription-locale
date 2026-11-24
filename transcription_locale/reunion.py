"""Enregistrement de reunion en un clic, sans logiciel tiers.

La commande raccourci pose une fois pour toutes l'application ~/Applications/Reunion.app,
epinglee au Dock : une petite application native (ressources/Reunion.swift), compilee sur
place. Elle ne la reconstruit pas si elle existe deja : macOS rattache l'autorisation
d'enregistrer a la signature de l'application, une application refaite perdrait cette
autorisation. Seule exception, une fois : l'ancienne applet AppleScript (jusqu'a 0.3.0), dont
les notifications portaient l'icone de script, est remplacee par l'application native.

Les notifications passent par l'application (fichier .notification ouvert en arriere-plan),
pour porter son icone ; sans elle, osascript.

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
import re
import signal
import subprocess
import sys
import textwrap
import time
import unicodedata
from typing import Callable, Optional, Sequence
from urllib.parse import quote

TITRE = "Réunion"
ID_APP = "digital.rn20.reunion"
MODULE_ENREGISTREUR = "transcription_locale.enregistreur"
MACOS_MINIMUM = (15, 0)
LARGEUR_MENU = 40
DELAI_FERMETURE = 3.0
DELAI_DEMARRAGE = 20.0  # imports PyObjC compris
EXTENSION_AUDIO = ".m4a"
# Son de visio : les voix se ressemblent plus qu'au micro-cravate. Mesure du 23/11/2026 sur
# une visio a deux voix : deux locuteurs stables de 0.7 a 0.9, fondus des 1.0 (defaut 1.1).
SEUIL_REUNION = 0.8
USAGE_MICRO = "Réunion enregistre votre micro pendant une visio, pour la transcrire sur ce Mac."
# Genre de l'application, inscrit dans son Info.plist. Le changer fait reconstruire
# l'application chez tout le monde, donc redonner l'autorisation d'enregistrer : a eviter.
LANCEUR = "natif-1"
EXECUTABLE = "Reunion"
EXTENSION_MESSAGE = ".notification"
DUREE_MESSAGE = 3600  # un message non lu (application absente, plantage) est efface apres
LONGUEUR_MESSAGE = 1000  # caracteres ; l'application refuse au-dela de 4096 octets
# Essai de 10 secondes. On verifie le son de l'ordinateur puis le micro l'un apres l'autre :
# un court silence sert de reference, un son joue sur le Mac pendant que l'utilisateur se
# tait, puis il parle. On mesure le niveau de chaque moment, toutes pistes audio melangees.
DUREE_ESSAI_SON = 4.0  # « Parlez maintenant » a cet instant
DUREE_ESSAI = 10.0
SON_ESSAI = "/System/Library/Sounds/Glass.aiff"  # 1,65 s
DEBUT_SON_ESSAI = 1.0  # apres le demarrage de la capture : le silence de reference le precede
FIN_SON_ESSAI = 3.0  # le son est coupe au plus tard ici, bien avant le moment du micro
NIVEAU_MINIMUM = -45.0  # dB : en dessous, rien n'a ete capte (le silence numerique est vers -90)
# Le son doit depasser le silence de reference d'au moins cet ecart : le bruit de la piece,
# entendu par le micro, ne passe pas pour le son de l'ordinateur.
ECART_SON = 10.0
MARGE_ESSAI = 0.5  # secondes ecartees autour de la bascule entre les moments


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


def fichier_bienvenue() -> pathlib.Path:
    """Present une fois l'accueil passe : il ne s'affiche qu'au tout premier lancement."""
    return dossier_etat() / "bienvenue-vue"


def fichier_essai() -> pathlib.Path:
    """L'enregistrement de l'essai, efface des qu'il est mesure."""
    return dossier_etat() / "essai.mov"


def dossier_messages() -> pathlib.Path:
    """Textes de notification en attente d'etre affiches par l'application."""
    return dossier_etat() / "notifications"


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


def info_app(python: str, version: str) -> dict:
    """Info.plist complet de l'application native. Un identifiant et un nom, pour que macOS
    affiche Reunion dans ses demandes d'autorisation et ses reglages."""
    return {
        "CFBundleIdentifier": ID_APP,
        "CFBundleName": TITRE,
        "CFBundleDisplayName": TITRE,
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": ".".join(str(n) for n in MACOS_MINIMUM),
        "LSUIElement": True,  # ni menu ni fenetre : l'application vit quelques secondes
        "NSMicrophoneUsageDescription": USAGE_MICRO,
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Notification Réunion",
            "CFBundleTypeExtensions": [EXTENSION_MESSAGE[1:]],
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
        }],
        "RN20Lanceur": LANCEUR,
        "RN20Python": python,  # secours si la commande transcription-locale manque au PATH
    }


def commande_compilation(source: str, sortie: str) -> list[str]:
    """Commande unique, reprise telle quelle par la CI : la cible suit MACOS_MINIMUM."""
    # par xcrun : il fournit le SDK de macOS, que swiftc appele directement ne trouve pas
    cible = "arm64-apple-macos" + ".".join(str(n) for n in MACOS_MINIMUM)
    return ["xcrun", "swiftc", "-O", "-target", cible, "-o", sortie, source]


def message_court(message: str, longueur: int = LONGUEUR_MESSAGE) -> str:
    return message if len(message) <= longueur else message[:longueur - 1] + "…"


def commande_message(app: pathlib.Path, message: pathlib.Path) -> list[str]:
    # -g : en arriere-plan, sans voler le focus de la visio
    return ["open", "-g", "-a", str(app), str(message)]


def commande_extraction(video: str, audio: str, nb_pistes: int) -> list[str]:
    """ffmpeg : le son seul, sans la video. Plusieurs pistes (ordinateur et micro separes)
    sont mixees en une, pour que personne ne manque a la transcription."""
    debut = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", video, "-vn"]
    if nb_pistes <= 1:
        return debut + ["-c:a", "copy", audio]
    return debut + ["-filter_complex", f"amix=inputs={nb_pistes}:normalize=0",
                    "-c:a", "aac", "-b:a", "160k", audio]


def commande_niveau(fichier: str, debut: float, fin: float, nb_pistes: int = 1) -> list[str]:
    """ffmpeg : niveau maximal du son entre deux instants (volumedetect, sur la sortie
    d'erreur). Plusieurs pistes (ordinateur et micro separes) sont d'abord melangees, comme
    pour la transcription : chacune compte."""
    mesure = f"atrim=start={debut:g}:end={fin:g},volumedetect"
    debut_commande = ["ffmpeg", "-nostdin", "-hide_banner", "-i", fichier]
    if nb_pistes <= 1:
        return debut_commande + ["-vn", "-af", mesure, "-f", "null", "-"]
    return debut_commande + ["-filter_complex",
                             f"amix=inputs={nb_pistes}:normalize=0,{mesure}", "-f", "null", "-"]


def lire_niveau(sortie_ffmpeg: str) -> Optional[float]:
    """max_volume en dB lu dans la sortie de volumedetect, ou None s'il manque."""
    trouve = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", sortie_ffmpeg)
    if not trouve:
        return None
    return float("-inf") if "inf" in trouve.group(1) else float(trouve.group(1))


def fenetres_essai() -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """(silence de reference, son de l'ordinateur, micro) : les moments mesures dans l'essai."""
    return ((0.2, DEBUT_SON_ESSAI - 0.1),
            (DEBUT_SON_ESSAI, DUREE_ESSAI_SON - MARGE_ESSAI),
            (DUREE_ESSAI_SON + MARGE_ESSAI, DUREE_ESSAI - MARGE_ESSAI))


def verdict_essai(silence: Optional[float], son: Optional[float],
                  micro: Optional[float]) -> tuple[bool, list[str]]:
    """(tout va bien, lignes du message) d'apres le niveau des moments de l'essai. None : rien
    de mesurable (pas de piste audio, ou fichier trop court)."""
    son_ok = (son is not None and son > NIVEAU_MINIMUM
              and (silence is None or son >= silence + ECART_SON))
    micro_ok = micro is not None and micro > NIVEAU_MINIMUM
    lignes = [
        "Son de l'ordinateur : capté." if son_ok else
        "Son de l'ordinateur : rien capté. Vérifiez que le volume du Mac n'est pas coupé, "
        "et que Réunion est coché dans Réglages > Confidentialité et sécurité > "
        "Enregistrement de l'écran et audio système.",
        "Micro : capté." if micro_ok else
        "Micro : rien capté. Vérifiez le micro choisi dans Réglages > Son > Entrée, et que "
        "Réunion est coché dans Réglages > Confidentialité et sécurité > Micro.",
    ]
    if son_ok and micro_ok:
        lignes.append("Avec un casque, l'essai du son de l'ordinateur est le plus sûr : sans "
                      "casque, le micro peut aussi entendre les haut-parleurs.")
    return son_ok and micro_ok, lignes


def niveaux_lisibles(niveaux: tuple[Optional[float], ...]) -> str:
    """Pour le journal : « silence -62.1 dB, son -14.3 dB, micro -21.0 dB »."""
    noms = ("silence", "son", "micro")
    return ", ".join(f"{nom} {'?' if n is None else f'{n:.1f} dB'}" for nom, n in zip(noms, niveaux))


def arguments_transcription(audio: pathlib.Path) -> list[str]:
    return ["transcrire", str(audio), "--seuil", str(SEUIL_REUNION)]


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


def notifier_par_script(message: str) -> None:
    subprocess.run(["osascript", "-e", "on run argv",
                    "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                    "-e", "end run", message, TITRE], capture_output=True)


def nettoyer_messages(maintenant: Optional[float] = None) -> None:
    """Cycle de vie des messages : l'application efface ceux qu'elle affiche, les autres
    (application absente ou plantee) partent au bout d'une heure."""
    maintenant = time.time() if maintenant is None else maintenant
    try:
        anciens = [m for m in dossier_messages().glob("*" + EXTENSION_MESSAGE)
                   if maintenant - m.stat().st_mtime > DUREE_MESSAGE]
    except OSError:
        return
    for message in anciens:
        message.unlink(missing_ok=True)


def notifier(message: str) -> None:
    """Par l'application, pour porter son icone ; a defaut, notification de script."""
    app = chemin_app()
    if app_en_place(app):
        nettoyer_messages()
        fichier = None
        try:
            dossier_messages().mkdir(parents=True, exist_ok=True)
            fichier = dossier_messages() / f"{time.time_ns()}-{os.getpid()}{EXTENSION_MESSAGE}"
            fichier.write_text(message_court(message), encoding="utf-8")
            if subprocess.run(commande_message(app, fichier), capture_output=True).returncode == 0:
                return
        except OSError:
            pass
        if fichier is not None:
            fichier.unlink(missing_ok=True)
    notifier_par_script(message)


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


def lancer_enregistreur(delai: float = DELAI_DEMARRAGE, options: Sequence[str] = ()) -> bool:
    """Enregistreur detache, puis attente qu'il soit pret (fichier PID ecrit). Faux si
    l'attente depasse le delai : il demarre encore, ou il a echoue (voir reunion.log).
    A appeler sous le verrou de la bascule : jamais deux enregistreurs en meme temps."""
    journaux = dossier_journaux()
    journaux.mkdir(parents=True, exist_ok=True)
    try:
        with open(journaux / "reunion.log", "a", encoding="utf-8") as sortie:
            processus = subprocess.Popen(
                [sys.executable, "-m", MODULE_ENREGISTREUR, *options], stdin=subprocess.DEVNULL,
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


def remplacer_enregistreur(options: Sequence[str], liberer: Callable[[], None]) -> bool:
    """L'enregistreur courant passe la main a un neuf (nouvel essai, autorisation recue),
    sous le verrou de la bascule : un clic sur le Dock pendant la relance attend que le
    nouveau soit pret et s'adresse a lui, au lieu d'en lancer un second."""
    dossier_etat().mkdir(parents=True, exist_ok=True)
    with open(fichier_verrou(), "w") as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        liberer()
        return lancer_enregistreur(options=options)


def deja_accueilli() -> bool:
    """L'accueil est passe, ou Reunion servait deja avant lui (mise a jour depuis 0.4) :
    un clic sur le Dock doit alors enregistrer tout de suite, pas ouvrir l'accueil."""
    if fichier_bienvenue().exists():
        return True
    try:
        return any(dossier_enregistrements().glob("Reunion *"))
    except OSError:
        return False


# --- installation ---------------------------------------------------------------------------

def app_en_place(app: pathlib.Path) -> bool:
    """L'application native existe et porte notre identifiant : on n'y touche plus. L'ancienne
    applet AppleScript (meme identifiant, sans RN20Lanceur) est a remplacer, une fois."""
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException):
        return False
    return info.get("CFBundleIdentifier") == ID_APP and info.get("RN20Lanceur") == LANCEUR


def verifier_swiftc() -> None:
    try:
        trouve = subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True, text=True)
    except OSError:
        trouve = None
    if trouve is None or trouve.returncode != 0 or not trouve.stdout.strip():
        raise ErreurReunion("compilateur Swift introuvable : installer les outils de "
                            "développement d'Apple avec xcode-select --install, puis relancer "
                            "transcription-locale raccourci")


def mettre_en_place(chantier: pathlib.Path, app: pathlib.Path) -> None:
    """Remplace app par chantier sans jamais laisser l'utilisateur sans application :
    l'ancienne est mise de cote, et remise en place si le remplacement echoue."""
    import shutil

    ancienne = app.with_name(f".{app.name}.ancienne")
    shutil.rmtree(ancienne, ignore_errors=True)
    try:
        if app.exists():
            os.rename(app, ancienne)
        os.rename(chantier, app)
    except OSError as e:
        if ancienne.exists() and not app.exists():
            os.rename(ancienne, app)
        raise ErreurReunion(f"remplacement de {app} impossible : {e}") from e
    shutil.rmtree(ancienne, ignore_errors=True)


def creer_app(app: pathlib.Path) -> None:
    """Compile l'application dans un dossier voisin, puis la met en place d'un coup : une
    compilation ou un remplacement rate laisse l'application precedente intacte."""
    import shutil
    from importlib.resources import as_file, files

    from . import __version__

    verifier_swiftc()
    chantier = app.with_name(f".{app.name}.construction")
    try:
        app.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(chantier, ignore_errors=True)
        macos = chantier / "Contents" / "MacOS"
        ressources = chantier / "Contents" / "Resources"
        macos.mkdir(parents=True)
        ressources.mkdir()
        paquet = files("transcription_locale").joinpath("ressources")
        with as_file(paquet.joinpath("Reunion.swift")) as source:
            compilation = subprocess.run(
                commande_compilation(str(source), str(macos / EXECUTABLE)),
                capture_output=True, text=True)
        if compilation.returncode != 0:
            raise ErreurReunion(f"compilation de l'application impossible : "
                                f"{compilation.stderr.strip()[-800:]}")
        (ressources / "AppIcon.icns").write_bytes(paquet.joinpath("reunion.icns").read_bytes())
        with open(chantier / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump(info_app(sys.executable, __version__), f)
        signature = subprocess.run(["codesign", "--force", "--sign", "-", str(chantier)],
                                   capture_output=True, text=True)
        if signature.returncode != 0:
            raise ErreurReunion(f"signature de l'application impossible : "
                                f"{signature.stderr.strip()}")
        mettre_en_place(chantier, app)
    except OSError as e:
        raise ErreurReunion(f"construction de {app} impossible : {e}") from e
    finally:
        shutil.rmtree(chantier, ignore_errors=True)
    # LaunchServices relit l'application (icone, type .notification)
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                    "LaunchServices.framework/Support/lsregister", "-f", str(app)],
                   capture_output=True)


def installer(dock: bool = True, reconstruire: bool = False) -> list[str]:
    """Cree l'application Reunion et l'epingle au Dock. Relancable sans risque."""
    verifier_macos()
    faits = []
    dossier_enregistrements().mkdir(parents=True, exist_ok=True)
    faits.append(f"Enregistrements : {dossier_enregistrements()}")

    app = chemin_app()
    remplacee = app.exists() and not app_en_place(app)
    reconstruit = not app_en_place(app) or reconstruire
    if reconstruit:
        creer_app(app)
        faits.append(f"Application : {app}")
        if remplacee or reconstruire:
            faits.append("Application refaite : macOS redemandera l'autorisation d'enregistrer. "
                         "Si la demande n'apparaît pas, ajouter Réunion par « + » dans Réglages > "
                         "Confidentialité et sécurité > Enregistrement de l'écran et audio "
                         "système, depuis ~/Applications. Si une ancienne ligne Réunion y "
                         "figure, la retirer d'abord.")
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


def mesurer_niveau(fichier: pathlib.Path, debut: float, fin: float,
                   nb_pistes: int = 1) -> Optional[float]:
    """Niveau maximal entre deux instants, None si rien n'est mesurable. OSError si ffmpeg
    manque."""
    try:
        mesure = subprocess.run(commande_niveau(str(fichier), debut, fin, nb_pistes),
                                capture_output=True, text=True, env=environnement(), timeout=60)
    except subprocess.TimeoutExpired:
        return None
    return lire_niveau(mesure.stderr)


def mesurer_essai(fichier: pathlib.Path) -> tuple[bool, list[str], str]:
    """(tout va bien, lignes du message, niveaux pour le journal). L'essai est efface
    ensuite : il ne contient que dix secondes de test."""
    try:
        pistes = nombre_de_pistes_audio(fichier)
        niveaux = tuple(mesurer_niveau(fichier, debut, fin, pistes)
                        for debut, fin in fenetres_essai())
    except OSError:
        return False, ["Mesure impossible : ffmpeg est introuvable (brew install ffmpeg, puis "
                       "refaire l'essai)."], "ffmpeg introuvable"
    finally:
        fichier.unlink(missing_ok=True)
    return (*verdict_essai(*niveaux), niveaux_lisibles(niveaux))


def apres_enregistrement(video: str) -> int:
    from .cli import main

    audio = extraire_audio(pathlib.Path(video))
    return main(arguments_transcription(audio))


if __name__ == "__main__":
    sys.exit(apres_enregistrement(sys.argv[1]))
