# Architecture du code : découpage modulaire, registre d'outils, contrainte stdlib, contrats d'erreur, stratégie de test

Fiche de conception issue de l'audit du 28 juillet 2026, après critique adversariale. Synthèse et ordre de construction dans [`../ARCHITECTURE_CIBLE.md`](../ARCHITECTURE_CIBLE.md).

## Diagnostic

VÉRIFICATION DU DIAGNOSTIC DU CONCEPTEUR — ce qui est exact, ce qui est faux.

EXACT, vérifié ligne à ligne :
- agent.py = 1531 lignes (l'énoncé de mission disait 1560, le concepteur 1531 : c'est 1531). Les huit responsabilités et leurs plages de lignes sont justes : `_chat` (311-364), ingestion (227-308, 365-423), prompts/schémas (48-220), tâches modèle (426, 464, 1015), parseur de déclaration (522-728), registre+dispatch (788-1012), validation de sortie (1067-1148), orchestration `process` (1254-1500).
- Les quatre charges utiles Ollama dupliquées existent bien : agent.py:431, 484, 875, 1039, toutes avec `model/stream/think/options/keep_alive`. Elles diffèrent utilement (format vs tools, num_ctx/num_predict seulement en rédaction) : une signature unique `chat(messages, *, schema, tools, timeout, num_ctx, num_predict)` les couvre toutes les quatre. Vérifié.
- Le registre est bien dupliqué sur cinq sites non reliés : tools.py:32-120, agent.py:216-220, 788-807, 838-848, 207-214.
- Double contrat des outils : confirmé. tools.py:289 (`build_rule_query` → `build_research_context`), tools.py:447, tools.py:546 appellent tous `build_research_context` sur leur argument. Il marche dans les deux sens parce que `build_research_context` (tools.py:183) est tolérant : sur des arguments déjà minimisés il renvoie `airline=""` sans se plaindre. La minimisation est donc bien une convention d'appelant.
- `step.fallback` : static/index.html:405 le lit, `grep '"fallback"' *.py` ne renvoie rien. Branche morte confirmée. Les comptes du concepteur sont exacts : 11 clés de `step` lues (step, state, tool, outcome, duration_seconds, details, selected_by, requested_tool_calls, rejected_tool_calls, tool_result_round_trips, fallback) et 13 clés de `data`.
- Job CI aveugle : .github/workflows/tests.yml construit `LOCAL` avec `rglob` mais itère sur `glob("*.py")` — racine seulement. Confirmé, c'est bien la ligne qui casse au premier sous-dossier.
- `AgentError` unique : 28 sites de `raise AgentError` couvrant aussi bien « Formats acceptés : PDF, PNG… » (304) qu'« Ollama est inaccessible » (344) ; app.py:126 mappe tout en 400. Confirmé.
- Zéro `dataclass`, `Protocol`, `TypedDict`, `Literal` dans le dépôt (grep sur tout le code hors .venv : aucun résultat). 48 `dict[str, Any]` : 30 + 12 + 6. Exact. Pas de pyproject.toml.

FAUX OU INCOMPLET — quatre corrections qui changent la séquence :

1. **Le piège de test est trois fois plus large qu'annoncé.** Le concepteur ne compte que les 7 `patch("agent._chat")`. Le recensement réel des cibles de `patch` dans test_agent.py : `agent.extract_flight` ×8, `agent.research_case` ×7, `agent._chat` ×7, `agent.draft_claim` ×6, `agent.verify_air_passenger_rule` ×5, `agent.find_claim_channel` ×5, `agent.retrieve_airline_policy` ×2 = **40 substitutions d'attribut de module**, pas 7. Chacune devient un test vert connecté au réseau dès que l'appelant déménage. Traiter `_chat` seul et considérer l'étape faite, c'est laisser 33 pièges armés au moment précis où on croit avoir désamorcé le champ de mines.

2. **« test_agent.py garde sa liste d'imports intacte grâce à la façade » est faux.** test_agent.py:28-37 fait `from eu261 import (AIRPORTS, arrival_delay_from_times, …)` — 9 noms — et test_agent.py:40-50 `from tools import (RESEARCH_TOOL_DEFINITIONS, _api_key, _is_official_url, …)` — 10 noms. La façade proposée est `agent.py` ; rien ne couvre `eu261` ni `tools`. Et eval/corpus.py:19-20 importe `merge_incident_statement` depuis `agent` **et** `classify_cause` depuis `eu261`, or `eval/corpus.py` est exécuté par la CI comme un test ordinaire (test_agent.py:1424-1433). L'étape « déplacement mécanique, zéro test modifié » casse donc 20 imports et le corpus. Il faut décider explicitement : shims de compatibilité `eu261.py` / `tools.py` à la racine, ou édition des imports dans le même commit. Non décidé = soirée perdue à déboguer un `ImportError` en croyant à un bug de refactor.

