"""Outillage du depot : verification d'une release avant publication."""
import importlib.util
import pathlib
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "notes_de_version", RACINE / ".github" / "scripts" / "notes_de_version.py")
notes_de_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notes_de_version)


class NotesDeVersion(unittest.TestCase):
    def depot(self, version: str, journal: str) -> pathlib.Path:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        dossier = pathlib.Path(temporaire.name)
        (dossier / "transcription_locale").mkdir()
        (dossier / "transcription_locale" / "__init__.py").write_text(
            f'"""x"""\n\n__version__ = "{version}"\n', encoding="utf-8")
        (dossier / "CHANGELOG.md").write_text(journal, encoding="utf-8")
        return dossier

    JOURNAL = "# Journal\n\n## 0.5.0 (2026-12-01)\n\n- Nouveau.\n\n## 0.4.1 (2026-11-24)\n\n- Ancien.\n"

    def test_notes_de_la_seule_version_demandee(self):
        self.assertEqual(notes_de_version.notes("v0.5.0", self.depot("0.5.0", self.JOURNAL)),
                         "- Nouveau.\n")

    def test_refus_si_version_ou_journal_discordants(self):
        cas = (("v0.5.0", self.depot("0.4.1", self.JOURNAL)),   # paquet pas a jour
               ("v0.6.0", self.depot("0.6.0", self.JOURNAL)),   # pas de section
               ("0.5.0", self.depot("0.5.0", self.JOURNAL)),    # etiquette sans v
               ("v0.5.0-rc1", self.depot("0.5.0", self.JOURNAL)))
        for etiquette, racine in cas:
            with self.subTest(etiquette=etiquette), self.assertRaises(ValueError):
                notes_de_version.notes(etiquette, racine)

    def test_titre_avec_espace_final_ou_fin_de_ligne_windows(self):
        journal = "# Journal\r\n\r\n## 0.5.0 (2026-12-01)  \r\n\r\n- Nouveau.\r\n"
        self.assertEqual(notes_de_version.notes("v0.5.0", self.depot("0.5.0", journal)).strip(),
                         "- Nouveau.")

    def test_depot_actuel_coherent(self):
        init = (RACINE / "transcription_locale" / "__init__.py").read_text(encoding="utf-8")
        version = init.split('__version__ = "')[1].split('"')[0]
        self.assertTrue(notes_de_version.notes(f"v{version}", RACINE).strip())


if __name__ == "__main__":
    unittest.main()
