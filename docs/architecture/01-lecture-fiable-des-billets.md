# Lecture fiable des billets réels (ingestion multimodale et extraction) — plan nettoyé après vérification adversariale du code et re-mesure sur cette machine

Fiche de conception issue de l'audit du 28 juillet 2026, après critique adversariale. Synthèse et ordre de construction dans [`../ARCHITECTURE_CIBLE.md`](../ARCHITECTURE_CIBLE.md).

## Diagnostic

VÉRIFICATION DU DIAGNOSTIC SOURCE. J'ai relu le code et rejoué les mesures avec gemma4:12b chargé.

CE QUI EST EXACT :
- `_image_bytes` (agent.py:297) envoie bien tout document en image ; le PDF passe par `_render_pdf_first_page` (agent.py:227, `-f 1 -singlefile -r 220`).
- `extract_flight` (agent.py:464) ne fixe PAS `num_ctx`, alors que `draft_claim` le monte à 8192 avec `num_predict: 2048` (agent.py:1051). Confirmé.
- Le format est décidé par l'extension seule : `ALLOWED_SUFFIXES` (app.py:21), test à app.py:102-103, `accept` à static/index.html:141.
- `resolve_airport` (eu261.py:132) lit bien `LIS` dans « LIONNONE LIS » et refuse d'arbitrer quand deux codes référencés coexistent. Le recalage est le bon réflexe.
- `uncertain_fields` est bien un fourre-tout : injecté par Python (agent.py:511-514), consommé seulement en agent.py:1024 et agent.py:1263, affiché comme un simple booléen dans l'UI (static/index.html:499).
- Offsets BCBP M1 de l'étape 3 : vérifiés contre la résolution IATA 792, ils sont justes (nom 2-21, PNR 23-29, orig 30-32, dest 33-35, transporteur 36-38, vol 39-43, jour julien 44-46, siège 48-51).

CE QUI EST FAUX OU SURVENDU — et ça change l'ordre des étapes :

1) « couche texte = 5/5 champs exacts » est une demi-vérité, et la moitié cachée casse la règle de fusion proposée. Mesure d'aujourd'hui, même PDF, même modèle :
   - Chemin texte (`pdftotext -layout` + Gemma, 11,3 s) : `booking_reference = FQ7T2K` JUSTE, `destination = LISBONNE LIS` juste, MAIS `scheduled_departure = 08:55` et `boarding_time = 09:25` — INVERSÉS (le billet dit EMBARQUEMENT 08:55, HEURE 09:25). `uncertain_fields = []`.
   - Chemin vision actuel (15,0 s) : `booking_reference = RQ7T2K` FAUX, mais `scheduled_departure = 09:25` et `boarding_time = 08:55` JUSTES.
   Aucun chemin ne domine l'autre. La couche texte gagne sur les champs exacts caractère par caractère et PERD sur l'association ligne/colonne, parce que `-layout` aplatit une mise en page à deux blocs en un texte où le modèle réassocie de travers. Conséquence directe : la règle « la vision ne sert plus qu'à compléter les champs restés nuls » (étape 1 du plan source) figerait l'inversion horaire, puisque les deux champs sont non nuls et faux. L'étape 5 (validateurs, dont `boarding_time < scheduled_departure`) n'est pas indépendante des étapes 1-4 : elle en est le PRÉREQUIS. Elle attrape exactement cette erreur, mesurée, pas intuitée.

2) Toutes les mesures du plan source reposent sur UN seul document, `billet_avion_fictif.pdf`, généré par le dépôt lui-même : une page, un vol, police base-14, couche texte parfaite. Ce n'est pas un échantillon, c'est une anecdote. Un e-ticket Amadeus ou Sabre réel a une couche texte, mais aussi trois pages de conditions tarifaires. Donc la mesure (étape 8) ne peut pas rester en dernier : sans elle, le classement des étapes 2 à 7 est une opinion.

