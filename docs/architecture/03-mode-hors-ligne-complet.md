# Mode hors ligne complet et RAG — plan nettoyé après audit du code

Fiche de conception issue de l'audit du 28 juillet 2026, après critique adversariale. Synthèse et ordre de construction dans [`../ARCHITECTURE_CIBLE.md`](../ARCHITECTURE_CIBLE.md).

## Diagnostic

CE QUE J'AI VÉRIFIÉ ET QUI EST EXACT

- `retrieve_airline_policy` est purement locale (tools.py:445-542), testée sans réseau (test_agent.py:1621-1626). Rien n'est perdu hors ligne. ✓
- `find_claim_channel` renvoie `channel: None` sur `SerpUnavailable` (tools.py:556-561) alors que le corpus contient déjà les URLs de canal (easyjet.json procédure `easyjet_compensation_claim` → `https://www.easyjet.com/claim/fr/eu261`). ✓ Trou réel.
- `_allowed_claim_urls` accepte déjà `channel["channel"]` (agent.py:1080-1082) ET les `channel_url` du corpus (agent.py:1084-1087). Le repli local serait citable dans la lettre sans toucher à la validation. ✓ Affirmation exacte, c'est bien le meilleur rapport valeur/effort.
- `verify_air_passenger_rule` hors ligne renvoie deux URLs codées en dur avec des snippets rédigés à la main (tools.py:296-319). Aucun caractère du règlement dans le dépôt : `knowledge/` ne contient que `airline_policies/` et `carriers.json`. ✓ Et `NOTICE` ne mentionne ni EUR-Lex ni la décision 2011/833/UE : l'ajout est nécessaire.
- Jurisprudence en commentaire mort : eu261.py:268-271 (Wallentin-Hermann C-549/07, Krüsemann C-195/17), invisible pour la lettre. ✓
- `stale` vide `procedures` à `[]` (tools.py:469-487), `MAX_POLICY_AGE_DAYS = 90` uniforme (tools.py:15). ✓
- Blackout total : `process` (agent.py:1254) appelle `extract_flight` → `_chat` (agent.py:311) → `AgentError`, run mort. ✓
- Mesures reproduites sur cette machine : `_load_policy_files` 0,090 ms, `identify_carrier` 0,044 ms, sqlite 3.51.0, FTS5 disponible. Le concepteur n'a pas gonflé ses chiffres. La conclusion « l'indexation coûte zéro jusqu'à plusieurs centaines de fiches » tient.

CE QUI EST FAUX — trois corrections structurantes

1. **L'étape 10 repose sur une prémisse fausse.** « La déclaration en texte libre passe par le parseur déterministe existant » : `merge_incident_statement` (agent.py:590-730) n'écrit QUE `disruption_type`, `delay_minutes`, `arrival_delay_minutes`, `departure_delay_minutes`, `trip_completed` et `disruption_cause` — la liste exhaustive est visible dans `eval/corpus.py:23-31` (`BLANK_RECORD`). Il ne produit JAMAIS `origin`, `destination`, `airline`, `flight_number`, `departure_date` ni le nom du passager. Or `qualify_delay` (eu261.py:330-341) retourne `needs_information` sans origine ET destination, et `process()` exige un document. Sans modèle, il n'y a pas de lecture de billet du tout : le PDF est rasterisé par Poppler (agent.py:227) puis envoyé en base64 à Gemma (agent.py:485-492). Conséquence : le « chemin moteur seul » n'est pas 40 lignes de gabarit, c'est un **nouveau chemin de saisie manuelle** (route API, champs de formulaire, arguments CLI) plus le gabarit. Requalifié.

2. **Le risque annoncé à l'étape 1 est faux, dans le sens rassurant.** « Des tests existants échoueront en révélant des sorties réseau non intentionnelles » : non. Les 106 tests passent en 0,056 s et tout est mocké en amont du transport — `agent._chat`, `agent.extract_flight`, `agent.research_case`, `tools.web_search`. Rien ne sort aujourd'hui. L'interrupteur sera vert au premier essai. Cela ne le disqualifie pas — sa valeur est de *verrouiller* la propriété et de rendre possibles deux tests bout-en-bout — mais l'effort tombe et le bénéfice annoncé doit être rectifié.

3. **`reference_source_reachable` ne pilote PAS eu261.py.** Le « à ne pas faire » n° 10 affirme que le fausser « corromprait la qualification ». eu261.py:404-407 dit explicitement l'inverse en commentaire : « Le statut dépend de la cause déclarée, jamais de la joignabilité d'une source en ligne : celle-ci est une information de provenance, pas un élément de qualification juridique. » C'est un champ de provenance transporté dans le résultat. L'interdiction reste bonne (par honnêteté), sa justification est à corriger.

PIÈGES QUE LE PLAN N'A PAS VUS