3. **Le fichier témoin de l'étape 1 n'est pas comparable à l'octet près.** examples/sample_output.json contient `"duration_seconds": 10.69` (une vraie mesure) et une étape `check_flight_date` d'issue `implausible` qui dépend de `date.today()` face à `departure_date: 2026-09-14`. Le test proposé serait rouge par écoulement du temps **le 14 septembre 2026**, sans qu'une ligne ait bougé. Le témoin doit geler l'horloge et normaliser les durées, sinon on ajoute une bombe à retardement dans le filet censé protéger le refactor.

4. **Le ROADMAP §6 est cité à l'envers.** Le concepteur écrit « Le ROADMAP §6 dit que le routage est déterministe par conception et que la boucle n'est là que pour la démonstration ». Le texte réel (ROADMAP.md:352-359) dit : « L'option honnête est de **supprimer la boucle sélecteur**, d'exécuter `RESEARCH_TOOL_ORDER` en Python […] et d'écrire "le routage est déterministe par conception". Il n'y a plus de jury à impressionner. » C'est une recommandation de suppression transformée en caution d'une stratégie. La conclusion du plan reste défendable — le function calling natif est l'argument de vitrine du dépôt — mais elle doit être assumée comme un désaccord avec le ROADMAP, pas présentée comme son application.

ANGLE MORT COMPLET DU DIAGNOSTIC — la couche d'ingestion n'a aucun test.
`grep '_image_bytes\|_audio_as_wav\|_render_pdf_first_page\|_webp_as_png\|shutil.which' test_agent.py` : **zéro résultat**. Les trois chemins subprocess (pdftoppm agent.py:229, ffmpeg 263/372, sips 269 — ce dernier macOS uniquement) ne sont couverts par aucun des 106 tests. C'est précisément la couche dont dépend l'objectif que l'utilisateur a formulé en premier — « lire les billets des gens », et un vrai billet est un PDF. Le plan classe `ingest.py` comme un simple déplacement mécanique en étape 9 ; c'est le seul module du dépôt dont on ne sait pas s'il marche ailleurs que sur le Mac de l'auteur.

DÉSÉQUILIBRE DE FOND DU PLAN.
Treize étapes, dix à douze soirées, et **rien de visible pour un visiteur GitHub ni pour un vrai billet**. Le refactor est justifié — le god-module est réel — mais un plan d'architecture qui ne contient aucune vérification que le produit fonctionne encore contre le vrai Gemma dépense dix soirées à l'aveugle. Les 106 tests mockés ne disent rien de la seule question qui décide de la démo : Gemma 4 émet-il des `tool_calls` valides ? Le plan met cette vérification en note de bas de page de l'étape 12, c'est-à-dire après tout l'investissement.

## Cible

Un paquet `droit/` de **17 modules** (le plan en listait 21 en annonçant 17 : `context.py` est absorbé par `registry.py`, `logsetup.py` par `errors.py`, `types.py` est optionnel), deux points d'entrée à la racine (`agent.py` façade + CLI, `app.py` HTTP), deux shims de compatibilité temporaires (`eu261.py`, `tools.py`), et `tests/`.

Le découpage du concepteur est repris tel quel — il est bon, chaque fonction a une adresse et une seule — avec trois modifications :

**`context.py` fusionne dans `registry.py`.** `build_research_context` et les trois `_*_arguments` sont la même préoccupation : ce qui sort du dossier vers l'extérieur. Les réunir avec le tuple `RESEARCH_TOOLS` met **toute la frontière de minimisation sur un seul écran**, auditable en une lecture. C'est l'argument de sûreté le plus vendeur du dépôt ; l'éparpiller sur deux fichiers l'affaiblit sans rien gagner.

**`logsetup.py` disparaît**, avec le formateur JSON qu'il portait. Un service unique, sur la machine de l'utilisateur, avec un seul lecteur de journal, n'a pas besoin d'un format machine. `logging.basicConfig` dans les deux points d'entrée + un `logging.Filter` de six lignes pour le `run_id`, dans `errors.py`. `DR_LOG_FORMAT=json` est du cargo-cult déguisé en sérieux : il n'existe aucun agrégateur pour le consommer.

**Le registre reste tel que proposé** — `ResearchTool` frozen/slots, tuple littéral, `_BY_NAME` dérivé — et l'argumentaire du concepteur tient : un tuple littéral écrit à la main dans un seul module est un ensemble clos au même titre qu'une chaîne de `if`, et le test AST « aucun `globals`/`getattr`/`eval`/`exec`/`__import__`/`importlib` dans `droit/` » étend la garantie de 25 lignes à 3 000. C'est un renforcement.

**Mais il crée un problème que le plan ne voit pas.** `run=websearch.verify_air_passenger_rule` capture l'objet fonction à l'import, dans un tuple gelé. Après cela, ni `patch("agent.verify_air_passenger_rule")` (12 sites actuels) ni `patch("droit.websearch.verify_air_passenger_rule")` n'intercepte quoi que ce soit : le registre tient déjà la référence. Ce n'est pas un défaut, c'est la conséquence logique de la liaison précoce, et il faut choisir la réponse **avant** l'étape 6, pas la découvrir dedans. La bonne réponse : **les tests cessent de substituer les outils et substituent la frontière réseau** (`droit.websearch.web_search`, `urllib.request.urlopen`). C'est strictement plus fort — un test qui remplace `web_search` prouve que l'outil ne sort pas du bac à sable, là où remplacer l'outil entier ne prouvait rien. La mauvaise réponse, à refuser : rendre `run` résoluble tardivement, ou exposer un point d'injection de registre « pour les tests ». Cela rouvrirait exactement l'espace de noms que le tuple ferme.

