"""Raccourci reunion : contenus generes pour le Dock et l'application, sans PyObjC ni reseau."""
import datetime
import os
import pathlib
import plistlib
import tempfile
import unittest
from unittest import mock

from transcription_locale import cli, reunion
from transcription_locale.transcription import sans_hallucinations


class Textes(unittest.TestCase):
    def test_nom_d_enregistrement_date_et_triable(self):
        moment = datetime.datetime(2026, 11, 23, 9, 5, 7)
        self.assertEqual(reunion.nom_enregistrement(moment), "Reunion 2026-11-23 09-05-07.mov")

    def test_duree_lisible(self):
        self.assertEqual(reunion.duree_lisible(75), "1 min 15 s")
        self.assertEqual(reunion.duree_lisible(3 * 3600 + 120 + 9), "3 h 02 min")

    def test_chrono_de_la_pilule(self):
        self.assertEqual(reunion.chrono(42), "0:42")
        self.assertEqual(reunion.chrono(12 * 60 + 4), "12:04")
        self.assertEqual(reunion.chrono(3600 + 2 * 60 + 4), "1:02:04")

    def test_menu_etroit(self):
        lignes = reunion.decouper("Réunion n'a pas l'autorisation d'enregistrer. Dans les Réglages, "
                                  "cocher Réunion, puis recliquer sur Réunion dans le Dock.")
        self.assertGreater(len(lignes), 1)
        self.assertTrue(all(len(l) <= reunion.LARGEUR_MENU for l in lignes))
        self.assertEqual(reunion.decouper(""), [""])

    def test_version_de_macos(self):
        self.assertTrue(reunion.version_suffisante("15.0"))
        self.assertTrue(reunion.version_suffisante("27.2.1"))
        self.assertFalse(reunion.version_suffisante("14.7.1"))
        self.assertFalse(reunion.version_suffisante(""))


class Hallucinations(unittest.TestCase):
    def test_retire_les_generiques_de_sous_titrage(self):
        self.assertEqual(sans_hallucinations("Sous-titrage ST' 501"), "")
        self.assertEqual(sans_hallucinations("Merci à tous. Sous-titres réalisés par la "
                                             "communauté d'Amara.org"), "Merci à tous.")

    def test_garde_les_vraies_phrases(self):
        for phrase in ("On parle du sous-titrage des vidéos de l'AG.",
                       "Merci d'avoir participé.", "Le site ST 501 est en ligne",
                       "On a demandé les sous-titres à Amara pour la vidéo de l'AG, "
                       "et ensuite on passe au budget."):
            self.assertEqual(sans_hallucinations(phrase), phrase)


class Extraction(unittest.TestCase):
    def test_une_piste_copiee_sans_reencodage(self):
        commande = reunion.commande_extraction("r.mov", "r.m4a", 1)
        self.assertEqual(commande[-3:], ["-c:a", "copy", "r.m4a"])
        self.assertIn("-vn", commande)

    def test_plusieurs_pistes_mixees(self):
        commande = reunion.commande_extraction("r.mov", "r.m4a", 2)
        self.assertIn("amix=inputs=2:normalize=0", commande)
        self.assertNotIn("copy", commande)
        self.assertEqual(commande[-1], "r.m4a")


    def test_transcription_au_seuil_des_reunions(self):
        args = cli.construire_parser().parse_args(
            reunion.arguments_transcription(pathlib.Path("/x/Reunion.m4a")))
        self.assertEqual(args.fichiers, ["/x/Reunion.m4a"])
        self.assertEqual(args.seuil, reunion.SEUIL_REUNION)
        self.assertLess(reunion.SEUIL_REUNION, cli.SEUIL_DEFAUT)


class Application(unittest.TestCase):
    def test_info_plist_de_l_application_native(self):
        info = reunion.info_app("/Users/x/py", "0.4.0")
        self.assertEqual(info["CFBundleIdentifier"], reunion.ID_APP)
        self.assertEqual(info["CFBundleName"], "Réunion")
        self.assertEqual(info["CFBundleExecutable"], reunion.EXECUTABLE)
        self.assertEqual(info["RN20Lanceur"], reunion.LANCEUR)
        self.assertEqual(info["RN20Python"], "/Users/x/py")
        self.assertEqual(info["LSMinimumSystemVersion"], "15.0")
        self.assertIn("NSMicrophoneUsageDescription", info)
        self.assertEqual(info["CFBundleDocumentTypes"][0]["CFBundleTypeExtensions"],
                         ["notification"])

    def test_application_existante_conservee_ancienne_applet_remplacee(self):
        with tempfile.TemporaryDirectory() as dossier:
            app = pathlib.Path(dossier) / "Réunion.app"
            self.assertFalse(reunion.app_en_place(app))
            (app / "Contents").mkdir(parents=True)

            def poser(info):
                with open(app / "Contents" / "Info.plist", "wb") as f:
                    plistlib.dump(info, f)

            poser({"CFBundleIdentifier": "com.apple.ScriptEditor.id.x"})
            self.assertFalse(reunion.app_en_place(app))
            poser({"CFBundleIdentifier": reunion.ID_APP, "CFBundleExecutable": "applet"})
            self.assertFalse(reunion.app_en_place(app))  # applet AppleScript jusqu'a 0.3.0
            poser(reunion.info_app("/py", "0.4.0"))
            self.assertTrue(reunion.app_en_place(app))

    def test_compilation_et_ouverture_du_message(self):
        commande = reunion.commande_compilation("/s/Reunion.swift", "/a/Reunion")
        self.assertEqual(commande[:3], ["xcrun", "swiftc", "-O"])
        self.assertIn("arm64-apple-macos15.0", commande)
        self.assertEqual(reunion.commande_message(pathlib.Path("/A/Réunion.app"), pathlib.Path("/m")),
                         ["open", "-g", "-a", "/A/Réunion.app", "/m"])

    def test_source_swift_livree_avec_le_paquet(self):
        from importlib.resources import files

        source = files("transcription_locale").joinpath("ressources", "Reunion.swift").read_text(
            encoding="utf-8")
        self.assertIn("exec transcription-locale reunion", source)
        self.assertIn('"RN20Python"', source)
        self.assertIn('["-c", script, "sh", python]', source)  # chemin en argument, pas dans le script
        self.assertIn("removeItem", source)  # chaque message lu est efface