3) Le contrôle « zéro dépendance » ne couvre pas ce que le plan veut ajouter. `.github/workflows/tests.yml:47` fait `pathlib.Path().glob("*.py")` — racine seulement. `eval/tickets/generate.py` importerait reportlab sans que la CI bronche. L'argument identitaire du dépôt cesserait d'être vérifié au moment précis où le plan l'invoque.

4) Trou non vu par le plan : il n'existe aucune boucle de correction. Le seul champ corrigible est la référence, via un champ texte du formulaire AVANT analyse (static/index.html:158) ; et `process` (agent.py:1254) rappelle `extract_flight` puis écrase la valeur. Corriger un caractère coûte donc une seconde extraction complète (~15 s) plus une nouvelle rédaction. L'étape 7 du plan source ajoute des champs de confirmation pour chaque champ faible : sans découpage de `process`, chaque confirmation paie ce prix.

5) Trou non vu par le plan : `document_type` est extrait (agent.py:56, requis agent.py:93) et consommé NULLE PART. Un selfie ou une facture produit une extraction toute nulle et une question générique, jamais un refus.

6) L'étape 6 (relance ciblée) est réfutée par la mesure de son propre auteur. Trois vues ont donné trois PNR différents, tous faux. Une seconde lecture visuelle sur ces documents produira un désaccord, donc un champ faible, donc une question — exactement ce qu'on obtient sans la faire, pour 10-15 s de moins. Elle n'apporte quelque chose que si l'accord entre deux lectures prédit la justesse, et aucune mesure ne le montre à ce jour.

7) HEIC (étape 2) : sur `<input type="file">`, iOS Safari transcode par défaut en JPEG. La branche HEIC est du travail non testable en CI (pas de `sips` sur ubuntu) pour un cas de bord rare. Le sniffing doit le RECONNAÎTRE et le refuser proprement, pas le convertir.

8) Décalages de lignes mineurs dans le plan source (agent.py fait 1531 lignes, pas 1560 ; `extract_flight` est en 464, pas 498). Sans effet sur le fond, mais le plan a été écrit contre un arbre légèrement différent.

## Cible

Une échelle de preuve explicite où le modèle est la dernière source, pas la première :

pass.json d'un .pkpass > chaîne BCBP trouvée en texte > couche texte d'un PDF ou d'un e-mail > lecture visuelle par Gemma > déclaration du voyageur.

Avec une correction essentielle par rapport au plan source : l'échelle ne s'applique PAS uniformément à tous les champs. Elle s'applique champ par champ, selon le type d'erreur auquel chacun est exposé.
- Champs à exactitude caractère par caractère (PNR, nom, numéro de vol) : la couche texte et le BCBP dominent la vision, mesuré. Jamais retenus sur une seule lecture visuelle.
- Champs d'association ligne/colonne (heures, dates) : la couche texte aplatie peut être PIRE que la vision, mesuré. Ils ne sont jamais retenus sans passer les validateurs déterministes, et une violation produit une question, pas un arbitrage.
- Champs avec référentiel (aéroports, compagnies) : recalés par Python sur `resolve_airport` / `carriers.json`, le libellé lu est jeté.

Chaque champ critique porte sa provenance et son niveau de vérification, dans la trace et dans l'interface. Les champs faibles sont corrigeables par le voyageur SANS relancer l'extraction.

Formats acceptés, type déterminé par les octets : PDF texte, PDF multipage, PDF scanné, PNG/JPEG/WEBP, .eml de confirmation, .pkpass. HEIC : reconnu et refusé avec un message actionnable.

Et une mesure publiée : taux d'exactitude par champ et par classe de source, et surtout taux d'ERREUR SILENCIEUSE (valeur fausse non marquée faible), sur des billets synthétiques dérivés d'une vérité terrain — zéro billet de tiers collecté. Aujourd'hui ce taux vaut au moins 1 sur 1 sur les deux chemins mesurés : les deux ont rendu un champ faux avec un `uncertain_fields` muet ou hors sujet.

