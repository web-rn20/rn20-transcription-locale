# Sécurité

## Signaler une faille

Une faille se signale en privé, par le [formulaire de signalement de GitHub](https://github.com/web-rn20/rn20-transcription-locale/security/advisories/new), jamais dans une issue publique. Décrire ce qui permet de la reproduire, sans joindre d'enregistrement réel. Nous répondons sous une semaine ouvrée, et le correctif est publié dans une release, avec mention de la personne qui l'a signalée si elle le souhaite.

Seule la dernière version publiée est corrigée.

## Ce que l'outil fait de vos données

- L'audio et le texte restent sur le Mac : aucun service tiers ne les reçoit.
- Accès réseau : le téléchargement des modèles (vérifiés par leur empreinte SHA-256 pour la séparation des voix), et, si on l'a activée, une lecture quotidienne de la dernière release sur l'API publique de GitHub, sans aucune donnée envoyée.
- L'application Réunion du Dock est compilée sur le Mac à partir de [`Reunion.swift`](transcription_locale/ressources/Reunion.swift), lisible dans le dépôt. Aucun binaire n'est livré tout fait.
- Les étiquettes de version `v*` sont protégées sur le dépôt : seuls ses administrateurs peuvent les créer ou les déplacer.
