"""Accueil : mesure de l'essai de 10 secondes, commande verifier, options de raccourci."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from transcription_locale import cli, modeles, reunion, transcription, verification


class MesureEssai(unittest.TestCase):
    def test_lecture_du_niveau(self):
        self.assertEqual(reunion.lire_niveau("[Parsed_volumedetect_1] max_volume: -12.3 dB"), -12.3)
        self.assertEqual(reunion.lire_niveau("max_volume: -inf dB"), float("-inf"))
        self.assertIsNone(reunion.lire_niveau("aucune mesure"))

    def test_les_moments_ne_se_chevauchent_pas(self):
        (z0, z1), (s0, s1), (m0, m1) = reunion.fenetres_essai()
        self.assertLess(0, z0)
        self.assertLessEqual(z1, reunion.DEBUT_SON_ESSAI)
        self.assertLessEqual(reunion.DEBUT_SON_ESSAI, s0)
        self.assertLess(s1, reunion.DUREE_ESSAI_SON)
        self.assertLess(reunion.DUREE_ESSAI_SON, m0)
        self.assertLess(m1, reunion.DUREE_ESSAI)

    def test_le_son_finit_avant_le_moment_du_micro(self):
        # le son coupe (afplay -t) se termine dans le moment du son, et laisse une marge
        # d'au moins une seconde avant celui du micro : un micro muet ne passe pas pour capte
        (_, _), (_, s1), (m0, _) = reunion.fenetres_essai()
        self.assertLessEqual(reunion.FIN_SON_ESSAI, s1)
        self.assertLessEqual(reunion.FIN_SON_ESSAI + 1.0, m0)

    def test_verdict(self):
        ok, lignes = reunion.verdict_essai(-70.0, -10.0, -20.0)
        self.assertTrue(ok)
        self.assertTrue(lignes[0].startswith("Son de l'ordinateur : capté"))
        ok, lignes = reunion.verdict_essai(-70.0, -10.0, float("-inf"))
        self.assertFalse(ok)
        self.assertIn("Réglages > Son > Entrée", lignes[1])
        ok, lignes = reunion.verdict_essai(None, None, -20.0)
        self.assertFalse(ok)
        self.assertIn("Enregistrement de l'écran", lignes[0])

    def test_rien_de_mesurable_n_accuse_pas_ffmpeg(self):
        ok, lignes = reunion.verdict_essai(None, None, None)
        self.assertFalse(ok)
        self.assertTrue(lignes[0].startswith("Son de l'ordinateur : rien capté"))
        self.assertTrue(lignes[1].startswith("Micro : rien capté"))
        self.assertNotIn("ffmpeg", " ".join(lignes))

    def test_le_bruit_de_la_piece_ne_passe_pas_pour_le_son(self):
        # le micro entend la piece a -38 dB avant comme pendant le son : rien de l'ordinateur
        ok, lignes = reunion.verdict_essai(-38.0, -36.0, -20.0)
        self.assertFalse(ok)
        self.assertTrue(lignes[0].startswith("Son de l'ordinateur : rien capté"))

    def test_ffmpeg_absent(self):
        with tempfile.TemporaryDirectory() as dossier:
            essai = pathlib.Path(dossier) / "essai.mov"
            essai.write_bytes(b"x")
            with mock.patch.object(reunion, "nombre_de_pistes_audio", side_effect=FileNotFoundError):
                ok, lignes, niveaux = reunion.mesurer_essai(essai)
            self.assertFalse(ok)
            self.assertIn("brew install ffmpeg", lignes[0])
            self.assertFalse(essai.exists())

    def test_plusieurs_pistes_sont_melangees(self):
        self.assertIn("-af", reunion.commande_niveau("e.mov", 1, 2))
        commande = reunion.commande_niveau("e.mov", 1, 2, nb_pistes=2)
        graphe = commande[commande.index("-filter_complex") + 1]
        self.assertTrue(graphe.startswith("amix=inputs=2:normalize=0,atrim=start=1:end=2"))

    @staticmethod
    def fabriquer(cible: pathlib.Path, *arguments: str) -> None:
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", *arguments, str(cible)],
                       check=True)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_mesure_d_un_vrai_fichier_puis_effacement(self):
        with tempfile.TemporaryDirectory() as dossier:
            essai = pathlib.Path(dossier) / "essai.m4a"
            # 1 s de silence, 3 s de son (l'ordinateur), puis 6 s de silence : un micro muet
            self.fabriquer(essai, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1",
                           "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
                           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=6",
                           "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1")
            ok, lignes, niveaux = reunion.mesurer_essai(essai)
            self.assertFalse(ok)
            self.assertTrue(lignes[0].startswith("Son de l'ordinateur : capté"))
            self.assertTrue(lignes[1].startswith("Micro : rien capté"))
            self.assertIn("son -", niveaux)
            self.assertFalse(essai.exists())

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_deux_pistes_separees(self):
        with tempfile.TemporaryDirectory() as dossier:
            essai = pathlib.Path(dossier) / "essai.mov"
            # piste 0 : l'ordinateur, de 1 a 4 s ; piste 1 : le micro, de 4 a 10 s
            self.fabriquer(essai, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1",
                           "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
                           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=6",
                           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=4",
                           "-f", "lavfi", "-i", "sine=frequency=330:duration=6",
                           "-filter_complex",
                           "[0][1][2]concat=n=3:v=0:a=1[a];[3][4]concat=n=2:v=0:a=1[b]",
                           "-map", "[a]", "-map", "[b]", "-c:a", "aac")
            self.assertEqual(reunion.nombre_de_pistes_audio(essai), 2)
            ok, lignes, _ = reunion.mesurer_essai(essai)
            self.assertTrue(ok, lignes)


class Accueil(unittest.TestCase):
    def test_deja_accueilli(self):
        with tempfile.TemporaryDirectory() as dossier:
            etat, films = pathlib.Path(dossier) / "etat", pathlib.Path(dossier) / "films"
            films.mkdir()
            with mock.patch.object(reunion, "dossier_etat", return_value=etat), \
                    mock.patch.object(reunion, "dossier_enregistrements", return_value=films):
                self.assertFalse(reunion.deja_accueilli())
                # mise a jour depuis 0.4 : des reunions existent deja, pas d'accueil
                (films / "Reunion 2026-11-20 10-00-00.txt").write_text("x")
                self.assertTrue(reunion.deja_accueilli())
                (films / "Reunion 2026-11-20 10-00-00.txt").unlink()
                etat.mkdir()
                reunion.fichier_bienvenue().touch()
                self.assertTrue(reunion.deja_accueilli())


class ModeleWhisper(unittest.TestCase):
    def cache(self, dossier: pathlib.Path, empreinte_poids: str) -> pathlib.Path:
        blobs, instantane = dossier / "blobs", dossier / "snapshots" / "abc"
        blobs.mkdir(parents=True)
        instantane.mkdir(parents=True)
        (blobs / empreinte_poids).write_bytes(b"poids")
        (blobs / "config").write_text("{}")
        (instantane / "weights.npz").symlink_to(blobs / empreinte_poids)
        (instantane / "config.json").symlink_to(blobs / "config")
        return instantane

    def test_poids_complets_reconnus_par_leur_empreinte(self):
        attendue = transcription.EMPREINTES_WHISPER["weights.npz"]
        with tempfile.TemporaryDirectory() as dossier:
            instantane = self.cache(pathlib.Path(dossier), attendue)
            self.assertTrue(transcription.fichiers_whisper_complets(str(instantane)))
            (instantane / "weights.npz").unlink()  # telechargement interrompu
            self.assertFalse(transcription.fichiers_whisper_complets(str(instantane)))

    def test_poids_d_une_autre_version_refuses(self):
        with tempfile.TemporaryDirectory() as dossier:
            instantane = self.cache(pathlib.Path(dossier), "0" * 64)
            self.assertFalse(transcription.fichiers_whisper_complets(str(instantane)))
            with self.assertRaises(transcription.ErreurTranscription) as erreur:
                transcription.verifier_whisper(str(instantane))
            self.assertIn("empreinte inattendue pour config.json", str(erreur.exception))

    def test_version_figee(self):
        self.assertRegex(transcription.REVISION_WHISPER, r"^[0-9a-f]{40}$")
        for empreinte in transcription.EMPREINTES_WHISPER.values():
            self.assertRegex(empreinte, r"^[0-9a-f]{64}$")


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