## Étapes

### 1. Validateurs déterministes et recalage sur les référentiels (PROMU en premier)

*Effort :* quelques soirees · *Prérequis :* Aucun. Bloque tout le reste : ne pas commencer l'étape 2 avant.

Nouveau module `extraction_checks.py`, sans modèle, entièrement testable en CI. C'était l'étape 5 du plan source ; la mesure d'aujourd'hui en fait le prérequis de tout le reste, parce que le chemin texte de l'étape suivante introduit une classe d'erreur (inversion ligne/colonne) que seul ce module attrape.

Règles, chacune née d'un cas OBSERVÉ, aucune d'une intuition :
- `boarding_time < scheduled_departure` — justifiée par la mesure du jour : le chemin texte a rendu 08:55/09:25 inversés avec `uncertain_fields` vide. Violation = les DEUX champs deviennent faibles et une question est posée. Jamais de permutation automatique : on ne sait pas lequel des deux est faux.
- Numéro de vol `^[A-Z0-9]{2}\s?\d{1,4}[A-Z]?$` + préfixe recoupé contre `knowledge/carriers.json`.
- PNR `^[A-Z0-9]{5,7}$` et différent du numéro de vol. Écrire noir sur blanc dans le code que cette règle attrape une erreur de FORME et jamais une erreur de caractère : `RQ7T2K` la passe alors que la vérité est `FQ7T2K`. Seule une source exacte tranche.
- Heures en `HH:MM`, date ISO plausible (règle déjà présente, `_implausible_date`).

Et le recalage, cinq lignes pour le meilleur gain du lot : quand `resolve_airport` (eu261.py:132) trouve un code référencé, le libellé du modèle est remplacé par le nom du référentiel et jeté. « LIONNONE LIS » devient « Lisbonne (LIS) » dans l'affichage ET dans la `search_query` de `route_case` (agent.py:731), qui envoie aujourd'hui le libellé brut du modèle vers SerpApi.

Typer `uncertain_fields` : entrées `champ:motif` produites par Python. L'auto-déclaration du modèle reste UN motif parmi d'autres — mesuré deux fois aujourd'hui, elle est muette quand le modèle se trompe.

*Fichiers :* `extraction_checks.py`, `agent.py`, `eu261.py`, `knowledge/carriers.json`, `test_agent.py`

*Risque :* Des règles trop strictes noieraient le voyageur sous les questions. Plafonner : une règle par erreur réellement observée, et le compteur de faux positifs mesuré à l'étape 6. Ne jamais laisser Python « corriger » un PNR ou un nom — on recale sur un référentiel ou on demande. `uncertain_fields` est lu à agent.py:1024 et 1263 et affiché à static/index.html:499 : le changement de typage doit garder ces trois points compatibles ou les migrer dans le même commit.

### 2. Couche texte d'abord pour les PDF, toutes pages, fusion par type de champ

*Effort :* soiree · *Prérequis :* Étape 1 (sans les validateurs, cette étape dégrade les horaires).

Nouveau module `sources.py` : `pdf_text_layer(path) -> str | None` via `pdftotext -layout` (même paquet Poppler que `pdftoppm`, déjà requis), seuil d'utilisabilité (≈80 caractères alphanumériques et au moins un jeton de forme IATA) pour distinguer une vraie couche texte d'un résidu de scan.

Sans argument `-f/-l`, `pdftotext` dump DÉJÀ toutes les pages, séparées par `\f` : le multipage texte est gratuit, il suffit de remplacer les `\f` par des marqueurs `--- page N ---`. Pas besoin de `pdfinfo`. C'est la moitié utile de l'étape 4 du plan source, absorbée ici pour zéro coût.