- **Le repli local du canal meurt exactement quand il sert.** L'URL de canal vit *dans* `procedures`, que `retrieve_airline_policy` vide dès `stale` (tools.py:469-487). Un repli qui lit la sortie de l'outil au lieu de la fiche perdra le canal au 91ᵉ jour — c'est-à-dire précisément dans le scénario « dépôt consulté un an plus tard ». Le repli doit lire la fiche.
- **Une date future est traitée comme périmée** (tools.py:441-443, `0 <= age <= MAX_POLICY_AGE_DAYS`). Une faute de frappe ou un décalage d'horloge tue silencieusement une fiche. À traiter dans le validateur, pas dans la fonction de fraîcheur.
- **Le contrôle AST de la CI ne scanne que la racine** (`.github/workflows/tests.yml`, `pathlib.Path().glob("*.py")`). `scripts/` et `eval/` sont hors du garde-fou. C'est commode pour un script réseau, mais c'est un accident, pas une décision : à rendre explicite.
- **`docs/RAG_SPEC.md` existe déjà** (70 lignes) et affirme déjà « une base vectorielle n'est pas utile pour ce MVP ». Sa section « Récupération MVP » impose la correspondance *exacte* et contredit l'étape 9. Il faut le réviser, pas l'écrire.
- **`examples/sample_airline_policy.json` sert déjà de gabarit.** `scripts/new_policy.py` est redondant : coupé.
- **Le seuil de 0,85 de l'étape 9 ne discrimine pas.** Mesuré ici sur noms normalisés : `air frnace`→`air france` 0,889 et `esayjet`→`easyjet` 0,857 (les cas à rattraper), mais `air europa`/`air europe` 0,889 et `aer lingus`/`air lingus` 0,889 (les confusions à interdire). Même bande. La règle d'ambiguïté n'est donc pas un garde-fou optionnel, c'est le mécanisme principal.

## Cible

Un agent qui, câble débranché, rend encore : le verdict et le montant (déjà acquis, eu261.py est déterministe), le canal officiel de dépôt issu du corpus local, et les articles du règlement cités verbatim depuis une copie embarquée et empreintée — donc une lettre plus vérifiable hors ligne qu'aujourd'hui en ligne, où elle ne cite qu'une URL.

Quatre principes, dont un ajouté après audit :

1. **Le règlement ne se cherche pas, il se joint.** `eu261.py` émet `legal_basis: ["art_7_1_b", ...]` sur la même branche qui calcule le montant. La citation est une jointure par clé primaire. Le modèle ne choisit jamais l'article qu'il cite — prolongement exact de « le modèle ne calcule jamais un montant ».

2. **Le RAG utile ici est de la résolution d'entité sur vocabulaire clos**, pas de la recherche vectorielle. Normalisation, alias, IATA/OACI, tolérance OCR par `difflib` — chiffré, testé, remplaçable le jour où une mesure le justifie. Le projet est à ~15-45 fragments ; le seuil BM25 est à ~200, FTS5 à ~5 000, les embeddings à ~1 000 fragments ET recall@5 < 0,85. Écrire ces seuils avec leur mesure dans RAG_SPEC.md, c'est démontrer qu'on a instruit la question au lieu de céder à la mode.

3. **Deux échelles distinctes.** Registre d'identité (`carriers.json`) : ~50 transporteurs, ~5 min chacun, données publiques factuelles. Fiches procédurales : coût réel 30-45 min chacune, rendement décroissant — viser 6 fiches livrées et mesurées, pas 14 annoncées. Annoncer un chiffre mesuré, jamais un objectif.

4. **[AJOUTÉ] Ce qui n'est pas mesuré ne fonctionne pas.** L'objectif « lire les billets des gens » n'a aujourd'hui aucune évaluation : les 31 cas de `eval/` testent le parseur de déclaration, pas l'extraction du billet. Tout l'édifice hors ligne repose sur des champs (`origin`, `destination`, `airline`) qui ne viennent que du modèle multimodal, et dont la fiabilité est inconnue.

Formulation annonçable dans le README, une fois mesurée : « registre : N transporteurs ; procédures : N compagnies, couverture mesurée sur les départs UE ; règlement : articles cités par le moteur embarqués verbatim, empreinte sha256, réutilisation sous décision 2011/833/UE ; extraction : N/N billets de test correctement lus ».

## Étapes

### 1. Interrupteur réseau au niveau socket, actif par défaut sur toute la suite

*Effort :* heures · *Prérequis :* Aucun. À faire en premier : sans cet outil, toute affirmation sur le mode hors ligne est une opinion.

Un gestionnaire de contexte stdlib qui patche `socket.socket.connect`, `socket.socket.connect_ex`, `socket.create_connection` et `socket.getaddrinfo` pour lever `OfflineViolation`, avec une liste blanche de couples (hôte, port) — typiquement 127.0.0.1:11434 pour simuler « avion, Ollama présent ». Le patch au niveau socket est le seul qui ne se contourne pas : il attrape urllib, http.client et le reste. Installer par défaut sur toute la suite via `setUpModule` avec allow-list vide.

RECTIFICATION : le plan annonçait que des tests existants casseraient. Non — les 106 tests passent en 0,056 s et tout est mocké en amont du transport (`agent._chat`, `agent.extract_flight`, `tools.web_search`). L'interrupteur sera vert immédiatement. Sa valeur n'est pas de révéler des fuites, c'est (a) d'empêcher qu'un futur test en introduise une, et (b) de rendre possibles deux tests bout-en-bout aujourd'hui inécrivables : internet coupé + Ollama simulé → `process()` aboutit, la trace contient MODE_DEGRADE, le canal vient du corpus ; blackout total → sortie sans modèle (étape 10).

PIÈGE CONCRET : un `.env` avec une clé SerpApi existe sur la machine de dev. `_api_key()` (tools.py:172) la trouvera, `web_search` tentera la connexion, et l'interrupteur lèvera `OfflineViolation` — qui n'est pas `SerpUnavailable` et traversera donc `verify_air_passenger_rule` (tools.py:294) jusqu'à faire exploser `research_case`. Deux options, à trancher explicitement : faire hériter `OfflineViolation` de `OSError` pour qu'`urllib` la convertisse en `URLError` puis en `SerpUnavailable`, ou l'attraper dans `web_search`. La première est plus propre et ne touche pas au code de production.

