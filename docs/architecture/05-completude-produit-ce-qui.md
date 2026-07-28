# Complétude produit : ce qui manque pour qu'un vrai passager traite un vrai incident, et pas un quart du règlement — plan revu après vérification du code, efforts requalifiés.

Fiche de conception issue de l'audit du 28 juillet 2026, après critique adversariale. Synthèse et ordre de construction dans [`../ARCHITECTURE_CIBLE.md`](../ARCHITECTURE_CIBLE.md).

## Diagnostic

## Ce que le diagnostic d'origine dit juste (vérifié)

- `eu261.py:549` `qualify_case` ne route que `delay` ; `eu261.py:530` `UNCOVERED_CASES` renvoie `not_covered` pour les trois autres. Confirmé.
- Tout le reste du pipeline accepte déjà les quatre types : `agent.py:73` (enum), `agent.py:592-600` (`merge_incident_statement` détecte annul / refus+embarquement / correspondance+rat|manqu / retard), `tools.py:136` (`POLICY_INCIDENT_BY_DISRUPTION`), `tools.py:122` (`ALLOWED_DISRUPTIONS`). Il manque bien une fonction de qualification, pas une couche.
- `eu261.py:446` `if disruption != "delay"` renvoie `not_assessed` pour `denied_boarding` : c'est un vrai bug juridique, l'art. 4(3) renvoie à l'art. 8 exactement comme l'annulation. (La fonction commence ligne 426, pas 431.)
- Le pied de lettre n'existe **nulle part** : `grep -n "automatis"` sur `agent.py`, `static/index.html` ne renvoie que `README.md:69`, sans rapport. Et `ROADMAP.md:428` (semaine 8) annonce « Pied de lettre inséré côté serveur, avec le test qui échoue s'il manque ». **Cette ligne est fausse.** Dans un dépôt dont l'argument est l'honnêteté, c'est un défaut de la même classe que la sous-réclamation.
- `app.py` : `GET /` + `POST /api/analyze` + `POST /api/transcribe`, rien d'autre. Aucun export. `static/index.html:624` rend bien la lettre dans un `<pre>` créé en JS (invisible à un grep `<pre`, la référence est correcte).
- `static/index.html:481` : panneau de faits en lecture seule, 11 libellés en dur, seule `booking_reference` corrigeable via `#reference` → `process(confirmed_booking_reference=...)`.
- `FLIGHT_SCHEMA` (`agent.py:52-116`) : 22 propriétés, toutes `required`, toutes orientées retard à l'arrivée. Aucun champ de préavis, de réacheminement, de motif de refus, de destination finale, de nombre de passagers.

## Ce qui est faux ou surestimé, et qu'il faut corriger avant de planifier

1. **« Une lettre qui a l'air complète » (annulation).** Le mécanisme décrit est réel — `qualify_case` → `not_covered`, `assess_ticket_reimbursement` → `likely` (`eu261.py:429-441`), donc `agent.py:1385-1420` bascule en `ready_for_claim` et rédige. Mais `CLAIM_SYSTEM` (`agent.py:196-198`) **ordonne explicitement** au modèle d'écrire qu'une indemnisation forfaitaire est peut-être due sans avancer de montant. Le vrai défaut n'est donc pas le silence : c'est qu'une phrase qui porte l'essentiel du dossier est **demandée au modèle et jamais vérifiée**, alors que le montant et l'URL le sont. C'est un argument plus fort, et c'est exactement la thèse de l'étape 4.

2. **« Les trois fiches déclarent `flight_cancellation` et `denied_boarding` ».** Faux. `tap_air_portugal.json` déclare `flight_delay`, `flight_cancellation`, `flight_rescheduling` — pas `denied_boarding`. 2 fiches sur 3. Conséquence concrète : un refus d'embarquement TAP tombera sur `incident_specific: false` (`tools.py:502`), la fiche entière sera servie, la checklist sera générique. Ce n'est pas bloquant, mais c'est un cas de test à écrire.

3. **« Accepter n'importe quel `extraction` ouvrirait la requête SerpApi à un contenu arbitraire ».** Surestimé. `build_research_context` (`tools.py:183-212`) filtre déjà : 7 champs seulement, `disruption_type` contrôlé contre `ALLOWED_DISRUPTIONS`, chaînes tronquées à 80/100, minutes bornées à `[0, 1440)`, `policy_incident` dérivé et jamais choisi. Le trou réel de `/api/refine` est ailleurs, et le concepteur ne l'a pas vu : **si le client fournit aussi le bloc `research`, il alimente `_allowed_claim_urls` (`agent.py:1071-1092`) et peut faire passer n'importe quelle URL dans la lettre.** C'est la seule propriété de sécurité que cette étape peut réellement casser.

4. **« < 20 s au lieu de 40 s ».** Arithmétiquement impossible avec les chiffres du dépôt : `docs/EVALUATION.md:87-92` donne 42,7 s dont 10,7 s d'extraction. Supprimer l'extraction donne ~32 s, pas 20. Passer sous 20 s exige de **ne pas rejouer la sélection d'outils (9,4 s) ni SerpApi** quand les faits qui alimentent `build_research_context` n'ont pas changé.

5. **« Le squelette `aria-live` existe pour la dictée, il ne couvre pas le résultat ».** Faux : `static/index.html:165` porte `<section id="result" class="card" aria-live="polite">`. Manquent `aria-busy` et le déplacement du focus.

6. **Angle mort de l'étape 6 (correspondance manquée), non signalé et grave.** `_derive_arrival_delay` (`agent.py:1188`) calcule `arrival_delay_minutes` depuis `scheduled_arrival` / `actual_arrival` du **document**, c'est-à-dire du premier segment. Router `missed_connection` vers `qualify_delay` avec `destination := final_destination` sans neutraliser ce calcul produit un retard de segment 1 (souvent faible ou nul) qualifié à la distance de la destination finale : montant faux, dans les deux sens, silencieusement. C'est le miroir exact du bug que le plan dénonce en ouverture.

7. **Doublon de vocabulaire non vu (étape 5).** `CAUSE_PATTERNS` (`eu261.py:275-297`) contient déjà `surbooking`, `surreservation`, `overbooking` en risque `low`. Un second classifieur `classify_denied_boarding_ground` avec sa propre liste crée exactement la divergence silencieuse que le plan redoute pour les bornes de tranche.

8. **Contradiction de l'étape art. 9.** « La somme est faite en Python » alors qu'un seul champ scalaire `care_expenses_eur` est défini : il n'y a rien à sommer, le total serait saisi par le passager et `_validate_claim` l'accepterait comme s'il venait du moteur.

## Ce que personne ne planifie, alors que l'objectif l'exige

