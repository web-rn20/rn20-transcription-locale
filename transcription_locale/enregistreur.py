"""Enregistreur de reunion : son de l'ordinateur et micro, badge et menu dans la barre d'etat.

Lance par la commande reunion (icone du Dock), dans son propre processus. ScreenCaptureKit
ecrit lui-meme le fichier ; a l'arret, un processus detache garde le son seul et transcrit.

Etats : preparation -> enregistrement -> finalisation -> transcription -> prete, ou echec.
Le menu du badge dit ce qui se passe et propose ce qu'on peut faire a ce moment-la.
SIGUSR1 (nouveau clic sur l'icone du Dock) arrete l'enregistrement, ou ferme l'enregistreur
quand il n'a plus rien a faire.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time
from typing import Optional

import AppKit
import AVFoundation
import Foundation
import Quartz
import rumps
import ScreenCaptureKit as SCK
from PyObjCTools.AppHelper import callAfter

from . import badge, mises_a_jour, reunion

REGLAGES = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
REFUS_TCC = -3801  # SCStreamErrorUserDeclined : l'autorisation manque
DELAI_FINALISATION = 60.0
DELAI_INSTALLATION = 300.0
# la pilule verte s'efface seule : la notification et le Finder ont deja montre le texte
DELAI_PRETE = 60.0
COULEUR_ETAT = {"preparation": "attente", "enregistrement": "enregistrement",
                "finalisation": "attente", "transcription": "attente",
                "prete": "prete", "echec": "echec", "installation": "attente"}


def log(*morceaux: object) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *morceaux, flush=True)


class Delegue(Foundation.NSObject):
    """Recoit les evenements de SCRecordingOutput, sur un fil secondaire."""

    def initWithApp_(self, app):
        self = self.init()
        self.app = app
        return self

    def recordingOutput_didFailWithError_(self, _sortie, erreur):
        log("echec de l'enregistrement :", erreur)
        callAfter(self.app.capture_interrompue, erreur.localizedDescription())

    def recordingOutputDidFinishRecording_(self, _sortie):
        callAfter(self.app.fichier_termine)


class Enregistreur(rumps.App):
    def __init__(self) -> None:
        super().__init__(reunion.TITRE, title="", quit_button=None)
        self.etat = "preparation"
        self.erreur = ""
        self.reglages = False
        self.debut = self.debut_tr = self.debut_fin = 0.0
        self.flux = self.sortie = None
        self.transcription: Optional[subprocess.Popen] = None
        self.ligne_duree: Optional[rumps.MenuItem] = None
        self.maj: Optional[mises_a_jour.Version] = None
        self.maj_installee = ""
        self.installation: Optional[subprocess.Popen] = None
        self.etat_avant_installation = "prete"
        self.debut_installation = 0.0
        self.debut_prete = 0.0
        self.erreur_maj = ""
        reunion.dossier_enregistrements().mkdir(parents=True, exist_ok=True)
        self.video = reunion.dossier_enregistrements() / reunion.nom_enregistrement(
            datetime.datetime.now())
        self.delegue = Delegue.alloc().initWithApp_(self)
        self.horloge = rumps.Timer(self.tic, 1)
        self.horloge.start()
        self.afficher()

    # --- menu et badge ----------------------------------------------------------------------

    @staticmethod
    def infos(texte: str) -> list[rumps.MenuItem]:
        """Explication non cliquable, en lignes courtes."""
        return [rumps.MenuItem(ligne) for ligne in reunion.decouper(texte)]

    def audio(self) -> pathlib.Path:
        return self.video.with_suffix(reunion.EXTENSION_AUDIO)

    def texte(self) -> pathlib.Path:
        return self.video.with_suffix(".txt")

    def lignes(self) -> list:
        e = self.etat
        if e == "preparation":
            return self.infos("Préparation de l'enregistrement…")
        if e == "enregistrement":
            self.ligne_duree = rumps.MenuItem(self.libelle_duree())
            return [self.ligne_duree,
                    *self.infos("On enregistre le son de l'ordinateur (les autres participants) "
                                "et votre micro (vous). Rien ne quitte ce Mac."),
                    *self.infos("Pensez à prévenir les participants."),
                    None,
                    rumps.MenuItem("Arrêter et transcrire", callback=self.arreter),
                    rumps.MenuItem("Ouvrir le dossier des réunions", callback=self.ouvrir_dossier)]
        if e == "finalisation":
            return self.infos("Enregistrement arrêté, écriture du fichier…")
        if e == "transcription":
            self.ligne_duree = rumps.MenuItem(self.libelle_duree())
            return [self.ligne_duree,
                    *self.infos(f"Fichier : {self.audio().name}"),
                    *self.infos("Comptez environ un dixième de la durée de la réunion. "
                                "Vous pouvez continuer à travailler, une notification suivra."),
                    None,
                    rumps.MenuItem("Ouvrir le dossier des réunions", callback=self.ouvrir_dossier)]
        if e == "installation":
            return [*self.infos(f"Installation de la version {self.maj.numero}…"),
                    *self.infos("Quelques secondes en général. Attendez la fin avant de "
                                "lancer un nouvel enregistrement."),
                    None,
                    rumps.MenuItem("Annuler la mise à jour", callback=self.annuler_mise_a_jour)]
        if e == "prete":
            fermeture = ([] if self.reste_ouverte()
                         else self.infos("Ce badge s'efface seul dans une minute."))
            return [*self.infos("Transcription prête"),
                    *self.infos(self.texte().name),
                    *fermeture,
                    None,
                    rumps.MenuItem("Ouvrir la transcription", callback=self.ouvrir_texte),
                    rumps.MenuItem("Afficher dans le Finder", callback=self.afficher_finder),
                    *self.lignes_mise_a_jour(),
                    None,
                    rumps.MenuItem("Fermer", callback=self.fermer)]
        actions = [rumps.MenuItem("Ouvrir les Réglages", callback=self.ouvrir_reglages)] \
            if self.reglages else []
        return [*self.infos("Un problème est survenu"),
                *self.infos(self.erreur),
                None,
                *actions,
                rumps.MenuItem("Ouvrir le dossier des réunions", callback=self.ouvrir_dossier),
                rumps.MenuItem("Ouvrir le journal", callback=self.ouvrir_journal),
                *self.lignes_mise_a_jour(),
                None,
                rumps.MenuItem("Fermer", callback=self.fermer)]

    def reste_ouverte(self) -> bool:
        """Une mise a jour proposee garde la pilule : son menu est le seul endroit ou
        l'installer."""
        return self.maj is not None

    def lignes_mise_a_jour(self) -> list:
        """Proposee seulement une fois la transcription finie (pret ou echec), jamais avant."""
        if self.maj_installee:
            return [None, *self.infos(f"Version {self.maj_installee} installée : elle servira "
                                      f"au prochain enregistrement.")]
        if self.maj is None:
            return []
        return [None,
                *self.infos(f"Mise à jour {self.maj.numero} disponible"),
                *(self.infos(self.erreur_maj) if self.erreur_maj else []),
                *(self.infos(self.maj.notes[:120]) if self.maj.notes else []),
                rumps.MenuItem(f"Installer la version {self.maj.numero}",
                               callback=self.installer_mise_a_jour)]

    def afficher(self) -> None:
        self.menu.clear()
        self.menu = self.lignes()
        self.poser_badge()

    def poser_badge(self) -> None:
        element = getattr(getattr(self, "_nsapp", None), "nsstatusitem", None)
        if element is not None:  # absent tant que la boucle de l'application n'a pas demarre
            duree = reunion.chrono(time.time() - self.debut) if self.etat == "enregistrement" else ""
            badge.poser(element, COULEUR_ETAT[self.etat], duree)

    def libelle_duree(self) -> str:
        if self.etat == "enregistrement":
            return f"Enregistrement en cours depuis {reunion.duree_lisible(time.time() - self.debut)}"
        return f"Transcription en cours depuis {reunion.duree_lisible(time.time() - self.debut_tr)}"

    def changer(self, etat: str) -> None:
        log("etat :", etat)
        self.etat = etat
        self.afficher()

    def echec(self, texte: str, reglages: bool = False) -> None:
        self.erreur, self.reglages = texte, reglages
        reunion.notifier(texte)
        self.changer("echec")

    def tic(self, _minuteur) -> None:
        if self.ligne_duree is not None and self.etat in ("enregistrement", "transcription"):
            self.ligne_duree.title = self.libelle_duree()
        if self.etat == "enregistrement":
            self.poser_badge()  # la duree defile dans la pilule
        if self.etat == "finalisation" and time.time() - self.debut_fin > DELAI_FINALISATION:
            self.echec("L'enregistrement ne s'est pas terminé correctement. Le fichier est "
                       "peut-être incomplet, dans le dossier des réunions.")
        if (self.etat == "prete" and not self.reste_ouverte()
                and time.time() - self.debut_prete > DELAI_PRETE):
            log("transcription prête depuis une minute, fermeture")
            self.fermer()
            return
        if self.etat == "installation":
            if self.installation.poll() is not None:
                self.fin_installation(self.installation.returncode)
            elif time.time() - self.debut_installation > DELAI_INSTALLATION:
                self.interrompre_installation("La mise à jour a pris trop de temps et a été "
                                              "annulée. Vous pouvez réessayer plus tard.")
        if self.etat == "transcription" and self.transcription.poll() is not None:
            code = self.transcription.returncode
            log("transcription terminée, code", code)
            if code == 0 and self.texte().is_file():
                reunion.notifier(f"Transcription prête : {self.texte().name}")
                subprocess.run(["open", "-R", str(self.texte())])  # le Finder montre le texte
                self.debut_prete = time.time()
                self.changer("prete")
            else:
                self.echec("La transcription a échoué. Le journal donne le détail.")

    # --- mise a jour au clic ----------------------------------------------------------------

    def verifier_mise_a_jour(self) -> None:
        """Fil secondaire : la requete reseau ne bloque ni le menu ni l'enregistrement."""
        def verifier():
            version = mises_a_jour.disponible()
            if version is not None:
                callAfter(self.mise_a_jour_trouvee, version)
        threading.Thread(target=verifier, daemon=True).start()

    def mise_a_jour_trouvee(self, version: mises_a_jour.Version) -> None:
        log("mise à jour disponible :", version.etiquette)
        self.maj = version
        if self.etat in ("prete", "echec"):
            self.afficher()

    def installer_mise_a_jour(self, _item) -> None:
        if self.maj is None or self.etat not in ("prete", "echec"):
            return
        uv = mises_a_jour.trouver_uv()
        if uv is None:
            self.maj_ratee("Mise à jour impossible : la commande uv est introuvable.")
            return
        try:
            commande = mises_a_jour.commande_installation(self.maj, uv)
            log("installation :", " ".join(commande))
            reunion.dossier_journaux().mkdir(parents=True, exist_ok=True)
            with open(reunion.dossier_journaux() / "mise-a-jour.log", "a",
                      encoding="utf-8") as sortie:
                self.installation = subprocess.Popen(
                    commande, stdin=subprocess.DEVNULL, stdout=sortie, stderr=subprocess.STDOUT,
                    start_new_session=True, env=reunion.environnement())
        except (OSError, ValueError) as e:
            log("installation impossible :", e)
            self.maj_ratee(f"Mise à jour impossible : {e}")
            return
        self.erreur_maj = ""
        self.etat_avant_installation = self.etat
        self.debut_installation = time.time()
        self.changer("installation")

    def annuler_mise_a_jour(self, _item) -> None:
        if self.etat == "installation":
            self.interrompre_installation("Mise à jour annulée. La version installée reste "
                                          "en place.")

    def interrompre_installation(self, texte: str) -> None:
        log("installation interrompue")
        try:
            os.killpg(self.installation.pid, signal.SIGTERM)  # uv et ses sous-processus git
        except OSError:
            pass
        self.changer(self.etat_avant_installation)
        self.maj_ratee(texte)

    def maj_ratee(self, texte: str) -> None:
        """Une mise a jour ratee ne touche pas a l'etat de la reunion : la transcription reste
        accessible, le menu dit ce qui s'est passe et propose de reessayer."""
        self.erreur_maj = texte
        reunion.notifier(texte)
        self.afficher()

    def fin_installation(self, code: int) -> None:
        log("installation terminée, code", code)
        if code == 0:
            self.maj_installee, self.maj = self.maj.numero, None
            self.debut_prete = time.time()  # une minute pour lire « Version installée »
            self.changer(self.etat_avant_installation)
            reunion.notifier(f"Réunion {self.maj_installee} installée. Elle servira au "
                             f"prochain enregistrement.")
        else:
            self.changer(self.etat_avant_installation)
            self.maj_ratee("La mise à jour a échoué. Le journal mise-a-jour.log donne le "
                           "détail.")

    # --- actions du menu --------------------------------------------------------------------

    def ouvrir_dossier(self, _item) -> None:
        subprocess.run(["open", str(reunion.dossier_enregistrements())])

    def ouvrir_texte(self, _item) -> None:
        subprocess.run(["open", str(self.texte())])

    def afficher_finder(self, _item) -> None:
        subprocess.run(["open", "-R", str(self.texte())])

    def ouvrir_reglages(self, _item) -> None:
        subprocess.run(["open", REGLAGES])

    def ouvrir_journal(self, _item) -> None:
        journal = self.journal_transcription()
        subprocess.run(["open", str(journal if journal.is_file()
                                    else reunion.dossier_journaux() / "reunion.log")])

    def fermer(self, _item=None) -> None:
        # quit_application quitte sans repasser par Python : on libere le PID avant
        liberer_pid()
        rumps.quit_application()

    # --- capture ----------------------------------------------------------------------------

    def demarrer(self) -> None:
        if not Quartz.CGPreflightScreenCaptureAccess():
            # affiche la demande de macOS la premiere fois ; ensuite, il faut passer par les Reglages
            if not Quartz.CGRequestScreenCaptureAccess():
                self.refus()
                return
        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(
            lambda contenu, erreur: callAfter(self.contenu, contenu, erreur))

    def refus(self) -> None:
        log("autorisation d'enregistrer absente")
        self.echec("Réunion n'a pas l'autorisation d'enregistrer. Dans les Réglages, cocher "
                   "Réunion, puis recliquer sur Réunion dans le Dock.", reglages=True)

    def contenu(self, contenu, erreur) -> None:
        if erreur is not None and erreur.code() == REFUS_TCC:
            self.refus()
            return
        if erreur is not None or contenu is None or not contenu.displays():
            log("contenu partageable indisponible :", erreur)
            self.echec("Impossible de préparer l'enregistrement : "
                       + (erreur.localizedDescription() if erreur is not None
                          else "aucun écran disponible."))
            return
        filtre = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(
            contenu.displays()[0], [])
        reglage = SCK.SCStreamConfiguration.alloc().init()
        # la video est imposee : une vignette a une image par seconde, supprimee a l'arret
        reglage.setWidth_(64)
        reglage.setHeight_(36)
        reglage.setMinimumFrameInterval_((1, 1, 1, 0))  # CMTime d'une seconde
        reglage.setShowsCursor_(False)
        reglage.setCapturesAudio_(True)
        reglage.setCaptureMicrophone_(True)
        reglage.setExcludesCurrentProcessAudio_(True)
        reglage.setSampleRate_(48000)
        reglage.setChannelCount_(2)
        self.flux = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(filtre, reglage, None)

        sortie = SCK.SCRecordingOutputConfiguration.alloc().init()
        sortie.setOutputURL_(Foundation.NSURL.fileURLWithPath_(str(self.video)))
        sortie.setOutputFileType_(AVFoundation.AVFileTypeQuickTimeMovie)
        self.sortie = SCK.SCRecordingOutput.alloc().initWithConfiguration_delegate_(sortie, self.delegue)
        ajoute, erreur = self.flux.addRecordingOutput_error_(self.sortie, None)
        if not ajoute:
            self.echec(f"Enregistrement impossible : {erreur.localizedDescription()}")
            return
        self.flux.startCaptureWithCompletionHandler_(lambda e: callAfter(self.demarre, e))

    def demarre(self, erreur) -> None:
        if erreur is not None:
            log("echec du demarrage :", erreur)
            self.echec(f"Échec du démarrage : {erreur.localizedDescription()}")
            return
        self.debut = time.time()
        self.changer("enregistrement")
        reunion.notifier("Enregistrement lancé. Prévenez les participants. Pour arrêter : "
                         "le badge rouge dans la barre des menus, ou Réunion dans le Dock.")

    def arreter(self, _item=None) -> None:
        if self.etat != "enregistrement":
            return
        self.debut_fin = time.time()
        self.changer("finalisation")
        self.flux.stopCaptureWithCompletionHandler_(lambda e: callAfter(self.capture_arretee, e))

    def capture_arretee(self, erreur) -> None:
        if erreur is not None and self.etat == "finalisation":
            log("echec de l'arret :", erreur)
            self.echec(f"L'arrêt de l'enregistrement a échoué : {erreur.localizedDescription()}")
        else:
            log("capture arrêtée")

    def capture_interrompue(self, description: str) -> None:
        # macOS signale parfois une erreur (ReplayKit -5814) une fois le fichier deja ecrit :
        # elle ne concerne plus l'enregistrement et ne doit pas griser une reunion transcrite.
        if self.etat in ("preparation", "enregistrement"):
            self.echec(f"L'enregistrement s'est interrompu : {description}")
        elif self.etat == "finalisation":
            # le fichier est peut-etre complet : on attend recordingOutputDidFinishRecording,
            # ou le delai de finalisation qui signalera l'echec
            log("erreur pendant la finalisation, en attente du fichier")
        else:
            log("erreur tardive ignorée, état :", self.etat)

    def fichier_termine(self) -> None:
        # un echec deja signale (ou un arret qui n'en finit pas) ne lance pas de transcription
        if self.etat in ("enregistrement", "finalisation"):
            self.transcrire()
        else:
            log("fichier terminé ignoré, état :", self.etat)

    def journal_transcription(self) -> pathlib.Path:
        return reunion.dossier_journaux() / f"{self.video.stem}.log"

    def transcrire(self) -> None:
        log("fichier écrit :", self.video.name)
        self.debut_tr = time.time()
        reunion.dossier_journaux().mkdir(parents=True, exist_ok=True)
        with open(self.journal_transcription(), "w", encoding="utf-8") as sortie:
            self.transcription = subprocess.Popen(
                [sys.executable, "-m", "transcription_locale.reunion", str(self.video)],
                stdin=subprocess.DEVNULL, stdout=sortie, stderr=subprocess.STDOUT,
                start_new_session=True, env=reunion.environnement())
        reunion.notifier("Enregistrement arrêté. Transcription en cours, une notification suivra.")
        self.changer("transcription")

    # --- nouveau clic sur l'icone du Dock ---------------------------------------------------

    def signal_dock(self) -> None:
        log("clic sur l'icône du Dock, état :", self.etat)
        messages = {
            "preparation": "Démarrage en cours, le badge passera au rouge dans un instant.",
            "finalisation": "Enregistrement en cours d'écriture, la transcription va suivre.",
            "transcription": "Transcription en cours : un nouvel enregistrement pourra "
                             "démarrer quand elle sera prête.",
            "installation": "Mise à jour en cours. Attendez la notification de fin pour "
                            "lancer un nouvel enregistrement.",
        }
        if self.etat == "enregistrement":
            self.arreter()
        elif self.etat in ("prete", "echec"):
            self.fermer()
        else:
            reunion.notifier(messages[self.etat])


