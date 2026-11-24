"""Accueil : mesure de l'essai de 10 secondes, commande verifier, options de raccourci."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from transcription_locale import cli, modeles, reunion, verification


class MesureEssai(unittest.TestCase):
    def test_lecture_du_niveau(self):
        self.assertEqual(reunion.lire_niveau("[Parsed_volumedetect_1] max_volume: -12.3 dB"), -12.3)
        self.assertEqual(reunion.lire_niveau("max_volume: -inf dB"), float("-inf"))
        self.assertIsNone(reunion.lire_niveau("aucune mesure"))

    def test_les_deux_moments_ne_se_chevauchent_pas(self):
        (s0, s1), (m0, m1) = reunion.fenetres_essai()
        self.assertLess(0, s0)
        self.assertLess(s1, reunion.DUREE_ESSAI_SON)
        self.assertLess(reunion.DUREE_ESSAI_SON, m0)
        self.assertLess(m1, reunion.DUREE_ESSAI)

    def test_verdict(self):
        ok, lignes = reunion.verdict_essai(-10.0, -20.0)
        self.assertTrue(ok)
        self.assertTrue(lignes[0].startswith("Son de l'ordinateur : capté"))
        ok, lignes = reunion.verdict_essai(-10.0, float("-inf"))
        self.assertFalse(ok)
        self.assertIn("Réglages > Son > Entrée", lignes[1])
        ok, lignes = reunion.verdict_essai(None, -20.0)
        self.assertFalse(ok)
        self.assertIn("Enregistrement de l'écran", lignes[0])
        ok, lignes = reunion.verdict_essai(None, None)
        self.assertFalse(ok)
        self.assertIn("ffmpeg", lignes[0])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_mesure_d_un_vrai_fichier_puis_effacement(self):
        with tempfile.TemporaryDirectory() as dossier:
            essai = pathlib.Path(dossier) / "essai.m4a"
            # 4 s de son (l'ordinateur), puis 6 s de silence : un micro muet
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                            "-i", "sine=frequency=880:duration=4", "-f", "lavfi",
                            "-i", "anullsrc=r=44100:cl=mono:d=6", "-filter_complex",
                            "[0][1]concat=n=2:v=0:a=1", str(essai)], check=True)
            ok, lignes = reunion.mesurer_essai(essai)
            self.assertFalse(ok)
            self.assertTrue(lignes[0].startswith("Son de l'ordinateur : capté"))
            self.assertTrue(lignes[1].startswith("Micro : rien capté"))
            self.assertFalse(essai.exists())


class Verifier(unittest.TestCase):
    def constater(self, **changes):
        base = dict(machine="arm64", version_macos="15.4", programme=lambda p: f"/opt/{p}",
                    swiftc=True, app_ok=True, dock=True, whisper=True, voix=True,
                    mises_a_jour=False)
        base.update(changes)
        return verification.rapport(verification.points(**base))

    def test_tout_en_place(self):
        texte, complet = self.constater()
        self.assertTrue(complet)
        self.assertNotIn("✗", texte)

    def test_ce_qui_manque_donne_son_remede(self):
        texte, complet = self.constater(programme=lambda p: None, whisper=False)
        self.assertFalse(complet)
        self.assertIn("→ brew install ffmpeg", texte)
        self.assertIn("→ transcription-locale modeles", texte)

    def test_reunion_seulement_conseille(self):
        texte, complet = self.constater(swiftc=False, app_ok=False, version_macos="14.6")
        self.assertTrue(complet)  # transcrire un fichier reste possible
        self.assertIn("→ xcode-select --install", texte)
        self.assertIn(": pour Réunion", texte)

    def test_modeles_presents_sans_reseau(self):
        with tempfile.TemporaryDirectory() as dossier, \
                mock.patch.object(modeles, "dossier_modeles", return_value=dossier):
            self.assertFalse(modeles.modeles_presents())
            for m in modeles.MODELES:
                chemin = pathlib.Path(dossier) / m.fichier
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_bytes(b"x")
            self.assertTrue(modeles.modeles_presents())


class LigneDeCommande(unittest.TestCase):
    def test_verifier_et_sans_modeles(self):
        parser = cli.construire_parser()
        self.assertIs(parser.parse_args(["verifier"]).action, cli.commande_verifier)
        self.assertTrue(parser.parse_args(["raccourci", "--sans-modeles"]).sans_modeles)
        self.assertFalse(parser.parse_args(["raccourci"]).sans_modeles)

    def test_raccourci_continue_si_le_telechargement_echoue(self):
        args = cli.construire_parser().parse_args(["raccourci", "--sans-dock"])
        with mock.patch.object(cli, "installer", return_value=["Application : x"]), \
                mock.patch.object(cli, "preparer_modeles",
                                  side_effect=modeles.ErreurModele("hors ligne")), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(cli.commande_raccourci(args), 0)


if __name__ == "__main__":
    unittest.main()
