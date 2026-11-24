# Journal des versions

Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Tant qu'il reste en 0.x, les options et le format des fichiers produits peuvent changer d'une version à l'autre.

## 0.5.0 (2026-11-24)

- Accueil au premier clic sur Réunion : un essai de 10 secondes vérifie que le son de l'ordinateur et le micro sont captés, et dit quoi régler sinon. Il se refait depuis le menu du badge.
- Autorisation guidée : sans autorisation d'enregistrer, Réunion ouvre les Réglages au bon endroit et démarre tout seul dès que Réunion y est activé, sans recliquer.
- `raccourci` télécharge d'avance Whisper (environ 3 Go) et les modèles de séparation des voix ; `--sans-modeles` pour s'en passer. `modeles` prépare aussi Whisper.
- Nouvelle commande `verifier` : prérequis, application, modèles, chacun avec la commande qui le répare.
- Whisper se télécharge dans une version figée, vérifiée par l'empreinte SHA-256 de ses fichiers, comme les modèles de séparation des voix.
- Mise à jour depuis 0.4 : l'accueil ne s'affiche pas si des réunions ont déjà été enregistrées ; le premier clic enregistre comme avant.

## 0.4.1 (2026-11-24)

- Le badge vert s'efface seul une minute après la transcription, et le Finder montre le texte dès qu'il est prêt. Il reste affiché tant qu'une mise à jour est proposée, son menu étant le seul endroit où l'installer.

## 0.4.0 (2026-11-24)

- L'application Réunion du Dock devient une petite application native (`Reunion.swift`, compilée sur le Mac par `raccourci`) : les notifications portent l'icône de Réunion au lieu de l'icône de script. L'ancienne application AppleScript est remplacée une fois : relancer `transcription-locale raccourci`, puis redonner l'autorisation d'enregistrer l'écran et accepter les notifications de Réunion. Demande les outils de développement d'Apple (`xcode-select --install`).
- L'application Réunion ne se laisse jamais à moitié remplacée : l'ancienne est remise en place si le remplacement échoue. Une notification ne peut plus démarrer ni arrêter un enregistrement, et un message arrivé pendant la fermeture de l'application n'est plus perdu. L'application ne lit que son dossier de messages, ne reste jamais bloquée en arrière-plan, et note dans le journal système pourquoi ses notifications sont refusées.

## 0.3.0 (2026-11-24)

- Mise à jour au clic, optionnelle (`transcription-locale raccourci --mises-a-jour`) : une nouvelle release apparaît dans le menu de Réunion une fois la transcription prête, et s'installe sur un clic. Une requête par jour au plus vers l'API publique de GitHub, sans donnée envoyée. Désactivée par défaut.
- Correction : une erreur que macOS signale parfois après la fin de l'enregistrement (ReplayKit -5814) ne fait plus passer au gris une réunion déjà transcrite, et n'empêche plus la transcription quand elle survient juste après l'arrêt.

## 0.2.0 (2026-11-23)

- Commandes `reunion` et `raccourci` : une icône Réunion dans le Dock enregistre une visio (son de l'ordinateur et micro) avec ScreenCaptureKit, sans logiciel tiers, puis lance la transcription en arrière-plan. Un badge coloré dans la barre des menus montre l'état (jaune, rouge, vert, gris) et son menu explique ce qui se passe et ce qu'on peut faire. Notifications au démarrage, à l'arrêt et à la fin. Seul le son est gardé, en `.m4a`. macOS 15 ou plus récent. Les voix des réunions sont séparées au seuil 0,8, mieux adapté au son de visio que le défaut.
- Les génériques de sous-titrage que Whisper invente sur les silences (« Sous-titrage ST' 501 », Amara.org) sont retirés de la transcription.
- Nouvelles dépendances sur macOS : PyObjC (MIT) et rumps (BSD).

## 0.1.0 (2026-10-01)

Première version publique : commande `transcription-locale` avec transcription MLX-Whisper, séparation des voix sherpa-onnx, comparaison des seuils, régénération sans retranscrire, assemblage des sessions coupées en plusieurs fichiers, modèles téléchargés et vérifiés par empreinte, skill Claude Code.
