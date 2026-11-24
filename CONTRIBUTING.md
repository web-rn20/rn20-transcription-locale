# Contribuer

Merci de votre intérêt. Le projet est en cours de développement : une issue avant une grosse modification évite de travailler pour rien.

## Organisation du dépôt

| Fichier | Rôle |
|---|---|
| `transcription_locale/cli.py` | Ligne de commande et enchaînement des étapes |
| `transcription_locale/audio.py` | Conversion et assemblage avec ffmpeg, lecture du WAV |
| `transcription_locale/transcription.py` | Transcription MLX-Whisper |
| `transcription_locale/diarisation.py` | Séparation des voix sherpa-onnx |
| `transcription_locale/modeles.py` | Téléchargement et vérification des modèles de séparation |
| `transcription_locale/fusion.py` | Attribution d'un locuteur à chaque segment de texte (module pur) |
| `transcription_locale/sorties.py` | Fichiers texte, SRT et JSON (module pur) |
| `transcription_locale/reunion.py` | Raccourci Réunion : application du Dock, bascule, extraction du son après l'enregistrement (sans PyObjC) |
| `transcription_locale/enregistreur.py` | Enregistreur ScreenCaptureKit, badge et menu de la barre des menus (PyObjC, macOS seulement) |
| `transcription_locale/badge.py` | Dessin du badge de la barre des menus |
| `transcription_locale/ressources/Reunion.swift` | Application Réunion du Dock : lance la bascule, affiche les notifications. Compilée sur chaque Mac par `raccourci` |
| `transcription_locale/verification.py` | Commande `verifier` : prérequis constatés, sans rien installer, avec le remède de chacun |
| `transcription_locale/mises_a_jour.py` | Mise à jour au clic, optionnelle : lecture de la dernière release, installation (sans PyObjC) |
| `SKILL.md` | Instructions du skill Claude Code |
| `site/` | Page de présentation (HTML et CSS écrits à la main, publiée par `.github/workflows/site.yml` sur GitHub Pages) |
| `SECURITY.md` | Signalement privé des failles, données traitées |
| `.github/workflows/release.yml`, `.github/scripts/notes_de_version.py` | Publication d'une release à partir d'une étiquette `vX.Y.Z` poussée depuis `main` |
| `tests/` | Tests unitaires, sans modèle ni réseau |

## Lancer les tests

```sh
python -m unittest discover -s tests
```

Les tests n'ont besoin ni de MLX, ni de sherpa-onnx, ni de ffmpeg, ni du réseau : ils tournent sur n'importe quelle machine. La CI les lance sous Linux et vérifie l'installation complète sur un Mac Apple Silicon.

Pour un essai de bout en bout, la synthèse vocale de macOS fabrique un enregistrement sans données personnelles :

```sh
say -v Jacques -o q.aiff "Pouvez-vous présenter votre exploitation ?"
say -v Flo -o r.aiff "Nous cultivons cent vingt hectares de blé et de tournesol."
```

Sur un entretien de synthèse de ce type, le texte sort sans faute et les deux voix se séparent entre 0,5 et 0,7, mais fusionnent dès 0,9. Les voix de synthèse sont trop propres et trop courtes pour régler le seuil par défaut, qui vient d'enregistrements réels.

## Règles du dépôt

Elles sont vérifiées à chaque revue.

- **L'audio et le texte ne quittent pas la machine.** Deux accès réseau seulement : le téléchargement des modèles, et, si l'utilisateur l'a activée, la lecture quotidienne de la dernière release sur l'API publique de GitHub, sans aucune donnée envoyée. La mise à jour ne suit que les releases (étiquettes `vX.Y.Z` validées avant usage, protégées sur GitHub) et ne s'installe que sur un clic. L'enregistrement des réunions reste local, et seul le son est gardé sur le disque. Tout nouveau modèle a une URL fixe (ou, sur Hugging Face, une révision figée) et une empreinte SHA-256 vérifiée avant usage.
- **Aucun enregistrement réel dans le dépôt.** Ni audio, ni transcription, ni extrait, même court. Les essais utilisent des voix de synthèse. Le `.gitignore` exclut les formats audio et les fichiers produits.
- **Les dépendances lourdes se chargent au dernier moment.** `mlx_whisper`, `sherpa_onnx` et `numpy` s'importent dans les fonctions qui les utilisent, pour que les tests et `--help` fonctionnent partout PyObjC et rumps ne s'importent que dans `enregistreur.py` et `badge.py`, que ni la ligne de commande ni les tests n'importent.
- **Des erreurs qui disent quoi faire.** Une erreur prévisible (fichier absent, ffmpeg manquant, modèle corrompu) produit un message en français qui nomme le fichier en cause, et le code de sortie 2.
- **Les fichiers produits ne contiennent pas de chemin complet.** Seul le nom du fichier source y figure.
- **Licences vérifiées.** Un modèle ou une dépendance ajoutés doivent permettre l'usage commercial, et leur licence est citée dans le README.
- **Python 3.10 ou plus récent**, messages et documentation en français. L'enregistrement des réunions demande macOS 15.
- **L'application Réunion n'est jamais refaite si elle existe.** macOS rattache l'autorisation d'enregistrer à sa signature : la reconstruire la ferait perdre sans nouvelle demande. Une modification de `Reunion.swift` ne sert donc qu'aux nouvelles installations ; changer `LANCEUR` dans `reunion.py` la ferait reconstruire chez tout le monde, à réserver à un vrai besoin et à annoncer dans le journal des versions.
- **L'application ne fait que deux choses.** Lancer `transcription-locale reunion` et afficher le texte d'un fichier `.notification`, qu'elle efface ensuite. Aucun accès réseau, aucun autre fichier lu, aucun binaire livré tout compilé.

## Le site

Une seule page, `site/index.html`, sans dépendance ni étape de construction, dans un style sobre : police du système, fond blanc et gris clair, un seul bleu pour les liens et les boutons ; les couleurs des états restent réservées au badge. Aucun traceur, aucun cookie, aucune ressource chargée depuis un autre site. Toute image ajoutée a une licence qui permet l'usage commercial, et son crédit est ajouté au pied de page. Les textes du menu montrés dans l'essai simulé reprennent ceux de `enregistreur.py` (seul le menu d'accueil « Essayez le badge » est propre à la page) : les mettre à jour ensemble.

## Publier une version

1. Dans la pull request : monter `__version__` dans `transcription_locale/__init__.py` et ajouter au journal des versions une section `## X.Y.Z (date)`.
2. Après la fusion, depuis `main` à jour : `git tag vX.Y.Z && git push origin vX.Y.Z`. Seuls les administrateurs du dépôt peuvent pousser une étiquette `v*`.
3. L'action Release vérifie que l'étiquette pointe sur un commit de `main`, et que l'étiquette, `__version__` et le journal concordent, puis publie la release avec les notes du journal. Une discordance bloque la publication.

La protection des étiquettes `v*` n'est pas dans le dépôt : c'est la règle « Etiquettes de version protegees » de ses réglages GitHub (Rules). La mise à jour au clic en dépend. Sur un fork ou un dépôt recréé, la poser avant toute release.

## Proposer une modification

Forker le dépôt, travailler sur une branche, ouvrir une pull request. La CI doit passer. Une modification du seuil par défaut ou des réglages de séparation s'accompagne des enregistrements de synthèse utilisés pour la mesurer et des résultats obtenus.
