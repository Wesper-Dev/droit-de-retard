# Feuille de route — remise à plat

Document de travail issu d'un audit à 13 agents (26 juillet 2026), sur six
dimensions : architecture, viabilité produit, vitrine GitHub, profondeur IA,
conformité juridique et roadmap fonctionnelle.

**Convention de lecture.** ✅ = reproduit et vérifié dans le code de ce dépôt.
⚠️ = constat d'audit crédible mais non revérifié individuellement. Ne traite
jamais un ⚠️ comme acquis sans le reproduire d'abord.

---

## 0. Vers où on va

Le plan de construction visé — lire de vrais billets, lire des sources
officielles en ligne, mode hors ligne complet, architecture solide — est dans
[`docs/ARCHITECTURE_CIBLE.md`](docs/ARCHITECTURE_CIBLE.md), avec cinq fiches de
conception détaillées dans [`docs/architecture/`](docs/architecture/).

Ce document-ci reste le journal de ce qui est **fait** ; l'autre décrit ce qui
est **visé**.

### Lot 0 — livré le 28 juillet 2026

Cinq commits d'assainissement, plus le filet qui protège les lots suivants.

- **La lettre ne peut plus citer une URL que le filtre venait d'écarter.**
  `find_claim_channel` ne renvoie plus les résultats bruts du moteur sous ses
  deux statuts de rejet. Ils ne pouvaient déjà plus être cités — le correctif
  `b119140` avait fermé la liste blanche — mais `draft_claim` sérialise tout le
  bloc `research` dans le prompt : le modèle les avait encore sous les yeux au
  moment de rédiger. Une défense qui tient sur un seul rempart n'en est pas une.
- **Le garde-fou « zéro dépendance » de la CI ne gardait rien.** Il bâtissait son
  ensemble de modules « locaux » avec `rglob` sans exclure `.venv/` : les paquets
  tiers y entraient, donc `requests` et `urllib3` passaient pour des modules du
  dépôt. Reproduit : un `import requests` ajouté **à la racine**, en plein dans
  le périmètre déclaré, sortait en code 0. Il balaie désormais tout le dépôt,
  `.venv/`, `__pycache__/`, `tmp/` et `output/` exclus, et refuse les deux cas.
- **Témoin de régression.** `RegressionWitnessTests` rejoue le pipeline entier
  hors ligne et compare 146 chemins de champs à `examples/regression_witness.json`,
  horloge gelée. Sur cinq régressions discrètes injectées à l'essai, cinq sont
  détectées et nommées. Limite connue : 29 de ces 146 chemins recopient les
  réponses du modèle en boîte — sur ceux-là le témoin prouve un passe-plat, pas
  un calcul.
- **Branche morte supprimée.** `static/index.html` lisait `step.fallback`, que
  rien n'a jamais émis. Un test de contrat garde désormais la frontière entre la
  trace et la page ; sa portée exacte est décrite dans sa docstring.
- **Documentation remise d'aplomb.** Le pied de lettre, annoncé livré en semaine 8,
  n'existe pas : retiré du passé, rattaché au lot 6.

~~Restes assumés, à traiter au lot 1 : `claim.source_indices` est requis par le
schéma, halluciné par le modèle — `[10, 11]` pour deux sources — et lu par
personne ; les permaliens « Où regarder » du README sont figés sur un commit
antérieur au durcissement.~~ Traités au lot 1.

### Lot 1 — livré le 31 juillet 2026

- **`claim.source_indices` supprimé.** Le champ était exigé par `CLAIM_SCHEMA`,
  halluciné par le modèle et lu par personne : exiger d'un modèle un champ que
  rien ne consomme, c'est fabriquer de l'hallucination obligatoire. Retiré des
  `properties` et du `required`, retiré de la réponse en boîte du témoin, témoin
  régénéré avec la commande documentée — 146 chemins deviennent 144, les
  121 tests restent verts. Les citations `[n]` dans le texte de la lettre et le
  recoupement d'URL de `_validate_claim` ne passaient pas par ce champ et sont
  inchangés. `examples/sample_output.json` reste la capture fidèle du run du
  27 juillet : il contient encore le champ, comme l'état du code à cette date.
