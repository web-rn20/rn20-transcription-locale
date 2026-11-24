"""Mise a jour au clic : lecture de la release, comparaison, commande, sans reseau."""
import pathlib
import tempfile
import unittest
from unittest import mock

from transcription_locale import cli, mises_a_jour as maj


class Etiquettes(unittest.TestCase):
    def test_seules_les_etiquettes_vxyz_sont_acceptees(self):
        self.assertEqual(maj.decoder_etiquette("v0.10.2"), (0, 10, 2))
        for invalide in ("0.2.0", "v0.2", "v0.2.0-rc1", "v0.2.0; rm -rf ~", "main", None, 3):
            self.assertIsNone(maj.decoder_etiquette(invalide), invalide)

    def test_comparaison_numerique(self):
        self.assertTrue(maj.plus_recente("v0.10.0", "0.9.0"))
        self.assertTrue(maj.plus_recente("v0.2.1", "0.2.0"))
        self.assertFalse(maj.plus_recente("v0.2.0", "0.2.0"))
        self.assertFalse(maj.plus_recente("v0.1.9", "0.2.0"))
        self.assertFalse(maj.plus_recente("pas-une-version", "0.2.0"))


class Release(unittest.TestCase):
    def test_release_publiee(self):
        v = maj.lire_release({"tag_name": "v0.3.0", "body": "- Mieux.\n\n- Plus vite.",
                              "draft": False, "prerelease": False})
        self.assertEqual((v.etiquette, v.numero, v.notes), ("v0.3.0", "0.3.0", "- Mieux. - Plus vite."))

    def test_brouillons_preversions_et_etiquettes_douteuses_ignores(self):
        for reponse in ({"tag_name": "v0.3.0", "draft": True},
                        {"tag_name": "v0.3.0", "prerelease": True},
                        {"tag_name": "v0.3.0 && curl x"}, {}):
            self.assertIsNone(maj.lire_release(reponse), reponse)

    def test_notes_tronquees(self):
        v = maj.lire_release({"tag_name": "v1.0.0", "body": "x" * 5000})
        self.assertEqual(len(v.notes), maj.NOTES_MAX)


class Installation(unittest.TestCase):
    def test_commande_figee_sur_l_etiquette(self):
        commande = maj.commande_installation(maj.Version("v0.3.0"), "/u/uv")
        # seul le paquet est reinstalle, pas tout l'environnement sous l'enregistreur qui tourne
        self.assertEqual(commande, ["/u/uv", "tool", "install", "--reinstall-package",
                                    "rn20-transcription-locale",
                                    "git+https://github.com/web-rn20/rn20-transcription-locale@v0.3.0"])

    def test_commande_refusee_si_etiquette_invalide(self):
        with self.assertRaises(ValueError):
            maj.commande_installation(maj.Version("main"), "/u/uv")


class Verification(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(maj, "dossier_etat", return_value=pathlib.Path(self.dossier.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dossier.cleanup)

    def test_desactivee_par_defaut_aucune_requete(self):
        with mock.patch.object(maj, "interroger_github") as github:
            self.assertIsNone(maj.disponible())
            github.assert_not_called()

    def test_une_requete_par_jour_au_plus(self):
        maj.choisir(True)
        reponse = {"tag_name": "v99.0.0", "body": "Nouveau"}
        with mock.patch.object(maj, "interroger_github", return_value=reponse) as github:
            self.assertEqual(maj.disponible(1000.0).etiquette, "v99.0.0")
            self.assertEqual(maj.disponible(1000.0 + 3600).etiquette, "v99.0.0")
            self.assertEqual(github.call_count, 1)
            maj.disponible(1000.0 + maj.INTERVALLE + 1)
            self.assertEqual(github.call_count, 2)

    def test_hors_ligne_sans_erreur(self):
        maj.choisir(True)
        with mock.patch.object(maj, "interroger_github", side_effect=OSError("hors ligne")):
            self.assertIsNone(maj.disponible(1000.0))

    def test_un_echec_compte_aussi_dans_la_limite_du_jour(self):
        maj.choisir(True)
        for erreur in (OSError("hors ligne"), ValueError("JSON"), RuntimeError("HTTP 404")):
            with self.subTest(erreur=erreur), \
                    mock.patch.object(maj, "interroger_github", side_effect=erreur) as github:
                maj.fichier_cache().unlink(missing_ok=True)
                self.assertIsNone(maj.disponible(1000.0))
                self.assertIsNone(maj.disponible(1000.0 + 3600))
                self.assertEqual(github.call_count, 1)

    def test_un_echec_garde_la_derniere_version_connue(self):
        maj.choisir(True)
        with mock.patch.object(maj, "interroger_github", return_value={"tag_name": "v99.0.0"}):
            maj.disponible(1000.0)
        with mock.patch.object(maj, "interroger_github", side_effect=OSError("hors ligne")):
            self.assertEqual(maj.disponible(1000.0 + maj.INTERVALLE + 1).etiquette, "v99.0.0")

    def test_cache_abime_sans_erreur(self):
        maj.choisir(True)
        for contenu in ("[]", '"x"', "{", '{"verifie": "hier"}', '{"etiquette": 3, "verifie": 1000}'):
            with self.subTest(contenu=contenu), \
                    mock.patch.object(maj, "interroger_github", return_value={"tag_name": "v0.0.1"}):
                maj.fichier_cache().write_text(contenu, encoding="utf-8")
                self.assertIsNone(maj.disponible(1000.0))

    def test_version_installee_a_jour(self):
        maj.choisir(True)
        with mock.patch.object(maj, "interroger_github", return_value={"tag_name": "v0.0.1"}):
            self.assertIsNone(maj.disponible(1000.0))

    def test_desactiver(self):
        maj.choisir(True)
        self.assertTrue(maj.activees())
        maj.choisir(False)
        self.assertFalse(maj.activees())


class LigneDeCommande(unittest.TestCase):
    def test_options_exclusives_et_reglage_inchange_par_defaut(self):
        parser = cli.construire_parser()
        self.assertIsNone(parser.parse_args(["raccourci"]).mises_a_jour)
        self.assertTrue(parser.parse_args(["raccourci", "--mises-a-jour"]).mises_a_jour)
        self.assertFalse(parser.parse_args(["raccourci", "--sans-mises-a-jour"]).mises_a_jour)
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            parser.parse_args(["raccourci", "--mises-a-jour", "--sans-mises-a-jour"])


if __name__ == "__main__":
    unittest.main()
