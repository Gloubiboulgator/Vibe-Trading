# Roadmap du fork

Travaux prévus sur la branche `perso` de ce fork. La roadmap du projet d'origine
est dans [guides/project.md](guides/project.md#-roadmap).

## À faire

- **Revue complète des refus du contrôle des chiffres.** Rejouer hors ligne tous
  les brouillons refusés des sessions passées (`~/.vibe-trading/sessions/*/trace.jsonl`)
  contre les preuves de chaque session, sans appel facturé. Trier vrais refus
  (chiffre faux ou inventé) et faux refus (bon chiffre bloqué par une règle trop
  étroite), corriger les faux refus par famille de règles, et vérifier que chaque
  correction ne réouvre aucun vrai refus.