COUPÉ : le job CI avec `HTTPS_PROXY=http://127.0.0.1:9`. Deux mécanismes à moitié fiables valent moins qu'un seul testé, et posé au niveau du job il casserait `actions/checkout`. Le contrôle socket est plus fort qu'un proxy que rien n'oblige urllib à honorer.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* `socket.getaddrinfo` est appelé avec des signatures variables par plusieurs chemins stdlib : patch tolérant en `*args, **kwargs`. Second risque, réel celui-là : oublier de restaurer les fonctions patchées et rendre la suite non réentrante sous `unittest discover -v`. Restauration en `tearDownModule` obligatoire.

### 2. Mode hors ligne explicite et forcé

*Effort :* heures · *Prérequis :* Aucun.

Une variable d'environnement `DROIT_DE_RETARD_OFFLINE=1` et un drapeau `--offline` qui font lever `SerpUnavailable` par `web_search()` avant toute tentative de connexion, avec une raison distincte : « mode hors ligne demandé » et non « recherche temps réel indisponible ». Un état dédié dans la trace, un badge dans l'interface, une ligne dans `demo.sh`.

Bénéfice direct et sous-estimé : la démo hors ligne devient reproductible sans débrancher le wifi. C'est indispensable pour la vidéo, et surtout pour qu'un lecteur du dépôt vérifie la propriété annoncée en une commande. Un README qui dit « fonctionne hors ligne » sans commande vérifiable est une affirmation ; avec la commande, c'est une démonstration.

Côté implémentation, le point d'insertion est `web_search` (tools.py:215) : un seul endroit, avant `_api_key()`. Ne pas disperser le test du drapeau dans les trois outils.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/tools.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/app.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/static/index.html`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/README.md`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/demo.sh`

*Risque :* Confondre les deux raisons dans la trace. « Je n'ai pas essayé » et « j'ai essayé et échoué » sont deux états distincts ; les aplatir détruit la valeur d'audit de la trace, qui est l'argument central du projet.

### 3. Repli du canal sur le corpus local, avec fraîcheur à deux paliers

*Effort :* soiree · *Prérequis :* Étape 1 pour tester le repli sous coupure réelle plutôt que sous mock.

Deux changements indissociables, que le plan d'origine séparait à tort (étapes 3 et 8).

(a) REPLI. Sur `SerpUnavailable` ou `no_official_match`, `find_claim_channel` cherche la fiche du transporteur et renvoie le `channel.url` de la procédure correspondant à l'incident, avec `status: "local_corpus"`, la date de vérification et la provenance explicite. Jamais `status: "online"`. Vérifier l'URL du corpus par `_is_official_url` contre les domaines du registre — la même garde qu'en ligne, appliquée au corpus, ce qui rend une fiche corrompue inoffensive. Aucun changement côté validation de la lettre : `_allowed_claim_urls` accepte déjà `channel["channel"]` (agent.py:1080-1082).

PIÈGE QUE LE PLAN A MANQUÉ : l'URL de canal vit *dans* `procedures`, que `retrieve_airline_policy` vide dès `stale` (tools.py:469-487). Un repli qui consomme la sortie de l'outil perdra le canal au 91ᵉ jour, c'est-à-dire exactement dans le scénario « dépôt de portfolio consulté un an plus tard ». Le repli doit lire la fiche via `_match_policy(airline, _load_policy_files())`, pas la sortie de l'outil.

(b) DEUX PALIERS, préalable au (a) et non postérieur. Remplacer le vidage brutal par : `fresh` ≤ 90 j, comportement actuel ; `stale` 90-180 j, les étapes ET le canal sont servis mais assortis d'une mention de reconfirmation, exigence vérifiée par `_validate_claim` et non simplement demandée dans le prompt ; `expired` > 180 j, comportement actuel (rien). Sans le palier intermédiaire, tout le mode hors ligne s'auto-détruit trois mois après le dernier commit.

Corriger au passage tools.py:441-443 : une date `verified_on` future est aujourd'hui classée `stale` par `0 <= age`. Elle doit être un `invalid` distinct, et le validateur de l'étape 5 doit l'interdire à la source.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/tools.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/RAG_SPEC.md`

*Risque :* Un canal issu d'une fiche `stale` annoncé comme le canal officiel courant. La mention de reconfirmation doit être imposée par `_validate_claim` — si le modèle l'omet, c'est une violation, pas un oubli toléré. Second risque : la section « Fraîcheur et fallback » de docs/RAG_SPEC.md décrit le comportement actuel et deviendra fausse ; la mettre à jour dans le même commit.

### 4. Embarquer les articles que le moteur cite, et les citer par jointure

*Effort :* quelques soirees · *Prérequis :* Aucun techniquement. Le travail est la transcription et la cartographie branche → articles, à relire une fois posément et à froid.

Créer `knowledge/regulation/eu261_fr.json` : CELEX 32004R0261, version consolidée FR, unités adressables (`art_5_1_c`, `art_5_3`, `art_6_1_c`, `art_7_1_a/b/c`, `art_7_2`, `art_8`, `art_9`, `art_14`, `art_16`, `cons_14`, `cons_15`), chacune avec libellé officiel, texte verbatim et ancre EUR-Lex. Ajouter `retrieved_on`, `sha256` du texte source et l'attribution dans `NOTICE` — qui ne mentionne aujourd'hui ni EUR-Lex ni la décision 2011/833/UE. Préciser que la version authentique reste le Journal officiel : la copie embarquée est une commodité vérifiable, jamais l'autorité.