- **Permaliens « Où regarder » ré-ancrés.** Les huit liens pointaient sur
  `6a0aea5`, antérieur au durcissement `b119140` ; ils pointent désormais sur
  `b0fcc01`, dernier commit poussé, avec les numéros de ligne recalculés sur ses
  blobs.
- **README dédoublé.** `README.md` passe en anglais, `README.fr.md` porte la
  version française, chacun lie l'autre en tête. Le cadrage honnête du coût
  déjà en place est conservé : pas de « Commission 0 % » en argument, le
  prélèvement nul est présenté à côté du coût réel (matériel, installation,
  suivi) et la comparaison est explicitement bornée aux modèles de service.

## 1. Où on en est

Le hackathon est terminé. Le projet passe en mode long terme, avec deux
objectifs : **une vitrine GitHub crédible**, et l'évaluation honnête d'une
éventuelle suite entrepreneuriale.

État réel du code : extraction multimodale Gemma 4 en JSON strict, function
calling natif Ollama à trois outils, moteur EU261 déterministe (61 aéroports),
corpus procédural local de 3 compagnies, dictée vocale locale. Le compte de
tests n'est pas repris ici — il avait déjà dérivé : il fait foi dans
[`docs/EVALUATION.md`](docs/EVALUATION.md), seul document qu'un test verrouille.
Dépôt personnel : `github.com/Wesper-Dev/droit-de-retard`.

---

## 2. Le verdict startup : non

Trois murs indépendants, et un seul suffit.

**Le canal d'accès.** AirHelp et Flightright ne gagnent pas parce qu'ils
calculent mieux, mais parce qu'ils captent le passager au moment de la
perturbation. Ce projet n'a aucun canal, et ce n'est pas un problème technique.

**Le juridique.** L'article 54 de la loi n°71-1130 ferme le B2C payant dès
qu'on facture un verdict individualisé — ce que produit exactement
`qualify_case`. Le « 0 % de commission » n'est pas un positionnement, c'est
une contrainte déguisée en argument.

**Le produit.** Le passager moyen ne veut pas préparer un dossier, il veut
l'argent sans effort. Le local-first parle à un lecteur technique, pas à
quelqu'un qui vient de rater sa correspondance.

**Ce que le projet devient à la place :** une pièce d'ingénierie de référence
sur la frontière de confiance entre un LLM local et un calcul juridique
déterministe. C'est déjà à 70 % dans le code (`_validate_tool_call`,
`_execute_research_tool`, `eu261.py`) et ce n'est écrit nulle part.

**Test de sortie, fin de trimestre :** si trois conversations avec des
gestionnaires de sinistres ou des compagnies régionales (une seule question —
qui traite les dossiers EU261 aujourd'hui, sur quel outil, à quel coût par
dossier) décrivent majoritairement un traitement sur tableur, la piste B2B
mérite une décision. Sinon elle est close.

---

## 3. Ce que le dépôt affirme et que son code contredit

**Statut : les quatre points sont CORRIGÉS** (26 juillet 2026, 63 tests).
Conservés ici comme mémoire du problème et de la solution retenue.

### 3.1 ~~`verified_live` ne vérifie rien~~ — corrigé

`_filter_official_rule_sources` (`tools.py`) teste seulement que l'URL
retournée par SerpApi *ressemble* à une page `europa.eu` — hostname, préfixe et
suffixe de chemin. **La page n'est jamais téléchargée.** Ce booléen pilote
pourtant `"likely" if verified_live else "conditional"` dans `eu261.py` : le
niveau de confiance juridique est branché sur un test de connectivité.

*Correctif :* renommer en `reference_source_reachable`, le sortir du calcul de
statut, propager dans l'UI et les tests. ~1 h.

### 3.2 ~~Le montant de la lettre n'est jamais recoupé~~ — corrigé

