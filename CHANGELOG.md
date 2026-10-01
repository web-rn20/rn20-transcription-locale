# Journal des versions

Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Tant qu'il reste en 0.x, les options et le format des fichiers produits peuvent changer d'une version à l'autre.

## Non publié

- Commandes `reunion` et `raccourci` : une icône Réunion dans le Dock démarre l'enregistrement OBS d'une visio (son de l'ordinateur et micro), puis l'arrête et lance la transcription en arrière-plan avec une notification à la fin.
- Nouvelle dépendance : websockets (BSD-3-Clause), pour piloter OBS en local.

## 0.1.0 (2026-10-01)

Première version publique : commande `transcription-locale` avec transcription MLX-Whisper, séparation des voix sherpa-onnx, comparaison des seuils, régénération sans retranscrire, assemblage des sessions coupées en plusieurs fichiers, modèles téléchargés et vérifiés par empreinte, skill Claude Code.