def liberer_pid() -> None:
    pid = reunion.fichier_pid()
    try:
        if pid.read_text().strip() == str(os.getpid()):
            pid.unlink()
    except OSError:
        pass


def main() -> int:
    # application de barre des menus : sans cela, le menu s'ouvre mais reste invisible
    AppKit.NSApplication.sharedApplication().setActivationPolicy_(
        AppKit.NSApplicationActivationPolicyAccessory)
    app = Enregistreur()
    # le gestionnaire Python tourne entre deux tics de l'horloge, sur le fil principal.
    # Il est pose AVANT d'ecrire le PID : la bascule n'envoie le signal qu'a un enregistreur
    # qui sait le recevoir (par defaut, SIGUSR1 tue le processus).
    signal.signal(signal.SIGUSR1, lambda *_: callAfter(app.signal_dock))
    pid = reunion.fichier_pid()
    pid.parent.mkdir(parents=True, exist_ok=True)
    pid.write_text(str(os.getpid()))
    try:
        rumps.Timer(lambda t: (t.stop(), app.poser_badge(), app.demarrer(),
                               app.verifier_mise_a_jour()), 0.1).start()
        log("enregistreur lancé :", app.video.name)
        app.run()
    finally:
        liberer_pid()
    return 0


if __name__ == "__main__":
    sys.exit(main())