STDLIB : l'analyse du concepteur est juste et vérifiée. `dataclass(slots=True)` (3.10+, matrice CI couverte), `Protocol`, `TypedDict`, `Literal`, `functools.lru_cache`, `contextvars`, `unittest.subTest` — tout est disponible sans rien installer. `enum.StrEnum` est bien 3.11+, donc hors matrice : refus correct.

Deux points d'honnêteté à publier, tous deux vérifiés dans le code :
- La revendication devient « **zéro dépendance Python à l'exécution** » — le ROADMAP.md:373-376 le demandait déjà. Rendue vérifiable en corrigeant `glob` → `rglob` avec exclusions.
- Le dépôt dépend **déjà** de trois binaires externes : `pdftoppm` (agent.py:229), `ffmpeg` (263, 372), `sips` (269, macOS uniquement). Le README doit dire « deux binaires externes optionnels, chacun avec un repli explicite » — et le repli doit être **testé**, ce qu'il n'est pas aujourd'hui.

TYPAGE : ambition réduite. `TypedDict` pour **deux** charges utiles seulement — `ExtractedFlight` et `Claim`, celles qui traversent tout le pipeline — plus `Literal` pour `DisruptionType` et les statuts. `ResearchBundle` et `Qualification` restent en `dict[str, Any]`, assumé et écrit. Annoter les quatre, c'est retoucher la signature de presque chaque fonction du dépôt : c'est le genre de chantier qu'une personne seule abandonne à la moitié, et un typage à moitié fait est pire que pas de typage. `mypy` sur `droit/eu261.py`, `droit/decision.py`, `droit/statement.py`, `droit/registry.py` uniquement.

## Étapes

### 1. Filet de régression et contrats CI, avant de déplacer une ligne

*Effort :* soiree · *Prérequis :* aucun

Corriger le job anti-dépendance : rglob('*.py') avec exclusion de .venv/, tests/, scripts/. Sans ça la garantie identitaire cesse silencieusement d'être vérifiée au premier sous-dossier. Ajouter pyproject.toml (name, requires-python >= 3.10, [project.optional-dependencies] dev = ruff + mypy) et un SECOND job CI qui installe l'extra et lint — le job existant continue sans aucune installation. AVERTISSEMENT VÉRIFIÉ : ruff sur 3 200 lignes jamais lintées sera rouge le premier jour. Lancer `ruff check` en local d'abord, choisir un jeu de règles restreint (E, F, I) et committer le job seulement une fois vert, sinon la CI rouge devient du bruit qu'on apprend à ignorer. Ajouter deux tests de contrat : (a) sortie de process() sur billet_avion_fictif.png comparée à examples/sample_output.json — avec horloge gelée via patch.object(datetime) et durations normalisées à zéro, car le fichier actuel contient duration_seconds: 10.69 et une étape check_flight_date qui dépend de date.today() face à departure_date 2026-09-14 : sans gel, le test devient rouge tout seul le 14 septembre 2026 ; (b) clés de trace émises ⊇ clés lues par static/index.html, extraites par regex sur le JS. Ce dernier échoue immédiatement sur step.fallback (index.html:405), qu'aucune ligne de Python n'émet : supprimer la branche morte.

*Fichiers :* `.github/workflows/tests.yml`, `pyproject.toml`, `test_agent.py`, `static/index.html`

*Risque :* aucun sur le code d'exécution. Le concepteur annonçait « heures » : le témoin JSON demande à lui seul de geler l'horloge, de normaliser les durées et de scripter trois réponses _chat cohérentes avec le fichier existant.

### 2. Couture ChatClient — et les QUARANTE substitutions de symboles, pas les sept

*Effort :* quelques soirees · *Prérequis :* étape 1

Définir ChatClient (Protocol) et OllamaChat dans droit/llm.py, y déplacer _chat (agent.py:311-364) et factoriser les quatre charges utiles (431, 484, 875, 1039) : la signature chat(messages, *, schema, tools, timeout, num_ctx, num_predict) les couvre toutes, vérifié. Faire descendre le client en paramètre optionnel de process, extract_flight, draft_claim, research_case. PORTÉE CORRIGÉE : le recensement réel des cibles de patch dans test_agent.py donne 40 substitutions d'attribut de module — extract_flight ×8, research_case ×7, _chat ×7, draft_claim ×6, verify_air_passenger_rule ×5, find_claim_channel ×5, retrieve_airline_policy ×2 — et non 7. Toutes deviennent des tests verts connectés au réseau après déménagement de leur appelant. Les traiter dans ce commit : les trois patchs de tâches modèle (extract_flight, research_case, draft_claim) deviennent des injections de dépendance dans process ; les douze patchs d'outils deviennent des substitutions de la frontière réseau — patch de web_search et de urllib.request.urlopen — ce qui est strictement plus fort, et ce qui restera la seule voie possible après l'étape 6 puisque le registre gelé tiendra une référence directe à chaque implémentation. Filet obligatoire dans le même commit : un test qui remplace urllib.request.urlopen par une exception et fait tourner le pipeline complet avec un ScriptedChat.

