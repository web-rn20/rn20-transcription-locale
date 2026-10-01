"""Enregistrement de reunion en un clic : OBS enregistre, l'outil transcrit a l'arret.

La commande raccourci prepare une fois pour toutes :
    un profil et une collection de scenes OBS "Reunion RN20" (son de l'ordinateur + micro),
    le serveur WebSocket d'OBS, protege par mot de passe,
    une application Reunion dans ~/Applications, epinglee au Dock.
La commande reunion bascule : elle demarre l'enregistrement, ou l'arrete et lance la
transcription en arriere-plan, avec une notification a la fin.

OBS est pilote en local par son WebSocket (protocole v5). Aucun audio ne sort de la machine.
"""
from __future__ import annotations

import base64
import configparser
import hashlib
import json
import os
import pathlib
import secrets
import subprocess
import sys
import time
import unicodedata
import uuid
from typing import Any, Optional
from urllib.parse import quote

NOM_OBS = "Reunion RN20"
DOSSIER_PROFIL = "Reunion_RN20"
FICHIER_COLLECTION = "Reunion_RN20.json"
SCENE = "Reunion"
APP_OBS = "/Applications/OBS.app"
ID_OBS = "com.obsproject.obs-studio"
PORT_DEFAUT = 4455
DELAI_DEMARRAGE = 40.0
DELAI_FICHIER = 30.0
TITRE = "Réunion"


class ErreurReunion(Exception):
    """OBS absent, non configure ou injoignable."""


class ObsPasPret(ErreurReunion):
    """OBS repond mais finit de demarrer (code 207 du protocole)."""


CODE_PAS_PRET = 207


# --- emplacements -------------------------------------------------------------------------

def dossier_support() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Application Support"


def emplacements_obs() -> dict[str, pathlib.Path]:
    """Dossiers de configuration d'OBS, en tenant compte de [Locations] dans global.ini."""
    defaut = dossier_support()
    global_ini = defaut / "obs-studio" / "global.ini"
    lieux = {"Configuration": defaut, "Profiles": defaut, "SceneCollections": defaut}
    if global_ini.is_file():
        ini = configparser.ConfigParser(interpolation=None, strict=False)
        ini.optionxform = str
        ini.read(global_ini, encoding="utf-8-sig")
        for cle in lieux:
            valeur = ini.get("Locations", cle, fallback="")
            if valeur:
                lieux[cle] = pathlib.Path(valeur)
    return {
        "racine": defaut / "obs-studio",
        "profils": lieux["Profiles"] / "obs-studio" / "basic" / "profiles",
        "scenes": lieux["SceneCollections"] / "obs-studio" / "basic" / "scenes",
        "websocket": lieux["Configuration"] / "obs-studio" / "plugin_config" / "obs-websocket"
                     / "config.json",
    }


def dossier_enregistrements() -> pathlib.Path:
    return pathlib.Path.home() / "Movies" / "Reunions"


def chemin_app() -> pathlib.Path:
    return pathlib.Path.home() / "Applications" / f"{TITRE}.app"


def dossier_journaux() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Logs" / "transcription-locale"


# --- contenus generes (fonctions pures) ----------------------------------------------------

def profil_obs(enregistrements: pathlib.Path) -> str:
    """basic.ini d'un profil leger : video minimale, le son seul compte."""
    return "\n".join([
        "[General]",
        f"Name={NOM_OBS}",
        "",
        "[Output]",
        "Mode=Simple",
        "FilenameFormatting=Reunion %CCYY-%MM-%DD %hh-%mm-%ss",
        "",
        "[SimpleOutput]",
        f"FilePath={enregistrements}",
        "RecFormat2=mkv",
        "RecQuality=Small",
        "RecAudioEncoder=aac",
        "ABitrate=160",
        "",
        "[Video]",
        "BaseCX=640",
        "BaseCY=360",
        "OutputCX=640",
        "OutputCY=360",
        "FPSType=1",
        "FPSInt=5",
        "",
        "[Audio]",
        "SampleRate=48000",
        "ChannelSetup=Stereo",
        "",
    ])


def source_audio(nom: str, identifiant: str, reglages: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": nom,
        "uuid": str(uuid.uuid4()),
        "id": identifiant,
        "versioned_id": identifiant,
        "settings": reglages,
        "mixers": 255,
        "enabled": True,
        "muted": False,
        "volume": 1.0,
        "balance": 0.5,
        "monitoring_type": 0,
    }