`estimated_compensation_eur` n'apparaît que dans `CLAIM_SCHEMA` et
`CLAIM_SYSTEM`. Aucune ligne ne le compare à `qualification["compensation_eur"]`.
L'UI affiche le montant déterministe, mais c'est `letter_body` que
l'utilisateur envoie.

*Correctif :* validation post-génération en Python — montant identique au
moteur, tout nombre suivi de `€` dans l'ensemble autorisé, URL en allow-list.
C'est le pendant exact de `_validate_tool_call`. Une soirée.

### 3.3 ~~`disruption_cause` est extrait puis ignoré~~ — corrigé

Trois occurrences, toutes dans `agent.py` (schéma, liste des requis,
affectation depuis la dictée). **Zéro dans `eu261.py`.** Un passager qui déclare
« 3 h de retard à cause de la météo » se voit annoncer 400 €, alors que les
circonstances extraordinaires exonèrent le transporteur.

*Correctif :* table `cause_risk` — `high` pour météo, grève ATC, sûreté ;
`low` pour panne technique (CJUE Wallentin-Hermann C-549/07) et grève du
personnel propre (Krüsemann C-195/17) ; `unknown` par défaut. **Ne jamais
transformer `high` en refus** : la charge de la preuve pèse sur le
transporteur. Deux soirées avec les tests.

### 3.4 ~~Le moteur ne traite qu'un cas EU261 sur quatre~~ — angle mort rendu explicite

`qualify_case` ne route que `delay`. Le schéma d'extraction et le parseur de
dictée annoncent pourtant quatre types d'incident.

Conséquence mesurée : une **annulation** tombe en `needs_information`, mais le
remboursement est `likely`, donc le pipeline produit une lettre qui réclame le
remboursement du billet **sans jamais mentionner les 250 à 600 € de l'article 7**.
Sous-réclamation silencieuse sur le cas le plus fréquent. Un **refus
d'embarquement** part en `not_assessed` alors que c'est le cas où le droit est
le plus solide (art. 4).

*Correctif immédiat (avant toute nouvelle branche) :* rendre l'angle mort
explicite à l'écran plutôt que de laisser croire que le dossier est complet.

**Fait.** `qualify_case` renvoie désormais un statut distinct `not_covered`,
jamais confondu avec `needs_information` : aucune information supplémentaire du
passager ne débloquerait ces cas, c'est l'implémentation qui manque. Le
pipeline expose `uncovered_right`, trace un état `DROIT_NON_COUVERT`, et
`CLAIM_SYSTEM` impose d'écrire qu'une indemnisation est peut-être due sans
avancer de montant. Les branches annulation et refus d'embarquement restent à
écrire (mois 3).

### 3.5 ✅ Un tableau sans `maxItems` fait boucler le décodage contraint

Découvert en corrigeant 3.3 : `source_indices` était déclaré
`{"type": "array", "items": {"type": "integer"}}` **sans borne**. Le décodage
contraint d'Ollama a produit `251, 252, 253… 283`, épuisant la limite de
génération et tronquant le JSON au milieu. L'échec se présentait comme
« Gemma n'a pas produit un dossier JSON exploitable » — un défaut de schéma
déguisé en défaillance du modèle.

*Corrigé :* `maxItems` sur les quatre tableaux de `CLAIM_SCHEMA`, plus une
détection explicite de `done_reason == "length"` qui nomme la troncature au
lieu de la masquer. Deux tests, dont un qui échoue si un futur tableau est
ajouté sans borne.

---

## 4. Dette technique — à traiter avant d'ajouter quoi que ce soit

**Statut : les dix points sont traités** (26 juillet 2026, 101 tests).
Conservés comme mémoire du problème et de la solution retenue.

**Ce que ces correctifs ont ajouté au dépôt :** `knowledge/carriers.json`,
registre d'identité des transporteurs — codes IATA et OACI, raisons sociales,
filiales, domaines officiels. Il sert à la fois à reconnaître une compagnie
sous n'importe quelle écriture (4.7) et à valider le canal publié dans la
lettre (4.6). Les deux se payaient bien ensemble, comme l'audit l'annonçait.