L'utilisateur veut « lire les billets des gens ». Or `docs/EVALUATION.md:125` dit qu'**aucune exactitude par champ n'est mesurée sur l'extraction**, et aucune des neuf étapes ne s'y attaque. Les neuf étapes améliorent le moteur en aval d'une couche dont personne ne connaît le taux d'erreur sur un vrai billet froissé, en anglais, à deux segments. Les 106 tests (`test_agent.py`, compte verrouillé par `test_documented_test_count_is_accurate:1474`) et les 31 cas de `eval/incident_cases.json` couvrent le déterministe ; la vision n'est couverte par rien.

## Cible

Un passager sort avec **le bon montant, sur le bon fondement, dans un fichier qu'il possède, avec l'échéance et la relance déjà écrites** — et le dépôt sait dire à quel point il lit correctement un vrai billet.

- **4 types d'incident sur 4 chiffrés**, `docs/EVALUATION.md:116` mis à jour seulement quand c'est vrai. La correspondance manquée n'est pas une branche : c'est un retard mesuré à la destination finale (CJUE *Folkerts*, C-11/11), avec la distance orthodromique premier départ → destination finale (art. 7(1) *in fine*, CJUE *Bossen*, C-559/16).
- **`not_covered` survit**, repointé sur les vrais trous (art. 10(2), art. 8(3)). C'est une propriété, pas un échafaudage.
- **Les champs qui portent un effet juridique ne sont jamais remplis par le modèle de vision.** `FLIGHT_SCHEMA` reste ce qu'un document montre ; les circonstances sont déclarées, et c'est une table de champs Python — pas un second JSON Schema.
- **Le moteur écrit ce qu'il sait** : pied de lettre, mention conditionnelle, montant, fondement. Il ne valide que ce qu'il ne peut pas écrire lui-même. Chaque décision porte un `code` stable.
- **Une boucle de réponse** qui ne relit pas le document et ne rejoue pas la recherche quand les faits de recherche n'ont pas bougé : ~20 s, et zéro appel SerpApi supplémentaire.
- **Le dossier sort de la machine** : `lettre.txt`, `dossier.json` réimportable, `suivi.md` daté, `relance.txt` par gabarit, impression navigateur pour le PDF.
- **L'extraction est mesurée** : un harnais par champ sur un jeu de billets réels anonymisés, plus un chemin déterministe (code-barres BCBP) qui court-circuite le modèle quand il est disponible.

## Étapes

### 1. Socle : `_scope`, codes de message stables, table des champs déclarés

*Effort :* quelques soirees · *Prérequis :* Aucun. Premier chantier. Suite verte avant et après : aucune de ces trois modifications ne doit changer un comportement observable.

**Trois refactors mécaniques, sans nouvelle règle de droit. Les faire d'abord ou ne jamais les faire.** Le plan d'origine les diluait dans les étapes 1 et 9 ; c'est précisément comme ça qu'un refactor transverse est sauté sous prétexte de livrer la fonctionnalité.

**1. `_scope(extracted)`** extrait du bloc `eu261.py:326-363` : renvoie soit un dict d'erreur (`needs_information` / `non_eligible` géographique), soit `(origin, destination, distance_km, intra_eu)`. `qualify_delay` s'y adosse à comportement strictement identique. Sans lui, ce bloc sera copié trois fois. ~40 lignes, suite verte inchangée.

**2. Un `code` stable sur chaque décision du moteur**, à côté du `reason` français : `art7_threshold_not_met`, `art5_1c_i_notice_14_days`, `art7_2_reduction`, `art2j_reasonable_grounds`, `art3_2_late_check_in`, `geo_out_of_scope`… Environ 15 retours existants à annoter dans `eu261.py`, plus les branches de `route_case` et de `process`. Trois bénéfices immédiats : `statusMeta` (`static/index.html:205`), aujourd'hui un dictionnaire magique de 25 entrées adossé à des `status` génériques, devient une table adossée à des identifiants ; le `dossier.json` de l'étape 7 devient lisible par un programme ; et les 40 phrases françaises des branches à venir ne se figent pas dans le moteur. Rétro-ajouter ces codes après trois branches coûte une soirée de plus.