SCOPE RÉDUIT : le plan visait « 19 articles + ~25 considérants ≈ 45 fragments ». Non. Embarquer une unité que le moteur ne peut pas émettre, c'est du poids mort qu'il faudra maintenir et dont personne ne consomme la sortie. Transcrire uniquement les unités atteignables par une branche de `qualify_delay`, `assess_ticket_reimbursement` et `UNCOVERED_CASES` (eu261.py:530-548) : ~12-15 unités. Le reste s'ajoute le jour où une branche l'exige. C'est ce qui fait tenir « quelques soirées ».

CÔTÉ MOTEUR : chaque branche émet `legal_basis: [ids]`, calculé par le même code Python qui calcule le montant. La tranche 400 € émet `art_7_1_b` ; le seuil de 3 h émet `cons_15` et Sturgeon ; `cause_risk == "high"` émet `art_5_3` avec Wallentin-Hermann C-549/07 et `cause_risk == "low"` Krüsemann C-195/17 — aujourd'hui simples commentaires (eu261.py:268-271). `verify_air_passenger_rule` hors ligne renvoie le texte de ces articles avec `status: "local_regulation"`, mais `reference_source_reachable` reste FALSE : ce champ signifie « j'ai joint la source vivante aujourd'hui ». (Contrairement à ce qu'affirme le plan, il ne pilote aucune décision — eu261.py:404-407 le dit explicitement — mais il reste une assertion de provenance qu'on ne falsifie pas.)

CORRECTION MAJEURE SUR LA VALIDATION : le plan propose que `_validate_claim` vérifie que « tout passage présenté comme une citation » soit une sous-chaîne d'un article. Détecter une citation dans de la prose française libre est une heuristique, et son taux de faux positifs sera élevé — « le règlement prévoit une indemnisation de 400 € » entre guillemets serait signalé. Ne pas analyser la prose : **structurer la sortie**. Ajouter à `CLAIM_SCHEMA` (agent.py:118) un champ `legal_citations: [{article_id, verbatim}]` borné par `maxItems`, et valider par égalité exacte — `article_id` ∈ `legal_basis` émis par le moteur, `verbatim` == texte du corpus, octet pour octet. Plus une règle simple et sûre en complément : tout passage entre guillemets français dans `letter_body` doit être une sous-chaîne d'une unité émise. C'est plus strict, moins cher, et cohérent avec la méthode déjà employée par `_validate_tool_call` (agent.py:833-834) — recalculer l'attendu et comparer, jamais interpréter.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/regulation/eu261_fr.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/tools.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/NOTICE`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/RAG_SPEC.md`

*Risque :* Le vrai risque est de transformer ce corpus en base de RAG où le modèle irait piocher : ce serait lui rendre le pouvoir de décision qu'on lui a retiré. La jointure par identifiant doit rester le seul chemin d'accès. Deuxième risque, concret : n'injecter dans le prompt que les unités émises par le moteur — le contexte de `draft_claim` est déjà à `num_ctx: 8192` avec un incident de troncature documenté en commentaire (agent.py:1046-1049), et quelques kilo-octets d'articles suffiraient à le rejouer.

### 5. Validateur de corpus stdlib, branché en CI

*Effort :* heures · *Prérequis :* Aucun, mais à faire AVANT d'écrire la quatrième fiche.

`scripts/check_corpus.py`, ~120 lignes sans dépendance (surtout pas jsonschema) : clés obligatoires, `airline_id` présent dans carriers.json, tout `source_ids` résolu dans `sources`, toute URL de source ou de canal appartenant à un domaine officiel du transporteur via `_is_official_url` (réutiliser la fonction, ne pas la réécrire), `incidents` ∈ `ALLOWED_POLICY_INCIDENTS` (tools.py:129), `verified_on` date ISO **non future** (cf. le bug tools.py:441-443), `recheck_after` cohérent avec `verified_on + max_age_days`.

C'est ce qui rend le corpus maintenable : écrire une fiche devient un remplissage vérifié par la machine. Sans cette étape, le corpus pourrit structurellement dès la dixième fiche.

COUPÉ : `scripts/new_policy.py`. `examples/sample_airline_policy.json` sert déjà de gabarit, et `carriers.json` fournit déjà company/aliases par copier-coller. Un script de 40 lignes dont la sortie est une copie d'un fichier existant, pour un corpus de 6 à 14 fiches, est de l'outillage pour l'outillage.

À NOTER DANS LE COMMIT : le contrôle AST de la CI ne scanne que la racine (`.github/workflows/tests.yml`, `pathlib.Path().glob("*.py")`). `scripts/` est donc hors du garde-fou de dépendances. C'est commode — l'étape 8 y met un script réseau — mais c'est aujourd'hui un accident. Le rendre explicite : soit étendre le scan à `scripts/` en excluant nommément les outils hors chemin d'inférence, soit écrire la règle en commentaire dans le workflow. Un garde-fou dont personne ne connaît la portée n'en est pas un.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/scripts/check_corpus.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/.github/workflows/tests.yml`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/RAG_SPEC.md`

*Risque :* Sur-spécifier le schéma et rendre l'ajout d'une fiche pénible. Le validateur doit refuser l'incohérence (source_id orphelin, domaine non officiel, date future), jamais imposer un style rédactionnel ni une longueur de résumé.

### 6. Registre d'identité porté à ~50 transporteurs

*Effort :* quelques soirees · *Prérequis :* Étape 5 : sans validateur, une faute de frappe dans un domaine passe inaperçue.

Étendre `carriers.json` à une cinquantaine de compagnies opérant depuis l'UE : nom, IATA, OACI, alias d'écriture, domaines officiels. Données publiques factuelles, ~5 min par entrée, aucune lecture de formulaire.

