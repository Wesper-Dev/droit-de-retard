# Recherche en ligne : lire des sources officielles au lieu d'interroger un moteur, et produire les livrables de dépôt (critique adversariale du plan initial)

Fiche de conception issue de l'audit du 28 juillet 2026, après critique adversariale. Synthèse et ordre de construction dans [`../ARCHITECTURE_CIBLE.md`](../ARCHITECTURE_CIBLE.md).

## Diagnostic

**Ce que j'ai reproduit et qui tient.** Les trois constats du concepteur sont exacts. `tools.py:289-325` : `verify_air_passenger_rule` ne télécharge jamais le corps d'une page, il garde `title`/`link`/`snippet` de SerpApi (`tools.py:246-253`) après un filtre de chemin (`tools.py:272-286`) ; la branche hors ligne rend deux URLs constantes. `tools.py:544-602` : `find_claim_channel` va chercher en réseau une URL déjà présente dans `knowledge/airline_policies/*.json` sous `procedures[].channel.url`. `tools.py:199-207` : le retard vient de la déclaration, `flight_number` n'est clé de rien. Mesures réseau refaites aujourd'hui depuis ce poste, en `urllib` nu avec `User-Agent: Droit-de-Retard/0.1` : EUR-Lex `32004R0261` → 200, 37 928 octets, « Article premier », « 250 euros », « 400 euros », « 600 euros » littéralement présents ; `62007CJ0402` → 200 ; `europa.eu/youreurope` → 200, 217 Ko ; `transport.ec.europa.eu/.../national-enforcement-bodies-neb_en` → 200, 94 Ko ; `easyjet.com/claim/fr/eu261` → 200, 53 Ko ; `wwws.airfrance.fr` → timeout ; OpenSky `/api/flights/all` → **HTTP 403**. Suite : 106 tests, 0,052 s. 61 aéroports dont 37 UE. 31 cas d'éval.

**Cinq corrections au diagnostic.**

**(a) La faille de `_allowed_claim_urls` est plus grave que décrite, et elle est déjà là.** `agent.py:1082-1084` ajoute à l'ensemble autorisé *tous* les `channel["results"][].link`. Or `find_claim_channel` renvoie ce champ précisément dans les deux cas où le filtre de domaine a **échoué** : `unverified_channel` (`tools.py:565-575`) et `no_official_match` (`tools.py:579-590`). Le commentaire de `tools.py:558-562` explique qu'il ne faut surtout pas publier ces résultats parce que la requête est dominée par les intermédiaires à 25-35 % — et `agent.py` les autorise ensuite dans la lettre. La propriété « toute URL citée est vérifiée » est **actuellement fausse**, indépendamment de tout le reste du plan. Ça se corrige en une ligne et ça doit passer devant.

**(b) Le volume du corpus est sous-estimé d'un facteur ~2.** Mesuré, texte extrait : règlement 31 Ko, Sturgeon 42 Ko (et non 41 Ko de HTML : le HTML fait 97 Ko), Wallentin-Hermann 30 Ko, Germanwings 16 Ko, Krüsemann 34 Ko, Airhelp 34 Ko → **189 Ko de texte pour six documents**, 400 Ko de HTML. Une douzaine d'arrêts, c'est ~350-400 Ko de texte. Ça reste tenable dans un dépôt, mais il faut l'écrire juste.

**(c) « Les articles pertinents tiennent dans le prompt » est faux tel quel.** `draft_claim` (`agent.py:1030`) sérialise le dict `research` **entier** en JSON dans le prompt, avec `num_ctx: 8192, num_predict: 2048` (`agent.py:1050`). Le règlement seul fait 31 Ko ≈ 9-10 k tokens, soit plus que la fenêtre entière. L'injection ne peut se faire qu'au grain point/paragraphe (200-600 octets), 3 unités maximum, avec un budget compté. À défaut, `done_reason == "length"` et l'échec se présente comme un modèle défaillant (le commentaire `agent.py:1046-1048` documente déjà ce piège).

**(d) Le risque « parseur juridique » est surévalué.** Le HTML EUR-Lex de cet acte n'a aucune classe sémantique (`ti-art` : 0 occurrence) mais c'est une suite plate de `<p>`. Prototype de six lignes exécuté à l'instant : 199 paragraphes, **19/19 titres d'article détectés** par `^Article (premier|\d+)$`, 42 paragraphes numérotés, 42 points `a)`. Une soirée, pas un gouffre. En revanche, ne pas espérer mieux ailleurs : `/TXT/XML/` renvoie une **notice de métadonnées de 1,78 Mo**, pas le corps de l'acte, et la manifestation Formex 4 du Cellar **404** pour ce CELEX.