*Fichiers :* `droit/llm.py`, `agent.py`, `test_agent.py`

*Risque :* élevé. « Soirée » n'était crédible que pour les 7 sites _chat ; à 40 sites et 30 méthodes de test touchées, c'est deux à trois soirées. Les faire à moitié est pire que ne rien faire : on croit le champ de mines désamorcé alors que 33 pièges restent armés.

### 3. AJOUTÉ — Vérifier que la démo marche encore, AVANT d'investir dix soirées

*Effort :* soiree · *Prérequis :* étape 2

eval/live.py : trois cas contre le vrai gemma4:12b via DR_LIVE=1, sortie tabulaire, jamais en CI. Plus trois vrais billets — pas seulement billet_avion_fictif.png — passés dans le pipeline complet, dont au moins un PDF multi-pages et une photo de smartphone. Mesurer : Gemma émet-il des tool_calls structurellement valides ? _validate_tool_call les accepte-t-il, et à quel taux ? l'extraction lit-elle un vrai billet, ou seulement le billet de démonstration fabriqué pour elle ? POURQUOI ICI ET PAS EN ÉTAPE 12 : les 106 tests sont intégralement mockés et ne disent rien de la seule question qui décide de la vitrine. Le plan d'origine plaçait cette vérification après tout l'investissement architectural. Si le taux d'appels d'outils valides est mauvais, ou si l'extraction échoue sur un vrai billet, la priorité n'est plus le découpage — et il vaut mieux l'apprendre à la soirée 3 qu'à la soirée 12. C'est aussi la première étape du plan qui serve directement l'objectif formulé par l'utilisateur.

*Fichiers :* `eval/live.py`, `docs/EVALUATION.md`

*Risque :* le risque, c'est le résultat. Un mauvais chiffre ne se cache pas : il se publie dans EVALUATION.md et il réordonne le plan. C'est exactement ce qu'on attend d'une mesure.

### 4. Créer le paquet droit/ par déplacement mécanique, avec shims de compatibilité

*Effort :* soiree · *Prérequis :* étape 2

git mv de eu261.py, tools.py et du corps d'agent.py dans droit/. Laisser agent.py réduit à la façade (process, transcribe_audio, AgentError) plus main(), app.py inchangé — vérifié : app.py:15 n'importe déjà que ces trois noms. CORRECTION FACTUELLE : l'affirmation « test_agent.py garde sa liste d'imports intacte grâce à la façade » est fausse. test_agent.py:28-37 importe 9 noms depuis eu261 et test_agent.py:40-50 en importe 10 depuis tools ; eval/corpus.py:19-20 importe merge_incident_statement depuis agent ET classify_cause depuis eu261, et ce module est exécuté par la CI comme un test (test_agent.py:1424-1433). Décider explicitement maintenant : laisser à la racine deux shims de trois lignes — `from droit.eu261 import *` et `from droit.tools import *` — marqués comme temporaires et supprimés à l'étape 14. C'est la seule façon d'obtenir vraiment le commit « zéro test modifié » que le plan promet. Vérifier le job AST corrigé à l'étape 1 sur ce commit précis : c'est le scénario qu'il existe pour attraper. Mettre à jour AGENTS.md (dont le tableau des fichiers devient faux) et le tableau du README ; laisser les six permaliens « Où regarder » pour la fin.

*Fichiers :* `droit/__init__.py`, `droit/eu261.py`, `droit/tools.py`, `agent.py`, `eu261.py`, `tools.py`, `app.py`, `eval/corpus.py`, `AGENTS.md`, `README.md`

*Risque :* faible avec les shims, moyen sans. Sans eux, ce commit casse 19 imports de test et le corpus d'évaluation, et une soirée part en débogage d'ImportError qu'on prendra pour un bug de refactor.

### 5. Sortir statement.py — 210 lignes pures, gain immédiat

*Effort :* heures · *Prérequis :* étape 4

Déplacer merge_incident_statement et tout son appareil (agent.py:522-728) : _clause_before, _find_unnegated, _spell_out_durations, NEGATION_MARKERS, CLAUSE_BREAKS, CLOCK_CONTEXT, DELAY_MARKERS, CAUSE_MARKERS, WORDED_HOURS, WORDED_DURATION. Vérifié : aucun import du reste du projet, aucune I/O. Le module qui porte le plus de subtilité linguistique du dépôt devient lisible seul. Réexporter depuis le shim agent.py tant qu'eval/corpus.py:19 l'importe de là.

*Fichiers :* `droit/statement.py`, `agent.py`, `test_agent.py`, `eval/corpus.py`

*Risque :* quasi nul, et le concepteur a raison de commencer par là : IncidentStatementRobustnessTests et les 31 cas du corpus couvrent ces fonctions sans une seule mock.

