"""Preparation audio, modeles et ligne de commande, sans ffmpeg ni reseau."""
import contextlib
import hashlib
import io
import os
import pathlib
import tarfile
import tempfile
import unittest
from unittest import mock

from transcription_locale import audio, cli, modeles


class Audio(unittest.TestCase):
    def test_liste_concat_chemins_absolus_et_apostrophes(self):
        liste = audio.liste_concat(["a.wav", "l'entretien.wav"])
        lignes = liste.splitlines()
        self.assertTrue(lignes[0].startswith("file '/") and lignes[0].endswith("/a.wav'"))
        self.assertTrue(lignes[1].endswith("/l'\\''entretien.wav'"))

    def test_commande_une_entree(self):
        cmd = audio.commande_conversion(["a.wav"], "a.16k.wav")
        self.assertEqual(cmd[-7:], ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "a.16k.wav"])
        self.assertEqual(cmd[cmd.index("-i") + 1], "a.wav")
        self.assertEqual(cmd[-1], "a.16k.wav")
        self.assertNotIn("concat", cmd)

    def test_commande_plusieurs_entrees(self):
        cmd = audio.commande_conversion(["a.wav", "b.wav"], "s.16k.wav", "liste.txt")
        self.assertEqual(cmd[cmd.index("-f") + 1], "concat")
        self.assertEqual(cmd[cmd.index("-i") + 1], "liste.txt")

    def test_fichier_introuvable(self):
        with self.assertRaisesRegex(audio.ErreurAudio, "introuvable"):
            audio.preparer(["absent.wav"], "sortie.16k.wav")

    def test_refuse_d_ecraser_l_entree(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            with self.assertRaisesRegex(audio.ErreurAudio, "ecraserait"):
                audio.preparer([f.name], f.name)

    def test_ffmpeg_absent(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as f, mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(audio.ErreurAudio, "brew install ffmpeg"):
                audio.preparer([f.name], f.name + ".16k.wav")


class Modeles(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.source = pathlib.Path(self.dossier.name, "modele.onnx")
        self.source.write_bytes(b"poids du modele")
        self.empreinte = hashlib.sha256(b"poids du modele").hexdigest()

    def test_telechargement_verifie(self):
        cible = os.path.join(self.dossier.name, "copie.onnx")
        modeles.telecharger(self.source.as_uri(), cible, self.empreinte)
        self.assertEqual(pathlib.Path(cible).read_bytes(), b"poids du modele")

    def test_empreinte_inattendue_refusee(self):
        cible = os.path.join(self.dossier.name, "copie.onnx")
        with self.assertRaisesRegex(modeles.ErreurModele, "empreinte inattendue"):
            modeles.telecharger(self.source.as_uri(), cible, "0" * 64)
        self.assertFalse(os.path.exists(cible) or os.path.exists(cible + ".partiel"))

    def test_archive_qui_sort_du_dossier_refusee(self):
        archive = os.path.join(self.dossier.name, "piege.tar.bz2")
        with tarfile.open(archive, "w:bz2") as tar:
            tar.add(self.source, arcname="../evasion.onnx")
        with self.assertRaisesRegex(modeles.ErreurModele, "suspecte"):
            modeles.extraire(archive, os.path.join(self.dossier.name, "modeles"))

    def test_dossier_configurable(self):
        with mock.patch.dict(os.environ, {modeles.VARIABLE_DOSSIER: "/tmp/ailleurs"}):
            self.assertEqual(modeles.dossier_modeles(), "/tmp/ailleurs")

    def test_modele_deja_present_non_retelecharge(self):
        pathlib.Path(self.dossier.name, modeles.EMPREINTE.fichier).write_bytes(b"x")
        with mock.patch.object(modeles, "telecharger") as telecharger:
            modeles.installer(modeles.EMPREINTE, self.dossier.name)
        telecharger.assert_not_called()


class LigneDeCommande(unittest.TestCase):
    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            try:
                code = cli.main(list(args))
            except SystemExit as e:  # erreurs d'arguments signalees par argparse
                code = e.code
        return code, sortie.getvalue(), erreur.getvalue()

    def test_seuils_sans_transcription_prealable(self):
        code, _, erreur = self.lancer("seuils", "inexistant")
        self.assertEqual(code, 2)
        self.assertIn("inexistant.16k.wav introuvable : lancer d'abord la commande transcrire", erreur)

    def test_valeurs_de_seuil_invalides(self):
        code, _, erreur = self.lancer("seuils", "base", "--valeurs", "1.0,abc")
        self.assertEqual(code, 2)
        self.assertIn("0.9,1.0,1.1", erreur)
        self.assertEqual(self.lancer("locuteurs", "base", "--seuil", "-1")[0], 2)
        self.assertEqual(self.lancer("locuteurs", "base", "--nb-locuteurs", "0")[0], 2)

    def test_lecture_des_seuils(self):
        self.assertEqual(cli.lire_seuils("0.9, 1.1,1.3"), [0.9, 1.1, 1.3])

    def test_base_par_defaut(self):
        self.assertEqual(cli.base_par_defaut("dossier/entretien.WAV"), "dossier/entretien")
        self.assertEqual(cli.fichiers_de_travail("x"), ("x.16k.wav", "x.segments.json"))

    def test_conseil_quand_une_seule_voix(self):
        self.assertIn("transcription-locale seuils entretien", cli.conseil_un_seul_locuteur("entretien", 1, None))
        self.assertIsNone(cli.conseil_un_seul_locuteur("entretien", 2, None))
        self.assertIsNone(cli.conseil_un_seul_locuteur("entretien", 1, 1))

    def test_transcrire_fichier_introuvable(self):
        code, _, erreur = self.lancer("transcrire", "absent.wav")
        self.assertEqual(code, 2)
        self.assertIn("absent.wav : fichier introuvable", erreur)


if __name__ == "__main__":
    unittest.main()
