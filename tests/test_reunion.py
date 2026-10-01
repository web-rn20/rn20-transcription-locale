"""Raccourci reunion : contenus generes pour OBS et le Dock, sans OBS ni reseau."""
import base64
import configparser
import hashlib
import pathlib
import unittest

from transcription_locale import cli, reunion


class ContenusObs(unittest.TestCase):
    def test_profil_lisible_et_range_les_enregistrements(self):
        ini = configparser.ConfigParser(interpolation=None)
        ini.optionxform = str
        ini.read_string(reunion.profil_obs(pathlib.Path("/Users/x/Movies/Reunions")))
        self.assertEqual(ini["General"]["Name"], reunion.NOM_OBS)
        self.assertEqual(ini["SimpleOutput"]["FilePath"], "/Users/x/Movies/Reunions")
        self.assertEqual(ini["SimpleOutput"]["RecFormat2"], "mkv")

    def test_collection_deux_sources_audio_actives_dans_la_scene(self):
        c = reunion.collection_obs()
        scene, *audio = c["sources"]
        self.assertEqual(c["current_scene"], scene["name"])
        self.assertEqual({s["id"] for s in audio}, {"sck_audio_capture", "coreaudio_input_capture"})
        self.assertTrue(all(not s["muted"] and s["volume"] == 1.0 and s["mixers"] for s in audio))
        uuids = {e["source_uuid"] for e in scene["settings"]["items"]}
        self.assertEqual(uuids, {s["uuid"] for s in audio})


class Websocket(unittest.TestCase):
    def test_garde_le_mot_de_passe_et_le_port_existants(self):
        config = reunion.config_websocket(
            {"server_enabled": False, "server_password": "ancien", "server_port": 4460,
             "first_load": True}, "nouveau")
        self.assertEqual(config["server_password"], "ancien")
        self.assertEqual(config["server_port"], 4460)
        self.assertTrue(config["server_enabled"] and config["auth_required"])
        self.assertFalse(config["first_load"])

    def test_pose_un_mot_de_passe_s_il_manque(self):
        config = reunion.config_websocket({"server_password": ""}, "nouveau")
        self.assertEqual(config["server_password"], "nouveau")
        self.assertEqual(config["server_port"], reunion.PORT_DEFAUT)

    def test_authentification_protocole_v5(self):
        def b64_sha256(texte):
            return base64.b64encode(hashlib.sha256(texte.encode()).digest()).decode()

        attendu = b64_sha256(b64_sha256("secret" + "sel") + "defi")
        self.assertEqual(reunion.authentification("secret", "sel", "defi"), attendu)


class Dock(unittest.TestCase):
    def test_applet_echappe_le_chemin_python(self):
        script = reunion.script_applet('/Users/x/a "b"\\py')
        self.assertIn('quoted form of "/Users/x/a \\"b\\"\\\\py"', script)
        self.assertIn("-m transcription_locale reunion", script)
        self.assertIn("on error erreur", script)

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
        self.assertTrue(parser.parse_args(["raccourci", "--sans-dock"]).sans_dock)


if __name__ == "__main__":
    unittest.main()
