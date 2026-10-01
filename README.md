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

Les modèles ne sont pas inclus dans ce dépôt. Les deux modèles de séparation des voix sont téléchargés depuis les publications de sherpa-onnx sur GitHub et vérifiés par leur empreinte SHA-256 avant usage. Ils sont rangés dans `~/.cache/rn20-transcription-locale`, ou dans le dossier indiqué par la variable `TRANSCRIPTION_LOCALE_MODELES`. Le code s'appuie sur [mlx-whisper](https://github.com/ml-explore/mlx-examples) (MIT), sherpa-onnx (Apache-2.0) et NumPy (BSD), et appelle [ffmpeg](https://ffmpeg.org) comme programme externe.

## Contribuer

Les signalements et les propositions sont les bienvenus. Le mode d'emploi et les règles du dépôt sont dans [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[MIT](LICENSE). Développé à Toulouse par [RN20](https://rn20.digital), agence-laboratoire IA des filières agricoles et viticoles.