Fusion — et c'est ici que je corrige le plan source. PAS « la vision complète les champs nuls » : mesuré aujourd'hui, cette règle fige une inversion horaire non nulle et fausse. La règle est :
- champs exacts (PNR, nom, numéro de vol) : la couche texte gagne, marqués `couche_texte` ;
- champs horaires et dates : retenus seulement s'ils passent les validateurs de l'étape 1 ; en cas de violation, faibles + question ;
- champs à référentiel : recalés, la provenance du libellé n'a plus d'importance.
Un seul appel modèle, texte, pas d'image, pas de rendu : 11,3 s mesurées contre 15,0 s pour le chemin actuel. Cette étape rend le pipeline plus RAPIDE.

Fixer `num_ctx: 8192` sur l'appel d'extraction (agent.py:464) : absent aujourd'hui, et une couche texte multipage le dépassera trivialement.

*Fichiers :* `sources.py`, `agent.py`, `test_agent.py`, `docs/EVALUATION.md`

*Risque :* Un PDF avec une couche texte issue d'un mauvais OCR est faux mais bien formé : n'est retenue que si l'enregistrement passe les validateurs, sinon repli vision avec le conflit tracé. Un e-ticket réel contient trois pages de conditions tarifaires : plafonner le texte injecté (≈8000 caractères) et couper sur les marqueurs de page, pas au milieu d'un mot. Poppler absent : chemin actuel, mode dégradé explicite, déjà géré.

### 3. Reconnaître le format par les octets — et refuser proprement ce qu'on ne sait pas lire

*Effort :* heures · *Prérequis :* Aucun, mais n'a d'intérêt qu'une fois l'étape 2 en place pour router les PDF texte.

`sources.sniff_kind(bytes)` : `%PDF`, `\x89PNG`, `\xff\xd8` JPEG, `RIFF....WEBP`, `ftypheic|heix|mif1` HEIC, `PK\x03\x04` ZIP, sinon texte. `app.py:102-103` ne rejette plus sur l'extension : elle devient un indice, les octets tranchent, et `static/index.html:141` élargit son `accept`. Une trentaine de lignes qui tuent une classe entière de bug (un HEIC renommé `.jpg` part aujourd'hui vers Ollama qui répond 400, exactement le symptôme que `_webp_as_png` avait déjà corrigé une fois).

CORRECTION du plan source : ne PAS convertir le HEIC. iOS Safari transcode déjà en JPEG sur un `<input type="file">` ; la branche `sips`/`ffmpeg` serait du code non testable en CI (pas de `sips` sur ubuntu) pour un cas de bord. Le sniffer le RECONNAÎT et renvoie un message actionnable. Le WEBP garde son convertisseur existant, qui est déjà écrit et déjà justifié par un 400 constaté.

*Fichiers :* `sources.py`, `app.py`, `static/index.html`, `test_agent.py`

*Risque :* Quasi nul : les tests sont des chaînes d'octets pures, sans Ollama et sans PII. Seul piège, la borne de taille : le sniffing doit lire les 16 premiers octets, pas charger le fichier deux fois.

### 4. .pkpass et BCBP : des champs exacts sans appeler le modèle

*Effort :* soiree · *Prérequis :* Étape 3 (détection ZIP).

Le meilleur rapport valeur/risque du plan, et je le confirme sans réserve. Un .pkpass est un ZIP contenant `pass.json` : `zipfile` + `json`, tout stdlib, donne nom, PNR, origine, destination, vol, siège, porte, sans aucune inférence. `parse_bcbp(text)` décode le format M1 de la résolution IATA 792 aux décalages fixes — j'ai vérifié les offsets du plan source contre la norme, ils sont justes. Le même parseur s'applique à toute chaîne de forme BCBP trouvée dans une couche texte, ce qui le rend utile même sans .pkpass.