def collection_obs() -> dict[str, Any]:
    """Une scene, deux sources : le son de l'ordinateur (les autres) et le micro (soi)."""
    systeme = source_audio("Son de l'ordinateur", "sck_audio_capture", {"type": 0})
    micro = source_audio("Micro", "coreaudio_input_capture", {"device_id": "default"})
    elements = [{"name": s["name"], "source_uuid": s["uuid"], "visible": True, "locked": False,
                 "id": i} for i, s in enumerate((systeme, micro), start=1)]
    scene = {
        "name": SCENE,
        "uuid": str(uuid.uuid4()),
        "id": "scene",
        "versioned_id": "scene",
        "settings": {"id_counter": len(elements), "custom_size": False, "items": elements},
        "mixers": 0,
        "enabled": True,
    }
    return {
        "name": NOM_OBS,
        "current_scene": SCENE,
        "current_program_scene": SCENE,
        "scene_order": [{"name": SCENE}],
        "sources": [scene, systeme, micro],
        "groups": [],
        "transitions": [],
        "quick_transitions": [],
        "current_transition": "",
        "transition_duration": 300,
    }


def config_websocket(existante: dict[str, Any], nouveau_mot_de_passe: str) -> dict[str, Any]:
    """Active le serveur avec mot de passe ; garde le port et le mot de passe deja choisis."""
    config = dict(existante)
    config["server_enabled"] = True
    config["auth_required"] = True
    config["first_load"] = False  # sinon OBS affiche le mot de passe au demarrage
    config.setdefault("alerts_enabled", False)
    config.setdefault("server_port", PORT_DEFAUT)
    if not config.get("server_password"):
        config["server_password"] = nouveau_mot_de_passe
    return config


def authentification(mot_de_passe: str, sel: str, defi: str) -> str:
    """Chaine d'authentification du protocole obs-websocket v5."""
    secret = base64.b64encode(hashlib.sha256((mot_de_passe + sel).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + defi).encode()).digest()).decode()


def chaine_applescript(texte: str) -> str:
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def script_applet(python: str) -> str:
    """AppleScript de l'icone du Dock : bascule, et affiche l'erreur si la commande echoue."""
    commande = (f'"export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; " & quoted form of '
                f'{chaine_applescript(python)} & " -m transcription_locale reunion"')
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

def obs_lance() -> bool:
    return subprocess.run(["pgrep", "-x", "OBS"], capture_output=True).returncode == 0


