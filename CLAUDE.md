# Revue de code (rn20-transcription-locale)

Avant tout merge sur `main` : `/code-review high`. Niveau `max` si le diff ajoute un
appel réseau, touche au téléchargement ou à la vérification des modèles, ou change ce
qui est écrit sur le disque.

Chaque revue vérifie les règles du dépôt décrites dans CONTRIBUTING.md :

@CONTRIBUTING.md

## Choix de stack

Site de présentation (`site/`) : une page HTML et CSS écrite à la main, publiée par GitHub
Pages à l'adresse github.io du dépôt. Pas d'Astro (défaut RN20 pour un site public) : une
seule page, aucun contenu édité par un client, et rien à construire ni à mettre à jour.
Passer à Astro si le site dépasse quelques pages. Décision de Julien du 24/11/2026.
