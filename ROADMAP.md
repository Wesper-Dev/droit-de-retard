# Feuille de route — remise à plat

Document de travail issu d'un audit à 13 agents (26 juillet 2026), sur six
dimensions : architecture, viabilité produit, vitrine GitHub, profondeur IA,
conformité juridique et roadmap fonctionnelle.

**Convention de lecture.** ✅ = reproduit et vérifié dans le code de ce dépôt.
⚠️ = constat d'audit crédible mais non revérifié individuellement. Ne traite
jamais un ⚠️ comme acquis sans le reproduire d'abord.

---

## 1. Où on en est

Le hackathon est terminé. Le projet passe en mode long terme, avec deux
objectifs : **une vitrine GitHub crédible**, et l'évaluation honnête d'une
éventuelle suite entrepreneuriale.

État réel du code : extraction multimodale Gemma 4 en JSON strict, function
calling natif Ollama à trois outils, moteur EU261 déterministe (61 aéroports),
corpus procédural local de 3 compagnies, dictée vocale locale, 47 tests.
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

Priorité absolue. Tant que ces points sont là, la CI et les captures décorent
un discours faux. Un lecteur technique les trouve en dix minutes de `grep`.

### 3.1 ✅ `verified_live` ne vérifie rien

`_filter_official_rule_sources` (`tools.py`) teste seulement que l'URL
retournée par SerpApi *ressemble* à une page `europa.eu` — hostname, préfixe et
suffixe de chemin. **La page n'est jamais téléchargée.** Ce booléen pilote
pourtant `"likely" if verified_live else "conditional"` dans `eu261.py` : le
niveau de confiance juridique est branché sur un test de connectivité.

*Correctif :* renommer en `reference_source_reachable`, le sortir du calcul de
statut, propager dans l'UI et les tests. ~1 h.

### 3.2 ✅ Le montant de la lettre n'est jamais recoupé

`estimated_compensation_eur` n'apparaît que dans `CLAIM_SCHEMA` et
`CLAIM_SYSTEM`. Aucune ligne ne le compare à `qualification["compensation_eur"]`.
L'UI affiche le montant déterministe, mais c'est `letter_body` que
l'utilisateur envoie.

*Correctif :* validation post-génération en Python — montant identique au
moteur, tout nombre suivi de `€` dans l'ensemble autorisé, URL en allow-list.
C'est le pendant exact de `_validate_tool_call`. Une soirée.

### 3.3 ✅ `disruption_cause` est extrait puis ignoré

Trois occurrences, toutes dans `agent.py` (schéma, liste des requis,
affectation depuis la dictée). **Zéro dans `eu261.py`.** Un passager qui déclare
« 3 h de retard à cause de la météo » se voit annoncer 400 €, alors que les
circonstances extraordinaires exonèrent le transporteur.

*Correctif :* table `cause_risk` — `high` pour météo, grève ATC, sûreté ;
`low` pour panne technique (CJUE Wallentin-Hermann C-549/07) et grève du
personnel propre (Krüsemann C-195/17) ; `unknown` par défaut. **Ne jamais
transformer `high` en refus** : la charge de la preuve pèse sur le
transporteur. Deux soirées avec les tests.

### 3.4 ✅ Le moteur ne traite qu'un cas EU261 sur quatre

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

---

## 4. Dette technique — à traiter avant d'ajouter quoi que ce soit

### 4.1 ✅ `extract_iata` prend le dernier code à trois lettres

```
extract_iata('Nice NCE, FRA')                    -> 'FRA'
extract_iata('Aéroport Charles de Gaulle, FRA')  -> 'FRA'
extract_iata('Milan MXP, ITA')                   -> 'ITA'

CDG -> LIS = 1470 km -> 250 €
FRA -> LIS = 1874 km -> 400 €      même vol, libellé différent, +150 €
```

`origin` vient de Gemma en texte libre. Défaillance silencieuse, plausible, et
du côté qui **sur-réclame**. Aucun des 47 tests ne couvre une chaîne à
plusieurs tokens majuscules.

*Correctif :* n'accepter un code que s'il appartient à `AIRPORTS` **et** est
unique, sinon `None` → `needs_information` ; ignorer les faux amis ISO-3166
après virgule. 15 cas paramétrés. Une heure.

### 4.2 ✅ `merge_incident_statement` ignore la négation

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

### 4.3 ⚠️ `scheduled_arrival` / `actual_arrival` extraits et lus par personne