def notifier(message: str) -> None:
    subprocess.run(["osascript", "-e", "on run argv",
                    "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                    "-e", "end run", message, TITRE], capture_output=True)


def lire_config_websocket() -> dict[str, Any]:
    chemin = emplacements_obs()["websocket"]
    if not chemin.is_file():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


class ObsWebsocket:
    """Client minimal du WebSocket d'OBS : identification puis requetes une a une."""

    def __init__(self, port: int, mot_de_passe: str):
        self.port = port
        self.mot_de_passe = mot_de_passe
        self.connexion = None

    def __enter__(self) -> "ObsWebsocket":
        from websockets.sync.client import connect

        try:
            self.connexion = connect(f"ws://127.0.0.1:{self.port}", open_timeout=3)
            bonjour = json.loads(self.connexion.recv(timeout=5))["d"]
        except Exception as e:  # OBS pas encore pret : refus, delai, poignee de main coupee
            raise ConnectionRefusedError(str(e)) from e
        identification: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
        if "authentication" in bonjour:
            a = bonjour["authentication"]
            identification["authentication"] = authentification(self.mot_de_passe, a["salt"],
                                                                 a["challenge"])
        self.connexion.send(json.dumps({"op": 1, "d": identification}))
        reponse = json.loads(self.connexion.recv(timeout=5))
        if reponse.get("op") != 2:
            raise ErreurReunion("OBS refuse le mot de passe WebSocket : relancer "
                                "transcription-locale raccourci, OBS fermé")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.connexion is not None:
            self.connexion.close()

    def requete(self, type_requete: str, donnees: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        identifiant = secrets.token_hex(8)
        message = {"requestType": type_requete, "requestId": identifiant}
        if donnees:
            message["requestData"] = donnees
        self.connexion.send(json.dumps({"op": 6, "d": message}))
        while True:
            reponse = json.loads(self.connexion.recv(timeout=30))
            if reponse.get("op") == 7 and reponse["d"].get("requestId") == identifiant:
                break
        statut = reponse["d"]["requestStatus"]
        if statut.get("code") == CODE_PAS_PRET:
            raise ObsPasPret(f"OBS n'est pas encore prêt pour {type_requete}")
        if not statut.get("result"):
            raise ErreurReunion(f"OBS a refusé {type_requete} : "
                                f"{statut.get('comment') or statut.get('code')}")
        return reponse["d"].get("responseData") or {}


def connexion_obs() -> ObsWebsocket:
    config = lire_config_websocket()
    if not config.get("server_enabled") or not config.get("server_password"):
        raise ErreurReunion("le WebSocket d'OBS n'est pas activé : quitter OBS puis lancer "
                            "transcription-locale raccourci")
    return ObsWebsocket(int(config.get("server_port", PORT_DEFAUT)), config["server_password"])


def attendre_obs(delai: float = DELAI_DEMARRAGE) -> None:
    fin = time.monotonic() + delai
    while True:
        try:
            with connexion_obs() as obs:
                if obs.requete("GetRecordStatus").get("outputActive"):
                    return
        except ObsPasPret:
            pass
        except ErreurReunion:
            raise
        except Exception:  # OBS demarre encore : on reessaie jusqu'au delai
            pass
        if time.monotonic() > fin:
            raise ErreurReunion("OBS est ouvert mais n'enregistre pas : vérifier ses "
                                "autorisations (micro, enregistrement de l'écran et audio système)")
        time.sleep(1)


def attendre_fichier(chemin: pathlib.Path, delai: float = DELAI_FICHIER) -> None:
    """Attend que la taille du fichier ne bouge plus : OBS a fini de l'ecrire."""
    fin = time.monotonic() + delai
    precedente = -1
    while time.monotonic() < fin:
        taille = chemin.stat().st_size if chemin.exists() else -1
        if taille > 0 and taille == precedente:
            return
        precedente = taille
        time.sleep(1)


def environnement() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin")
    return env


def lancer_transcription(enregistrement: pathlib.Path) -> pathlib.Path:
    """Transcription detachee : l'icone du Dock rend la main tout de suite."""
    journaux = dossier_journaux()
    journaux.mkdir(parents=True, exist_ok=True)
    journal = journaux / f"{enregistrement.stem}.log"
    with open(journal, "w", encoding="utf-8") as sortie:
        subprocess.Popen([sys.executable, "-m", "transcription_locale.reunion", str(enregistrement)],
                         stdin=subprocess.DEVNULL, stdout=sortie, stderr=subprocess.STDOUT,
                         start_new_session=True, env=environnement())
    return journal


def demarrer() -> str:
    dossier_enregistrements().mkdir(parents=True, exist_ok=True)
    if not obs_lance():
        subprocess.run(["open", "-a", APP_OBS, "--args", "--profile", NOM_OBS, "--collection",
                        NOM_OBS, "--scene", SCENE, "--startrecording", "--minimize-to-tray",
                        "--disable-shutdown-check"], check=True)
    else:
        with connexion_obs() as obs:
            if obs.requete("GetProfileList").get("currentProfileName") != NOM_OBS:
                obs.requete("SetCurrentProfile", {"profileName": NOM_OBS})
            if obs.requete("GetSceneCollectionList").get("currentSceneCollectionName") != NOM_OBS:
                obs.requete("SetCurrentSceneCollection", {"sceneCollectionName": NOM_OBS})
            obs.requete("StartRecord")
    attendre_obs()
    message = "Enregistrement en cours. Prévenez les participants. Recliquez sur Réunion pour arrêter."
    notifier(message)
    return message


def arreter(obs: ObsWebsocket) -> str:
    chemin = pathlib.Path(obs.requete("StopRecord")["outputPath"])
    notre_profil = obs.requete("GetProfileList").get("currentProfileName") == NOM_OBS
    attendre_fichier(chemin)
    if notre_profil:
        subprocess.run(["osascript", "-e", f'tell application id "{ID_OBS}" to quit'],
                       capture_output=True)
    lancer_transcription(chemin)
    message = f"Enregistrement arrêté : {chemin.name}. Transcription en cours, notification à la fin."
    notifier(message)
    return message


def basculer() -> str:
    if not os.path.isdir(APP_OBS):
        raise ErreurReunion("OBS introuvable dans /Applications : brew install --cask obs")
    if not obs_lance():
        return demarrer()
    try:
        with connexion_obs() as obs:
            if obs.requete("GetRecordStatus").get("outputActive"):
                return arreter(obs)
    except (ConnectionRefusedError, TimeoutError) as e:
        raise ErreurReunion("OBS est ouvert mais son WebSocket ne répond pas : quitter OBS "
                            "puis recliquer sur Réunion") from e
    return demarrer()


# --- installation ---------------------------------------------------------------------------

def ecrire_json(chemin: pathlib.Path, contenu: dict[str, Any]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, indent=4, ensure_ascii=False), encoding="utf-8")


def poser_icone(app: pathlib.Path) -> None:
    """Remplace l'icone d'applet par celle du paquet, puis resigne l'application.

    osacompile range aussi l'icone dans Assets.car, que macOS prefere a applet.icns :
    on le retire, avec la cle CFBundleIconName qui le designe.
    """
    import plistlib
    from importlib.resources import files

    ressources = app / "Contents" / "Resources"
    (ressources / "applet.icns").write_bytes(
        files("transcription_locale").joinpath("ressources", "reunion.icns").read_bytes())
    (ressources / "Assets.car").unlink(missing_ok=True)
    info_plist = app / "Contents" / "Info.plist"
    with open(info_plist, "rb") as f:
        info = plistlib.load(f)
    info.pop("CFBundleIconName", None)
    with open(info_plist, "wb") as f:
        plistlib.dump(info, f)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], capture_output=True)
    subprocess.run(["touch", str(app)], capture_output=True)