**3. `DECLARED_FIELDS`, une table Python — pas un JSON Schema.** Le plan d'origine propose un `CIRCUMSTANCE_SCHEMA` au format JSON Schema. C'est une erreur de forme : ce schéma ne serait jamais passé à Ollama (c'est tout son intérêt), donc aucun décodeur ne le consomme, et sa seule fonction serait décorative — en invitant quelqu'un, un jour, à le passer au modèle « par symétrie ». Écrire à la place :

```
DECLARED_FIELDS = {
    "cancellation_notice_days": int,
    "rerouting_offered": bool,
    ...
}
```

plus un `validate_declared(payload) -> dict` qui contrôle type et bornes. Cette table sert trois consommateurs réels : `merge_incident_statement`, la liste blanche de `/api/refine` (étape 4), et le formulaire de l'interface.

**Ne pas scinder le dict `extracted` en deux dicts à l'exécution** : toutes les fonctions du moteur lisent `extracted.get(...)`, et deux dicts imposeraient de changer chaque signature pour un gain nul. La propriété recherchée — le modèle de vision ne peut pas remplir un champ à effet juridique — est déjà garantie par le seul fait que `FLIGHT_SCHEMA` ne contient pas ces champs. Un dict plat à l'exécution, deux tables de déclaration qui disent qui a le droit d'écrire quoi.

**4. `field_sources: dict[str, str]`** écrit à trois endroits seulement : `extract_flight` → `"document"`, `merge_incident_statement` → `"declaration"`, `/api/refine` → `"correction"`. ~10 lignes, et c'est ce qui rendra visible dans l'interface la distinction que le pied de page revendique déjà.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Le vrai risque est de le sauter. Le second est de transformer `_scope` en objet de configuration : il renvoie un tuple ou un dict d'erreur, rien de plus.

### 2. Branche annulation : art. 5(1)(c), art. 7, réduction de 50 % de l'art. 7(2)

*Effort :* semaines · *Prérequis :* Étape 1 entièrement livrée (`_scope`, codes, `DECLARED_FIELDS`). Livrer dans le même lot que l'étape 3 : la lettre change de toute façon, et `claimable_amounts` doit naître avec la réduction de l'art. 7(2).

**Le cas le plus fréquent, aujourd'hui non chiffré.**

**Champs.** `FLIGHT_SCHEMA` ne gagne que `cancellation_notice_date` (string|null, lisible sur un mail d'annulation) et la valeur `cancellation_notice` dans l'enum `document_type`. Dans `DECLARED_FIELDS` : `cancellation_notice_days` (int), `rerouting_offered` (bool), `rerouting_arrival_time` (str), `rerouting_arrival_delay_minutes` (int). `trip_completed` existe déjà et porte la distinction remboursement / réacheminement accepté.

**Précédence déterministe, calquée sur `_derive_arrival_delay` (`agent.py:1188`) :** si `cancellation_notice_date` et `departure_date` sont présents, Python soustrait ; si le déclaré diverge de plus d'un jour, on garde le déclaré et on trace `divergent`. Le modèle ne fait jamais la soustraction. Réutiliser la forme de trace existante (`step` / `state` / `outcome` / `details`), pas en inventer une.

**Table de décision de `qualify_cancellation` :**

1. Pas de seuil de retard. Un vol annulé notifié 3 jours avant, sans réacheminement, ouvre le montant plein.
2. Préavis ≥ 14 j → `non_eligible`, code `art5_1c_i_notice_14_days`, montant 0. **Ne pas laisser cette branche écraser `assess_ticket_reimbursement`** : le droit de l'art. 8 reste dû.
3. Préavis 7–13 j → exonération seulement si réacheminement offert **et** arrivée à destination finale < 4 h après l'horaire initial. La condition « départ au plus 2 h avant l'horaire initial » n'est pas mesurée : si elle est inconnue, on n'applique pas l'exonération. L'art. 5(4) met la charge de la preuve du préavis sur le transporteur. Ce choix supprime deux champs d'horaires et va dans le sens conservateur.
4. Préavis < 7 j → exonération seulement si réacheminement et arrivée < 2 h après l'horaire initial.
5. **Préavis inconnu → ne pas basculer en `needs_information`.** Indemnisation retenue, note citant l'art. 5(4), question ajoutée. Bloquer un dossier valide sur une information que le transporteur détient serait l'erreur inverse.
6. Sinon montant = `compensation_amount(distance, intra_eu)`, puis art. 7(2) : si le réacheminement a été accepté et que `rerouting_arrival_delay_minutes` ≤ seuil, montant divisé par 2 (125 / 200 / 300). Seuils : 120 min ≤ 1500 km ; 180 min pour intra-UE > 1500 km et 1500–3500 km ; 240 min au-delà. Écrire `_article_7_2_threshold(distance, intra_eu)` avec **les mêmes bornes** que `compensation_amount` (`eu261.py:255`), et un test qui échoue si les deux divergent.
7. `classify_cause` s'applique comme au retard (art. 5(3)) : `high` → `conditional`, jamais un refus.

**Parseur.** `merge_incident_statement` apprend « prévenu la veille / le matin même / 3 jours avant / 3 semaines avant », « ils m'ont proposé un autre vol », « j'ai refusé le réacheminement », « j'ai été remboursé », « je suis parti le lendemain ». Chaque marqueur passe par `_find_unnegated` (`agent.py:566`) et arrive avec ses cas dans `eval/incident_cases.json` — c'est ce corpus qui avait révélé que `classify_cause` était inopérant.

**À corriger dans le même lot :** `eu261.py:446`, `not_assessed` pour `denied_boarding` alors que l'art. 4(3) renvoie à l'art. 8.

**Coût réel, sous-estimé par le plan d'origine.** Ce n'est pas seulement une fonction : `cancellation_notice_date` traverse `FLIGHT_SCHEMA` (+ `required`), le prompt d'extraction, `route_case`, `draft_claim`, le panneau de faits de `static/index.html:481`, `CLAIM_SYSTEM` (dont l'instruction `not_covered` devient partiellement morte), et ~14 tests existants qui construisent des extractions à la main. ~25 tests neufs, ~15 cas de corpus, `docs/EVALUATION.md` verrouillé par `test_documented_test_count_is_accurate`. À quelques heures par semaine, c'est un chantier de plusieurs semaines, pas de trois soirées.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/incident_cases.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/EVALUATION.md`

*Risque :* Bloquer en `needs_information` dès qu'un champ manque : la charge de la preuve du préavis pèse sur le transporteur. Dupliquer les bornes de tranche entre `compensation_amount` et le seuil de l'art. 7(2). Et sous-estimer le coût de plomberie du nouveau champ de schéma, qui dépasse largement le coût de la table de décision.

### 3. Garde-fous de sortie : le moteur écrit ce qu'il sait, et la lettre part dans la langue du transporteur

*Effort :* quelques soirees · *Prérequis :* Même lot que l'étape 2. Doit précéder l'étape 7 : exporter des fichiers sans mention d'assistance automatisée serait le pire cas de figure.

**Principe qui tranche une classe entière de décisions :** tout ce que le moteur connaît déjà est **inséré** côté Python après la rédaction, pas demandé au modèle puis vérifié. On ne valide que ce qu'on ne peut pas écrire soi-même. C'est l'étape la moins chère et la plus structurante du lot — et le dépôt affirme déjà l'avoir faite.

**1. `_finalize_letter(claim, qualification, ruleset)`**, appelé après `_validate_claim` (`agent.py:1148`), appose systématiquement : « préparé avec l'assistance d'un outil automatisé, relu et envoyé sous la responsabilité du signataire », la date de génération, le fondement retenu (article + montant), et `RULESET.verified_on` (`eu261.py:17`). Un test qui échoue si la lettre sort sans ce bloc. **Corriger `ROADMAP.md:428`, qui l'annonce comme fait depuis la semaine 8.** Et **ajouter une étape de trace `finalize_letter` distincte** : si la lettre est modifiée après `validate_claim`, une trace qui s'arrête à `outcome: ok` ment sur le contenu final.

**2. Mention conditionnelle insérée, pas espérée.** `CLAIM_SYSTEM` (`agent.py:192-195`) demande au modèle d'écrire la nuance quand `cause_risk == high`, et rien ne vérifie qu'il l'a fait. Même chose pour l'instruction `not_covered` (`agent.py:196-198`) : c'est aujourd'hui la seule mention de l'indemnisation non chiffrée sur une annulation, et elle repose entièrement sur l'obéissance du modèle. Insérer ces phrases depuis `qualification` coûte zéro et supprime la dépendance.

**3. `claimable_amounts: list[int]` renvoyé par la qualification.** `_validate_claim` (`agent.py:1119-1121`) reconstruit aujourd'hui les montants autorisés à partir de deux champs. Avec la réduction de l'art. 7(2), les frais de l'art. 9 et le multi-passagers, cette reconstruction sera fausse et signalera des montants légitimes. Inverser : le moteur publie la liste, `_validate_claim` s'y adosse. La règle ne s'assouplit pas, elle devient exacte.

**4. Borner le texte libre du voyageur.** `disruption_cause` (`agent.py:1029-1034`, via `facts_for_claim`) et bientôt `denied_boarding_reason` sont recopiés dans le prompt. Plafonner la longueur, retirer les caractères de contrôle, écraser les retours à la ligne, et délimiter un bloc « déclarations non vérifiées » dans le prompt. **Ne pas écrire de détecteur de consignes par expression régulière** : sur du français libre il produira des faux positifs (« il faut que vous compreniez que… ») et donnera une confiance imméritée. Le filet reste structurel — montants recalculés, URL en liste blanche — et le commentaire doit le dire sans prétendre plus.

**5. La langue de la lettre suit le transporteur, pas l'interface.** Un courrier en anglais à Ryanair ou TAP passe mieux qu'un courrier en français. Ajouter `correspondence_language` à `knowledge/carriers.json` (qui porte déjà `verified_on`, `aliases`, `domains`) et passer une consigne de langue à `CLAIM_SYSTEM`, plus un `<select>` pour forcer le choix. **Attention au coût caché** : le bloc de pied de lettre du point 1 doit alors exister dans les deux langues, donc ce sont des données bilingues, pas dix lignes. Compter une soirée, pas dix minutes — la valeur reste très élevée.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/carriers.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/ROADMAP.md`

*Risque :* Aucun sur le plan technique. Le seul risque est de le repousser parce que la valeur utilisateur est indirecte — alors que le dépôt affirme déjà l'avoir livré.

### 4. Répondre aux questions et corriger les faits sans relancer l'extraction

*Effort :* semaines · *Prérequis :* Étapes 1 et 2, pour connaître la liste finale des champs à exposer. Ne pas livrer l'étape 2 seule : une branche annulation qui pose trois questions sans moyen d'y répondre est une régression d'usage.

**Sans ça, les nouvelles branches rendent l'outil moins utilisable :** elles posent plus de questions, et il n'existe aucun moyen d'y répondre autrement qu'en re-téléversant le billet.

**Scinder `process`** (`agent.py:1254`) en `process_document(document, incident_text)` (extraction multimodale, renvoie les faits) et `process_facts(extracted, research=None)` (déterministe + recherche + rédaction). `process` devient la composition ; signature publique et CLI inchangés. À comportement strictement constant, suite verte avant toute nouveauté.

**`POST /api/refine`** dans `app.py` : reçoit `{session_id, answers}`, ne relit aucun document.

**Le point que le plan d'origine rate.** Il annonce « < 20 s au lieu de 40 s » : impossible avec ses propres chiffres (42,7 s − 10,7 s = 32 s). Passer sous 20 s exige de **ne pas rejouer la sélection d'outils (9,4 s) ni SerpApi** quand les faits de recherche n'ont pas bougé. Deux façons, une seule acceptable :

- *Refusée* : le client renvoie le bloc `research`. Il alimenterait `_allowed_claim_urls` (`agent.py:1071-1092`) et pourrait donc faire citer n'importe quelle URL dans la lettre — c'est-à-dire détruire la propriété de sortie la plus forte du projet, celle qui empêche de désigner un intermédiaire à 30 % comme canal officiel.
- *Retenue* : un cache **en mémoire** dans `app.py`, `dict[session_id] -> (extraction, research)`, borné à quelques entrées, jamais écrit sur disque, vidé à l'arrêt du processus. ~15 lignes de stdlib, aucune PII persistée, et le client ne fournit jamais d'URL. Sur `refine`, recomparer `build_research_context(extraction)` avant/après : identique → recherche réutilisée (~20 s de rédaction seule) ; différent → recherche rejouée. C'est le même geste que `_validate_tool_call` — comparaison à l'octet près, pas confiance.

**Garde-fou d'entrée.** Filtrer `answers` sur `DECLARED_FIELDS` + les propriétés de `FLIGHT_SCHEMA`, contrôler le type, borner les longueurs, rejeter le reste. **Justification correcte** : ce n'est pas SerpApi qui est exposé — `build_research_context` (`tools.py:183-212`) tronque déjà à 80/100 caractères et contrôle `disruption_type` contre un enum. Ce qui est exposé, c'est le prompt de `draft_claim` et le contenu de la lettre que le passager enverra en son nom. ~25 lignes, deux tests.

**Interface, trois changements :**

1. Les questions deviennent structurées : chaque question porte un `code` (étape 1), un `field` et un `type` (`boolean` / `integer` / `date` / `text`) en plus du libellé. Cela touche `qualify_*`, `assess_ticket_reimbursement`, `route_case` (`agent.py:731`), `_pending_questions` (`agent.py:1151`) et le rendu `static/index.html:504-509` : c'est transverse, pas local.
2. Le panneau « Faits extraits » devient éditable, avec « Corriger et relancer ». Les 11 libellés en dur deviennent une table pilotée par les schémas. Le champ `#reference` dédié disparaît au profit du cas général.
3. **Accessibilité dans le même passage, pas en étape séparée** (sinon elle ne se fait jamais) : `aria-busy` pendant l'analyse, focus déplacé sur le résultat, erreurs associées aux champs. Noter que `aria-live="polite"` existe déjà sur `#result` (`static/index.html:165`), contrairement à ce qu'affirmait le plan initial.

**Effort.** Scission du point le plus testé du dépôt + cache + endpoint + liste blanche + questions structurées transverses + formulaire de faits en JS vanilla + provenance. Plusieurs semaines à quelques heures par semaine.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/app.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/static/index.html`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Accepter un bloc `research` fourni par le client : c'est la seule façon de casser la liste blanche d'URL, et elle est tentante parce qu'elle évite le cache. Second risque : la scission de `process` touche le code le plus testé du dépôt.

### 5. Branche refus d'embarquement : art. 4, exclusion de l'art. 2(j), condition de l'art. 3(2)

*Effort :* quelques soirees · *Prérequis :* Étapes 1, 2 et 3 : `_scope`, `_article_7_2_threshold`, questions non bloquantes et `claimable_amounts` existent déjà. La branche se réduit alors à une table de décision et un classifieur.

**Le droit le plus solide du règlement, aujourd'hui le plus mal traité :** `qualify_case` renvoie `not_covered` et `eu261.py:446` renvoie `not_assessed` pour le remboursement, donc `reimbursement_actionable` est faux et **aucune lettre n'est produite du tout**.

**Champs déclarés :** `denied_boarding_voluntary` (bool), `denied_boarding_reason` (str), `checked_in_on_time` (bool). `rerouting_arrival_delay_minutes` de l'étape 2 est réutilisé tel quel.

**Classifieur `classify_denied_boarding_ground(reason)`**, même patron que `CAUSE_PATTERNS`, du plus spécifique au plus générique, renvoyant `carrier_overbooking` / `reasonable_grounds` / `unknown`. Motifs `reasonable_grounds` (art. 2(j)) : documents de voyage, passeport, visa, ESTA, pièce d'identité, santé, sûreté, sécurité, comportement, ébriété, animal non conforme. Motifs `carrier_overbooking` : surbooking, surréservation, overbooking, vol complet, changement d'appareil, appareil plus petit.

**Correction au plan d'origine :** `CAUSE_PATTERNS` (`eu261.py:284-291`) contient **déjà** `surbooking`, `surreservation`, `overbooking`. Deux classifieurs qui lisent le même texte libre avec deux vocabulaires partiellement recouvrants divergeront exactement comme les bornes de tranche. Extraire ces trois motifs dans un tuple `OVERBOOKING_MARKERS` unique, consommé par les deux, et faire retomber `denied_boarding_reason` sur `disruption_cause` quand il est absent — le parseur remplit déjà ce dernier depuis `CAUSE_MARKERS` (`agent.py:530-541`).

**Table de décision de `qualify_denied_boarding` :**

1. `denied_boarding_voluntary` vrai → `non_eligible` pour l'art. 7, avec une explication qui dit ce que le passager **conserve** : le choix de l'art. 8 et le bénéfice négocié. Pas un simple zéro.
2. Motif = `reasonable_grounds` → `non_eligible`, code `art2j_reasonable_grounds`, en nommant le motif retenu.
3. `checked_in_on_time` faux → `non_eligible`, code `art3_2_late_check_in`. Inconnu → ne bloque pas : le relevé d'enregistrement est détenu par le transporteur. Indemnisation retenue + question + note.
4. Sinon montant plein, réduit de 50 % par le même `_article_7_2_threshold` si un réacheminement suffisamment rapide a été accepté.

**Le point à commenter dans le code :** `qualify_denied_boarding` **ne lit pas `cause_risk`**. Les circonstances extraordinaires de l'art. 5(3) exonèrent l'annulation et, par *Sturgeon*, le retard — pas le refus d'embarquement, dont l'art. 4(3) est inconditionnel (CJUE *Finnair*, C-22/11 : un refus consécutif à une réorganisation après grève reste indemnisable). Un moteur qui appliquerait `cause_risk` partout par symétrie détruirait la propriété.

**Cas de test à ne pas oublier :** `tap_air_portugal.json` ne déclare pas `denied_boarding` dans ses `supported_incidents`. `retrieve_airline_policy` renverra `incident_specific: false` et servira la fiche entière. Comportement correct, à figer par un test plutôt qu'à découvrir en démonstration.

~18 tests, ~8 cas de corpus.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/incident_cases.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Appliquer `cause_risk` par symétrie et transformer le droit le plus solide en `conditional`. Second risque : `unknown` traité comme `reasonable_grounds`, qui rejetterait un dossier valide sur un mot mal choisi.

### 6. Correspondance manquée : un retard mesuré à la destination finale

*Effort :* quelques soirees · *Prérequis :* Étapes 1, 2 et 4. La destination finale doit exister dans `AIRPORTS` : sinon `resolve_airport` renvoie déjà un `needs_information` correct, comportement à conserver plutôt qu'à contourner.

**Le dernier `not_covered` se ferme pour peu de lignes — à condition de neutraliser un piège que le plan d'origine n'a pas vu.**

**Champs :** `final_destination` (string|null, extractible d'un billet à segments, donc dans `FLIGHT_SCHEMA`), `single_booking` (bool, déclaré, donc dans `DECLARED_FIELDS`).

**Fondement.** CJUE *Folkerts*, C-11/11 : l'indemnisation est due dès que le passager atteint sa destination finale avec 3 h de retard ou plus, même si le vol initial est parti à l'heure. Deux conditions : réservation unique et premier départ dans le champ géographique.

**Mise en œuvre :** `qualify_case` route `missed_connection` vers `qualify_delay` en substituant `destination := final_destination`.

**Le piège, absent du plan d'origine et bloquant.** `_derive_arrival_delay` (`agent.py:1188`) calcule `arrival_delay_minutes` depuis `scheduled_arrival` / `actual_arrival`, qui sur une carte d'embarquement sont ceux du **premier segment**. Router vers `qualify_delay` sans neutraliser ce calcul qualifie un retard de segment 1 — souvent faible — à la distance de la destination finale : montant faux, silencieusement, dans les deux sens. C'est exactement le défaut que ce plan dénonce en ouverture, réintroduit. **Correctif obligatoire :** quand `disruption_type == "missed_connection"` et que `destination != final_destination`, `_derive_arrival_delay` n'écrit rien et pose la question du retard à l'arrivée finale. Un test dédié, nommé, commenté.

**La propriété gratuite qu'il ne faut pas casser :** la distance qui détermine la tranche est l'orthodromie du premier départ à la destination finale, pas la somme des segments (art. 7(1) *in fine*, CJUE *Bossen*, C-559/16). Comme `compute_distance` (`eu261.py:229`) prend deux codes IATA, c'est acquis — à condition de lui passer la bonne destination. À commenter et à tester, sinon quelqu'un « corrigera » un jour en additionnant les segments et fera passer un dossier de 400 à 600 €.

**Réservations séparées :** `single_booking` faux → `non_eligible` motivé. Inconnu → question **bloquante**, contrairement au préavis d'annulation : c'est une information que le passager détient et que le transporteur ne peut pas suppléer.

Une fois livré : `docs/EVALUATION.md:116` passe à « 4 sur 4 » et `UNCOVERED_CASES` est repointé sur les trous restants (art. 10(2), art. 8(3)) — jamais vidé.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/incident_cases.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/EVALUATION.md`

*Risque :* Le calcul de retard sur le premier segment (voir ci-dessus) : c'est le seul vrai risque, et il produit un montant faux sans aucun signal. Second risque : traiter la correspondance manquée comme une branche autonome et dupliquer les seuils.

### 7. Ce qui se passe après la lettre : export, échéance, relance

*Effort :* quelques soirees · *Prérequis :* Étape 3 impérativement : distribuer des fichiers sans mention d'assistance automatisée serait le pire cas de figure de tout le lot.

**La réponse honnête sans backend : le dossier sort de la machine sous forme de fichiers que le passager possède, et son système de fichiers fait office de suivi.**

**Export, côté navigateur uniquement** (`Blob` + lien `download`, rien n'est écrit côté serveur) :

- `lettre.txt` — objet, corps, pied de lettre de l'étape 3
- `dossier.json` — résultat complet, trace comprise, **réimportable**. Un bouton « Reprendre un dossier » qui l'accepte permet de réafficher et de relancer sans Ollama et sans le billet. C'est ce qui remplace un historique persistant.
- « Copier la lettre » — trois lignes, la fonction la plus utilisée de toutes
- `@media print` sur la section résultat : le PDF réel, c'est l'impression du navigateur. ~25 lignes de CSS contre 400 à 600 pour un générateur PDF en stdlib.

**Échéance et relance, sans modèle :**

- `suivi.md` : date de génération, incident, montant et fondement, cases à cocher (envoyée le ____, accusé le ____, réponse le ____), et « relancer à partir du JJ/MM » calculé **depuis la date d'envoi déclarée**, pas depuis la génération.
- `relance.txt` par gabarit à trous, rempli des faits connus. Zéro latence, zéro hallucination.
- **Correction au plan d'origine :** générer ces deux fichiers **en Python**, renvoyés comme chaînes dans la réponse JSON, et seulement écrits sur disque par le navigateur. « Généré par gabarit » + « export côté navigateur » se lit trop facilement comme « écrire les gabarits en JavaScript », ce qui mettrait du texte juridique non testé dans la couche interface. Les gabarits vivent à côté du moteur, avec des tests ; le fichier ne transite jamais par le disque du serveur.
- **Le délai de 6 semaines doit être sourcé, pas codé en dur.** Il vient de la pratique de saisine des organismes nationaux, pas du règlement, qui ne fixe aucun délai de réponse. Le mettre dans les données avec son `verified_on`, au même titre que le reste.
- Étape suivante en cas de silence : l'organisme national de contrôle du pays de départ, dans `knowledge/enforcement_bodies.json`, avec un `verified_on` par entrée et la mécanique de fraîcheur de `_policy_freshness` (`tools.py:432`) — périmé = non servi. Commencer par 4 ou 5 pays réellement vérifiés (FR, ES, PT, DE, IT), « non renseigné » ailleurs.

**Attention au type d'effort.** Le code est une soirée ; **vérifier cinq organismes nationaux un par un est du temps de recherche, pas du temps de code**, et c'est là que l'étape déborde. Une ligne fausse ici envoie quelqu'un écrire à la mauvaise administration.

**Ce qu'on ne promet pas, et qu'il faut écrire dans l'interface :** l'outil n'envoie rien, n'accuse réception de rien, ne surveille rien. Il prépare et il date.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/static/index.html`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/enforcement_bodies.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/tools.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* La table des organismes vieillit et personne ne la revérifie — la mécanique de fraîcheur est la seule réponse acceptable. Second risque : les fichiers exportés contiennent nom, référence et trajet ; l'export doit rester intégralement côté navigateur, jamais un fichier écrit par `app.py`.

### 8. [AJOUT] Mesurer et sécuriser la lecture des vrais billets

*Effort :* quelques soirees · *Prérequis :* Aucun pour le harnais : il peut se faire en parallèle des branches et il n'y touche pas. Le parseur BCBP gagne à venir après l'étape 1 (`field_sources`).

**L'objectif dit « lire les billets des gens ». Aucune des neuf étapes du plan d'origine ne s'en occupe, et `docs/EVALUATION.md:125` reconnaît qu'aucune exactitude par champ n'est mesurée.** Les 106 tests et les 31 cas de corpus couvrent le déterministe ; la couche vision, celle qui alimente tout le reste, n'est couverte par rien. Ajouter cinq branches juridiques en aval d'une couche dont on ignore le taux d'erreur, c'est améliorer la précision d'un calcul sur des entrées non mesurées.

**1. Un jeu de billets et un harnais, hors CI.** `eval/tickets/` : une dizaine de justificatifs variés (carte d'embarquement papier photographiée, PDF de compagnie, capture d'écran d'application, billet en anglais, billet à deux segments, mail d'annulation), **anonymisés ou fabriqués**, avec pour chacun un `expected.json` des champs vérifiables à l'œil. `scripts/extract_bench.py` appelle `extract_flight` et imprime l'exactitude par champ plus la liste des hallucinations (champ rempli alors que le document ne le montre pas). Il n'entre pas en CI — il exige Ollama — mais il produit un tableau versionnable, exactement comme `eval/corpus.py` le fait pour la déclaration. Sans lui, `docs/EVALUATION.md` restera indéfiniment à « prochain chantier », et la phrase « ne pas changer de modèle avant d'avoir un harnais » restera une interdiction sans issue.

**2. Le chemin déterministe qui court-circuite le modèle : le code-barres BCBP.** Toute carte d'embarquement conforme à la résolution IATA 792 encode une chaîne à champs de position fixe qui contient nom du passager, PNR, code IATA de départ et d'arrivée, transporteur, numéro de vol, date julienne, siège. **Un parseur de cette chaîne fait environ 80 lignes de stdlib, ne se trompe jamais, et donne exactement les champs qui pilotent la qualification.** Ajouter un champ « collez ici le contenu du code-barres si votre carte est numérique » et, quand il est présent, écrire ces champs avec `field_sources = "barcode"` — le modèle de vision ne peut plus les écraser. C'est le geste le plus juste de tout le lot pour l'identité du projet : là où il existe une source structurée, on ne demande rien à un modèle.

**Ce qu'il ne faut pas tenter :** décoder l'image du code-barres (Aztec / PDF417) en stdlib. C'est un chantier de plusieurs centaines de lignes de correction d'erreurs Reed-Solomon, ou une dépendance. Le champ de saisie couvre le cas réel — les cartes d'embarquement numériques exposent la chaîne, et beaucoup de PDF la portent en texte.

**3. Ce que le harnais va révéler et qu'il faudra accepter :** sur un billet à deux segments, `origin` / `destination` sont ambigus ; sur une photo froissée, la référence de réservation est fausse une fois sur deux — ce que le dépôt anticipe déjà avec `booking_reference_requires_confirmation` (`agent.py:511-514`). Le formulaire de correction de l'étape 4 est la réponse ; le harnais dit sur quels champs il faut la rendre visible en priorité.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eval/tickets/`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/scripts/extract_bench.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/docs/EVALUATION.md`

*Risque :* Constituer le jeu de billets avec de vrais documents non anonymisés et les committer. Chaque fichier doit être fabriqué ou caviardé, et le dire dans le README du dossier. Second risque : viser vingt billets et n'en produire aucun — dix suffisent pour que le tableau cesse d'être vide.

### 9. [AJOUT] Corpus local des articles cités, pour que le mode dégradé produise encore une lettre solide

*Effort :* soiree · *Prérequis :* Étapes 1 (les `code` servent de clés) et 3 (`_finalize_letter` est le seul endroit qui insère la citation).

**Aujourd'hui, quand SerpApi est indisponible, `verify_air_passenger_rule` renvoie `offline` et la lettre ne peut plus citer que deux URL constantes (`OFFICIAL_RIGHTS_URL`, `REGULATION_URL`, `tools.py:18-26`).** Le mode dégradé est honnête mais pauvre. Or les branches des étapes 2, 5 et 6 vont produire des lettres fondées sur des articles précis — art. 5(1)(c), 7(1), 7(2), 4(3), 8, 9 — dont le texte n'existe nulle part dans le dépôt.

**`knowledge/regulation_261.json` :** le texte verbatim d'une dizaine d'alinéas, avec pour chacun `article`, `langue`, `texte`, `url` et `verified_on`, exactement au format des fiches compagnies. `_finalize_letter` (étape 3) y puise la citation qui correspond au `code` de la décision (étape 1) et l'insère **côté Python**, jamais via le modèle.

**Pourquoi c'est plus qu'un enjolivement :**

- Une lettre qui cite l'alinéa applicable mot pour mot est payée plus souvent qu'une lettre qui dit « selon le règlement européen ». C'est de la valeur utilisateur directe.
- Cela rend le mode hors ligne **complet** au lieu de dégradé : le fondement, le montant, le texte de l'article et la procédure locale viennent tous du disque. Seule la vérification en ligne manque, et elle est déjà tracée comme telle.
- C'est la brique de récupération dont un RAG a besoin, sans en être un : dix alinéas se sélectionnent par `code`, pas par similarité vectorielle. Sortir un index d'embeddings pour dix paragraphes serait du cargo-cult ; une table indexée par code d'article est la bonne réponse à cette taille.
- Le mécanisme de fraîcheur s'applique tel quel : `_policy_freshness` est déjà écrit et générique.

**Coût.** Le code est trivial (lecture JSON + sélection par code). Le travail est de **recopier fidèlement une dizaine d'alinéas depuis la source officielle et de noter la date de vérification**. Une soirée, dont l'essentiel est de la recopie soigneuse — et une erreur de recopie ici est une citation fausse dans un courrier juridique, donc à relire deux fois.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/knowledge/regulation_261.json`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/tools.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Recopier de mémoire ou reformuler : une citation approximative dans un courrier juridique est pire que pas de citation. Chaque entrée porte son URL et sa date. Second risque : laisser le modèle citer les articles depuis ses poids plutôt que depuis le fichier — la citation est insérée par Python, pas demandée.

### 10. Réclamation multi-passagers

*Effort :* soiree · *Prérequis :* Étapes 3 (`claimable_amounts`) et 4 (le formulaire, seul endroit où ces champs sont saisis).

**Le plus gros écart de montant du dépôt.** L'indemnisation de l'art. 7 est due par passager : une famille de quatre sur un Paris–New York annulé, c'est 2 400 €, et la lettre en demanderait 600.

- `passenger_count` (int, défaut 1) et `passenger_names` (liste bornée à ~9, comme les tableaux de `CLAIM_SCHEMA`).
- **Correction au plan d'origine : ces deux champs ne vont pas dans `FLIGHT_SCHEMA`.** Le plan interdit lui-même de gonfler le schéma d'extraction, puis y ajoute un tableau de noms — c'est-à-dire le champ le plus propice à l'hallucination qui soit : une carte d'embarquement ne montre qu'un passager, et lire N noms sur une photo de confirmation est exactement le cas que le décodage contraint remplit au jugé. Les deux champs vont dans `DECLARED_FIELDS`, saisis dans le formulaire de l'étape 4. Défaut à 1 quand le champ est absent : jamais de multiplication par une valeur devinée.
- Le moteur garde le montant **unitaire** dans `compensation_eur` — c'est lui qui se rattache à la tranche de distance et qui doit rester recoupable — et ajoute `total_compensation_eur`. `claimable_amounts` contient les deux, sinon `_validate_claim` signalera le total légitime.
- La lettre liste les passagers et écrit « X € par passager, soit Y € pour N passagers ». Beaucoup de transporteurs ne versent que pour le signataire quand la lettre est au singulier.
- **Point juridique que le plan omet :** une réclamation collective signée par une seule personne se heurte souvent à un refus procédural. Le pied de lettre de l'étape 3 doit indiquer que le signataire agit avec l'accord des autres passagers nommés, et la checklist rappeler qu'une pièce d'identité ou un mandat peut être exigé pour chacun. Sans cette phrase, l'outil produit des lettres rejetées sur la forme et le passager conclut que le montant était faux.

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Laisser le modèle lire un nombre de passagers sur un billet ambigu et multiplier un montant. Le garde-fou est structurel : le champ n'est pas dans le schéma d'extraction, Python multiplie, le modèle recopie, `_validate_claim` recoupe.

### 11. Art. 9 : prise en charge et frais engagés

*Effort :* quelques soirees · *Prérequis :* Étapes 2, 3, 4 et 5. La prise en charge se greffe sur les trois branches ; l'écrire avant qu'elles existent obligerait à y revenir trois fois.

**Le droit le plus systématiquement oublié, et souvent le second montant du dossier** — un hôtel et deux repas après une annulation du soir, c'est 150 à 250 € qui s'ajoutent aux 400 € de l'art. 7.

Ce n'est pas un forfait mais un remboursement sur justificatifs : le moteur ne le chiffre pas, il **dit qu'il est dû** et le fait figurer dans la lettre et la checklist.

- `care_entitlement(distance_km, intra_eu, departure_delay_minutes, overnight)` renvoyant les prestations dues. Seuils de l'art. 6(1) : 2 h ≤ 1500 km ; 3 h pour intra-UE > 1500 km et 1500–3500 km ; 4 h au-delà. Plus hébergement et transferts dès qu'une nuit devient nécessaire.
- **Nuance à respecter :** ces seuils s'apprécient sur le retard **au départ**. `departure_delay_minutes` existe dans le pipeline mais est souvent nul. Absent, ne pas extrapoler depuis le retard à l'arrivée : indiquer que la prise en charge est en principe due et que le seuil s'apprécie au départ. Même patron que partout ailleurs : on ne devine pas, on dit.
- La prise en charge est due **quelle que soit la cause**, y compris en circonstances extraordinaires. C'est le contrepoint utile à un dossier `conditional` : même si le transporteur s'exonère de l'indemnisation, il doit l'hôtel.
- **Correction au plan d'origine :** il affirme « la somme est faite en Python » tout en ne définissant qu'un scalaire `care_expenses_eur`. Il n'y aurait rien à sommer, et `_validate_claim` accepterait un total saisi par le passager comme s'il venait du moteur. Définir à la place `care_expenses` : une liste bornée à ~10 entrées `{libelle, montant_eur}`, saisies dans le formulaire de l'étape 4 ; Python additionne, le total entre dans `claimable_amounts`, et la lettre écrit « frais engagés déclarés par le passager, sur justificatifs : X € » — le libellé doit dire que ce montant est déclaré, pas calculé, sinon la propriété « tout montant vient du moteur » devient un slogan.
- Applicable aux trois branches : retard (art. 6), annulation (art. 5(1)(b)), refus d'embarquement (art. 4(3)).

*Fichiers :* `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/eu261.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/agent.py`, `/Users/arnaud/Project/Hackathons/Gemma4-hackathon/test_agent.py`

*Risque :* Calculer les seuils de prise en charge sur le retard à l'arrivée parce que c'est la donnée disponible : c'est faux, et du côté qui sur-réclame. Second risque : faire passer un total déclaré par le passager pour un montant calculé par le moteur.

## À ne pas faire

- **Un `CIRCUMSTANCE_SCHEMA` au format JSON Schema.** Ce schéma ne serait jamais passé à Ollama — c'est tout son intérêt — donc aucun décodeur ne le consomme et sa seule fonction est décorative. Pire : sa forme invite à le passer un jour au modèle « par symétrie » avec `FLIGHT_SCHEMA`, ce qui détruirait exactement la propriété qu'il prétend établir. Une table `DECLARED_FIELDS: dict[str, type]` plus un validateur rendent le même service, en dix fois moins de lignes, et se branchent directement sur la liste blanche de `/api/refine` et sur le formulaire.

- **Scinder le dict `extracted` en deux dicts à l'exécution.** Toutes les fonctions du moteur lisent `extracted.get(...)` ; deux dicts imposeraient de changer chaque signature pour un gain nul. Le modèle de vision ne peut pas remplir un champ absent de `FLIGHT_SCHEMA` : la propriété est déjà acquise par la structure du schéma d'extraction, pas par la séparation des conteneurs. Un dict plat, deux tables de déclaration.

- **Accepter un bloc `research` fourni par le client dans `/api/refine`.** Il alimente `_allowed_claim_urls` (`agent.py:1071-1092`) : un client pourrait faire citer n'importe quelle URL dans la lettre qu'un passager envoie en son nom, c'est-à-dire annuler le seul garde-fou qui empêche de désigner un intermédiaire à 30 % comme canal officiel. Le cache en mémoire côté `app.py` coûte quinze lignes et ne crée aucune surface.

- **Un détecteur de consignes injectées par expression régulière** sur `disruption_cause`. Sur du français libre il produira des faux positifs (« il faut que vous compreniez que… »), rejettera des déclarations légitimes, et donnera une confiance imméritée. Ce qui protège réellement est structurel : montants recalculés, URL en liste blanche, arguments d'outils recalculés à l'octet près. Plafonner la longueur, retirer les caractères de contrôle, délimiter le bloc, et l'écrire comme ça dans le commentaire — sans prétendre plus.

- **Un générateur de PDF en stdlib.** Largeurs de glyphes, pagination, table xref : 400 à 600 lignes. L'impression navigateur avec une feuille `@media print` donne un vrai PDF pour 25 lignes de CSS. Déjà tranché dans `ROADMAP.md`.

- **Décoder l'image du code-barres d'une carte d'embarquement.** Aztec et PDF417 demandent une correction d'erreurs Reed-Solomon : plusieurs centaines de lignes, ou une dépendance. Le champ de saisie où l'on colle la chaîne BCBP couvre le cas réel — les cartes numériques l'exposent — pour 80 lignes de parseur à champs fixes.

- **Envoyer la lettre.** SMTP, e-recommandé, LRAR, API postale : identifiants, prestataire, argent, et une responsabilité sur un envoi qui échoue silencieusement. L'outil prépare et date ; le passager envoie. Écrire cette phrase dans l'interface plutôt que d'y suppléer.

- **Un historique persistant dans l'application.** `localStorage` mettrait nom, référence et trajet dans le profil du navigateur — l'inverse exact de l'argument de confidentialité, pour une commodité. Le `dossier.json` exporté est réimportable et le système de fichiers du passager fait office d'historique. En vitrine, ce choix se défend mieux qu'un historique navigateur.

- **Un suivi avec relances automatiques et notifications.** Cela suppose un service qui tourne, donc un backend ou un démon, donc l'abandon du local-first. Le substitut honnête — `suivi.md` daté avec cases à cocher et relance déjà rédigée — couvre le besoin réel à 90 %.

- **Une table de prescription à 27 pays.** Le délai varie de 1 à 10 ans selon le droit applicable et le for compétent. Dire à quelqu'un que son droit est vivant alors qu'il est prescrit est pire que le silence. Garder l'avertissement conservateur de `_implausible_date` (`agent.py:1163`).

- **La branche UK261.** Le Royaume-Uni est déjà traité honnêtement : `eu: False` sur LHR, LGW, STN, MAN, EDI (`eu261.py:72-76`), dossier `non_eligible` motivé. Ajouter UK261 double la surface juridique à maintenir pour un règlement qui n'est plus synchronisé avec l'UE.

- **Les articles 10(2) (déclassement) et 8(3) (aéroport de substitution).** Le déclassement se calcule en pourcentage du prix du billet, qui ne figure quasiment jamais sur une carte d'embarquement, et le cas est rare. Les laisser dans `UNCOVERED_CASES` : c'est ce mécanisme qui donne sa valeur au reste.

- **Traduire l'interface en anglais.** Le plan d'origine le proposait ; c'est le plus faible retour du lot pour un dépôt dont le README, le corpus, les messages du moteur et le public de démonstration sont français. Ce qui a un destinataire, c'est la lettre, et elle est traitée à l'étape 3 en suivant la langue du transporteur. Environ 60 chaînes d'interface à maintenir en double pour un bénéfice décoratif. Si un jour un README anglais existe, la question se reposera — et les `code` de l'étape 1 l'auront rendue possible sans toucher au moteur.

- **Laisser le modèle calculer quoi que ce soit de nouveau.** Jours de préavis, division par deux de l'art. 7(2), total multi-passagers, somme des frais engagés, retard à la destination finale : ce sont des opérations arithmétiques, donc Python. La tentation est réelle parce que ces calculs sont triviaux — c'est exactement la propriété que le dépôt revendique.

- **Gonfler `FLIGHT_SCHEMA`.** Un schéma de 36 propriétés toutes `required` alourdit le décodage contraint, allonge le prompt et invite le modèle à halluciner : aucune carte d'embarquement ne dit si vous vous êtes présenté à l'heure, ni combien de personnes voyageaient. Le schéma ne gagne que `cancellation_notice_date`, `final_destination` et une valeur d'enum.

- **Étendre au ferroviaire, au maritime ou aux bagages (Montréal).** Trois corpus juridiques supplémentaires, chacun avec ses seuils et ses organismes. Un paragraphe dans les Limites du README, pas du code.

- **Changer de modèle ou en ajouter un second pour améliorer l'extraction, avant que le harnais de l'étape 8 tourne.** Ce serait troquer une inconnue contre une autre et ajouter 20 s de latence pour un gain non observable. La différence avec le plan d'origine : le harnais est désormais une étape planifiée, pas une condition impossible à remplir.

- **Laisser `ROADMAP.md` annoncer des choses qui n'existent pas.** La ligne 428 déclare le pied de lettre serveur et son test livrés en semaine 8 ; ni l'un ni l'autre n'existent. Dans un projet dont l'argument central est de dire ce qu'il ne sait pas faire, une feuille de route qui surestime l'état est un défaut du même ordre que la sous-réclamation qu'elle décrit.