### 6. registry.py : les cinq sites deviennent un tuple littéral — et absorbent la minimisation

*Effort :* quelques soirees · *Prérequis :* étapes 2 et 4

Créer ResearchTool (frozen, slots) et le tuple RESEARCH_TOOLS. Dériver ollama_definitions() (remplace tools.py:32-120), system_prompt() (remplace agent.py:207-214) et ORDER (remplace agent.py:216-220). MODIFICATION : y installer aussi build_research_context et les trois tables d'incidents (tools.py:122-143, 183-212) plutôt que de créer un context.py séparé — la fonction de minimisation et les trois _*_arguments qui la consomment sont la même préoccupation, et les réunir met toute la frontière PII sur un écran auditable d'une lecture. _validate_tool_call ne change pas de logique : appartenance à _BY_NAME, puis égalité stricte à tool.arguments(context). Quatre tests remplacent la coordination manuelle : set(tool.arguments(témoin)) == set(parameters['required']) par outil ; additionalProperties False partout ; registre comparé à une liste littérale écrite dans le test (nom, run.__module__, run.__qualname__) ; test AST « aucun globals/getattr/eval/exec/__import__/importlib dans droit/ ». CONSÉQUENCE À ASSUMER DANS LE MÊME COMMIT : run= capture l'objet fonction à l'import dans un tuple gelé, donc plus aucun patch d'attribut de module n'intercepte un outil. C'est pour ça que l'étape 2 a déjà déplacé les 12 patchs d'outils vers la frontière réseau. Ne pas ajouter de point d'injection de registre « pour les tests » : ce serait rouvrir l'espace de noms qu'on ferme.

*Fichiers :* `droit/registry.py`, `droit/research.py`, `droit/tools.py`, `tests/test_registry.py`, `README.md`

*Risque :* c'est la propriété la plus regardée du dépôt. Le message de commit doit expliquer pourquoi un tuple littéral dans un module unique est un ensemble clos au même titre qu'une chaîne de if, et pourquoi le test AST élargit la garantie de 25 lignes à 3 000. Sans cette justification écrite, un lecteur pressé lira une régression de sûreté.

### 7. research.py : boucle sélecteur isolée, stratégie explicite

*Effort :* soiree · *Prérequis :* étape 6