def installer(dock: bool = True) -> list[str]:
    """Prepare OBS, cree l'application Reunion et l'epingle au Dock. Relancable sans risque."""
    if not os.path.isdir(APP_OBS):
        raise ErreurReunion("OBS introuvable dans /Applications : brew install --cask obs, "
                            "l'ouvrir une fois pour accepter ses autorisations, puis relancer")
    lieux = emplacements_obs()
    if not lieux["racine"].is_dir():
        raise ErreurReunion("OBS n'a jamais été ouvert : l'ouvrir une fois, accepter ses "
                            "autorisations, le quitter, puis relancer")
    if obs_lance():
        raise ErreurReunion("OBS est ouvert : le quitter puis relancer, sinon il écraserait "
                            "la configuration en se fermant")
    faits = []

    profil = lieux["profils"] / DOSSIER_PROFIL / "basic.ini"
    profil.parent.mkdir(parents=True, exist_ok=True)
    profil.write_text(profil_obs(dossier_enregistrements()), encoding="utf-8")
    faits.append(f"Profil OBS : {profil}")

    collection = lieux["scenes"] / FICHIER_COLLECTION
    ecrire_json(collection, collection_obs())
    faits.append(f"Scènes OBS : {collection}")

    websocket = lieux["websocket"]
    existante = json.loads(websocket.read_text(encoding="utf-8")) if websocket.is_file() else {}
    ecrire_json(websocket, config_websocket(existante, secrets.token_urlsafe(24)))
    os.chmod(websocket, 0o600)
    faits.append(f"WebSocket OBS activé, avec mot de passe : {websocket}")

    dossier_enregistrements().mkdir(parents=True, exist_ok=True)
    faits.append(f"Enregistrements : {dossier_enregistrements()}")

    app = chemin_app()
    app.parent.mkdir(parents=True, exist_ok=True)
    compilation = subprocess.run(["osacompile", "-o", str(app), "-e", script_applet(sys.executable)],
                                 capture_output=True, text=True)
    if compilation.returncode != 0:
        raise ErreurReunion(f"création de {app} impossible : {compilation.stderr.strip()}")
    poser_icone(app)
    faits.append(f"Application : {app}")

    if dock:
        actuelles = subprocess.run(["defaults", "read", "com.apple.dock", "persistent-apps"],
                                   capture_output=True, text=True).stdout
        if dock_contient(actuelles, app):
            faits.append("Déjà dans le Dock")
        else:
            subprocess.run(["defaults", "write", "com.apple.dock", "persistent-apps",
                            "-array-add", entree_dock(app)], check=True)
            faits.append("Ajoutée au Dock")
        subprocess.run(["killall", "Dock"], capture_output=True)  # recharge aussi l'icone
    return faits


# --- transcription en arriere-plan ----------------------------------------------------------

def apres_enregistrement(enregistrement: str) -> int:
    from .cli import main

    code = main(["transcrire", enregistrement])
    texte = pathlib.Path(enregistrement).with_suffix(".txt")
    if code == 0 and texte.is_file():
        notifier(f"Transcription prête : {texte.name}")
        subprocess.run(["open", "-R", str(texte)], capture_output=True)
    else:
        notifier(f"La transcription a échoué. Détails : {dossier_journaux()}")
    return code


if __name__ == "__main__":
    sys.exit(apres_enregistrement(sys.argv[1]))
