"""Fusion du texte et des voix, et fichiers produits. Aucune dependance lourde."""
import json
import os
import tempfile
import unittest

from transcription_locale.fusion import (Passage, Replique, Segment, attribuer, locuteur_du_segment,
                                         nombre_de_locuteurs, parts_de_parole, regrouper_tours)
from transcription_locale.sorties import (ecrire_resultats, ecrire_segments, horodatage, horodatage_srt,
                                          lire_segments, sous_titres, texte_lisible)

SEGMENTS = [
    Segment(0.0, 4.0, "Bonjour à tous."),
    Segment(4.0, 9.0, "Merci de nous recevoir."),
    Segment(9.5, 12.0, "Première question."),
    Segment(12.0, 15.0, "Je vous réponds."),
]
PASSAGES = [Passage(0.0, 9.2, 7), Passage(9.2, 11.8, 3), Passage(11.9, 15.0, 7)]


class Attribution(unittest.TestCase):
    def test_le_plus_grand_chevauchement_l_emporte(self):
        self.assertEqual(locuteur_du_segment(Segment(9.0, 11.0, "x"), PASSAGES), 3)

    def test_sans_chevauchement_le_passage_le_plus_proche(self):
        passages = [Passage(0.0, 1.0, 1), Passage(10.0, 11.0, 2)]
        self.assertEqual(locuteur_du_segment(Segment(8.0, 9.0, "x"), passages), 2)

    def test_aucun_passage(self):
        self.assertIsNone(locuteur_du_segment(Segment(0.0, 1.0, "x"), []))
        self.assertEqual({r.locuteur for r in attribuer(SEGMENTS, [])}, {"Locuteur 1"})

    def test_noms_dans_l_ordre_de_prise_de_parole(self):
        repliques = attribuer(SEGMENTS, PASSAGES)
        self.assertEqual([r.locuteur for r in repliques],
                         ["Locuteur 1", "Locuteur 1", "Locuteur 2", "Locuteur 1"])
        self.assertEqual(nombre_de_locuteurs(repliques), 2)

    def test_tours_de_parole(self):
        tours = regrouper_tours(attribuer(SEGMENTS, PASSAGES))
        self.assertEqual(len(tours), 3)
        self.assertEqual(tours[0], Replique(0.0, 9.0, "Locuteur 1", "Bonjour à tous. Merci de nous recevoir."))

    def test_parts_de_parole(self):
        parts = dict(parts_de_parole(attribuer(SEGMENTS, PASSAGES)))
        self.assertAlmostEqual(parts["Locuteur 1"], 12 / 14.5)
        self.assertAlmostEqual(sum(parts.values()), 1.0)


class Sorties(unittest.TestCase):
    def test_horodatages(self):
        self.assertEqual(horodatage(3725.9), "1:02:05")
        self.assertEqual(horodatage_srt(3725.0456), "01:02:05,046")

    def test_texte_par_tours(self):
        texte = texte_lisible("essai.wav", attribuer(SEGMENTS, PASSAGES))
        self.assertIn("Locuteurs : 2", texte)
        self.assertIn("[0:00:09] Locuteur 2 :\nPremière question.", texte)

    def test_sous_titres(self):
        srt = sous_titres(attribuer(SEGMENTS[:2], PASSAGES))
        self.assertTrue(srt.startswith("1\n00:00:00,000 --> 00:00:04,000\nLocuteur 1 : Bonjour à tous.\n"))
        self.assertIn("\n2\n00:00:04,000 --> 00:00:09,000\n", srt)
        self.assertIn("1\n00:00:00,000 --> 00:00:04,000\nBonjour à tous.\n", sous_titres(SEGMENTS[:1]))

    def test_fichiers_ecrits_et_cache_relu(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "essai")
            ecrits = ecrire_resultats(base, "/chemin/prive/essai.16k.wav", 1.1,
                                      repliques=attribuer(SEGMENTS, PASSAGES))
            self.assertEqual([os.path.basename(e) for e in ecrits], ["essai.txt", "essai.srt", "essai.json"])
            with open(f"{base}.json", encoding="utf-8") as f:
                donnees = json.load(f)
            self.assertEqual(donnees["source"], "essai.16k.wav")  # jamais le chemin complet
            self.assertEqual((donnees["seuil"], donnees["locuteurs"]), (1.1, 2))
            cache = ecrire_segments(f"{base}.segments.json", "essai.16k.wav", "modele", SEGMENTS)
            self.assertEqual(lire_segments(cache), SEGMENTS)

    def test_sortie_sans_locuteurs(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "essai")
            ecrire_resultats(base, "essai.16k.wav", None, segments=SEGMENTS)
            with open(f"{base}.txt", encoding="utf-8") as f:
                texte = f.read()
        self.assertNotIn("Locuteur", texte)
        self.assertIn("[0:00:12] Je vous réponds.", texte)


if __name__ == "__main__":
    unittest.main()