Les deux horaires qui donneraient le retard par soustraction dorment dans le
JSON pendant que le regex se trompe.

*Prérequis honnête :* ajouter un champ `tz` (identifiant IANA) aux 61 entrées
d'`AIRPORTS` et normaliser en UTC avec `zoneinfo`. Sans ça, un CDG–LIS a une
heure d'écart artificielle et un passage de minuit donne un retard négatif.
C'est le prérequis de **tout** ce qui touche aux horaires.

### 4.4 ⚠️ `_chat` ne respecte pas son contrat d'erreur

`json.load(response)` est dans le `try` alors que les `except` ne couvrent que
`HTTPError` et `URLError`. Un `JSONDecodeError` traverse `research_case` (qui
ne rattrape qu'`AgentError`) et, comme il hérite de `ValueError`, `app.py`
renvoie un **HTTP 400** — une erreur serveur présentée comme une faute de
l'utilisateur. Les deux pannes les plus probables (Ollama qui recharge un
modèle, proxy qui répond du HTML) ne déclenchent pas le fallback qui est
l'argument central de robustesse.

*Correctif :* ajouter `json.JSONDecodeError`, `TimeoutError`, `OSError` ; un
test par famille.

### 4.5 ⚠️ `process()` perd une question

Avec un aéroport hors des 61 entrées, `qualify_case` et
`assess_ticket_reimbursement` produisent chacun une question, mais seule celle
de la qualification remonte. Le passager est mis dans une impasse.

*Correctif :* concaténer et dédupliquer toutes les `question`/`reason` non
nulles. Trois lignes.

### 4.6 ⚠️ `find_claim_channel` publie le premier résultat Google brut

`results[0]["link"]`, aucun filtre — alors que `_filter_official_rule_sources`
impose un hostname exact deux cents lignes plus haut. Et `draft_claim`
sérialise le dict `research` **entier** dans le prompt, avec `CLAIM_SYSTEM` qui
ordonne de citer le `channel_url` tel quel.

La requête `"{airline} site officiel formulaire réclamation retard vol"` est
dominée en publicité par AirHelp et Flightright : **le produit peut désigner
comme canal officiel un intermédiaire qui prélève 25 à 35 %, dans la lettre que
l'utilisateur envoie.**

*Correctif :* allow-list de domaines, à payer avec 4.7.

### 4.7 ⚠️ `_match_policy` est une égalité stricte

`'Air France KLM'`, `'AirFrance'`, `'TAP Portugal'`, `'easyJet Europe'` → `None`.
Et la fiche easyJet liste `EZY/EJU/EZS`, qui sont des codes **OACI** : le code
IATA d'easyJet est `U2`, celui imprimé sur le billet.

*Correctif :* `knowledge/carriers.json` — IATA + OACI + raisons sociales +
filiales + domaine officiel. Le champ domaine sert d'allow-list à 4.6, les deux
chantiers se paient ensemble.

### 4.8 ⚠️ `app.py` : deux vérifications, vingt lignes

Valider `Host ∈ {127.0.0.1:port, localhost:port}` (tue le DNS rebinding, qui
permet aujourd'hui à un site tiers de lire l'extraction nominative renvoyée par
l'API locale) et exiger `Content-Type: application/json` en POST (force un
préflight, tue le CSRF sur le quota SerpApi). Plus un `traceback.print_exc()`
avant le 500, dont le message invite à consulter un terminal où rien n'est écrit.

### 4.9 ⚠️ Une fiche périmée est servie comme valide

La fraîcheur est calculée mais jamais appliquée : `status: "found"` avec toutes
les procédures, quelle que soit l'ancienneté. Les trois fiches portent
`recheck_after: 2026-10-23`. **Le 24 octobre 2026, le dépôt déclarera son
propre corpus périmé tout en continuant à dicter les démarches.**

*Correctif :* dégrader en `needs_verification` sans étapes, plus un test
anti-pourrissement.

### 4.10 ⚠️ Aucun contrôle de vraisemblance sur la date

Le billet de démo est daté du **14 septembre 2026**, soit dans le futur, et
passe sans un mot.

---

## 5. Vitrine GitHub — ordre d'exécution