class Notifications(unittest.TestCase):
    def setUp(self):
        self.dossier = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dossier, ignore_errors=True))
        for nom, valeur in (("dossier_etat", self.dossier), ("chemin_app", self.dossier / "Réunion.app")):
            patcher = mock.patch.object(reunion, nom, return_value=valeur)
            patcher.start()
            self.addCleanup(patcher.stop)

    def messages(self):
        return list(reunion.dossier_messages().glob("*.notification"))

    def test_sans_application_native_notification_de_script(self):
        with mock.patch.object(reunion.subprocess, "run") as run:
            reunion.notifier("Bonjour")
        self.assertEqual(run.call_args.args[0][0], "osascript")

    def test_par_l_application_native(self):
        with mock.patch.object(reunion, "app_en_place", return_value=True), \
                mock.patch.object(reunion.subprocess, "run",
                                  return_value=mock.Mock(returncode=0)) as run:
            reunion.notifier("Transcription prête")
        commande = run.call_args.args[0]
        self.assertEqual(commande[:3], ["open", "-g", "-a"])
        message = pathlib.Path(commande[-1])
        self.assertEqual(message.read_text(encoding="utf-8"), "Transcription prête")
        self.assertEqual(message.parent, reunion.dossier_messages())

    def test_ouverture_ratee_message_efface_et_script(self):
        with mock.patch.object(reunion, "app_en_place", return_value=True), \
                mock.patch.object(reunion.subprocess, "run",
                                  return_value=mock.Mock(returncode=1)) as run:
            reunion.notifier("Bonjour")
        self.assertEqual(run.call_args.args[0][0], "osascript")
        self.assertEqual(self.messages(), [])

    def test_messages_oublies_effaces_apres_une_heure(self):
        reunion.dossier_messages().mkdir(parents=True)
        vieux = reunion.dossier_messages() / "1.notification"
        recent = reunion.dossier_messages() / "2.notification"
        for m in (vieux, recent):
            m.write_text("x")
        os.utime(vieux, (1000.0, 1000.0))
        os.utime(recent, (1000.0 + reunion.DUREE_MESSAGE, 1000.0 + reunion.DUREE_MESSAGE))
        reunion.nettoyer_messages(maintenant=1000.0 + reunion.DUREE_MESSAGE + 1)
        self.assertEqual(self.messages(), [recent])


class Dock(unittest.TestCase):
    def test_dock_reconnait_l_app_accents_composes_ou_non(self):
        app = pathlib.Path("/Users/x/Applications/Réunion.app")
        nfc, nfd = reunion.urls_dock(app)
        self.assertIn("R%C3%A9union.app/", nfc)
        self.assertIn("Re%CC%81union.app/", nfd)
        self.assertTrue(reunion.dock_contient(f'"_CFURLString" = "{nfd}";', app))
        self.assertFalse(reunion.dock_contient('"_CFURLString" = "file:///Applications/Slack.app/";',
                                               app))
        self.assertIn(nfc, reunion.entree_dock(app))

    def test_icone_livree_avec_le_paquet(self):
        from importlib.resources import files

        icone = files("transcription_locale").joinpath("ressources", "reunion.icns").read_bytes()
        self.assertEqual(icone[:4], b"icns")


class LigneDeCommande(unittest.TestCase):
    def test_sous_commandes(self):
        parser = cli.construire_parser()
        self.assertIs(parser.parse_args(["reunion"]).action, cli.commande_reunion)
        args = parser.parse_args(["raccourci", "--sans-dock", "--reconstruire"])
        self.assertTrue(args.sans_dock and args.reconstruire)
        self.assertFalse(parser.parse_args(["raccourci"]).reconstruire)


if __name__ == "__main__":
    unittest.main()
