# Droit de Retard

[![tests](https://github.com/Wesper-Dev/droit-de-retard/actions/workflows/tests.yml/badge.svg)](https://github.com/Wesper-Dev/droit-de-retard/actions/workflows/tests.yml)

**🇬🇧 [English version](README.md)**

Assistant local de préparation de réclamations aériennes EU261.

![Interface de Droit de Retard : le dossier analysé, l'indemnisation qualifiée et la trace de l'agent état par état](docs/images/interface.png)

À partir d'un billet PDF ou image, le prototype extrait les faits avec Gemma 4,
demande les informations manquantes, recherche des sources officielles et
calcule une indemnisation potentielle avec des règles Python déterministes. Il
peut refuser de générer une lettre et continue prudemment lorsque la recherche
web est indisponible.

> Ce prototype est informatif : il ne fournit pas de conseil juridique, ne
> représente pas le passager et ne garantit aucune indemnisation.

## Pourquoi un agent ?

Le résultat n'est pas systématiquement une lettre. Le pipeline choisit entre :

- demander le retard à l'arrivée ou une autre preuve manquante ;
- rechercher les règles et le canal de réclamation ;
- expliquer une non-éligibilité sans produire de lettre ;
- préparer une demande conditionnelle si les sources en direct sont
  indisponibles.

Le function calling natif Gemma/Ollama pilote les recherches. Gemma reçoit les
schémas JSON stricts des trois outils, produit `message.tool_calls`, puis un
dispatcher Python en liste blanche valide le nom et exige exactement les
arguments issus du contexte minimisé. Les résultats sont renvoyés au modèle
avec le rôle `tool` lorsqu'un second tour est nécessaire. Si un appel manque,
est invalide ou n'est pas produit, un fallback déterministe exécute uniquement
les outils autorisés et rend cette récupération visible dans la trace.

## Architecture

```mermaid
flowchart LR
    A["Billet PDF ou image"] --> B["Gemma 4 Vision<br>JSON strict"]
    B --> C{"Routeur déterministe"}
    C -->|Faits manquants| D["Question ciblée"]
    C -->|Dossier suffisant| E["Gemma sélectionne<br>les outils"]
    E --> F{"Validation stricte<br>et liste blanche"}
    F -->|Valide| K["Exécution des outils"]
    F -->|Absent ou rejeté| L["Fallback déterministe"]
    K -->|En ligne| M["Sources vérifiées"]
    K -->|Échec réseau| G["Mode dégradé"]
    L --> K
    M --> H["Calcul EU261 Python"]
    G --> H
    H -->|Sous le seuil| I["Explication, sans lettre"]
    H -->|Potentiel| J["Gemma 4 rédige<br>au conditionnel"]
```

Gemma lit le document et rédige. Le code conserve la responsabilité des
seuils, de la distance, du montant et des branches de sécurité.

| Fichier | Rôle |
| --- | --- |
| `agent.py` | Extraction multimodale, routage, recherche, rédaction et trace |
| `eu261.py` | Distance et qualification EU261 simplifiées |
| `tools.py` | Recherche SerpApi minimisée, corpus local et récupération hors ligne |
| `knowledge/airline_policies/` | Corpus procédural local des compagnies |
| `knowledge/carriers.json` | Identité des transporteurs et domaines officiels |
| `app.py` | Serveur HTTP local sans dépendance Python externe |
| `static/index.html` | Interface de démonstration |
| `test_agent.py` | Tests déterministes |
| `scripts/` | Vérifications manuelles, hors suite automatisée |
| `docs/` | Spécifications et analyses maintenues |
| `docs/hackathon/` | Archive figée de juillet 2026, non maintenue |

L'état des travaux et la dette restante sont suivis dans
[`ROADMAP.md`](ROADMAP.md) ; l'architecture visée et son plan de construction
dans [`docs/ARCHITECTURE_CIBLE.md`](docs/ARCHITECTURE_CIBLE.md). Les chiffres mesurés — nombre de tests, latence,
couverture — vivent dans [`docs/EVALUATION.md`](docs/EVALUATION.md), qui est
leur point de vérité unique.

**Voir la sortie sans rien installer :** [`examples/`](examples/) contient la
réponse complète d'une exécution réelle, sa trace d'agent et le résultat du
corpus local, versionnés tels quels.

## Où regarder

Si tu n'ouvres que cinq fichiers, ouvre ceux-là. Les liens sont figés sur un
commit : les numéros de ligne resteront valides.

- **[`_validate_tool_call`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/agent.py#L810-L835)** — quand Gemma demande
  un outil, le code ne résout pas le nom qu'il donne. Il **recalcule** en Python
  les arguments attendus et rejette tout ce qui diffère, à l'octet près. Le
  modèle choisit, il n'ordonne pas.
- **[`_execute_research_tool`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/agent.py#L838-L848)** — une chaîne de `if`
  littérale, sans résolution dynamique. Trois lignes ennuyeuses là où la norme
  de l'écosystème reste `globals()[name](**args)`, c'est-à-dire l'exécution
  d'une fonction nommée par le modèle.
- **[`_validate_claim`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/agent.py#L1101-L1155)** — le pendant, côté
  sortie : la lettre rédigée par le modèle est recoupée avec le moteur. Un
  montant qui diverge est remplacé, une URL absente des sources est signalée.
- **[`qualify_delay`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/eu261.py#L325-L423)** et
  **[`resolve_airport`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/eu261.py#L132-L155)** — la décision juridique et
  la résolution d'aéroport, en Python déterministe et testable hors ligne. Le
  modèle ne calcule jamais un montant. `resolve_airport` pose une question
  plutôt que de choisir quand un libellé est ambigu.
- **[`classify_cause`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/eu261.py#L314-L322)** — la jurisprudence dans le
  code : panne technique (CJUE Wallentin-Hermann C-549/07) et grève du personnel
  propre (Krüsemann C-195/17) n'exonèrent pas le transporteur, une grève du
  contrôle aérien le peut. Une cause à risque ne vaut jamais refus : la charge
  de la preuve pèse sur la compagnie.

Les deux tests qui verrouillent cette frontière :
**[un modèle qui tente de lire `.env`](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/test_agent.py#L700-L723)** et
**[un argument personnel glissé dans un appel d'outil](https://github.com/Wesper-Dev/droit-de-retard/blob/b0fcc016253601b1e28b09db5592998c75591e7c/test_agent.py#L728-L753)**,
tous deux rejetés.

## Prérequis

- Python 3.10 ou supérieur ;
- [Ollama](https://ollama.com/) avec `gemma4:12b` ;
- Poppler pour lire un PDF (`brew install poppler` sur macOS) ; les images
  PNG, JPEG et WEBP n'en ont pas besoin ;
- FFmpeg pour la dictée locale optionnelle (`brew install ffmpeg`) ;
- une clé SerpApi facultative pour la vérification en direct.

Le code d'exécution utilise uniquement la bibliothèque standard Python.

## Installation

Depuis un checkout du dépôt :

```bash
git clone git@github.com:Wesper-Dev/droit-de-retard.git
cd droit-de-retard

ollama pull gemma4:12b
ollama serve
```

Aucun environnement virtuel n'est nécessaire : le chemin d'exécution n'utilise
que la bibliothèque standard. Dans un second terminal :

```bash
cd droit-de-retard
export DR_MODEL=gemma4:12b
```

Pour activer la recherche, exportez `SERPAPI_KEY` dans le processus de lancement
ou renseignez le fichier `.env` local ignoré par Git. La variable
d'environnement est prioritaire. Ne placez jamais de clé dans le code, une
commande enregistrée ou une capture de la démo.

## Lancer la démo

### Interface web

```bash
./demo.sh
```

Ce script vérifie Ollama, précharge `gemma4:12b`, démarre l'application et
ouvre le navigateur. Le lancement manuel reste disponible avec
`.venv/bin/python app.py`.

Ouvrez [http://127.0.0.1:7865](http://127.0.0.1:7865), chargez
`billet_avion_fictif.png`, puis décrivez l'incident :

```text
Le vol est arrivé avec 3 h 25 de retard après un problème technique.
```

La référence lue sur le billet doit être confirmée manuellement avant d'être
utilisée dans la lettre.

Le bouton **Dicter avec Gemma** enregistre au maximum 20 secondes, convertit
l'audio localement en WAV puis demande à `gemma4:12b` de le transcrire. Aucun
audio n'est envoyé à un service cloud et aucun fichier n'est conservé. La
transcription doit être relue et confirmée avant l'analyse. Cette fonction est
optionnelle : la saisie manuelle reste toujours disponible.

### Ligne de commande

```bash
python3 agent.py billet_avion_fictif.png \
  --incident "Le vol est arrivé avec 3 h 25 de retard." \
  --booking-reference FQ7T2K
```

Le scénario fictif CDG–LIS illustre une indemnisation **potentielle** de 250 €
pour un retard déclaré à l'arrivée de 3 h 25. Le remboursement du billet est
évalué séparément. Pour un retard, le départ doit avoir été décalé d'au moins
5 heures **et** le passager doit déclarer avoir renoncé au voyage. Si ce choix
n'est pas renseigné, le résultat reste `needs_information` et l'agent pose la
question ; il ne déduit pas un remboursement du seul retard. Aurora Airlines
étant fictive, le prototype n'invente aucun formulaire réel.

Lors d'une exécution en ligne validée, Gemma a produit les trois `tool_calls`
sans qu'aucun soit rejeté, SerpApi a répondu, la qualification interne a pris le
statut `likely` pour 250 € potentiels et le pipeline a duré environ 36 secondes.
Cette mesure décrit un passage sur la configuration de démonstration, pas une
garantie de latence ou d'éligibilité.

## Vérification

```bash
python3 -m unittest discover -v
```

Les tests couvrent le routage, la normalisation des durées, les seuils, les
tranches de distance, le remboursement séparé et la confidentialité des
recherches. Ils vérifient également les schémas d'outils, le parsing de
`tool_calls`, le retour `role=tool`, le rejet des fonctions ou arguments hors
liste blanche et le fallback déterministe. Les cas de remboursement prouvent
qu'un retard au départ d'au moins 5 heures sans choix explicite du passager
déclenche une question, tandis qu'un voyage abandonné peut ouvrir un résultat
conditionnel ou `likely`. Les appels Ollama doivent rester séquentiels pour
obtenir des mesures de latence comparables.

Le compte exact et ce que la suite **ne** couvre pas sont dans
[`docs/EVALUATION.md`](docs/EVALUATION.md) ; un test échoue si ce document
cesse d'être à jour.

S'y ajoute un **corpus de déclarations** : une trentaine de formulations, dont
des formulations hostiles, passées dans la couche qui transforme une phrase de
voyageur en faits chiffrés. Il tourne sans réseau ni Ollama et documente
explicitement ce qui n'est pas encore compris.

```bash
python3 eval/corpus.py
```

## Confidentialité et résilience

Le document, le nom et la référence de réservation sont traités par Ollama sur
la machine. Gemma ne reçoit pour la sélection d'outils que le type d'incident,
le trajet, les durées utiles et la compagnie. Les recherches SerpApi excluent
le nom du passager et la référence. Sans clé, en cas de quota ou de panne
réseau, les sources de référence sont affichées comme non vérifiées et la trace
le signale. Le verdict, lui, ne dépend pas du réseau : il découle des faits
déclarés et de la cause. Ce qui peut le rendre conditionnel, c'est une cause
susceptible de relever des circonstances extraordinaires, jamais une panne de
connexion. La lettre produite est enfin recoupée avec le moteur : un montant ou
une URL que le modèle aurait inventés sont corrigés ou signalés.

## Positionnement

Ce projet prépare un dossier que l'utilisateur contrôle ; il n'effectue ni
recouvrement ni action en justice. Il ne prélève rien sur une éventuelle
indemnité, mais ce n'est pas gratuit pour autant : il demande une machine
capable de faire tourner un modèle de 12 milliards de paramètres, et le travail
de suivi reste à la charge du voyageur. La comparaison ci-dessous porte sur les
modèles, pas sur un rapport qualité-prix.

| Critère | Droit de Retard | AirHelp | Flightright |
| --- | --- | --- | --- |
| Modèle | Libre-service local | Recouvrement géré | Recouvrement géré |
| Prélèvement sur l'indemnité | Aucun | 35 % TTC | 27 % + TVA |
| Coût réel pour l'utilisateur | Matériel, installation et suivi du dossier | Aucun si le dossier échoue | Aucun si le dossier échoue |
| Relance et représentation | Non couvertes | Incluses | Incluses |
| Trace et mode hors ligne | Visibles | Non revendiqués | Non revendiqués |

Sources : [frais AirHelp](https://www.airhelp.com/en-int/our-fees/),
[fonctionnement d'AirHelp](https://www.airhelp.com/en-int/blog/how-to-use-airhelp-to-claim-flight-compensation/),
[service Flightright](https://www.flightright.fr/blog/droit-aerien) et
[conditions Flightright](https://www.flightright.fr/wp-content/uploads/sites/4/2021/03/Conditions-Ge%CC%81ne%CC%81rales_FRA.pdf).
Ces services restent plus complets pour les relances et la représentation.

## Limites

- règles volontairement simplifiées pour les scénarios de démonstration ;
- 61 aéroports référencés dans le calcul local : un code absent produit
  `needs_information`, jamais une distance approximative. Un libellé contenant
  plusieurs aéroports référencés déclenche une question plutôt qu'un choix
  arbitraire ;
- seul le retard à l'arrivée est chiffré. Une annulation ou un refus
  d'embarquement renvoie `not_covered` : le droit existe peut-être, cet outil
  ne le calcule pas et le dit au lieu de laisser croire le dossier complet ;
- le Royaume-Uni est traité hors champ EU261 depuis le Brexit ; le régime
  UK261 n'est pas implémenté ;
- aucune vérification historique fiable d'un vol ou transporteur fictif ;
- aucun envoi automatique de réclamation ;
- corpus procédural local limité à trois compagnies : toute autre compagnie
  renvoie `not_found` plutôt qu'une procédure inventée.

## Origine

Ce projet est né au **Gemma 4 Hackathon — Track 02: Autonomous Agents**
(juillet 2026). Les documents de cette période — writeup, pitch, plans,
rapports et scripts vidéo — sont archivés tels quels dans
[`docs/hackathon/`](docs/hackathon/) et ne sont plus maintenus : leurs chiffres
décrivent l'état du projet à ce moment-là, pas l'état actuel.

Le développement s'est poursuivi depuis. Voir [`ROADMAP.md`](ROADMAP.md) pour
l'audit, la dette traitée et les travaux en cours.

La vidéo de démonstration est référencée dans [`VIDEO.md`](VIDEO.md).