### 4.1 ~~`extract_iata` prend le dernier code à trois lettres~~ — corrigé

```
extract_iata('Nice NCE, FRA')                    -> 'FRA'
extract_iata('Aéroport Charles de Gaulle, FRA')  -> 'FRA'
extract_iata('Milan MXP, ITA')                   -> 'ITA'

CDG -> LIS = 1470 km -> 250 €
FRA -> LIS = 1874 km -> 400 €      même vol, libellé différent, +150 €
```

`origin` vient de Gemma en texte libre. Défaillance silencieuse, plausible, et
du côté qui **sur-réclame**.

*Correctif :* n'accepter un code que s'il appartient à `AIRPORTS` **et** est
unique, sinon `None` → `needs_information` ; ignorer les faux amis ISO-3166
après virgule. 15 cas paramétrés. Une heure.

**Fait.** `resolve_airport` remplace la devinette et retourne `(code, motif)` :
un seul aéroport référencé → il est retenu ; plusieurs → question au lieu de
choix ; aucun → le code inconnu est nommé dans le message. Une table ISO-3166
écarte un code pays qui suit une virgule, si bien que `Nice NCE, FRA` résout
désormais **NCE** et non Francfort, tandis que `Francfort FRA` continue de
résoudre FRA. Six tests.

### 4.2 ~~`merge_incident_statement` ignore la négation~~ — corrigé

```
"mon vol n'a pas été annulé, juste 3h30 de retard"  ->  cancellation
```

Le déclencheur est `if "annul" in normalized`, sans fenêtre de négation.
Également non capturé : « trois heures et demie de retard » → durée `None`.
Les six tests existants ne testent que des formulations coopératives.

*Correctif déterministe, ~30 lignes :* n'accepter une durée qu'avec marqueur
explicite (`de retard`, `retardé de`), rejeter tout match précédé de
`à`/`vers`/`au lieu de`/`prévu`, fenêtre de négation de 30 caractères, et **ne
rien écrire** en cas de matches multiples non attribuables.
**Ne pas remplacer par un appel Gemma** : +20 s de latence et une surface
d'hallucination pour un problème purement lexical.

**Fait, en Python déterministe.** La négation est cherchée dans la seule
proposition qui précède le marqueur, tronquée aux ruptures (`,`, `mais`,
`juste`) : « mon vol n'a pas été annulé, juste 3 h 30 de retard » donne
maintenant `delay`/210 au lieu de `cancellation`. Une durée n'est retenue que
si un marqueur de retard figure dans son voisinage immédiat et qu'elle n'est
pas précédée d'un contexte horaire (`à`, `vers`, `au lieu de`, `prévu à`) :
« arrivée 23 h 50 au lieu de 20 h 25 » ne produit plus rien, et
« 3 h 30 de retard, je suis arrivé à 23 h 50 » donne 210 et non 1430. Les
durées en toutes lettres sont converties avant analyse (« trois heures et
demie » → 210). Sept tests.

### 4.3 ~~`scheduled_arrival` / `actual_arrival` extraits et lus par personne~~ — corrigé

Les deux horaires qui donneraient le retard par soustraction dorment dans le
JSON pendant que le regex se trompe.

*Prérequis honnête :* ajouter un champ `tz` (identifiant IANA) aux 61 entrées
d'`AIRPORTS` et normaliser en UTC avec `zoneinfo`. Sans ça, un CDG–LIS a une
heure d'écart artificielle et un passage de minuit donne un retard négatif.
C'est le prérequis de **tout** ce qui touche aux horaires.

**Fait.** Les 61 aéroports portent un identifiant IANA, tous résolus par
`zoneinfo`. `arrival_delay_from_times` retourne `(minutes, motif)` et refuse
plutôt que de deviner : horaire illisible, date absente, fuseau inconnu ou
écart hors bornes donnent `None` avec un motif. Le passage de minuit est traité
(23 h 50 → 01 h 30 = 100 min).