Trois points que le plan source oublie et qu'il faut coder :
- `pass.json` : lire `barcodes` (tableau, depuis iOS 9) AVANT `barcode` (champ déprécié encore présent). Ne lire que l'un des deux ferait rater la moitié des passes réels.
- Ne pas vérifier la signature du .pkpass : cela demande les certificats Apple WWDR, aucun chemin stdlib. Le dire dans le code et dans le README : on lit un ZIP fourni par l'utilisateur, on ne l'authentifie pas.
- Borne anti-zip-bomb : `app.py` plafonne l'upload à 10 Mo, mais 10 Mo de ZIP se décompressent en gigaoctets. Refuser si la somme des `ZipInfo.file_size` dépasse quelques Mo, et n'extraire que `pass.json`.

Ces valeurs sont marquées `exact` et écrasent le modèle sans discussion ; sur un .pkpass le modèle n'est même pas interrogé. Le jour julien BCBP, sans année, ne sert QU'À recouper une date lue ailleurs, jamais à en fabriquer une.

*Fichiers :* `sources.py`, `agent.py`, `test_agent.py`, `docs/EVALUATION.md`

*Risque :* Technique : nul, tests unitaires sur chaînes BCBP synthétiques. Attente : un .pkpass est une carte d'embarquement, il donne l'identité du vol et JAMAIS la perturbation — il ne dispense donc pas de la déclaration du voyageur. Ne pas laisser croire dans le README qu'il suffit à produire un dossier.

### 5. E-mail de confirmation (.eml) — étape à part entière, pas un rider du sniffing

*Effort :* quelques soirees · *Prérequis :* Étapes 2 et 3.

Le plan source la fondait dans l'étape 2 en la comptant pour rien. C'est faux : le parsing MIME est trivial (module stdlib `email`, aplatissement HTML par une sous-classe de `html.parser.HTMLParser`, zéro dépendance), mais la SÉMANTIQUE ne l'est pas. Un e-mail de confirmation contient presque toujours l'aller ET le retour, une date de réservation confondable avec la date de vol, des pieds de page marketing, et souvent le tout en deux langues.

Règle de conception, non négociable : si le texte contient plus d'un numéro de vol ou plus d'une paire origine/destination, on ne choisit PAS. On liste les segments détectés et on demande au voyageur lequel concerne l'incident. C'est le même principe que `resolve_airport` qui refuse d'arbitrer entre deux codes IATA (eu261.py:132) — un motif déjà en place dans le dépôt, à généraliser plutôt qu'à réinventer.

*Fichiers :* `sources.py`, `agent.py`, `static/index.html`, `test_agent.py`

*Risque :* C'est le format le plus hétérogène du lot et le seul où le vrai travail est de renoncer. Se donner une limite dure : si la détection de segments n'est pas fiable après deux soirées, dégrader vers « un seul vol détecté ou question », et ne jamais livrer une extraction silencieuse de l'aller quand le retour était concerné.

### 6. Éval minimale de l'extraction, tôt, et extension du contrôle zéro-dépendance

*Effort :* quelques soirees · *Prérequis :* Étape 1 (les champs faibles doivent être typés pour que l'erreur silencieuse soit calculable). À faire dès que les étapes 2 à 4 sont livrées, pas après tout le reste.

Le plan source mettait la mesure en dernier. C'est l'inverse qu'il faut : sans elle, le classement des étapes repose sur UN document synthétique généré par le dépôt lui-même. Version minimale, livrable en quelques soirées, qui suffit déjà à trancher.

`eval/tickets/ground_truth.json` : la vérité terrain du billet déjà présent plus deux variantes de mise en page. Les variantes hostiles sont dérivées à l'exécution avec les outils déjà installés, hors chemin d'inférence : rastérisation sans couche texte (`pdftoppm`), rotation 7° et 90°, JPEG qualité 40, recadrage type capture de téléphone (`ffmpeg`, déjà dépendance optionnelle du WEBP).

`eval/vision.py` publie DEUX métriques par champ et par classe de source : exactitude, et surtout taux d'ERREUR SILENCIEUSE (valeur fausse non marquée faible). C'est la seule qui compte : une valeur fausse et signalée devient une question, une valeur fausse et confiante devient une lettre fausse. Sur les deux runs d'aujourd'hui, ce taux vaut 1/1 dans les deux sens (PNR faux non signalé côté vision ; horaires inversés non signalés côté texte). C'est le chiffre de départ à faire baisser.

Et un correctif de trois lignes qui protège l'identité du dépôt : `.github/workflows/tests.yml:47` fait `pathlib.Path().glob("*.py")` — racine seulement. Passer en `rglob` en excluant `.venv/` et `tmp/`, AVANT que `eval/tickets/` existe. Sinon le seul garde-fou du « zéro dépendance » cesse de couvrir le code que ce plan ajoute.

Rapport horodaté dans `eval/reports/`, tableau dans `docs/EVALUATION.md` qui annonce aujourd'hui explicitement ce trou (ligne 125, « Aucun taux d'exactitude par champ »). Hors CI : Ollama requis.