- [x] Sortir les billets du dépôt, `.gitignore` en liste blanche médias
- [x] Dépôt personnel `Wesper-Dev/droit-de-retard`, historique complet
- [ ] **`LICENSE` Apache-2.0 + `NOTICE`** — sans licence, « tous droits
      réservés » : personne ne peut forker. Le `NOTICE` reprend les Gemma Terms
      of Use, le modèle n'étant pas sous Apache.
- [ ] **`.github/workflows/tests.yml` + badge** — la suite tourne en 0,04 s,
      sans réseau ni Ollama ni dépendance. Matrice 3.10 → 3.13, ce qui tranche
      au passage l'affirmation jamais vérifiée du README. Un seul badge.
- [ ] **Réconcilier les chiffres** — 32 tests annoncés dans `PLAN.md`,
      `RAPPORT_*.md`, `SCRIPT_VIDEO_3MIN.md` ; 47 dans `README.md` ; réel : 47.
      Port 7860 dans `AUDIT_UI.md`, `PLAN.md`, `SCRIPT_VIDEO.md` et surtout
      `WRITEUP_KAGGLE.md` — le document anglais, donc celui que suit un lecteur
      international — contre 7865 réel. La première commande du visiteur échoue
      dans le document le mieux écrit du dépôt. Créer `docs/EVALUATION.md`
      comme point de vérité unique, plus un test qui verrouille le compte.
- [ ] **Section « Where to look »**, cinq lignes, permaliens figés, pointant
      `_validate_tool_call`, `_execute_research_tool`, `eu261.py` et les deux
      tests qui simulent un modèle tentant de lire `.env`. Dans un écosystème où
      la norme reste `globals()[name](**args)`, c'est l'artefact le plus citable
      du projet. Trente minutes.
- [ ] **Une capture PNG** — zéro image dans 18 fichiers `.md`, pour un produit
      dont l'élément central est une trace visuelle. Plus le lien vidéo, absent
      du README. Plus `examples/sample_output.json` et `examples/sample_trace.json`.
- [ ] **Ranger la racine** — `git mv` les artefacts d'événement dans
      `docs/hackathon/`. `PLAN.md` affiche « 34/45, 76 % » et `AUDIT_UI.md`
      « B3 reste ouvert » au-dessus du README : le visiteur conclut « inachevé »
      sur un projet qui fonctionne de bout en bout. Supprimer `chat.py` et
      `SERPAPI_AGENTS.md`. Déplacer `test_local.py` / `test_serpapi.py` vers
      `scripts/` (aucun `TestCase` dedans, mais compter trois fichiers `test_*`
      en lisant « 47 tests » fait soupçonner du remplissage).
      **Attention :** déplacer `test_agent.py` dans `tests/` casse
      `unittest discover` tel que documenté — trancher avant de commiter.
- [ ] **Corriger `demo.sh`** — dépend de `rg` (ripgrep, non installé par
      défaut) sur un dépôt qui vend « zéro dépendance » ; `open` est macOS sous
      `set -euo pipefail` ; `.venv` exigé alors que le code est stdlib ;
      `DEMO_NO_OPEN` non documenté.
- [ ] **README en anglais + `README.fr.md`** — `WRITEUP_KAGGLE.md` est déjà un
      meilleur document de présentation. **Supprimer la colonne « Commission
      0 % »** : annoncer 0 % en exigeant Ollama, 8 Go de modèle et un compte
      SerpApi payant est la phrase la plus attaquable du dépôt.
- [ ] Décider du sort de `Droit_de_Retard_Pitch.pptx` — 66 Ko de binaire, seul
      artefact dont la titularité est ambiguë (travail d'équipe).

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
| 5-6 | `eval/cases.yaml` — 25 à 30 déclarations adversariales — et `eval/run.py` avec trois taux : correct / manquant / **halluciné**. Puis §4.2 piloté par ces cas |
| 7 | §3.2 validation du montant de la lettre. §4.6 + §4.7 allow-list et `carriers.json` |
| 8 | §4.4 contrat d'erreur, §4.8 `Host` et `Content-Type`, §4.9 fiche périmée. Pied de lettre inséré côté serveur, avec le test qui échoue s'il manque |

*Livrable : un tableau de mesures publié, chiffres mauvais compris, et une
lettre dont chaque montant est recoupé par le moteur.*

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
| 12 | `ingest.py` + `llm.py` extraits, `agent.py` en façade. `eval/baseline_monoprompt.py` — le chiffre que `WRITEUP_KAGGLE.md` annonce lui-même comme manquant. README anglais |

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