CADRAGE HONNÊTE DU GAIN, que le plan surévalue. Il annonce que `find_claim_channel` passerait de `unverified_channel` (tools.py:568-577) à « un verdict réel ». En partie seulement : avec des domaines connus mais aucun résultat SerpApi sur ces domaines, on passe de `unverified_channel` à `no_official_match` (tools.py:578-587) — qui renvoie aussi `channel: None`. Le gain réel n'est pas le taux de succès, c'est la **garde** : bloquer les intermédiaires à commission qui dominent la requête publicitaire, pour 50 compagnies au lieu de 3. C'est déjà une bonne raison, et c'est ce qui rend la liste blanche non décorative. Le taux de succès, lui, vient de l'étape 3 (repli corpus) et de l'étape 7 (fiches).

PIÈGE TECHNIQUE : le plan demande au validateur d'exiger « un domaine enregistrable (pas de sous-domaine) ». Il n'y a pas de Public Suffix List en stdlib, et `airfrance.co.uk` — déjà présent dans le registre — a trois labels tout en étant enregistrable. Une règle algorithmique du type « au plus deux labels » rejetterait des entrées valides. La règle réalisable est syntaxique et modeste : pas de schéma, pas de chemin, pas de port, pas de joker, au moins deux labels, aucun domaine d'agrégateur figurant sur une petite liste noire explicite. Le reste relève de la relecture humaine, et il faut l'écrire comme tel plutôt que de simuler une vérification.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/carriers.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/scripts/check_corpus.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Un domaine erroné est pire que pas de domaine : il ferait passer une URL non officielle pour officielle, dans la lettre que le passager envoie. Un test doit vérifier qu'aucune entrée du registre n'est un domaine générique ou un agrégateur connu de réclamation.

### 7. Fiches procédurales : viser 6, mesurer, puis décider

*Effort :* semaines · *Prérequis :* Étapes 5 et 6.

Ajouter trois fiches aux trois existantes, choisies sur le volume de départs UE : Ryanair, Lufthansa, KLM. Une fiche par session avec le gabarit et le validateur, en lisant réellement les pages officielles.

REQUALIFICATION : le plan visait 12-15 compagnies en « semaines » tout en refusant 50 comme irréaliste. Le calcul qu'il applique à 50 s'applique à 15 : à 30-45 min l'unité *plus* la vérification des sources et l'écriture des `limits`, treize fiches nouvelles font une dizaine d'heures de travail attentif, soit des mois à quelques heures par semaine. C'est l'étape où un projet solo meurt, et elle est en fin de plan, donc jamais atteinte. Poser un jalon livrable — 6 fiches — le tenir, publier le chiffre mesuré, et rouvrir la question ensuite. Le README annonce le nombre réel, jamais la cible.

PIÈGE JURIDIQUE que le plan n'a pas vu dans sa liste de compagnies : British Airways relève du UK261 post-Brexit, pas du règlement 261/2004, et Swiss opère sous accord bilatéral avec un organisme national d'exécution distinct. Une fiche pour ces transporteurs, dans un outil dont `eu261.py` ne calcule que le régime UE, produit un `legal_scope` trompeur. Les exclure du premier lot, ou leur écrire un `legal_scope` qui dit explicitement que le moteur ne couvre pas leur régime.