Nuance découverte en écrivant les tests : les deux horaires étant exprimés dans
le **même** fuseau, leur écart n'en dépend pas — sauf une nuit de changement
d'heure. Et là, CPython piège : quand deux `datetime` partagent le même objet
`tzinfo`, la soustraction est faite sur les horloges **sans corriger le
décalage**. Le 25 octobre 2026 à Paris, 01 h 30 → 03 h 00 donnait 90 minutes
au lieu de 150. La conversion en UTC avant soustraction règle le cas, et un
test le verrouille.

Le pipeline calcule désormais le retard quand aucune durée n'est déclarée, et
**recoupe** sans jamais écraser quand une durée l'est : un écart supérieur à
5 minutes produit une étape de trace `HORAIRES_RECOUPES` en `divergent`.

### 4.4 ~~`_chat` ne respecte pas son contrat d'erreur~~ — corrigé

`json.load(response)` est dans le `try` alors que les `except` ne couvrent que
`HTTPError` et `URLError`. Un `JSONDecodeError` traverse `research_case` (qui
ne rattrape qu'`AgentError`) et, comme il hérite de `ValueError`, `app.py`
renvoie un **HTTP 400** — une erreur serveur présentée comme une faute de
l'utilisateur. Les deux pannes les plus probables (Ollama qui recharge un
modèle, proxy qui répond du HTML) ne déclenchent pas le fallback qui est
l'argument central de robustesse.

*Correctif :* ajouter `json.JSONDecodeError`, `TimeoutError`, `OSError` ; un
test par famille.

