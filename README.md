# Transcription locale RN20

[![CI](https://github.com/web-rn20/rn20-transcription-locale/actions/workflows/ci.yml/badge.svg)](https://github.com/web-rn20/rn20-transcription-locale/actions/workflows/ci.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
![Mac Apple Silicon](https://img.shields.io/badge/macOS-Apple%20Silicon-lightgrey)
![Statut : en cours de développement](https://img.shields.io/badge/statut-en%20cours%20de%20d%C3%A9veloppement-orange)

Un outil en ligne de commande qui transcrit des enregistrements en français et sépare les intervenants, entièrement sur un Mac Apple Silicon. L'audio ne quitte pas la machine. Il n'y a ni compte à créer ni clé d'API, et seuls les modèles sont téléchargés, une fois, au premier lancement.

L'outil est né pour transcrire une journée de conférences, environ cinq heures d'audio prises avec des micros-cravates et un enregistreur de salle. Il sert aussi pour des entretiens et des réunions.

> Projet en cours de développement. Les options et le format des fichiers produits peuvent encore changer entre deux versions. Les retours sont bienvenus dans les [issues](https://github.com/web-rn20/rn20-transcription-locale/issues).

## Installation

L'outil demande un Mac Apple Silicon (M1 ou plus récent), Python 3.10 ou plus récent et ffmpeg.

```sh
brew install ffmpeg
uv tool install git+https://github.com/web-rn20/rn20-transcription-locale
```

`pipx install git+https://github.com/web-rn20/rn20-transcription-locale` fonctionne aussi. Les modèles de séparation des voix (environ 110 Mo) peuvent être préparés à l'avance avec `transcription-locale modeles`. Le modèle de transcription Whisper large-v3 pèse environ 3 Go et se télécharge à la première transcription.

## Utilisation

```sh
transcription-locale transcrire entretien.m4a
```

La commande écrit ses fichiers à côté de l'enregistrement.

| Fichier | Contenu |
|---|---|
| `entretien.txt` | Le texte par tours de parole, avec l'heure de chaque prise de parole |
| `entretien.srt` | Des sous-titres, un par segment, préfixés du locuteur |
| `entretien.json` | Les segments avec leurs horaires et leur locuteur, pour un autre programme |
| `entretien.16k.wav` et `entretien.segments.json` | L'audio converti et le texte brut, gardés pour recalculer les locuteurs sans retranscrire |

Certains enregistreurs coupent une longue session en plusieurs fichiers. On les donne dans l'ordre, et `-o` fixe le nom des fichiers produits :

```sh
transcription-locale transcrire PARTIE1.WAV PARTIE2.WAV PARTIE3.WAV -o conference
```

`--sans-locuteurs` donne le texte seul, et `--langue en` transcrit un enregistrement en anglais.

## Enregistrer une réunion en un clic

Les notes automatiques de Google Meet ou de Teams dépendent de l'abonnement de l'organisateur. Un invité extérieur n'y a pas accès. Une icône Réunion dans le Dock comble ce manque pour n'importe quelle visio : un clic lance l'enregistrement, un second l'arrête et lance la transcription. Une notification signale la fin, et le Finder montre le texte.

L'enregistrement passe par ScreenCaptureKit, l'outil de capture intégré à macOS : il capte à la fois le son de l'ordinateur (les autres participants, même au casque) et le micro (soi). Aucun logiciel tiers n'est nécessaire. Il faut macOS 15 ou plus récent.

```sh
transcription-locale raccourci
```

La commande pose l'application `~/Applications/Réunion.app` dans le Dock. `--sans-dock` crée l'application sans l'épingler.

Au premier clic, macOS demande l'autorisation d'enregistrer l'écran et l'audio système, puis le micro. Si la demande n'apparaît pas, le badge gris de la barre des menus propose « Ouvrir les Réglages » : cocher Réunion dans « Enregistrement de l'écran et des sons du système », puis recliquer sur Réunion dans le Dock. L'autorisation se donne une fois par Mac. macOS la rattache à la signature de l'application : `raccourci` ne refait donc jamais une application déjà en place, et les mises à jour de l'outil ne la touchent pas. `--reconstruire` force sa recréation, au prix d'une nouvelle autorisation.

Pendant la réunion, un badge dans la barre des menus montre où l'on en est :

| Badge | État | Au clic, le menu propose |
|---|---|---|
| Jaune | Préparation, puis transcription | Durée écoulée, dossier des réunions |
| Rouge, avec la durée et un carré stop | Enregistrement en cours | Durée, rappel de prévenir les participants, « Arrêter et transcrire » |
| Vert | Transcription prête | Ouvrir la transcription, l'afficher dans le Finder, fermer |
| Gris | Problème | Explication, Réglages si l'autorisation manque, journal |

Un clic sur Réunion dans le Dock fait la même chose que le badge : il démarre, arrête, ou, une fois la transcription prête, lance un nouvel enregistrement. Une notification signale le démarrage, l'arrêt et la fin de la transcription.

| Emplacement | Contenu |
|---|---|
| `~/Movies/Reunions` | Les enregistrements (`Reunion 2026-11-23 14-00-00.m4a`) et leurs transcriptions, côte à côte |
| `~/Library/Logs/transcription-locale` | Le journal de l'enregistreur (`reunion.log`) et un journal par transcription |

ScreenCaptureKit impose une piste vidéo : l'écran est capté en vignette de 64 × 36 pixels, une image par seconde. À l'arrêt, seul le son est gardé, en `.m4a`, et la vidéo est supprimée. Si l'extraction du son échoue, la vidéo reste et c'est elle qui est transcrite ; le journal le signale. Rien d'autre n'est supprimé automatiquement : les enregistrements restent jusqu'à ce qu'on les efface.

Points d'attention :

- **Prévenir les participants** en début de réunion que l'on enregistre pour le compte rendu. Contrairement aux notes de Meet, l'enregistrement local ne l'annonce à personne.
- Les voix sont séparées au seuil 0,8, plus bas que le défaut (1,1) réglé sur des micros-cravates : sur un son de visio, les voix se ressemblent davantage. Si deux personnes sont fondues en une, ou une personne éclatée en plusieurs, comparer puis régénérer sans retranscrire : `transcription-locale seuils "~/Movies/Reunions/Reunion 2026-11-23 14-00-00"`, puis `transcription-locale locuteurs "…" --seuil 0.9`.
- Whisper invente parfois une phrase sur un long silence. Les génériques de sous-titrage (« Sous-titrage ST' 501 », « Sous-titres réalisés par la communauté d'Amara.org ») sont retirés automatiquement. D'autres formules, comme « Merci d'avoir regardé cette vidéo », restent, car elles peuvent être prononcées pour de vrai.
- Une version précédente passait par OBS Studio. Si elle a été installée, OBS n'est plus nécessaire : on peut le désinstaller, avec son profil « Reunion RN20 ».

## Régler la séparation des voix

La séparation repose sur un seuil, la distance entre deux empreintes vocales au-delà de laquelle on considère qu'il s'agit de deux personnes. Un seuil bas éclate une même personne en plusieurs voix ; un seuil haut finit par fondre deux personnes en une. Le bon réglage dépend d'abord du micro.

| Enregistrement | Seuil constaté |
|---|---|
| Micro-cravate, son propre | 0,95 à 1,2 |
| Enregistreur de salle, micro lointain | 1,1 à 1,4 |
| Entretien à deux voix | autour de 1,3 |

La commande `seuils` compare plusieurs valeurs sans retranscrire. Pour chacune, elle affiche le nombre de locuteurs et leur part du temps de parole, avec le début de l'échange. On retient le seuil où le nombre de voix se stabilise sur un chiffre plausible, puis on régénère le résultat.

```sh
transcription-locale seuils conference --valeurs 1.0,1.1,1.2,1.3,1.4
transcription-locale locuteurs conference --seuil 1.3
```

Quand on connaît le nombre d'intervenants, `--nb-locuteurs 2` l'impose directement.

Une limite tient à la physique. Avec un seul micro au fond de la salle, l'orateur se distingue bien de l'animateur et des questions, mais chaque personne du public ne peut pas être séparée proprement. Le texte, lui, reste bon.

## Vitesse

Sur un MacBook Pro M5 Pro, la transcription avec Whisper large-v3 prend environ 6 minutes pour une heure d'audio, sur le processeur graphique. La séparation des voix tourne sur le processeur et demande quelques minutes par heure.

## Comme skill Claude Code

Le dépôt est aussi un skill pour [Claude Code](https://claude.com/claude-code). Claude repère les fichiers d'une même session, lance la transcription, vérifie que le nombre de voix est plausible et résume le résultat.

```sh
git clone https://github.com/web-rn20/rn20-transcription-locale.git ~/.claude/skills/transcription-locale
```

## Modèles et licences

| Rôle | Modèle | Licence |
|---|---|---|
| Transcription | [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3) d'OpenAI, [converti pour MLX](https://huggingface.co/mlx-community/whisper-large-v3-mlx) | Apache-2.0, conversion sous MIT |
| Détection de la parole | [pyannote segmentation 3.0](https://huggingface.co/pyannote/segmentation-3.0), export ONNX de [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | MIT |
| Empreinte vocale | [NVIDIA NeMo TitaNet large](https://huggingface.co/nvidia/speakerverification_en_titanet_large), export ONNX de sherpa-onnx | CC-BY-4.0 |

Les modèles ne sont pas inclus dans ce dépôt. Les deux modèles de séparation des voix sont téléchargés depuis les publications de sherpa-onnx sur GitHub et vérifiés par leur empreinte SHA-256 avant usage. Ils sont rangés dans `~/.cache/rn20-transcription-locale`, ou dans le dossier indiqué par la variable `TRANSCRIPTION_LOCALE_MODELES`. Le code s'appuie sur [mlx-whisper](https://github.com/ml-explore/mlx-examples) (MIT), sherpa-onnx (Apache-2.0) et NumPy (BSD). L'enregistrement des réunions s'appuie sur [PyObjC](https://github.com/ronaldoussoren/pyobjc) (MIT) et [rumps](https://github.com/jaredks/rumps) (BSD). Il appelle [ffmpeg](https://ffmpeg.org) comme programme externe, sans l'embarquer.

## Contribuer

Les signalements et les propositions sont les bienvenus. Le mode d'emploi et les règles du dépôt sont dans [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[MIT](LICENSE). Développé à Toulouse par [RN20](https://rn20.digital), agence-laboratoire IA des filières agricoles et viticoles.