Laisser `not_found` (tools.py:449-459) faire son travail honnête pour le reste : ne rien dire est la bonne réponse quand on ne sait pas.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/airline_policies/`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/README.md`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/RAG_SPEC.md`

*Risque :* La tentation de générer les fiches en scrapant ou en interrogeant un modèle. Une fiche fausse est strictement pire qu'une fiche absente : elle envoie le passager sur un mauvais canal en se présentant comme vérifiée. Chaque affirmation vient d'une page officielle réellement lue, avec son URL et sa date.

### 8. Contrôle des sources, en lecture seule

*Effort :* heures · *Prérequis :* Étape 5 pour le schéma. Sans intérêt en dessous de ~6 fiches.

`scripts/recheck_sources.py`, hors chemin d'inférence : pour chaque URL de chaque fiche, requête urllib, extraction du texte visible via `html.parser`, normalisation des espaces, empreinte sha256, comparaison à l'empreinte stockée. Le script **rapporte** : identique, dérive, redirection hors domaine, code d'erreur, blocage anti-robot. Il n'écrit rien dans les fiches.

DEUX AMPUTATIONS PAR RAPPORT AU PLAN, l'une pour l'honnêteté, l'autre pour la correction.

(a) Suppression du renouvellement automatique de `verified_on` au-dessus de 0,98 de similarité. Le plan le propose *et* interdit dans son propre « à ne pas faire » de renouveler ce champ sans mesure. Une empreinte stable dit « les octets n'ont pas bougé » ; `verified_on` affirme « un humain a lu cette page ce jour-là ». Ce sont deux assertions différentes et une machine ne peut produire que la première. Si l'information est jugée utile, elle mérite son propre champ `content_unchanged_on`, distinct et non substituable. Sinon le script se contente de son rapport.

(b) Pas de `SequenceMatcher` sur le texte intégral des pages : son coût est quadratique et une page de 100 ko le rendra inutilisable. Égalité par hachage pour le cas identique, similarité par intersection de jetons (Jaccard sur des ensembles de mots) pour la dérive. Deux fois plus simple et borné en temps.

COUPÉ : l'Action hebdomadaire qui tient une issue à jour. À 6-14 fiches et ~25 URLs, plusieurs sites de compagnies sont derrière Cloudflare et rendus en JS — urllib les verra mal, et le rapport hebdomadaire dira « N fiches bloquées » toutes les semaines. Une notification qu'on apprend à ignorer est pire qu'aucune notification, et l'automatisation coûte alors plus cher que le contrôle manuel trimestriel qu'elle remplace. Le script tourne à la main, ou dans une Action `workflow_dispatch` déclenchée quand on décide de maintenir.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/scripts/recheck_sources.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/airline_policies/`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/RAG_SPEC.md`

*Risque :* Le script est un accès réseau : il doit vivre hors du chemin d'inférence, et l'interrupteur de l'étape 1 doit garantir qu'aucun test ne l'exécute. Vérifier aussi qu'il n'envoie aucun en-tête identifiant et qu'il respecte un délai entre requêtes — un script qui martèle les sites des compagnies depuis le dépôt public serait un mauvais argument de portfolio.

### 9. Résolution d'entité tolérante et mesure de la récupération

*Effort :* soiree · *Prérequis :* Étape 6 : la tolérance ne se mesure que sur un registre de taille réaliste. Sur trois transporteurs, tous les seuils passent.

Après l'échec de la correspondance exacte (tools.py:376-388 dans `identify_carrier`, pas 413-429 comme indiqué — 413 est `_match_policy`), ajouter un repli `difflib.get_close_matches` sur les noms normalisés. Ne renvoyer le résultat approché qu'avec un champ `match: "approximate"` visible dans la trace, jamais silencieusement.

CORRECTION MESURÉE ET DÉCISIVE : le seuil de 0,85 proposé ne discrimine pas. Sur les noms normalisés par `_normalise_carrier`, j'ai mesuré ici — `air frnace`→`air france` 0,889, `esayjet`→`easyjet` 0,857, ce sont les cas à rattraper ; mais `air europa`/`air europe` 0,889 et `aer lingus`/`air lingus` 0,889, ce sont les confusions à interdire. Même bande, aucune marge. Conséquences à implémenter, pas à noter en commentaire : (1) la règle d'ambiguïté est le mécanisme principal — calculer les ratios contre TOUTES les entrées, refuser si les deux meilleurs candidats sont à moins de 0,05 l'un de l'autre ; (2) un plancher de longueur, sous 6 caractères normalisés le repli approché est désactivé (`tap`/`sas` mesuré à 0,333 rassure, mais le rapport signal/bruit s'effondre sur les libellés courts) ; (3) le repli approché ne doit alimenter QUE `identify_carrier`, jamais la sélection d'une fiche procédurale par `_match_policy` — se tromper de compagnie sur un canal de dépôt coûte plus cher que de ne pas la reconnaître.

Puis `eval/retrieval_cases.json` : 30 à 40 libellés, et surtout — le plan ne le dit pas — **des cas négatifs adversariaux**, pas seulement des corruptions OCR à rattraper. Mesurer recall@1 ET taux de fausse attribution. Le second chiffre est le seul qui importe pour un outil qui donne une adresse d'envoi.

Écrire dans docs/RAG_SPEC.md — qui existe déjà, 70 lignes, et dont la section « Récupération MVP » impose aujourd'hui la correspondance exacte et contredirait cette étape — les seuils avec leur mesure : scan linéaire en dessous de ~200 fragments (on y est), BM25 ~80 lignes stdlib jusqu'à ~5 000, SQLite FTS5 au-delà (disponible ici, sqlite 3.51.0 vérifié, mais option de compilation donc contrôle à l'exécution obligatoire avec repli), embeddings Ollama seulement si recall@5 lexical mesuré tombe sous 0,85 avec plus de 1 000 fragments. Documenter un seuil qu'on a mesuré et qu'on ne franchit pas est un meilleur argument d'ingénierie qu'une base vectorielle.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/tools.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/retrieval_cases.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/corpus.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/RAG_SPEC.md`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Une fausse attribution silencieuse. Poser un test qui interdit toute confusion entre deux entrées distinctes du registre, et le faire échouer volontairement une fois pour vérifier qu'il mord.

### 10. Chemin sans modèle : saisie manuelle de secours

*Effort :* quelques soirees · *Prérequis :* Étapes 3 et 4 : sans le canal local et sans le règlement embarqué, la sortie sans modèle serait trop pauvre pour valoir la peine.

REFORMULÉ — la version du plan ne peut pas fonctionner. Elle affirme que « la déclaration en texte libre passe par le parseur déterministe existant ». `merge_incident_statement` (agent.py:590-730) n'écrit que `disruption_type`, les minutes de retard, `trip_completed` et `disruption_cause` — liste exhaustive visible dans `eval/corpus.py:23-31`. Il ne produit ni `origin`, ni `destination`, ni `airline`, ni la date, ni le nom du passager. Or `qualify_delay` (eu261.py:330-341) retourne `needs_information` sans origine et destination, et une lettre sans nom ni référence de réservation n'est pas envoyable. Sans modèle, il n'y a aucune lecture de billet : le PDF est rasterisé (agent.py:227) puis envoyé en base64 à Gemma (agent.py:485-492).

CE QU'IL FAUT VRAIMENT FAIRE : un chemin d'entrée où les faits sont saisis, pas extraits. Une fonction `process_manual(fields, incident_text)` qui prend origine, destination, compagnie, date, numéro de vol, nom, référence ; passe la déclaration libre par `merge_incident_statement` pour l'incident et la cause ; appelle `qualify_case` et `assess_ticket_reimbursement` ; obtient le canal via le corpus (étape 3) et les articles via la jointure (étape 4) ; et produit la lettre par un gabarit français à trous — zéro génération, zéro variance. Le dossier annonce « rédaction par gabarit, modèle indisponible ». Côté surface : une route `/api/analyze_manual` dans app.py, un formulaire replié dans `static/index.html`, des arguments dans le CLI (agent.py:1503).