Déplacer _validate_tool_call et la boucle (agent.py:810-1012). Introduire ModelSelector(chat) et DeterministicSelector(), choisis par DR_TOOL_SELECTOR (défaut model). La trace conserve exactement ses champs (selected_by, requested_tool_calls, rejected_tool_calls, tool_result_round_trips). CORRECTION DE CITATION : le ROADMAP.md:352-359 ne dit pas que la boucle est là pour la démonstration — il recommande de la SUPPRIMER (« L'option honnête est de supprimer la boucle sélecteur, d'exécuter RESEARCH_TOOL_ORDER en Python […] Il n'y a plus de jury à impressionner »). Garder la boucle derrière une stratégie est un désaccord raisonnable avec le ROADMAP — le function calling natif de Gemma 4 est l'argument de vitrine du dépôt et le supprimer viderait la démonstration — mais il faut l'écrire comme tel dans le commit et corriger le paragraphe du ROADMAP, au lieu de faire dire au document l'inverse de ce qu'il dit. Bénéfice concret et non décoratif : DeterministicSelector donne un chemin d'exécution sans modèle pour les évaluations.

*Fichiers :* `droit/research.py`, `droit/registry.py`, `ROADMAP.md`, `tests/test_research.py`

*Risque :* faible. Les quatre chemins sont déjà couverts ; ces tests changent d'import et de forme de substitution, pas d'assertion.

### 8. decision.py : la cascade de process() devient une fonction pure

*Effort :* soiree · *Prérequis :* étape 5

Extraire les neuf branches qualification × reimbursement (agent.py:1347-1451) en decide(route, qualification, reimbursement) -> Decision. PRÉCISION SUR LA FORME : ce n'est pas un simple dict de décision. La cascade actuelle fait trois choses à la fois — elle écrit result['decision'], elle pose result['refusal'] et result['uncovered_right'], elle empile une étape de trace (flag_uncovered_right, agent.py:1401), et quatre de ses branches sortent par `return result` avant la rédaction. Decision doit donc porter cinq champs : decision, refusal, uncovered_right, trace_entries, should_draft. Sans le should_draft explicite, la fonction « pure » ne remplace pas la cascade et process() garde ses if. Tester le produit cartésien complet des statuts avec subTest : c'est l'endroit du dépôt où une régression est la plus probable et la moins visible — un remboursement masqué par un refus d'indemnisation est le bug que deux tests existants documentent déjà comme ayant eu lieu.

*Fichiers :* `droit/decision.py`, `droit/pipeline.py`, `tests/test_pipeline.py`

*Risque :* modéré : cette cascade encode du droit. Aucune reformulation de message utilisateur dans ce commit — déplacement littéral, simplification dans un commit séparé si elle s'impose.

### 9. trace.py : déclarer la forme au lieu de la fabriquer à la main

*Effort :* soiree · *Prérequis :* étapes 1 et 8

Step (frozen, slots) avec step/state/tool/duration_seconds/outcome/details et les champs optionnels du sélecteur ; Trace.add() ; as_json() qui omet les None. Remplacer les treize dicts littéraux de process() et de research_case. Le témoin de l'étape 1 garantit la sortie et le test de couverture des clés UI empêche qu'un champ lu par index.html cesse d'être émis — la panne exacte constatée sur step.fallback.

*Fichiers :* `droit/trace.py`, `droit/pipeline.py`, `droit/research.py`, `tests/test_pipeline.py`

*Risque :* faible, entièrement couvert par le témoin de l'étape 1 — à condition que celui-ci gèle bien l'horloge.

### 10. Vider le reste d'agent.py : prompts, extraction, drafting, routing, pipeline, ingest

*Effort :* quelques soirees · *Prérequis :* étapes 6 à 9

Six déplacements mécaniques, un commit chacun, aucune réécriture : prompts.py (48-220), extraction.py (426-517), drafting.py (1015-1148, où draft_claim et _validate_claim restent ensemble — c'est une paire, pas deux couches), routing.py (731-785, 1151-1251), pipeline.py (1254-1500), ingest.py (227-308, 365-423). agent.py finit à ~80 lignes de façade et de CLI.

*Fichiers :* `droit/prompts.py`, `droit/extraction.py`, `droit/drafting.py`, `droit/routing.py`, `droit/pipeline.py`, `droit/ingest.py`, `agent.py`

*Risque :* faible dans l'ordre indiqué, mais « une soirée pour six modules » n'est pas crédible : chaque déplacement demande son passage de suite complète et son commit. Compter deux soirées.

### 11. AJOUTÉ — ingest.py : sonde de capacité et replis réellement testés

*Effort :* soiree · *Prérequis :* étape 10

Constat vérifié et absent du diagnostic d'origine : grep de _image_bytes, _audio_as_wav, _render_pdf_first_page, _webp_as_png et shutil.which dans test_agent.py renvoie ZÉRO résultat. Les trois chemins subprocess — pdftoppm (agent.py:229), ffmpeg (263, 372), sips (269, macOS uniquement) — ne sont couverts par aucun des 106 tests, alors que c'est exactement la couche dont dépend « lire les billets des gens ». Faire trois choses : (1) une fonction capabilities() qui sonde shutil.which pour les trois binaires, exposée par la CLI et par une route de diagnostic, pour qu'un utilisateur sache avant l'échec ce qui manque ; (2) les binaires manquants lèvent ConfigError nommant le binaire ET le repli — « installe poppler, ou fournis un PNG » ; (3) des tests qui substituent shutil.which pour couvrir les six chemins d'absence et de dépassement de délai, plus un test de bout en bout sur billet_avion_fictif.pdf marqué skipUnless(shutil.which('pdftoppm')). Rectifier le README dans le même commit : « zéro dépendance Python à l'exécution ; deux binaires externes optionnels, chacun avec un repli explicite ».

*Fichiers :* `droit/ingest.py`, `droit/errors.py`, `agent.py`, `tests/test_ingest.py`, `README.md`

*Risque :* faible techniquement. Le vrai risque est de découvrir que le repli WEBP ne fonctionne que sur macOS — ce que le code laisse fortement penser (sips) et que rien ne vérifie aujourd'hui.

### 12. Éclater tools.py et fermer le double contrat

*Effort :* quelques soirees · *Prérequis :* étape 6

Répartir en websearch.py (SerpApi et les deux outils en ligne, tools.py:146-325 et 544-602), carriers.py (registre et allow-list de domaines, 345-410), policies.py (corpus local et futur point d'accroche unique du RAG, 328-343 et 413-541). build_research_context est déjà parti en registry.py à l'étape 6. Surtout : supprimer le double contrat. Les trois outils ne reçoivent plus que des arguments minimisés — plus de build_research_context à l'intérieur (tools.py:258 via build_rule_query, 447, 546) — et le seul chemin depuis un dossier complet passe par tool.arguments(context). Attention, build_rule_query (tools.py:256) appelle la minimisation lui aussi : il devient build_rule_query(args) et ne dérive plus rien. La minimisation cesse d'être une convention d'appelant pour devenir une frontière vérifiable. Ajouter lru_cache sur load_carriers et _load_policy_files, qui reparsent leur JSON à chaque appel alors qu'identify_carrier est appelé plusieurs fois par dossier.

*Fichiers :* `droit/websearch.py`, `droit/carriers.py`, `droit/policies.py`, `droit/registry.py`, `tests/test_tools.py`

*Risque :* modéré. test_minimized_arguments_are_accepted_without_disruption_type dépend explicitement du double contrat : il doit être remplacé par son inverse — un dossier complet passé directement à un outil doit lever, pas se laisser reminimiser en silence. Le concepteur annonçait « soirée » pour un éclatement en quatre modules plus trois changements de signature dans la zone la plus testée du dépôt : ce n'est pas une soirée.

### 13. errors.py, statuts HTTP, journalisation et run_id — sans le formateur JSON

*Effort :* soiree · *Prérequis :* étape 10

Quatre sous-classes d'AgentError portant code et http_status : InputError (400), UpstreamUnavailable (503), ModelOutputError (502), ConfigError (500). Reclasser les 28 sites de raise. app.py:126 mappe exc.http_status au lieu de renvoyer 400 pour tout, ce qui corrige un vrai défaut : Ollama éteint est aujourd'hui annoncé au navigateur comme une entrée invalide. Remplacer les cinq print par logging.getLogger(__name__), configuration unique dans agent.py et app.py. run_id (uuid4, 12 caractères) dans un contextvars.ContextVar, injecté par un logging.Filter et renvoyé dans le JSON de résultat ; DR_TRACE_DIR écrit {run_id}.json, rejouable par le harnais d'évaluation. CE QUI EST COUPÉ : le module logsetup.py et le formateur JSON sur DR_LOG_FORMAT. Un service unique, local, avec un seul lecteur humain, n'a aucun agrégateur pour consommer du JSON — c'est du cargo-cult déguisé en sérieux. Le Filter tient en six lignes dans errors.py.

*Fichiers :* `droit/errors.py`, `droit/pipeline.py`, `app.py`, `agent.py`, `tests/test_pipeline.py`

*Risque :* faible. Vérifier que static/index.html affiche toujours le message d'erreur : la clé error ne change pas, code s'y ajoute. Le contextvars est justifié par ThreadingHTTPServer, qui entrelace déjà les journaux de plusieurs requêtes.

### 14. Découper test_agent.py, supprimer les shims, refermer la documentation

*Effort :* quelques soirees · *Prérequis :* étapes 11, 12 et 13

tests/__init__.py — indispensable, sans lui unittest discover collecte zéro test en silence — plus sept fichiers thématiques : test_eu261, test_statement, test_registry, test_research, test_pipeline, test_tools, test_ingest, test_docs. DocumentedFiguresTests (test_agent.py:1474-1495) passe d'une lecture de test_agent.py à un parcours de tests/*.py — le compte actuel mesuré par AST est de 106, à comparer à l'identique après découpage, dans le commit lui-même. Supprimer les deux shims de compatibilité eu261.py et tools.py posés à l'étape 4, et corriger les imports d'eval/corpus.py. Régénérer en dernier les six permaliens « Où regarder » du README, une fois la disposition stabilisée. Mettre AGENTS.md à jour pour de bon : son tableau des fichiers et sa consigne « ajouter la couverture à test_agent.py » sont faux à partir d'ici.

*Fichiers :* `tests/__init__.py`, `tests/test_eu261.py`, `tests/test_statement.py`, `tests/test_registry.py`, `tests/test_research.py`, `tests/test_pipeline.py`, `tests/test_tools.py`, `tests/test_ingest.py`, `tests/test_docs.py`, `eval/corpus.py`, `AGENTS.md`, `README.md`

*Risque :* un test oublié dans le découpage disparaît sans bruit. Le comptage AST avant/après, dans le même commit, est la seule protection.

### 15. Typage borné : deux charges utiles nommées, mypy sur le noyau seulement

*Effort :* quelques soirees · *Prérequis :* étape 14

PORTÉE RÉDUITE PAR RAPPORT AU PLAN. TypedDict (total=False) pour ExtractedFlight et Claim uniquement — les deux formes qui traversent tout le pipeline — plus Literal pour DisruptionType et les statuts de décision. ResearchBundle et Qualification restent en dict[str, Any], et c'est écrit dans le pyproject. Annoter les quatre charges utiles revient à retoucher la signature de presque chaque fonction du dépôt : c'est le format de chantier qu'une personne seule abandonne à mi-parcours, et un typage à moitié fait vaut moins que pas de typage. Configurer mypy dans pyproject.toml sur droit/eu261.py, droit/decision.py, droit/statement.py et droit/registry.py — le noyau déterministe, celui qui encode du droit — avec follow_imports = silent, exécuté par le job [dev] de l'étape 1. Zéro octet de changement à l'exécution, JSON inchangé.

*Fichiers :* `droit/types.py`, `droit/eu261.py`, `droit/decision.py`, `droit/registry.py`, `pyproject.toml`

*Risque :* l'ambition doit rester bornée. Si l'annotation d'un module hors noyau dépasse une soirée, l'abandonner et l'écrire dans le pyproject. Cette étape est la première du plan qu'on peut sauter entièrement sans conséquence : la mettre en dernier n'est pas un hasard.

## À ne pas faire

- Ne pas déplacer une seule fonction avant d'avoir traité les QUARANTE substitutions d'attribut de module, pas seulement les sept patch('agent._chat'). Recensement vérifié : extract_flight ×8, research_case ×7, _chat ×7, draft_claim ×6, verify_air_passenger_rule ×5, find_claim_channel ×5, retrieve_airline_policy ×2. C'est le seul piège qui produit des tests verts qui appellent le réseau — panne silencieuse, découverte des semaines plus tard sur une facture SerpApi ou un timeout Ollama en démonstration. Traiter _chat seul et se croire à l'abri est pire que ne rien faire.

- Ne pas ajouter de point d'injection au registre « juste pour les tests » — ni run résoluble tardivement, ni override de RESEARCH_TOOLS, ni paramètre tools= dans run_research. Le registre gelé rend les outils non substituables par patch : c'est la conséquence logique de la liaison précoce, et la réponse est que les tests substituent la frontière réseau (web_search, urlopen), ce qui prouve davantage. Rouvrir le registre pour la commodité de test détruit exactement la propriété qu'on passe trois soirées à construire.

- Ne pas committer le job ruff avant d'avoir lancé ruff en local et atteint le vert. 3 200 lignes jamais lintées produiront une centaine de findings ; une CI rouge dès le premier jour est une CI qu'on apprend à ignorer, et elle discrédite le job anti-dépendance qui tourne à côté.

- Ne pas écrire le test de fichier témoin sans geler l'horloge ni normaliser les durées. examples/sample_output.json contient duration_seconds: 10.69 et une étape check_flight_date dont l'issue dépend de date.today() face à departure_date 2026-09-14. Un témoin naïf devient rouge tout seul en septembre 2026, dans le filet même censé sécuriser le refactor.

- Ne pas croire que le déplacement du paquet laisse les tests intacts sans shims. test_agent.py importe 9 noms de eu261 et 10 de tools ; eval/corpus.py importe classify_cause de eu261 et est exécuté par la CI comme un test. Sans deux shims temporaires à la racine, le commit « mécanique » casse 20 imports.

- Ne pas créer domain/, application/, infrastructure/, ports/ ni adapters/. À 3 000 lignes et un mainteneur, un niveau de dossier suffit. L'architecture hexagonale ajouterait quinze fichiers d'indirection pour zéro frontière réelle et signalerait l'inverse de la maîtrise recherchée.

- Ne pas remplacer le dispatcher par une résolution dynamique, même élégante : ni globals()[name], ni getattr(module, name), ni importlib, ni un décorateur @register. Le décorateur est le piège subtil : il rouvre l'espace de noms — n'importe quel module importé peut ajouter un outil — et détruit précisément la propriété qu'on préserve. Le tuple littéral en un seul endroit est la seule forme acceptable.

- Ne pas garder le formateur de journal JSON ni le module logsetup.py. Un seul service, sur la machine de l'utilisateur, un seul lecteur humain, aucun agrégateur : DR_LOG_FORMAT=json est du cargo-cult qui a l'air sérieux. Le run_id et un logging.Filter de six lignes suffisent, et eux sont justifiés par l'entrelacement réel des requêtes de ThreadingHTTPServer.

- Ne pas annoter les quatre charges utiles en TypedDict. Deux suffisent — ExtractedFlight et Claim. Les quatre imposent de retoucher presque chaque signature du dépôt, ce qui est le format exact de chantier qu'une personne seule abandonne à la moitié. Un typage partiel assumé et écrit vaut mieux qu'un typage global abandonné.

- Ne pas transformer le résultat de process() en dataclass sérialisée dans le même mouvement que le reste. static/index.html lit treize clés de data et onze de step, vérifiées : le contrat JSON est une interface publique de fait. Éventuellement en dernier, avec le témoin en filet.

- Ne pas introduire pydantic ni pytest. TypedDict plus les schémas JSON déjà imposés à Ollama par le paramètre format couvrent le besoin ; la validation est faite par le décodage contraint. Et pytest ferait entrer une dépendance sur le chemin de test que le job CI zéro-installation doit continuer d'exécuter — subTest couvre le paramétrage.

- Ne pas activer mypy --strict globalement. Les 48 dict[str, Any] produiront des centaines d'erreurs et le chantier sera abandonné en une semaine. Noyau déterministe uniquement, exemption écrite et assumée dans le pyproject.

- Ne pas ajouter d'observabilité au-delà du run_id et de logging : pas d'OpenTelemetry, pas de spans, pas de métriques, pas de corrélation inter-services.

- Ne pas séparer draft_claim et _validate_claim en deux couches. Le second n'existe que parce que le premier est un modèle : les disperser détruit la seule frontière de sûreté côté sortie.

- Ne pas faire du RAG une couche transverse. Il n'a qu'une adresse : droit/policies.py, derrière retrieve_airline_policy(args) -> dict, signature qui ne bouge pas quand la récupération passe d'une égalité de chaînes à un index. Le ROADMAP le dit déjà : à trois fiches, la contrainte est éditoriale, pas algorithmique.

- Ne pas profiter d'un déplacement pour reformuler un message utilisateur, un libellé de trace ou un texte juridique. Un commit qui déplace ne modifie rien d'autre : c'est ce qui rend la revue possible et le retour en arrière trivial.

- Ne pas faire dire au ROADMAP §6 l'inverse de ce qu'il écrit. Il recommande de SUPPRIMER la boucle sélecteur. La garder derrière une stratégie est un désaccord défendable — c'est l'argument de vitrine du dépôt — mais il s'assume dans un commit et se corrige dans le document, il ne se maquille pas en application du plan existant.

