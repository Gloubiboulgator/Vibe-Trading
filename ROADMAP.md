# Roadmap du fork

Travaux prévus sur la branche `perso` de ce fork. La roadmap du projet d'origine
est dans [guides/project.md](guides/project.md#-roadmap).

## À faire

### Corriger en masse les refus du contrôle des chiffres, sans appel facturé

**Constat.** Jusqu'ici, chaque erreur a été corrigée à partir de la question qui
venait de la produire, puis vérifiée par une relance facturée. Chaque relance
révélait la famille de refus suivante, et deux corrections ont même créé de
nouveaux refus que le rejeu ne montrait pas (quota de preuves rempli par les
tours précédents, symboles des tours précédents exigés). Le plan inverse
l'ordre : tout mesurer hors ligne d'abord, corriger par famille, relancer le
moins possible.

**Corpus.** Tout ce qui est déjà stocké : chaque `trace.jsonl` de
`~/.vibe-trading/sessions` garde les brouillons et les résultats d'outils, et
chaque run garde ses preuves (`artifacts/grounding_evidence.json`). Il reste en
local et n'entre jamais dans le dépôt : les tests utilisent des valeurs
inventées.

1. **Un rejeu fidèle au service.** Étendre `agent/scripts/replay_grounding.py`
   pour qu'il construise le contrôle exactement comme `loop.py` : identités et
   preuves des tours précédents, résultats d'outils réingérés tels quels, puis
   toute la chaîne (validation, récupération, version expurgée, réponse de
   secours). Un seul point de construction partagé avec `loop.py`, pour que le
   rejeu ne puisse plus diverger du service.
2. **Un bilan chiffré.** Pour chaque brouillon : les refus par code et par
   raison ; pour chaque question : brouillon qui passe, chiffres retirés,
   réponse de secours. Un fichier de référence garde ce bilan ; chaque
   correction est comparée à lui.
3. **Un tri automatique.** Un refus est suspect (faux refus probable) quand sa
   valeur existe dans les preuves de la session sous une autre forme : autre
   notation, autre échelle (milliards, millions), autre outil, autre tour, ou
   quand un brouillon suivant fait passer la même valeur. Une valeur absente de
   toutes les preuves est un vrai refus. Seuls les suspects demandent une
   lecture humaine.
4. **Corriger par famille, du plus coûteux au moins coûteux.** Classer les
   familles par chiffres retirés et par réponses de secours, puis par
   brouillons refaits. Pour chaque famille : un test avec des valeurs
   inventées, la correction, puis le rejeu du corpus entier. Une correction qui
   fait passer un vrai refus est rejetée.
5. **Réduire les vrais refus du modèle.** Les plus fréquents (source pas sur la
   même ligne, chiffre non déclaré, estimation présentée comme un calcul) coûtent
   un brouillon facturé chacun. Mesurer sur le corpus quelles consignes du
   message de correction et du prompt système les évitent, en comparant le
   1er et le 2e brouillon de chaque question.
6. **Les outils à part.** Relever dans `journalctl --user -u vibe-trading` et
   dans les traces les appels en échec, groupés par outil et par cause
   (symbole introuvable comme « Airbnb » lu comme une paire de cryptos, source
   sans données, coupure réseau), et les corriger dans le même ordre de coût.
7. **Relancer peu, et seulement à la fin.** Le rejeu tient lieu de
   vérification. Une relance facturée ne se fait qu'après un lot de familles,
   sur deux ou trois questions représentatives, et jamais pendant qu'une
   requête tourne.

**Coût.** Les étapes 1 à 6 ne font aucun appel facturé. La seule dépense est
l'étape 7, quelques relances par lot au lieu d'une par correction.

**Terminé quand** le rejeu du corpus ne montre plus aucun faux refus connu,
qu'aucune question ne finit en réponse de secours faute de pouvoir lire un
chiffre juste, et que le bilan de référence est dans le dépôt sous une forme
sans données personnelles (codes et compteurs seulement).