C'est la démonstration la plus nette de la thèse architecturale : si retirer le modèle laisse intacts le verdict, le montant, le fondement juridique et l'adresse d'envoi, alors le modèle n'a effectivement jamais décidé. Et c'est un chemin utile en soi — un utilisateur sans billet numérisé peut s'en servir.

EFFORT REQUALIFIÉ : ce n'est pas « 40 lignes de gabarit ». C'est un point d'entrée, sa validation d'arguments, une surface web, une surface CLI et le gabarit. Trois soirées au minimum, davantage si l'interface est soignée.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/app.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/static/index.html`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/README.md`

*Risque :* Dupliquer la logique de rédaction en deux chemins qui divergent. Le gabarit doit consommer exactement les mêmes structures `qualification`, `reimbursement` et `research` que le prompt de `draft_claim`, et être testé sur les mêmes cas. Second risque : le mode doit refuser de conclure quand les champs manquent et lister les questions ouvertes via `_pending_questions` (agent.py:1151) — jamais deviner pour combler un trou.

### 11. [AJOUTÉ] Évaluation de l'extraction de billets : le maillon non mesuré

*Effort :* quelques soirees · *Prérequis :* Étape 1, pour garantir que ce harnais ne peut pas se déclencher dans la suite déterministe. L'essentiel du coût est la constitution du jeu de billets, pas le code.

Tout l'édifice hors ligne repose sur `origin`, `destination` et `airline`, et ces trois champs ne viennent que du modèle multimodal. Or rien ne mesure sa fiabilité : les 31 cas de `eval/incident_cases.json` évaluent `merge_incident_statement`, c'est-à-dire le parseur de déclaration, et `eval/corpus.py:1-5` le dit lui-même — « aucun appel au modèle ». L'objectif explicite de l'utilisateur est « lire les billets des gens », et c'est la seule partie du système sans chiffre.

Conséquence directe sur ce plan : l'étape 9 justifie la tolérance OCR par « les corruptions d'un billet photographié ». Personne ne sait si Gemma corrompt les noms de compagnie, ni comment. On construirait un correctif sans avoir observé le défaut.

CE QU'IL FAUT : `eval/tickets/` avec 8 à 12 billets — captures réelles anonymisées, PDF de compagnies différentes, une photo de travers, un scan médiocre, un billet en anglais, une carte d'embarquement mobile — chacun accompagné d'un `expected.json`. Un harnais `eval/tickets.py` opt-in (`--with-model`, jamais dans la suite déterministe ni dans la CI, l'interrupteur de l'étape 1 s'en charge) qui exécute `extract_flight` et compte par champ : exact, absent, faux. Le champ « faux » est le seul dangereux — un `origin` absent produit un `needs_information` honnête, un `origin` faux produit un montant faux avec un aplomb parfait.

Ce tableau, publié dans le README avec sa date et le tag du modèle, est l'élément qui distingue un projet de portfolio d'une démo. C'est aussi ce qui rendra visible le jour où `gemma4:12b` sera remplacé.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/tickets.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/tickets/`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/EVALUATION.md`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/README.md`

*Risque :* Publier des billets réels non anonymisés dans un dépôt public. Chaque pièce doit être caviardée (nom, référence, code-barres, numéro de carte de fidélité) et le caviardage vérifié à l'œil sur le rendu, pas seulement dans les métadonnées — un PDF conserve la couche texte sous un rectangle noir. Alternative sûre : générer les billets de test soi-même, au prix d'une représentativité moindre, à assumer par écrit.

### 12. [AJOUTÉ] Un bloc de provenance unique dans la sortie, l'interface et la lettre

*Effort :* heures · *Prérequis :* Étapes 2, 3 et 4 : le bloc n'a de contenu qu'une fois les états de provenance créés.

Après les étapes 2 à 4, la provenance d'un dossier sera dispersée sur au moins six emplacements : `research.rights.status` (online / offline / local_regulation), `research.rights.reference_source_reachable`, `research.claim_channel.status` (online / local_corpus / no_official_match / unverified_channel / demo_carrier), `research.airline_policy.freshness` (fresh / stale / expired), le drapeau hors ligne, et les états de la trace. Un lecteur du JSON ne peut pas répondre en un coup d'œil à la seule question qui compte : « qu'est-ce qui, dans ce dossier, a été vérifié en ligne aujourd'hui, et qu'est-ce qui vient d'une copie locale, de quelle date ? »

Ajouter un bloc `provenance` normalisé, calculé en Python à partir des états existants — jamais rédigé par le modèle : mode (`online` / `offline_forced` / `degraded`), origine du canal avec sa date, origine du fondement juridique avec l'empreinte du corpus, âge de la fiche procédurale, et la liste des éléments à reconfirmer. L'afficher dans l'interface et le résumer en pied de lettre.

Pourquoi ce n'est pas de la cosmétique : le projet vend l'auditabilité. Neuf étapes de plomberie hors ligne qu'aucun lecteur ne peut constater en ouvrant la démo ou la sortie JSON ne valent presque rien en portfolio. C'est aussi la capture d'écran qui rend le README crédible, et le point d'appui de la démonstration vidéo — « voici le même dossier en ligne, voici hors ligne, voici ce qui change et ce qui ne change pas ». Enfin, c'est le seul endroit où la mention de reconfirmation exigée à l'étape 3 devient vérifiable de bout en bout.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/static/index.html`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/examples/sample_output.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/README.md`

*Risque :* En faire une couche d'abstraction qui masque les états sous-jacents. Le bloc est un résumé dérivé, calculé à la lecture ; les champs d'origine restent dans la sortie et font foi. Ne jamais laisser le modèle écrire une ligne de ce bloc, ni le paraphraser dans la lettre autrement que par le texte fourni.

