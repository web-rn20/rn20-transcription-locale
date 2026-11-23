# Journal des versions

Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Tant qu'il reste en 0.x, les options et le format des fichiers produits peuvent changer d'une version à l'autre.

## Non publié

- Mise à jour au clic, optionnelle (`transcription-locale raccourci --mises-a-jour`) : une nouvelle release apparaît dans le menu de Réunion une fois la transcription prête, et s'installe sur un clic. Une requête par jour au plus vers l'API publique de GitHub, sans donnée envoyée. Désactivée par défaut.
- Correction : une erreur que macOS signale parfois après la fin de l'enregistrement (ReplayKit -5814) ne fait plus passer au gris une réunion déjà transcrite.

## 0.2.0 (2026-11-23)

- Commandes `reunion` et `raccourci` : une icône Réunion dans le Dock enregistre une visio (son de l'ordinateur et micro) avec ScreenCaptureKit, sans logiciel tiers, puis lance la transcription en arrière-plan. Un badge coloré dans la barre des menus montre l'état (jaune, rouge, vert, gris) et son menu explique ce qui se passe et ce qu'on peut faire. Notifications au démarrage, à l'arrêt et à la fin. Seul le son est gardé, en `.m4a`. macOS 15 ou plus récent. Les voix des réunions sont séparées au seuil 0,8, mieux adapté au son de visio que le défaut.
- Les génériques de sous-titrage que Whisper invente sur les silences (« Sous-titrage ST' 501 », Amara.org) sont retirés de la transcription.
- Nouvelles dépendances sur macOS : PyObjC (MIT) et rumps (BSD).

## 0.1.0 (2026-10-01)

Première version publique : commande `transcription-locale` avec transcription MLX-Whisper, séparation des voix sherpa-onnx, comparaison des seuils, régénération sans retranscrire, assemblage des sessions coupées en plusieurs fichiers, modèles téléchargés et vérifiés par empreinte, skill Claude Code.