**(e) « Sortir SerpApi = majoritairement de la suppression » est optimiste.** Le nom d'outil est câblé à six endroits : `RESEARCH_TOOL_SYSTEM` (`agent.py:207-214`) qui **ordonne** au modèle d'appeler les trois outils, `RESEARCH_TOOL_ORDER` (`agent.py:216`), la boucle `for _round in range(len(RESEARCH_TOOL_ORDER))` (`agent.py:871`), `_expected_tool_arguments` (`agent.py:~815`), le dispatcher littéral (`agent.py:838-848`), le constructeur de trace (`agent.py:~985-1010`), plus `static/index.html` et une quinzaine de tests. Ça reste une soirée, mais une soirée pleine.

**Ce qui manque à la dimension.** `eu261.py:530-547` renvoie `not_covered` pour l'annulation. Le plan investit trois soirées à corroborer une heure d'atterrissage par ADS-B pendant que le cas le plus fréquent après le retard renvoie « ce moteur ne le calcule pas encore ». Sur l'objectif « vraiment fonctionner sur de vrais billets », c'est le mauvais arbitrage.

## Cible

Inverser le sens de l'accès réseau — on ne cherche plus, on lit — et rendre la citation **structurellement** invérifiable-par-le-modèle plutôt que vérifiée après coup.