*Fichiers :* `eval/tickets/ground_truth.json`, `eval/vision.py`, `eval/reports/`, `docs/EVALUATION.md`, `.github/workflows/tests.yml`, `.gitignore`

*Risque :* Un billet synthétique est plus facile qu'un vrai : le score sera flatteur, l'écrire dans le rapport lui-même. Holdout privé dans `eval/real/`, couvert par la liste blanche médias du `.gitignore`, dont seul l'agrégat est publié avec son n et sa date.

### 7. Boucle de correction sans ré-extraction (ÉTAPE AJOUTÉE)

*Effort :* soiree · *Prérequis :* Étape 1 (les champs faibles désignent quoi proposer à la correction).

Trou que le plan source ne voit pas, et qui bloque son étape 7. Aujourd'hui le seul champ corrigible est la référence, via un champ texte du formulaire AVANT analyse (static/index.html:158) ; et `process` (agent.py:1254) rappelle `extract_flight` puis écrase la valeur. Corriger un caractère coûte donc une extraction complète (~15 s) plus une nouvelle rédaction. Multiplier les champs de confirmation sans corriger cela rend l'interface inutilisable.

Découper `process` en deux : `process(document, ...)` qui extrait, et `process_extracted(extraction, overrides)` qui prend un enregistrement déjà extrait, applique les corrections du voyageur, puis rejoue seulement route / qualify / draft. Un endpoint `POST /api/refine` dans `app.py` qui prend l'extraction retournée plus les corrections. Zéro appel modèle pour l'extraction, zéro octet de document renvoyé.

C'est du code sans modèle, entièrement testable en CI, et c'est ce qui rend l'outil utilisable sur un VRAI billet où le modèle s'est trompé sur un champ — l'objectif affiché du projet. Les corrections du voyageur sont marquées `saisie_voyageur`, le niveau le plus haut de l'échelle de preuve avec les sources exactes.

*Fichiers :* `agent.py`, `app.py`, `static/index.html`, `test_agent.py`

*Risque :* Faire confiance à un enregistrement renvoyé par le client : `process_extracted` doit revalider l'enregistrement avec `extraction_checks` et refuser tout champ hors schéma, exactement comme `_validate_tool_call` recalcule les arguments d'outil au lieu de les croire. Ne jamais accepter un champ calculé (retard, montant) depuis le client : seuls les champs extraits sont corrigibles.

### 8. Provenance et confiance visibles jusque dans l'interface

*Effort :* quelques soirees · *Prérequis :* Étapes 1, 4 et 7.

`extraction_provenance: {champ: {source, verification}}` en structure SŒUR du dictionnaire plat `extraction` — le plan source a raison sur ce point et il est important : refondre `extraction` en {valeur, source, confiance} casserait `route_case` (agent.py:731), `qualify_case`, `draft_claim`, `_validate_claim` et la majorité des 106 tests pour un gain cosmétique.