## À ne pas faire

- Embarquer un magasin vectoriel (Chroma, FAISS, LanceDB, sqlite-vec). Dépendance externe sur le chemin d'inférence, pour un corpus mesuré à 13 595 octets et une jointure par clé primaire. Le contrôle AST de la CI casserait, et il aurait raison.

- Indexer le corpus procédural. Mesuré et reproduit sur cette machine : 0,090 ms pour charger et parser trois fiches, appelé une fois par dossier. Un index serait plus lent à construire qu'un scan complet. Si la charge le justifiait un jour, la réponse serait un cache module-level de `_load_policy_files`, pas un moteur de recherche.

- Faire du RAG sur le texte du règlement. Corpus clos, adressable, clé d'accès calculée par Python : c'est une jointure. Un retriever y ajouterait de l'incertitude et rendrait au modèle le choix de l'article cité.

- Laisser le modèle sélectionner, reformuler ou abréger l'article cité. `legal_basis` est produit exclusivement par eu261.py, sur la même branche que le montant.

- Valider les citations en analysant la prose de la lettre. Détecter « ce passage se présente comme une citation » dans du français libre est une heuristique à fort taux de faux positifs. Structurer la sortie (`legal_citations: [{article_id, verbatim}]`) et comparer par égalité exacte, comme `_validate_tool_call` le fait déjà pour les arguments d'outils.

- Transcrire les 19 articles et 25 considérants du règlement. Embarquer une unité qu'aucune branche du moteur ne peut émettre, c'est du poids mort à maintenir sans consommateur. Douze à quinze unités atteignables, puis ajout à la demande.

- Télécharger un modèle d'embeddings « pour être prêt ». 300 à 600 Mo, un appel HTTP de plus par dossier, et un facteur d'environ 20 entre le volume réel du corpus et le seuil où la question se poserait.

- Générer les fiches procédurales par scraping ou par un modèle. Sites en JS, protections anti-robot, et surtout : une fiche fausse envoie le passager sur un mauvais canal en se présentant comme vérifiée. `not_found` est une réponse correcte.

- Annoncer un objectif de fiches dans le README. Publier le nombre livré et mesuré. Un « objectif : 15 compagnies » sur un dépôt figé à 4 est le signal exactement inverse de celui recherché.

- Écrire une fiche pour British Airways ou Swiss sans qualifier leur régime. UK261 post-Brexit et l'accord bilatéral suisse ne sont pas le règlement que calcule eu261.py ; un `legal_scope` silencieux sur ce point est trompeur.

- Laisser un script écrire `verified_on`. Le champ affirme qu'un humain a lu la page ce jour-là ; une empreinte stable n'affirme que la stabilité des octets. Si cette seconde information est utile, elle mérite son propre champ, pas l'usurpation du premier.

- Mettre en place une Action hebdomadaire qui ouvre une issue de revérification. À 6-14 fiches derrière Cloudflare, elle criera au loup chaque semaine jusqu'à être ignorée. Un déclenchement manuel coûte moins cher que l'entretien de son propre bruit.

- Comparer les pages par `SequenceMatcher` sur le texte intégral : coût quadratique, inutilisable sur une page de 100 ko. Hachage pour l'égalité, Jaccard sur jetons pour la dérive.

- Continuer à simuler le hors ligne en mockant `web_search` ou `urlopen` sur une fonction isolée. Ça ne prouve rien sur `process()` et se contourne par n'importe quel autre chemin réseau. Le patch doit être au niveau socket et actif par défaut.

- Doubler l'interrupteur socket d'un `HTTPS_PROXY` en CI. Deux mécanismes à moitié fiables valent moins qu'un seul testé, et posé au niveau du job il casserait `actions/checkout`.

- Passer `reference_source_reachable` à True parce qu'une copie locale existe. Contrairement à ce qu'affirmait le plan d'origine, ce champ ne pilote aucune décision de eu261.py (le commentaire eu261.py:404-407 l'exclut explicitement) — mais c'est une assertion de provenance, et les assertions de provenance sont tout ce que ce projet vend.

- Supprimer le palier `expired` en gardant seulement `stale`. Une fiche de deux ans doit se taire. Le repli à deux paliers ajoute une nuance, il ne supprime pas la limite.

- Faire consommer au repli de canal la sortie de `retrieve_airline_policy` plutôt que la fiche elle-même. La sortie vide `procedures` dès `stale`, et l'URL de canal y est enfermée : le repli mourrait exactement dans le scénario qu'il est censé couvrir.

- Appliquer la correspondance approchée à la sélection d'une fiche procédurale. Se tromper de compagnie sur un canal de dépôt coûte plus cher que ne pas la reconnaître. Le repli `difflib` ne concerne que `identify_carrier`, et jamais en silence.

- Retenir le seuil de 0,85 sans la règle d'ambiguïté. Mesuré ici : les corruptions à rattraper (0,857-0,889) et les confusions à interdire (0,889) occupent la même bande. C'est l'écart entre les deux meilleurs candidats qui décide, pas le seuil absolu.

- Publier des billets réels non caviardés dans `eval/tickets/`. Un PDF conserve sa couche texte sous un rectangle noir : vérifier le caviardage sur le contenu extrait, pas sur l'apparence.

- Construire les dix étapes de plomberie hors ligne sans jamais les rendre visibles dans la sortie, l'interface et le README. Une propriété que personne ne peut constater en ouvrant le dépôt n'existe pas, du point de vue de ce pour quoi ce projet est fait.

