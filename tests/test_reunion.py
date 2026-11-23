"""Raccourci reunion : contenus generes pour le Dock et l'application, sans PyObjC ni reseau."""
import datetime
import pathlib
import unittest

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


class Application(unittest.TestCase):
    def test_applet_passe_par_la_commande_du_path(self):
        script = reunion.script_applet('/Users/x/a "b"\\py')
        self.assertIn("command -v transcription-locale", script)
        self.assertIn("exec transcription-locale reunion", script)
        self.assertIn('quoted form of "/Users/x/a \\"b\\"\\\\py"', script)  # secours
        self.assertIn("-m transcription_locale reunion; fi", script)
        self.assertIn("on error erreur", script)

    def test_info_plist_nomme_l_application(self):
        info = reunion.info_app({"CFBundleName": "applet", "CFBundleIconName": "applet",
                                 "CFBundleExecutable": "applet"})
        self.assertEqual(info["CFBundleIdentifier"], reunion.ID_APP)
        self.assertEqual(info["CFBundleName"], "Réunion")
        self.assertEqual(info["CFBundleExecutable"], "applet")
        self.assertIn("NSMicrophoneUsageDescription", info)
        self.assertNotIn("CFBundleIconName", info)

    def test_application_existante_conservee(self):
        import plistlib
        import tempfile

        with tempfile.TemporaryDirectory() as dossier:
            app = pathlib.Path(dossier) / "Réunion.app"
            self.assertFalse(reunion.app_en_place(app))
            (app / "Contents").mkdir(parents=True)
            with open(app / "Contents" / "Info.plist", "wb") as f:
                plistlib.dump({"CFBundleIdentifier": "com.apple.ScriptEditor.id.x"}, f)
            self.assertFalse(reunion.app_en_place(app))  # ancienne version : a refaire
            with open(app / "Contents" / "Info.plist", "wb") as f:
                plistlib.dump(reunion.info_app({}), f)
            self.assertTrue(reunion.app_en_place(app))

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