Pastille par champ : exact (.pkpass / BCBP), couche texte, lecture visuelle, saisie voyageur, faible. Champ faible = champ de correction, en réutilisant l'endpoint de l'étape précédente.

Requalification de l'effort : le plan source annonce « soiree ». Toucher agent.py + app.py + index.html + un `examples/sample_output.json` versionné + les tests qui comparent des structures complètes, ce n'est pas une soirée. C'est quelques soirées, et la moitié du temps part dans les tests existants.

Portée bornée : provenance affichée sur SIX champs seulement — vol, origine, destination, date, heure prévue, référence. Pas le siège, pas la porte.

*Fichiers :* `agent.py`, `static/index.html`, `app.py`, `test_agent.py`, `examples/sample_output.json`

*Risque :* Un affichage trop bavard rend l'écran illisible : la pastille par défaut (lecture unique) ne s'affiche pas, seules les extrémités de l'échelle sont visibles. Second risque, cosmétique déguisé en technique : si la provenance n'ouvre pas une action de correction, elle ne sert à rien — d'où la dépendance à l'étape 7.

### 9. Refuser explicitement un document qui n'est pas un justificatif de voyage (ÉTAPE AJOUTÉE)

*Effort :* heures · *Prérequis :* Étape 1.

Second trou non vu par le plan. `document_type` figure dans `FLIGHT_SCHEMA` (agent.py:56) et dans les champs requis (agent.py:93), mais n'est consommé NULLE PART. Un selfie, une facture ou un PDF vide produit aujourd'hui une extraction toute nulle et une question générique — l'outil ne sait pas dire « ce n'est pas un billet ».

Consommer `document_type` dans `route_case` : si le type est hors de l'énumération attendue, ou si les quatre champs d'identité du vol sont nuls ET qu'aucune source exacte n'a rien donné, retourner un statut `document_non_pertinent` avec un message clair, au lieu d'enchaîner sur la recherche et la rédaction. Quelques heures, zéro risque, et c'est le premier écran que voit quiconque teste le dépôt avec un mauvais fichier.

*Fichiers :* `agent.py`, `static/index.html`, `test_agent.py`

*Risque :* Refuser un billet valide mal lu. Le seuil doit être franc — les quatre champs d'identité nuls, pas trois — et la voie de secours reste la saisie manuelle de l'étape 7, jamais un cul-de-sac.

### 10. Générateur complet de billets synthétiques (REQUALIFIÉ : semaines, à faire en dernier ou pas du tout)

*Effort :* semaines · *Prérequis :* Étape 6, ET une preuve tirée de ses résultats que la diversité de mise en page change le classement.

`eval/tickets/generate.py` fabrique N billets depuis une vérité terrain : compagnies fictives, mises en page et langues variées (FR/EN/ES), PDF écrit à la main en stdlib avec les polices base-14.

Requalification franche : le plan source annonce « quelques soirées ». Écrire un producteur de PDF en Python pur (table xref, objets, flux de contenu, métriques de police base-14) est faisable — c'est un exercice connu d'une centaine de lignes — mais MULTIPLIER par plusieurs mises en page, trois langues, une vérité terrain cohérente, puis stabiliser le tout, c'est plusieurs semaines à quelques heures par semaine. Pour une personne seule le soir, c'est le genre d'étape qui devient le projet.

Donc : l'étape 6 livre déjà la métrique qui compte, avec trois mises en page et six variantes hostiles. Cette étape-ci n'est justifiée QUE si l'étape 6 montre que le classement des chemins d'ingestion dépend de la mise en page. Si le classement est stable, elle ne se fait pas, et le README dit pourquoi.

*Fichiers :* `eval/tickets/generate.py`, `eval/tickets/ground_truth.json`, `docs/EVALUATION.md`

*Risque :* Le générateur devient un projet en soi — c'est le risque principal, et la mitigation est de ne pas le commencer sans la preuve ci-dessus. Second risque : un billet synthétique reste plus facile qu'un vrai, quel que soit le nombre de mises en page. Le holdout privé de l'étape 6 reste la seule mesure honnête.

