# Mesures et chiffres de référence

**Point de vérité unique.** Tout chiffre cité ailleurs dans le dépôt doit
renvoyer ici plutôt que d'être recopié : c'est la recopie qui a produit quatre
comptes de tests différents dans quatre documents.

Dernière vérification : 27 juillet 2026.

## Suite de tests

Le dépôt compte **108** tests déterministes.

```bash
python3 -m unittest discover -v
```

Ils tournent en moins de 0,05 s, **sans réseau, sans Ollama et sans aucune
dépendance externe** : tous les appels au modèle sont remplacés par des doubles.
C'est ce qui permet à la CI de les exécuter sur Python 3.10, 3.11, 3.12 et 3.13
à chaque poussée.

`test_documented_test_count_is_accurate` compare le nombre annoncé ci-dessus au
nombre réel de méthodes de test. Ajouter un test sans mettre ce document à jour
fait échouer la suite : la dérive redevient impossible plutôt que corrigée à la
main.

### Ce que la suite couvre, et ce qu'elle ne couvre pas

Elle couvre le routage, les seuils et tranches EU261, la résolution d'aéroport,
le parseur d'incident, la classification de cause, le corpus local, la
validation des appels d'outils et celle de la lettre produite.

Elle ne couvre **pas** la qualité de l'extraction multimodale. Tous les tests
remplacent `_chat` par un double : ils vérifient donc tout sauf la couche du
modèle. Voir « Ce qui n'est pas mesuré » plus bas.

## Corpus de déclarations

Entre la phrase écrite par le voyageur et les faits chiffrés, il y a une couche
de règles déterministes qui peut se tromper en silence. Elle est désormais
mesurée par un corpus de formulations, dont des formulations hostiles.

```bash
python3 eval/corpus.py
```

| Mesure | Valeur |
| --- | --- |
| Cas au corpus | 31 |
| Cas attendus qui passent | **28 / 28** |
| Trous connus, documentés | 3 |

Le corpus tourne **sans réseau et sans Ollama**, et il est appliqué par la suite
de tests : un cas attendu qui échoue fait échouer la CI, et un trou connu qui se
met à passer aussi — pour forcer sa promotion plutôt que son oubli.

### Les trois trous assumés

| Cas | Pourquoi il n'est pas traité |
| --- | --- |
| « j'ai attendu plus de 4 heures » | « attendre » est ambigu entre le temps passé en aéroport et le retard à l'arrivée ; les confondre sur-réclamerait |
| « arrivé 5h plus tard » | « plus tard » sans marqueur de retard ; le type est détecté, la durée non |
| « devait partir à 14h, il est parti à 19h30 » | déduire une durée de deux heures d'horloge dans du texte libre ; le pipeline sait le faire sur les champs d'horaires, pas sur une phrase |

### Ce que le corpus a trouvé à sa première exécution

Trois échecs, sur du code réputé testé par 103 tests verts :

1. **« retard estimé à 3 h environ »** perdait la durée. Le rejet des heures
   d'horloge, ajouté deux jours plus tôt pour éviter de lire « arrivé à 23 h 50 »
   comme une durée, écartait aussi une durée légitime précédée de « à ».
2. et 3. **La cause déclarée était aplatie en étiquette générique.** « Grève des
   contrôleurs aériens » et « grève du personnel de la compagnie » devenaient la
   même chaîne, si bien que `classify_cause` renvoyait `unknown` au lieu de
   `high` et `low`. La qualification de cause était donc inopérante dès que la
   cause venait de la déclaration du voyageur — c'est-à-dire dans le cas
   principal.

Aucun des 103 tests existants ne couvrait ces chemins.

## Exécution réelle de bout en bout

Mesure du 27 juillet 2026, billet de démonstration fictif `billet_avion_fictif.png`,
incident déclaré « 3 h 25 de retard après un problème technique », machine de
développement avec `gemma4:12b` déjà chargé.

| Étape | Durée |
| --- | --- |
| Extraction multimodale | 10,7 s |
| Sélection des outils par Gemma | 9,4 s |
| Rédaction de la lettre | ~20 s |
| **Total bout en bout (HTTP)** | **42,7 s** |

Résultat : `ready_for_claim`, éligibilité `likely`, **250 €** potentiels sur
1470,2 km, lettre produite. Function calling : **3 appels demandés, 0 rejeté**,
2 allers-retours de résultats d'outils.

La sortie complète de ce run est versionnée dans
[`../examples/sample_output.json`](../examples/sample_output.json).

Ces durées décrivent une machine et une configuration ; ce ne sont pas des
garanties de latence. Elles varient fortement selon que le modèle est déjà
chargé en mémoire ou non.

## Port d'écoute

L'application sert sur **7865** (`app.py`, option `--port`, et `demo.sh` via
`DEMO_PORT`).

## Couverture fonctionnelle

| Élément | Valeur |
| --- | --- |
| Aéroports référencés | 61 |
| Compagnies au corpus procédural | 3 |
| Types d'incident chiffrés | 1 sur 4 (retard à l'arrivée) |
| Outils exposés à Gemma | 3 |

Les trois autres types d'incident — annulation, refus d'embarquement,
correspondance manquée — renvoient `not_covered` : le droit existe peut-être,
ce moteur ne le calcule pas et le dit.

## Ce qui n'est pas mesuré

- **Aucun taux d'exactitude par champ sur l'extraction multimodale**, ni taux
  d'hallucination. C'est la couche du modèle : elle exige Ollama, donc elle ne
  peut pas tourner en CI. C'est le prochain chantier.
- **Aucune comparaison agent contre mono-prompt.** Le writeup du hackathon
  l'annonçait déjà comme manquant ; ça reste vrai.
- **Aucune mesure sur billets réels** au-delà de trois essais manuels décrits
  dans la feuille de route.

Tant que ces trois points ne sont pas comblés, aucune affirmation de
supériorité ne doit être écrite dans ce dépôt.