1. Le règlement 261/2004 et 5 à 8 arrêts CJUE embarqués verbatim (~250-300 Ko de texte, mesuré), découpés en articles/paragraphes/points, chaque unité portant son SHA-256 et son URL ELI.
2. Chaque constante de `eu261.py` adossée à un `legal_basis` (« art_7_1_b »), et un test CI qui exige que le texte de l'unité citée contienne littéralement le nombre appliqué. Vérifié faisable : « 250 euros », « 400 euros », « 600 euros » sont dans le texte fetché. C'est ça, « vérifier une règle » — hors ligne, en 0,05 s, dans la suite existante.
3. `fetch_official_source(source_id)` remplace `web_search` : liste blanche d'**URLs**, pas de requête, `html.parser`, marqueurs attendus, cache daté + SHA-256. En ligne = relecture fraîche ; hors ligne = copie datée. Le mode dégradé rend le même texte, plus vieux, au lieu de rendre le vide.
4. **Le modèle n'écrit plus jamais d'URL.** Il produit des identifiants de citation ; Python rend le bloc « Sources ». `_allowed_claim_urls` disparaît au profit d'une règle plus simple et strictement plus forte : toute URL dans la sortie du modèle est une violation.
5. SerpApi quitte le chemin d'inférence, backend par défaut `none`, survit comme outil de mainteneur en mode `manual`.
6. « Remplir » = produire des documents (`.eml`, PDF stdlib, fiche de saisie, chronologie d'escalade), jamais piloter le formulaire d'autrui.
7. L'annulation est couverte par le moteur, en s'appuyant sur l'art. 5(1)(c) désormais embarqué verbatim.
8. L'observation ADS-B, si elle arrive, arrive en dernier et opt-in : elle corrobore, jamais elle n'infirme.

Propriété conservée : Python décide, le modèle rédige. Ajoutée : le texte officiel fonde, et Python — pas le modèle — signe les sources.

## Étapes

### 1. Refermer la fuite de la liste blanche d'URLs (à faire avant tout le reste)

*Effort :* heures · *Prérequis :* Aucun.

`agent.py:1082-1084` verse dans l'ensemble des URLs citables tous les `channel["results"][].link`. Or `find_claim_channel` ne renvoie ce champ que sous les statuts `unverified_channel` (`tools.py:565-575`) et `no_official_match` (`tools.py:579-590`), c'est-à-dire exactement quand le filtre de domaine officiel a échoué — donc quand les résultats sont, de l'aveu du commentaire de `tools.py:558-562`, dominés par les intermédiaires à commission. Aujourd'hui, le projet peut produire une lettre qui renvoie le passager vers un service qui prélève 30 %, tout en affichant que l'URL a été vérifiée.

Correctif : supprimer la boucle sur `results` dans `_allowed_claim_urls`, et cesser de renvoyer `results` au modèle depuis `find_claim_channel` sous ces deux statuts (le message textuel suffit). Deux tests : un cas `unverified_channel` où une URL d'intermédiaire citée par le modèle doit produire une violation ; un cas `no_official_match` idem.

À faire maintenant parce que c'est une propriété annoncée qui est fausse, que le correctif tient en une dizaine de lignes, et que les étapes 2 et 3 réécrivent cette zone — autant partir d'un état sain et avoir les tests de non-régression déjà écrits.

*Fichiers :* `agent.py`, `tools.py`, `test_agent.py`

*Risque :* Nul, c'est un rétrécissement d'une liste blanche. Le seul effet visible est qu'une lettre citera moins d'URLs sur les transporteurs hors registre — ce qui est le comportement voulu.

### 2. Corpus juridique embarqué et ancrage des constantes du moteur

*Effort :* quelques soirees · *Prérequis :* Étape 0 faite (zone de code assainie). Rien d'autre.

Script de mainteneur, hors chemin d'inférence, qui télécharge depuis EUR-Lex le règlement 261/2004 en français et 5 à 8 arrêts CJUE par CELEX, extrait le texte et le découpe en unités : `{celex, article, paragraphe, point, texte, url_eli, retrieved_on, sha256_source}`.

Le parseur est plus simple qu'annoncé, et je l'ai mesuré : le HTML n'a aucune classe sémantique (`ti-art` : 0), mais c'est une suite plate de `<p>`. Six lignes de regex sur `<p>...</p>` isolent **19 titres d'article sur 19**, 42 paragraphes `^\d+\. ` et 42 points `^[a-z]\) `. Écrire cette machine à états proprement avec `html.parser` (pas de regex sur le HTML en production) : une soirée. Ne pas chercher mieux ailleurs, c'est du temps perdu : `/TXT/XML/` rend une notice de métadonnées de 1,78 Mo et pas le corps de l'acte, la manifestation Formex 4 du Cellar renvoie 404 pour ce CELEX.

Volumes réels mesurés, à écrire dans le README sans arrondir vers le bas : règlement 31 Ko de texte, Sturgeon 42, Wallentin-Hermann 30, Germanwings 16, Krüsemann 34, Airhelp 34 → 189 Ko pour six documents. Prévoir 250-300 Ko pour huit.

Le geste qui compte : un champ `legal_basis` sur chaque règle de `eu261.py` (`compensation_amount` → `art_7_1_a|b|c`, les seuils de 3 h → l'arrêt Sturgeon, `classify_cause` → Wallentin-Hermann et Krüsemann, déjà nommés en commentaire aux lignes 271-278), puis un test qui affirme que (a) chaque `legal_basis` existe dans le corpus et (b) le texte de l'unité contient littéralement le nombre appliqué. Vérifié fetchable : « 250 euros », « 400 euros », « 600 euros » sont bien dans le texte. Un jury vérifie ça en trente secondes, et ça tourne sans réseau.

Contrainte à inscrire dès maintenant, sinon l'étape 2 la découvre trop tard : `draft_claim` tourne avec `num_ctx: 8192` et sérialise tout `research` (`agent.py:1030, 1050`). Le corpus est un magasin d'unités **courtes**, adressables par identifiant ; l'injection se fait au grain point/paragraphe, 3 unités maximum, avec un budget de caractères compté et testé.

NOTICE : © Union européenne ; contenu EUR-Lex réutilisable, décision 2011/833/UE ; seule la version publiée au JO fait foi, et le Recueil pour la jurisprudence.

*Fichiers :* `scripts/build_legal_corpus.py`, `knowledge/legal/reg_261_2004.fr.json`, `knowledge/legal/caselaw/`, `knowledge/legal/MANIFEST.json`, `eu261.py`, `test_agent.py`, `NOTICE`

*Risque :* Abaissé par la mesure : le découpage est régulier sur cet acte. Le vrai risque restant est ailleurs — les arrêts CJUE ne suivent PAS la structure article/paragraphe du règlement (ils sont en points numérotés du dispositif). Prévoir deux schémas d'unité, pas un seul, et ne pas essayer de faire rentrer un arrêt dans le moule d'un règlement. Si EUR-Lex change son HTML, le script casse à la maintenance, bruyamment, et le corpus versionné continue de servir : c'est le comportement voulu, le SHA-256 du HTML source rend le changement visible.

### 3. fetch_official_source, et le modèle qui n'écrit plus jamais d'URL

*Effort :* quelques soirees · *Prérequis :* Étape 1 (le corpus fournit les sources `regulation` et les identifiants de citation).

Remplacer `verify_air_passenger_rule` et `web_search` par un outil qui ne prend pas de requête mais un `source_id`. `knowledge/sources.json` : `{source_id, url, kind: regulation|institutional|carrier_procedure, expected_markers, last_fetch: {date, http_status, sha256, chars}}`. Rien n'est téléchargé si son identifiant n'est pas dans le fichier : la liste blanche porte sur des URLs, pas sur des domaines, strictement plus fort que `tools.py:272-286`.

Implémentation stdlib : GET, UA déclaré, timeout 15 s, plafond 2 Mo, refus de redirection cross-host, HTML→texte par sous-classe de `html.parser.HTMLParser`. Puis contrôle de marqueurs (« 600 euros », « 3 heures » sur la page Your Europe) ; marqueur manquant → statut `structure_changed` et on rend la copie en cache avec l'avertissement. Réutiliser telle quelle la politique de fraîcheur déjà écrite (`tools.py:432-442`, `MAX_POLICY_AGE_DAYS = 90`) en l'étendant aux sources : c'est du code existant, testé, à généraliser — pas à réécrire.

**Amendement important au plan initial.** Le concepteur propose d'étendre `_validate_claim` pour exiger que la phrase citée par le modèle existe dans le texte extrait. C'est fragile et ça coûtera plus cher que prévu : le modèle paraphrase, réaccentue, recompose la ponctuation, et on finit par écrire un comparateur flou — c'est-à-dire par réintroduire du jugement là où le projet a justement construit de l'exactitude à l'octet près. Faire l'inverse, qui est moins cher et plus fort : **interdire toute URL dans la sortie du modèle**. Le schéma `CLAIM_SCHEMA` gagne un champ `citations: [source_id | legal_unit_id]`, validé contre le corpus et le registre ; Python compose le bloc « Sources » et l'appose sous la lettre. `_allowed_claim_urls` (`agent.py:1071-1094`) disparaît, remplacé par une règle d'une ligne : toute occurrence de `_URL_IN_TEXT` dans la sortie du modèle est une violation. On passe d'« il a le droit de citer cette URL » à « il n'a pas la main sur les URLs », ce qui est exactement la même bascule que `_validate_tool_call` a déjà opérée sur les arguments d'outil.

`find_claim_channel` change de nature : plus de recherche, lecture du `channel.url` déjà présent dans les fiches locales, revérification de vivacité optionnelle via `fetch_official_source`. L'outil devient une vérification d'URL connue, et il marche hors ligne.

`scripts/check_sources.py` + job CI hebdomadaire : parcourt `sources.json`, signale 404, redirection hors domaine, marqueur perdu. La vérification a lieu à la maintenance, à visage découvert, et pas dans le dos du passager.

*Fichiers :* `tools.py`, `knowledge/sources.json`, `scripts/check_sources.py`, `.github/workflows/`, `agent.py`, `test_agent.py`

*Risque :* Mesuré aujourd'hui : institutionnel lisible (europa.eu 200/217 Ko, transport.ec.europa.eu 200/94 Ko, EUR-Lex 200), compagnies inégales (easyjet.com 200/53 Ko, **wwws.airfrance.fr timeout**). Traiter `carrier_procedure` en best-effort : l'échec est nominal et ne dégrade rien, la procédure est déjà dans le corpus local. Ne pas entrer dans une course d'armement contre la détection de bots. Risque propre à l'amendement : la migration du schéma de sortie casse en bloc les tests qui inspectent `letter_body` — les compter avant de commencer, c'est la moitié du coût de l'étape.

### 4. Sortir SerpApi du chemin d'inférence

*Effort :* soiree · *Prérequis :* Étapes 1 et 2, sinon on retire une capacité sans l'avoir remplacée.

Après les étapes 1 et 2, plus rien sur le chemin nominal n'a besoin d'un moteur. Backend par défaut `none`, `SERPAPI_KEY` retirée des prérequis (`README.md`, `.env.example`, `scripts/smoke_serpapi.py`).

Ce n'est pas de la simple suppression, et le plan initial le sous-estime : le nom d'outil est câblé à six endroits — `RESEARCH_TOOL_SYSTEM` (`agent.py:207-214`, qui *ordonne* les trois appels), `RESEARCH_TOOL_ORDER` (`agent.py:216`), la boucle `for _round in range(len(RESEARCH_TOOL_ORDER))` (`agent.py:871`), `_expected_tool_arguments` (`agent.py:~815`), le dispatcher littéral (`agent.py:838-848`), le constructeur de trace (`agent.py:~985-1010`) — plus `static/index.html` et une quinzaine de tests. Le dispatcher reste une chaîne de `if` littérale : c'est une propriété acquise, elle ne bouge pas.

**Écarter le backend `searxng` proposé.** Une instance SearXNG auto-hébergée n'est pas « un conteneur, pas un import » : c'est un service à installer, tenir et documenter, pour un script de mainteneur exécuté trois fois par an, dans un projet dont l'argument identitaire est l'absence de dépendance. Deux implémentations suffisent derrière le protocole : `manual` (le mainteneur colle l'URL, aucun réseau) et `serpapi` (conservé, optionnel). Ça fait ~30 lignes au lieu de 80 et ça ne ment pas sur le coût.

Écrire dans le README l'argument daté, qui est le vrai différenciateur : Brave Search a supprimé son palier gratuit en février 2026 ; Google Custom Search JSON est fermée aux nouveaux clients depuis 2025 et s'arrête le 1er janvier 2027. Il n'existe plus de socle de recherche hébergée gratuite sur lequel bâtir — c'est ce qui justifie la conception registre-d'abord, et peu de projets peuvent écrire ce paragraphe avec des dates.

*Fichiers :* `agent.py`, `tools.py`, `scripts/discover_carrier.py`, `scripts/smoke_serpapi.py`, `.env.example`, `README.md`, `static/index.html`, `test_agent.py`

*Risque :* Faible techniquement. Risque narratif réel : ne pas donner l'impression d'avoir renoncé à « chercher en ligne ». Le README doit dire que l'agent va toujours en ligne, mais lire des URLs officielles au lieu d'interroger un intermédiaire payant qui rend des extraits.

### 5. Couvrir l'annulation — le cas que le moteur refuse aujourd'hui

*Effort :* quelques soirees · *Prérequis :* Étape 1 (les seuils viennent du corpus et sont ancrés par le test).

ÉTAPE AJOUTÉE. `eu261.py:530-547` renvoie `not_covered` pour `cancellation`, `denied_boarding` et `missed_connection`. Le message est honnête, mais sur l'objectif « vraiment fonctionner sur de vrais billets », un outil qui répond « ce moteur ne le calcule pas encore » au deuxième cas le plus fréquent n'est pas fini. Et c'est précisément l'étape 1 qui débloque ça : l'art. 5(1)(c), avec ses trois branches (i) plus de deux semaines avant, (ii) entre deux semaines et sept jours avec réacheminement encadré, (iii) moins de sept jours, est désormais dans le dépôt verbatim, découpé, avec ses seuils horaires exacts. Le code n'a plus à les retaper de mémoire : il les adosse au corpus, et le test d'ancrage de l'étape 1 les vérifie.

Périmètre serré et assumé : **l'annulation seulement**, en réutilisant `compensation_amount` et le barème existant, plus la réduction de 50 % de l'art. 7(2) quand le réacheminement rentre dans les fenêtres. Le refus d'embarquement et la correspondance manquée restent `not_covered` avec leur message — le projet préfère déjà le trou déclaré à la valeur devinée (`eval/` documente 3 trous sur 31), on conserve la doctrine.

Coût comparé, et c'est l'argument : c'est moins de code que l'adaptateur ADS-B de l'étape 7, ça n'ajoute aucune dépendance, aucun compte, aucun réseau, ça se teste intégralement hors ligne, et ça change ce que l'outil fait pour un vrai passager. Le parseur de déclaration reconnaît déjà `cancellation` (`eval/incident_cases.json`), donc l'amont est en place.

À arbitrer avec le plan « moteur » s'il existe : si un autre volet possède déjà cette étape, la lui laisser et ne garder ici que la fourniture des unités juridiques art. 5 et art. 7(2).

*Fichiers :* `eu261.py`, `knowledge/legal/reg_261_2004.fr.json`, `agent.py`, `eval/incident_cases.json`, `test_agent.py`

*Risque :* Le vrai piège est la branche (ii) de l'art. 5(1)(c) : ses conditions de réacheminement (départ pas plus de deux heures avant, arrivée moins de quatre heures après) exigent des horaires que le billet ne porte pas toujours. Traiter l'absence comme `needs_information` avec une question précise, jamais comme une exonération du transporteur — c'est à lui de prouver qu'il a informé à temps, et le code ne doit pas faire ce travail à sa place.

### 6. Dossier de réclamation : .eml, PDF stdlib, fiche de saisie

*Effort :* quelques soirees · *Prérequis :* Étape 1 (le PDF cite les articles par leur identifiant). Étape 2 pour le bloc « Sources » composé par Python.

Les frontières posées par le concepteur sont bien mesurées et je les reprends telles quelles : le formulaire officiel UE de plainte est un PDF plat (`/AcroForm` absent, 0 `/Widget`) donc non remplissable ; le formulaire easyJet est un POST rendu serveur protégé par `__RequestVerificationToken` donc non pré-remplissable par URL ; `mailto:` plafonne vers 2 000 caractères et la RFC 6068 ne prévoit pas de pièce jointe. Trois impasses vérifiées, pas trois principes.

Ce qui reste : (a) `.eml` via `email.message.EmailMessage` (stdlib) avec destinataire, objet, corps, pièces jointes et en-tête `X-Unsent: 1` — en documentant que le « nouveau Outlook » ne l'honore pas, d'où la livraison conjointe d'un panneau de texte copiable ; (b) PDF généré de zéro en stdlib, Helvetica base-14 et `/WinAnsiEncoding`, 200-250 lignes pour le multipage et la césure. C'est la pièce « zéro dépendance » la plus démonstrative du dépôt, et le prototype de 833 octets prouve que le socle tient.

**Amendement sur la fiche de saisie.** Récolter les attributs `name=` des formulaires (`BookingReference`, `DateOfDisruptedFlight`) produit le mauvais artefact : le passager ne voit jamais ces chaînes à l'écran, il voit des libellés en français. Une fiche qui dit « champ *BookingReference* → ABC123 » l'oblige à traduire lui-même, et elle casse au prochain déploiement de la compagnie. Porter dans les fiches locales un bloc `form_fields` avec le **libellé visible**, l'ordre à l'écran, et la provenance de la valeur, relevé à la main au moment où l'on vérifie la fiche — trois compagnies, c'est vingt minutes, et ça se rattache naturellement au contrôle de fraîcheur à 90 jours et au job CI de l'étape 2.

**Contrainte à ne pas rater côté serveur.** `app.py` n'expose que `/api/analyze` et `/api/transcribe`, il se lie à `127.0.0.1` et contrôle l'en-tête Host contre le DNS rebinding (`app.py:50-54, 143`). Une route de téléchargement doit réutiliser ce contrôle, et surtout **rendre le `.eml` et le PDF dans le corps de la réponse avec `Content-Disposition`, sans jamais les écrire dans l'arborescence du dépôt** : sinon la propriété « aucune donnée personnelle » se dégrade en « des données personnelles dans le répertoire de travail, protégées par le seul `.gitignore` ».

Limites juridiques, cinq lignes de README : le passager envoie tout lui-même, pas de mandat, pas de représentation, pas de dépôt par un tiers. L'art. 54 de la loi n° 71-1130 réserve la consultation juridique à titre habituel et rémunéré, et préserve expressément la diffusion de renseignements à caractère documentaire. Un outil gratuit qui cite l'article et pose l'arithmétique est du côté documentaire, à condition de ne jamais rendre d'avis personnalisé ni de pronostic.

*Fichiers :* `claim_pack.py`, `pdf_writer.py`, `agent.py`, `app.py`, `static/index.html`, `knowledge/airline_policies/`, `test_agent.py`, `README.md`

*Risque :* Le générateur PDF est la seule brique qui réécrit du connu. Le prototype prouve que c'est tenable, à condition de tenir un sous-ensemble décidé d'avance : une police, un encodage, pas d'images, pas d'Unicode hors WinAnsi. Un nom en cyrillique ou en grec impose une police embarquée et le coût explose — le déclarer hors périmètre dès la première ligne du module, pas après. Risque secondaire concret : `letter_body` est aujourd'hui du texte libre ; la césure et la pagination doivent tomber sur des mots, pas au milieu d'un montant. Un test qui vérifie que le PDF contient la chaîne du montant non coupée.

### 7. Chronologie d'escalade et organismes nationaux, en dur et sans réseau

*Effort :* soiree · *Prérequis :* Étape 5 (la chronologie s'imprime dans le dossier).

La moitié manquante de « préparer », en Python pur. À partir de la date de l'incident, produire un calendrier : envoyer aujourd'hui → relancer à J+30 → saisine de l'ONA recevable à partir de J+60 (la DGAC n'instruit qu'après saisine du transporteur et deux mois d'attente) → prescription à cinq ans en France. Du calcul de dates, déterministe et testable, exactement ce que `eu261.py` sait déjà faire. Une partie existe d'ailleurs : `_implausible_date` (`agent.py:~1195`) alerte déjà au-delà de quatre ans en s'appuyant sur la prescription quinquennale — cette étape rend explicite et complète une logique aujourd'hui réduite à un avertissement.

**Amendement sur le registre des ONA.** Le PDF `2004_261_national_enforcement_bodies.pdf` rend bien 112 Ko de texte en stdlib, mais 112 Ko de texte issu d'opérateurs `Tj` n'est pas 27 fiches structurées : c'est un flux où les colonnes, les retours à la ligne et les adresses arrivent dans l'ordre du rendu, pas dans l'ordre logique. Écrire un parseur robuste sur ça, c'est une soirée de plus que prévu pour un fichier qui change une fois par an. Faire le geste économique : le script extrait le texte brut, le mainteneur **curate à la main 5 à 8 pays** (France, Belgique, Espagne, Portugal, Allemagne, Pays-Bas, Italie), chacun avec sa date de vérification. Le vide est déclaré partout ailleurs, avec renvoi vers la page officielle de la Commission (mesurée à 200, 94 Ko, donc citable via `fetch_official_source`).

Même discipline pour les délais de prescription : ne coder que ceux qu'on a sourcés — 5 ans en France — et rendre « délai non renseigné pour ce pays, vérifier auprès de l'ONA » partout ailleurs.

*Fichiers :* `scripts/extract_enforcement_bodies.py`, `knowledge/enforcement_bodies.json`, `eu261.py`, `claim_pack.py`, `agent.py`, `test_agent.py`

*Risque :* Faible techniquement, juridique par nature. Un tableau de prescriptions par pays est vite faux et se périme. La date de vérification s'affiche à côté de chaque valeur, et le trou est assumé ailleurs.

### 8. Observation ADS-B en corroboration asymétrique — opt-in, et en dernier

*Effort :* quelques soirees · *Prérequis :* Étapes 3 et 4. Ne pas empiler deux dépendances réseau tant que SerpApi n'est pas sorti.

Conservé, mais **déclassé en dernière position** et à ne lancer que si les sept étapes précédentes sont livrées. Raison : c'est le pire rapport valeur/effort du plan. Il faut un client OAuth2 client-credentials, le rapprochement numéro de vol → callsign, un champ `icao` sur les 61 entrées de `AIRPORTS` (`eu261.py:29-89`), un type de résultat, des fixtures figées, une clause NOTICE et un opt-in — pour une fonctionnalité qui, **par construction, ne peut jamais changer une décision**, qui est éteinte chez quiconque clone le dépôt sans compte, et qui n'apparaît donc pas dans la démo par défaut. L'annulation (étape 4) coûte moins et change ce que l'outil fait.

Mesuré aujourd'hui : `/api/flights/all` → **HTTP 403**, l'historique exige un compte gratuit et OAuth2 depuis mars 2026. `/api/states/all` répond en anonyme mais ne sert à rien ici : il est temps réel, une réclamation est rétrospective.

Si on la fait, la conception du concepteur est la bonne et il n'y a rien à y retrancher : port `FlightObservation`, adaptateurs `none` (défaut), `opensky` (opt-in), résultat parmi `confirmed_at_least(minutes) | flight_found_no_timing | not_matched | unavailable`. L'asymétrie est inscrite dans le code et testée : `lastSeen` est un dernier contact ADS-B, pas l'ouverture des portes au sens de Germanwings C-452/13, et le roulage ajoute 5 à 20 minutes — l'observation **sous-estime** donc le retard, dans le sens favorable au transporteur. Elle peut confirmer, jamais infirmer : 2 h 50 observées renvoient `inconclusive`, pas `not_eligible`. Exiger `estArrivalAirport == OACI de destination` ; 0 ou plus d'un candidat → `not_matched`, jamais de devinette.

Commencer par le sous-ensemble qui coûte le moins et rapporte le plus : **attester que le vol a existé et s'est posé à l'aéroport et à la date revendiqués**. Ça seul supprime la faiblesse la plus visible de la démo — un billet inventé produit aujourd'hui une lettre confiante. La minute de retard vient après, ou jamais.

Licence : OpenSky concède l'usage pour la recherche non lucrative, l'enseignement et l'évaluation interne, et exige un accord écrit préalable pour toute intégration dans un produit, service ou système automatisé en exploitation. Un usage local personnel se défend, un service hébergé non. À écrire dans le NOTICE, et les fixtures de test ne redistribuent qu'une poignée d'enregistrements, pas un extrait de base.

*Fichiers :* `flight_observation.py`, `tools.py`, `eu261.py`, `agent.py`, `test_agent.py`, `NOTICE`, `.env.example`, `README.md`

*Risque :* C'est un piège si on l'annonce comme « nous vérifions le retard », excellent si on l'annonce comme « une seconde observation, indépendante et gratuite, qui peut corroborer mais jamais contredire ». Le mot « vérifié » est banni de l'interface. Risque secondaire : la dépendance à un compte rend la fonctionnalité non reproductible pour qui clone le dépôt — d'où l'opt-in strict et les réponses figées, comme les appels Ollama déjà mockés.

## À ne pas faire

- Laisser `_allowed_claim_urls` (agent.py:1082-1084) absorber les `channel["results"][].link`. Ce sont exactement les résultats que le filtre de domaine a rejetés (tools.py:565-575, 579-590), c'est-à-dire les intermédiaires à 25-35 % que le commentaire de tools.py:558-562 dit d'exclure. C'est une propriété annoncée qui est fausse aujourd'hui.

- Étendre `_validate_claim` pour vérifier que la phrase citée par le modèle existe littéralement dans le texte extrait. Le modèle paraphrase et réaccentue : on finira par écrire un comparateur flou, donc par réintroduire du jugement là où le projet a bâti de l'exactitude à l'octet près. Retirer au modèle la main sur les URLs est moins cher et strictement plus fort.

- Injecter le règlement, un article long ou un arrêt entier dans le prompt. `draft_claim` tourne à `num_ctx: 8192` avec `num_predict: 2048` (agent.py:1050) et sérialise déjà tout `research` (agent.py:1030) ; le règlement seul fait 31 Ko de texte, soit plus que la fenêtre entière. Grain point/paragraphe, 3 unités maximum, budget de caractères compté et testé.

- Chercher un format structuré pour le règlement du côté de Formex ou XML : mesuré, `/TXT/XML/` rend une notice de métadonnées de 1,78 Mo et pas le corps de l'acte, et la manifestation Formex 4 du Cellar renvoie 404 pour 32004R0261. Le HTML est la seule voie, et six lignes de regex y trouvent déjà 19 articles sur 19.

- Monter une instance SearXNG comme backend de recherche. « Un conteneur, pas un import » est un sophisme dans un projet dont l'argument identitaire est l'absence de dépendance : c'est un service à installer, tenir et documenter, pour un script de mainteneur lancé trois fois par an. `manual` suffit.

- Surimprimer du texte à des coordonnées fixes sur le PDF officiel UE de plainte. Vérifié : PDF plat, `/AcroForm` absent, 0 `/Widget`, 0 champ `/Tx`. Un changement de mise en page mettrait silencieusement le nom du passager sur la mauvaise ligne.

- Toute soumission automatique : rejeu du `__RequestVerificationToken` d'easyJet, POST forgé, navigateur headless pilotant un formulaire de compagnie. C'est le jeton anti-CSRF lui-même qui dit non, et c'est ce qui ferait basculer le projet du côté des sociétés de recouvrement.

- Les deep-links à paramètres vers les formulaires des transporteurs : easyJet est un POST rendu serveur, TAP une SPA sans champs exploitables, et wwws.airfrance.fr n'a même pas répondu à urllib aujourd'hui (timeout). Techniquement mort, inégal, cassé au prochain déploiement.

- Récolter les attributs `name=` des formulaires pour la fiche de saisie. Le passager ne voit jamais `BookingReference` à l'écran, il voit un libellé en français : on lui livrerait une traduction à faire lui-même, dans un fichier qui se périme au prochain déploiement. Relever les libellés visibles à la main, avec l'ordre d'affichage et la date de vérification.

- Écrire le `.eml` ou le PDF, qui contiennent nom, adresse et référence de réservation, dans l'arborescence du dépôt. `app.py` se lie à 127.0.0.1 et contrôle l'en-tête Host (app.py:50-54, 143) : rendre les fichiers dans le corps de la réponse avec `Content-Disposition`, sinon « aucune donnée personnelle » devient « des données personnelles protégées par le seul .gitignore ».

- Laisser une observation ADS-B réduire ou infirmer une éligibilité. `lastSeen` est un dernier contact, pas l'ouverture des portes au sens de Germanwings C-452/13 : il sous-estime le retard de 5 à 20 minutes de roulage. Corroboration seulement ; 2 h 50 observées → `inconclusive`, jamais `not_eligible`.

- Écrire « retard vérifié » ou afficher un badge de vérification. La formulation exacte est « observation indépendante cohérente avec la déclaration ».

- Faire l'adaptateur ADS-B avant de couvrir l'annulation. C'est trois soirées de plomberie OAuth2 pour une fonctionnalité qui ne peut jamais changer une décision et qui est éteinte chez quiconque clone le dépôt, pendant que `eu261.py:530-547` répond `not_covered` au deuxième cas le plus fréquent.

- Garder SerpApi sur le chemin d'inférence, ou le remplacer par une autre API de recherche hébergée. Brave a supprimé son palier gratuit en février 2026 ; Google Custom Search JSON est fermée aux nouveaux clients depuis 2025 et s'arrête le 1er janvier 2027. Il n'y a plus de socle gratuit, et c'est précisément l'argument de la conception registre-d'abord.

- Scraper les sites de compagnies au moment de l'inférence. wwws.airfrance.fr part en timeout sur urllib aujourd'hui. On n'intègre pas une course d'armement contre la détection de bots dans un outil de réclamation.

- Ajouter reportlab, fpdf, pypdf, requests, beautifulsoup ou un client OAuth. Le prototype PDF de 833 octets et les ~30 lignes du flux client-credentials démontrent qu'aucune n'est nécessaire, et le job CI qui analyse les imports en AST casserait de toute façon.

- Bâtir un index vectoriel pour 250-300 Ko de corpus. Un BM25 lexical en Python pur suffit largement, et la contrainte réelle n'est pas la recherche mais le budget de contexte à l'injection.

- Coder un tableau de prescriptions ou de coordonnées d'ONA pour les 27 États membres à partir d'un texte extrait automatiquement d'un PDF. Curer 5 à 8 pays à la main, avec leur date de vérification, et déclarer le trou ailleurs — la doctrine que eval/ applique déjà en documentant 3 trous sur 31.

- Rendre un avis juridique personnalisé ou un pronostic de succès. L'art. 54 de la loi n° 71-1130 réserve la consultation juridique ; ce qui reste permis, et suffit ici, est l'information à caractère documentaire : citer l'article, poser l'arithmétique, laisser le passager décider.