## À ne pas faire

- Appliquer la règle « la couche texte gagne, la vision complète les champs nuls ». Mesuré aujourd'hui sur le même PDF : le chemin texte a rendu scheduled_departure et boarding_time INVERSÉS, non nuls, avec uncertain_fields vide, là où la vision les avait justes. Cette règle figerait l'erreur. La priorité de source se décide champ par champ, et les horaires passent obligatoirement par les validateurs déterministes.

- Coder la relance ciblée (étape 6 du plan source) avant d'avoir la mesure. Elle est réfutée par la mesure de son propre auteur : trois vues du même PNR ont donné trois valeurs différentes, toutes fausses. Une seconde lecture visuelle sur un document difficile produira un désaccord, donc un champ faible, donc une question — le même résultat qu'en marquant le champ faible sans rien relancer, pour 10 à 15 secondes de plus. À ne coder que si l'éval de l'étape 6 montre que l'accord entre deux lectures prédit la justesse, avec une précision chiffrée.

- Convertir le HEIC. iOS Safari transcode déjà en JPEG sur un input de fichier ; la branche sips/ffmpeg serait du code non testable en CI pour un cas de bord. Le sniffer le reconnaît et le refuse avec un message actionnable, point.

- Ajouter Pillow, pypdf, pdfplumber, pytesseract ou reportlab, sur le chemin d'inférence comme dans eval/. Poppler et le parseur BCBP en stdlib couvrent les cas fréquents. Et corriger d'abord .github/workflows/tests.yml:47, qui ne scanne que la racine : aujourd'hui un import de reportlab dans eval/ passerait la CI sans bruit.

- Écrire un décodeur PDF417 ou Aztec depuis une image. Des semaines pour lire un code-barres dont le contenu est déjà disponible en texte dans un .pkpass ou une couche texte. Le refuser explicitement dans le README plutôt que de le laisser en dette implicite.

- Rejouer N fois le même appel d'extraction pour faire de l'auto-cohérence. À température 0, deux appels identiques donnent une sortie strictement identique. Seule la diversité de vue, de formulation ou de MODALITÉ produit un signal — et la modalité, c'est déjà ce que fait le couple texte/vision.

- Traiter uncertain_fields comme un score de confiance. Deux mesures aujourd'hui, deux erreurs différentes, zéro auto-signalement pertinent. Les validateurs Python sont le juge.

- Laisser le modèle corriger ou normaliser un champ qu'il vient de lire. Un modèle qui corrige sa propre lecture fabrique une valeur plausible et fausse. On recale sur un référentiel, ou on demande au voyageur.

- Refondre extraction en dictionnaire de {valeur, source, confiance}. Cela casserait route_case (agent.py:731), qualify_case, draft_claim, _validate_claim et la majorité des 106 tests pour un gain cosmétique. La structure sœur extraction_provenance donne le même service sans la casse.

- Arbitrer automatiquement entre deux lectures divergentes, entre deux pages d'un PDF, ou entre l'aller et le retour d'un e-mail de confirmation. Le projet tient parce qu'il pose une question au lieu de choisir ; chaque arbitrage silencieux est une régression de conception.

- Multiplier les champs de confirmation dans l'interface avant d'avoir découpé process (agent.py:1254). Chaque confirmation relance aujourd'hui l'extraction complète du document : la fonctionnalité serait livrée avec quinze secondes de latence par correction.

- Constituer un jeu de 30 à 50 vrais billets. Donnée personnelle de tiers, déjà refusé. Le synthétique plus un holdout privé donnent une mesure publiable sans rien collecter.

- Écrire un décodeur JPEG en Python pur pour recadrer ou pivoter. Le PNG est faisable en stdlib avec zlib, le JPEG non, et rien ne prouve encore que la rotation soit un goulot — le mesurer à l'étape 6 avant d'écrire une ligne.

