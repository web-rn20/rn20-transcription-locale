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
| `SKILL.md` | Instructions du skill Claude Code |
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

- **L'audio et le texte ne quittent pas la machine.** Le seul accès réseau est le téléchargement des modèles. Tout nouveau modèle a une URL fixe et une empreinte SHA-256 vérifiée avant usage.
- **Aucun enregistrement réel dans le dépôt.** Ni audio, ni transcription, ni extrait, même court. Les essais utilisent des voix de synthèse. Le `.gitignore` exclut les formats audio et les fichiers produits.
- **Les dépendances lourdes se chargent au dernier moment.** `mlx_whisper`, `sherpa_onnx` et `numpy` s'importent dans les fonctions qui les utilisent, pour que les tests et `--help` fonctionnent partout.
- **Des erreurs qui disent quoi faire.** Une erreur prévisible (fichier absent, ffmpeg manquant, modèle corrompu) produit un message en français qui nomme le fichier en cause, et le code de sortie 2.
- **Les fichiers produits ne contiennent pas de chemin complet.** Seul le nom du fichier source y figure.
- **Licences vérifiées.** Un modèle ou une dépendance ajoutés doivent permettre l'usage commercial, et leur licence est citée dans le README.
- **Python 3.10 ou plus récent**, messages et documentation en français.

## Proposer une modification

Forker le dépôt, travailler sur une branche, ouvrir une pull request. La CI doit passer. Une modification du seuil par défaut ou des réglages de séparation s'accompagne des enregistrements de synthèse utilisés pour la mesurer et des résultats obtenus.
