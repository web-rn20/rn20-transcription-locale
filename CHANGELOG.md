# Journal des versions

Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Tant qu'il reste en 0.x, les options et le format des fichiers produits peuvent changer d'une version à l'autre.

## Non publié

- Commandes `reunion` et `raccourci` : une icône Réunion dans le Dock enregistre une visio (son de l'ordinateur et micro) avec ScreenCaptureKit, sans logiciel tiers, puis lance la transcription en arrière-plan. Un badge coloré dans la barre des menus montre l'état (jaune, rouge, vert, gris) et son menu explique ce qui se passe et ce qu'on peut faire. Notifications au démarrage, à l'arrêt et à la fin. Seul le son est gardé, en `.m4a`. macOS 15 ou plus récent. Les voix des réunions sont séparées au seuil 0,8, mieux adapté au son de visio que le défaut.
- Les génériques de sous-titrage que Whisper invente sur les silences (« Sous-titrage ST' 501 », Amara.org) sont retirés de la transcription.
- Nouvelles dépendances sur macOS : PyObjC (MIT) et rumps (BSD).

## 0.1.0 (2026-10-01)

Première version publique : commande `transcription-locale` avec transcription MLX-Whisper, séparation des voix sherpa-onnx, comparaison des seuils, régénération sans retranscrire, assemblage des sessions coupées en plusieurs fichiers, modèles téléchargés et vérifiés par empreinte, skill Claude Code.