**Fait.** Transport et décodage sont désormais séparés dans `_chat` : la
réponse est lue en octets, puis décodée dans un second bloc. Quatre familles
d'erreurs produisent un `AgentError` explicite — refus HTTP, serveur
injoignable, dépassement de délai (avec la durée), réponse illisible (avec
l'URL, pour désigner un proxy). Trois tests. `app.py` écrit en plus un
`traceback` avant son 500, dont le message invitait à consulter un terminal où
rien n'était écrit.

### 4.5 ~~`process()` perd une question~~ — corrigé

Avec un aéroport hors des 61 entrées, `qualify_case` et
`assess_ticket_reimbursement` produisent chacun une question, mais seule celle
de la qualification remonte. Le passager est mis dans une impasse.

*Correctif :* concaténer et dédupliquer toutes les `question`/`reason` non
nulles. Trois lignes.

### 4.6 ~~`find_claim_channel` publie le premier résultat Google brut~~ — corrigé

`results[0]["link"]`, aucun filtre — alors que `_filter_official_rule_sources`
impose un hostname exact deux cents lignes plus haut. Et `draft_claim`
sérialise le dict `research` **entier** dans le prompt, avec `CLAIM_SYSTEM` qui
ordonne de citer le `channel_url` tel quel.

La requête `"{airline} site officiel formulaire réclamation retard vol"` est
dominée en publicité par AirHelp et Flightright : **le produit peut désigner
comme canal officiel un intermédiaire qui prélève 25 à 35 %, dans la lettre que
l'utilisateur envoie.**

*Correctif :* allow-list de domaines, à payer avec 4.7.

### 4.7 ~~`_match_policy` est une égalité stricte~~ — corrigé

`'Air France KLM'`, `'AirFrance'`, `'TAP Portugal'`, `'easyJet Europe'` → `None`.
Et la fiche easyJet liste `EZY/EJU/EZS`, qui sont des codes **OACI** : le code
IATA d'easyJet est `U2`, celui imprimé sur le billet.

*Correctif :* `knowledge/carriers.json` — IATA + OACI + raisons sociales +
filiales + domaine officiel. Le champ domaine sert d'allow-list à 4.6, les deux
chantiers se paient ensemble.

### 4.8 ~~`app.py` : deux vérifications, vingt lignes~~ — corrigé

Valider `Host ∈ {127.0.0.1:port, localhost:port}` (tue le DNS rebinding, qui
permet aujourd'hui à un site tiers de lire l'extraction nominative renvoyée par
l'API locale) et exiger `Content-Type: application/json` en POST (force un
préflight, tue le CSRF sur le quota SerpApi). Plus un `traceback.print_exc()`
avant le 500, dont le message invite à consulter un terminal où rien n'est écrit.

### 4.9 ~~Une fiche périmée est servie comme valide~~ — corrigé

La fraîcheur est calculée mais jamais appliquée : `status: "found"` avec toutes
les procédures, quelle que soit l'ancienneté. Les trois fiches portent
`recheck_after: 2026-10-23`. **Le 24 octobre 2026, le dépôt déclarera son
propre corpus périmé tout en continuant à dicter les démarches.**

*Correctif :* dégrader en `needs_verification` sans étapes, plus un test
anti-pourrissement.

### 4.10 ~~Aucun contrôle de vraisemblance sur la date~~ — corrigé

Le billet de démo est daté du **14 septembre 2026**, soit dans le futur, et
passe sans un mot.

---

## 5. Vitrine GitHub — ordre d'exécution

- [x] Sortir les billets du dépôt, `.gitignore` en liste blanche médias
- [x] Dépôt personnel `Wesper-Dev/droit-de-retard`, historique complet
- [x] **`LICENSE` Apache-2.0 + `NOTICE`** — sans licence, « tous droits
      réservés » : personne ne peut forker. Le `NOTICE` reprend les Gemma Terms
      of Use, le modèle n'étant pas sous Apache.
- [x] **`.github/workflows/tests.yml`** (badge en tête du README) — la suite tourne en 0,04 s,
      sans réseau ni Ollama ni dépendance. Matrice 3.10 → 3.13, ce qui tranche
      au passage l'affirmation jamais vérifiée du README. Un seul badge.
- [x] **Réconcilier les chiffres** — `docs/EVALUATION.md` est le point de
      vérité unique, et `test_documented_test_count_is_accurate` le verrouille :
      ajouter un test sans mettre le document à jour fait échouer la suite. Un
      second test vérifie le port. Les documents périmés sont dans
      `docs/hackathon/`, explicitement gelés.
- [x] **Section « Où regarder »** — six permaliens figés sur un commit, vers
      la validation des appels d'outils, le dispatcher littéral, la validation
      de la lettre, le moteur déterministe, la classification de cause avec sa
      jurisprudence, et les deux tests qui rejettent un modèle tentant de lire
      `.env`.
- [x] **Capture et exemples** — `docs/images/interface.png` montre l'interface
      réelle rendue avec une sortie réelle. `examples/` versionne la réponse
      complète, la trace isolée et le résultat du corpus local, consultables
      sans installer Ollama.
- [x] **Ranger la racine** — douze artefacts d'événement archivés dans
      `docs/hackathon/`, avec un `README.md` qui les déclare gelés et renvoie
      vers l'état réel. `RAG_SPEC.md` et `COMPARAISON_CONCURRENTS.md` passés
      dans `docs/` comme documents vivants. `test_local.py` et `test_serpapi.py`
      renommés en `scripts/smoke_*.py`. `chat.py`, `SERPAPI_AGENTS.md` et le
      `.pptx` supprimés. `test_agent.py` reste à la racine : le déplacer dans
      `tests/` casserait `unittest discover` tel que documenté.
- [x] **`demo.sh` portable** — ripgrep remplacé par grep, ouverture du
      navigateur couvrant macOS, Linux et WSL sans faire échouer le script,
      venv rendu facultatif, variables documentées. Vérifié avec
      `/usr/bin/python3`, sans venv ni ripgrep.
- [x] **README en anglais + `README.fr.md`** — fait au lot 1 : `README.md` en
      anglais, `README.fr.md` en miroir, liens croisés en tête. La colonne
      « Commission 0 % » n'existe plus en tant qu'argument : le prélèvement nul
      est affiché à côté du coût réel (matériel, installation, suivi du
      dossier) et la comparaison est bornée aux modèles de service.
- [x] `Droit_de_Retard_Pitch.pptx` supprimé — binaire de 66 Ko, seul artefact
      dont la titularité était ambiguë.

---

## 6. Ce qu'il ne faut PAS faire

**Rendre le function calling « plus agentique ».** Le payload `research` est
intégralement reconstruit depuis `_expected_tool_arguments`, et
`_validate_tool_call` rejette tout argument différent à l'octet près. Gemma
n'influence que `selection_source` et trois compteurs, pour jusqu'à trois
allers-retours sur un modèle 12B. L'option honnête est de **supprimer la boucle
sélecteur**, d'exécuter `RESEARCH_TOOL_ORDER` en Python, de garder la validation
comme frontière de sûreté documentée, et d'écrire « le routage est déterministe
par conception ». Il n'y a plus de jury à impressionner.

**La détection automatique des vols éligibles** (boîte mail, calendrier, carte
bancaire) : OAuth, source de statut payante, backend hébergé — c'est l'abandon
du local-first et un an de travail à plein temps.

**La vérification ADS-B / OpenSky maintenant.** Sans fuseau dans `AIRPORTS`, on
ne peut même pas construire la fenêtre de requête. S'y ajoutent l'OAuth2, le
mapping IATA→OACI cassé par les partages de code, et une couverture ADS-B
lacunaire au-dessus de l'Atlantique — la vérification échouerait précisément sur
les long-courriers à 600 €.

**FastAPI, pydantic, python-dotenv.** Remplacer 24 lignes de lecture `.env` par
une dépendance est une perte nette. Le vrai risque du `ThreadingHTTPServer` est
la saturation d'Ollama : un `threading.Semaphore(1)` le traite en une ligne.
Reformuler la contrainte en « zéro dépendance sur le chemin d'inférence » et la
rendre vérifiable par un test qui inspecte les imports d'`eu261`.

**BM25 / FTS5 / embeddings sur le corpus.** Trois fiches, sept procédures. Le
travail pour passer à 200 compagnies n'est pas l'indexation, c'est **rédiger
800 fiches à la main**. Écrire dans `RAG_SPEC.md` que la contrainte est
éditoriale et non algorithmique, et que le palier suivant se franchira au-delà
de ~50 fiches **et** après mesure d'un gain de recall : ce raisonnement
documenté vaut plus, en vitrine, que du code FTS5 sans données.

**`mypy --strict` global, `SECURITY.md`, `CONTRIBUTING.md`, AIPD.** `mypy` sur
`agent.py`, saturé de `dict[str, Any]`, produit des centaines d'erreurs et sera
abandonné en une semaine — le cantonner à `eu261.py`. L'exemption domestique
(art. 2(2)(c) RGPD) s'applique tant que tout tourne chez l'utilisateur : pas de
responsable de traitement, donc pas de registre ni d'AIPD. Trois fichiers de CGU
sur un outil sans utilisateur signalent le contraire du sérieux recherché.

**Un générateur PDF maison en stdlib.** Largeurs de glyphes Helvetica,
pagination, décalages de table xref : 400 à 600 lignes pour une valeur nulle
face à un `.txt` et l'impression navigateur. Faire le niveau 1 — bouton copier,
export `.txt`, export `.json` du dossier complet avec la trace. Une heure.

**Le ferroviaire, une table de prescription à 27 pays, 20 passagers testeurs.**
Le rail, c'est 25 % d'un billet régional à 40 € contre l'installation d'un
modèle de 12 milliards de paramètres. Une table de prescription construite au
jugé est un risque, pas une fonctionnalité — dire à quelqu'un que son droit est
vivant alors qu'il est prescrit est pire que se taire. Pour ces trois-là, la
bonne livraison est **un paragraphe** dans les Limites du README, pas du code.

**Réécrire l'historique.** Détectable et disqualifiant. Le `createdAt` récent du
dépôt se compense par une activité réelle étalée, pas par un import massif.

---

## 7. Séquence sur trois mois (quelques heures par semaine)

### Mois 1 — rendre le dépôt visible et vrai

| Semaine | Contenu |
| --- | --- |
| 1 | ✅ billets sortis, `.gitignore`, dépôt perso. Reste : `LICENSE` + `NOTICE`, description et topics |
| 2 | CI + badge, `pyproject.toml` minimal, correction de `demo.sh`, rangement de la racine en un commit |
| 3 | §3.1 `verified_live`, §4.1 `extract_iata`, §4.5 question perdue |
| 4 | Réconciliation des chiffres + `docs/EVALUATION.md`, « Where to look », capture, `examples/`, 4 issues sur les limites connues |

*Livrable : un dépôt compris en 30 secondes, badge vert adossé à une suite
réelle, zéro affirmation contredite par son propre code.*

### Mois 2 — mesurer, puis corriger ce que la mesure révèle

| Semaine | Contenu |
| --- | --- |
| 5-6 | ~~`eval/cases.yaml`~~ **fait** : `eval/incident_cases.json` (31 cas, JSON et non YAML pour préserver le zéro-dépendance) et `eval/corpus.py`, appliqués par la CI. Trois bugs trouvés à la première exécution, dont l'aplatissement de la cause qui neutralisait la qualification §3.3 |
| 7 | §3.2 validation du montant de la lettre. §4.6 + §4.7 allow-list et `carriers.json` |
| 8 | §4.4 contrat d'erreur, §4.8 `Host` et `Content-Type`, §4.9 fiche périmée |

*Livrable : un tableau de mesures publié, chiffres mauvais compris, et une
lettre dont chaque montant est recoupé par le moteur.*

**Retiré de la semaine 8, parce que non livré :** le pied de lettre — mention
d'assistance automatisée, date, fondement, `RULESET.verified_on` — inséré côté
Python après `_validate_claim`. Ni le pied ni son test n'existent :
`grep -n "automatis" agent.py static/index.html` ne renvoie rien. Il passe donc
en travaux prévus, dans le **lot 6** de
[`docs/ARCHITECTURE_CIBLE.md`](docs/ARCHITECTURE_CIBLE.md), dont il conditionne
la sortie de fichiers : distribuer un `lettre.txt` sans mention d'assistance
automatisée serait pire que ne rien exporter.

**Périmètre à refuser :** « 30 à 50 vrais billets » pour le jeu d'évaluation.
C'est du PII à anonymiser sans casser la mise en page, ce sera commencé et
jamais fini. Le meilleur rendement est dans les déclarations textuelles : une
minute à écrire chacune.

### Mois 3 — le moteur devient un moteur

| Semaine | Contenu |
| --- | --- |
| 9 | §3.3 `cause_risk` câblé, jurisprudence citée dans le code, dix tests |
| 10 | Angles morts signalés, puis branche annulation : art. 5(1)(c), réduction de 50 % de l'art. 7(2), `cancellation_notice_days` |
| 11 | Branche refus d'embarquement (art. 4), distinction involontaire / volontaire. §4.10 vraisemblance de date |
| 12 | `ingest.py` + `llm.py` extraits, `agent.py` en façade. `eval/baseline_monoprompt.py` — le chiffre que `WRITEUP_KAGGLE.md` annonce lui-même comme manquant. ~~README anglais~~ (fait au lot 1) |

*Livrable : un moteur qui traite trois cas EU261 sur quatre avec la cause
modélisée, un harnais qui le prouve, et un dépôt où « le calcul juridique est
sorti du modèle » est une propriété vérifiée par des tests plutôt qu'une phrase
de README.*

---

## 8. Premier pas, demain matin

Ouvrir `eu261.py`, remplacer les trois `"status": "likely" if verified_live
else "conditional"` par `"conditional"` en dur, lancer
`python3 -m unittest discover`, corriger les tests qui rougissent.

Trente minutes, et le dépôt cesse d'affirmer ce qu'il ne sait pas.
