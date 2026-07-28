# Architecture cible

Plan de construction issu d'un audit à 11 agents (28 juillet 2026), sur cinq
dimensions, chacune passée au crible d'une critique adversariale avant synthèse.

**Objectif visé**, dans les termes de l'auteur : lire les billets des gens,
chercher en ligne les informations nécessaires pour préparer voire remplir la
réclamation, offrir un mode hors ligne avec repli et RAG, sur une base technique
et architecturale solide.

**Ce document est une proposition, pas un état des lieux.** Ce qui est déjà fait
vit dans [`../ROADMAP.md`](../ROADMAP.md) ; les chiffres mesurés vivent dans
[`EVALUATION.md`](EVALUATION.md).

> **Avertissement de lecture.** Les constats ci-dessous viennent d'une lecture du
> code par des agents. Plusieurs affirmations d'audit se sont révélées inexactes
> au cours de ce projet — et d'autres, exactes et graves. Avant d'agir sur un
> point, reproduis-le. Le seul défaut de ce rapport vérifié et corrigé à ce jour
> est le lot 0, la liste blanche d'URL citables.

## Fiches de conception détaillées

| Fiche | Dimension | Étapes |
| --- | --- | --- |
| [`architecture/01-lecture-fiable-des-billets.md`](architecture/01-lecture-fiable-des-billets.md) | Lecture fiable des billets réels (ingestion multimodale et extraction) — plan nettoyé après vérification adversariale du code et re-mesure sur cette machine | 10 |
| [`architecture/02-recherche-en-ligne-lire.md`](architecture/02-recherche-en-ligne-lire.md) | Recherche en ligne : lire des sources officielles au lieu d'interroger un moteur, et produire les livrables de dépôt (critique adversariale du plan initial) | 8 |
| [`architecture/03-mode-hors-ligne-complet.md`](architecture/03-mode-hors-ligne-complet.md) | Mode hors ligne complet et RAG — plan nettoyé après audit du code | 12 |
| [`architecture/04-architecture-du-code-decoupage.md`](architecture/04-architecture-du-code-decoupage.md) | Architecture du code : découpage modulaire, registre d'outils, contrainte stdlib, contrats d'erreur, stratégie de test | 15 |
| [`architecture/05-completude-produit-ce-qui.md`](architecture/05-completude-produit-ce-qui.md) | Complétude produit : ce qui manque pour qu'un vrai passager traite un vrai incident, et pas un quart du règlement — plan revu après vérification du code, efforts requalifiés. | 11 |

---

# Plan de construction — Droit de Retard

*Établi contre l'arbre actuel : `agent.py` 1531 l., `eu261.py` 573 l., `tools.py` 602 l., `test_agent.py` 1656 l. / 106 tests, `app.py` 157 l., `static/index.html` 681 l.*

---

## 1. La vision en cinq lignes

Un passager dépose un vrai billet — PDF d'e-ticket, photo de carte d'embarquement, `.pkpass` — et l'outil en tire les faits **en disant d'où vient chaque champ et lesquels sont douteux**, corrigeables sans relancer les 15 s d'extraction.
Le moteur chiffre les **quatre** types d'incident (aujourd'hui 1 sur 4, `eu261.py:530-547`), et chaque montant est adossé à un article du règlement **embarqué verbatim dans le dépôt**, pas à une paraphrase du modèle.
Il va en ligne pour **lire des URL officielles nommées à l'avance**, jamais pour interroger un moteur de recherche payant ; câble débranché, il rend le même verdict, le même montant, le même article et le même canal de dépôt, avec une date de fraîcheur.
Le modèle n'écrit ni montant, ni URL, ni article : il rédige de la prose française autour de valeurs que Python a calculées et insérées.
Le passager repart avec `lettre.txt`, `dossier.json` réimportable et `suivi.md` daté — l'outil prépare et date, il n'envoie rien.

---

## 2. L'ordre de construction

Principe d'ordonnancement, valable pour tout le plan : **on ne construit rien au-dessus d'une couche dont on ne connaît pas le taux d'erreur, et on ne livre pas une fonctionnalité qui pose des questions avant d'avoir un moyen d'y répondre.**

### Lot 0 — Réparer une propriété annoncée qui est fausse, et poser le filet · **une soirée et demie**
**Pour l'utilisateur :** aujourd'hui la lettre peut citer comme canal une URL d'intermédiaire à 30 %. `_allowed_claim_urls` (`agent.py:1080-1082`) verse dans l'ensemble citable tous les `channel["results"][].link` — or `find_claim_channel` ne renvoie ce champ que sous `unverified_channel` (`tools.py:571`) et `no_official_match` (`tools.py:585`), c'est-à-dire exactement quand le filtre de domaine officiel a **échoué**, et le commentaire de `tools.py:562-565` dit noir sur blanc que ces résultats sont dominés par les commissionnaires. Après ce lot, la propriété « toute URL citée est vérifiée » redevient vraie.
**Débloque :** tous les lots suivants réécrivent cette zone ; on part d'un état sain avec les tests de non-régression déjà écrits. Le filet (témoin JSON, CI corrigée) protège les huit lots suivants.
**Pourquoi ici :** c'est le seul défaut du dépôt qui trompe l'utilisateur *aujourd'hui*, et il se corrige en une dizaine de lignes. Tout le reste peut attendre une semaine, pas ça.

### Lot 1 — Ce que l'outil lit est vérifié par Python, pas cru sur parole · **quelques soirées**
**Pour l'utilisateur :** fin des erreurs silencieuses. Mesure du dépôt sur le même PDF : le chemin vision rend `booking_reference = RQ7T2K` (vérité `FQ7T2K`), le chemin texte rend les horaires d'embarquement et de départ **inversés** — dans les deux cas avec `uncertain_fields` vide. Un champ faux et confiant devient une lettre fausse ; un champ faux et signalé devient une question.
**Contenu :** nouveau module `extraction_checks.py` (zéro modèle, 100 % testable en CI) ; recalage sur `resolve_airport` (`eu261.py:132`) et `knowledge/carriers.json` ; typage de `uncertain_fields` en `champ:motif` produits par Python ; consommation enfin de `document_type` (déclaré `agent.py:56`, requis `agent.py:93`, consommé **nulle part**) pour répondre « ce n'est pas un justificatif de voyage ».
**Débloque :** le lot 2 (la couche texte introduit l'inversion horaire que seuls ces validateurs attrapent), le lot 3 (les champs faibles désignent quoi proposer à la correction), le lot 7 (l'erreur silencieuse n'est calculable que si « faible » est typé).
**Pourquoi ici et pas plus tard :** c'est le prérequis de la lecture de billets, et l'objectif n°1 formulé par l'utilisateur est « lire les billets des gens ».

### Lot 2 — Lire le format réel du fichier, et les sources exactes avant le modèle · **quelques soirées**
**Pour l'utilisateur :** un `.pkpass` donne nom, PNR, origine, destination, vol **sans aucune inférence** (`zipfile` + `json`). Un PDF avec couche texte est lu par `pdftotext -layout` — 11,3 s mesurées contre 15,0 s pour le rendu image actuel : le pipeline devient **plus rapide**. Et un HEIC renommé `.jpg` cesse de partir vers Ollama qui répond 400 : `app.py:103` teste aujourd'hui l'extension (`ALLOWED_SUFFIXES`, `app.py:21`), les octets trancheront.
**Contenu :** `sources.py` — `sniff_kind(bytes)`, `pdf_text_layer()` (multipage gratuit : `pdftotext` sans `-f/-l` dump déjà toutes les pages séparées par `\f`), `parse_pkpass()`, `parse_bcbp()` (offsets IATA 792). Fusion **champ par champ**, pas « la couche texte gagne ». Fixer `num_ctx: 8192` sur l'extraction : `agent.py:498` ne le pose pas alors que `transcribe_audio` (`agent.py:448`) et `draft_claim` (`agent.py:1050`) le posent.
**Dépend de :** lot 1, strictement.

### Lot 3 — Corriger un caractère sans repayer 15 secondes · **semaines**
**Pour l'utilisateur :** aujourd'hui le seul champ corrigible est la référence, via un champ **avant** analyse (`static/index.html:158`), et `process` (`agent.py:1254`) rappelle `extract_flight` puis écrase la valeur. Corriger une lettre du PNR coûte une extraction complète plus une nouvelle rédaction : 42,7 s mesurées (`docs/EVALUATION.md:87-92`). Après ce lot : le panneau de faits (`static/index.html:481`, 11 libellés en dur, lecture seule) devient éditable, et une correction coûte ~20 s.
**Contenu :** scission de `process` en `process_document()` / `process_facts()` ; `POST /api/refine` dans `app.py` (qui n'expose aujourd'hui que `/api/analyze` et `/api/transcribe`, `app.py:57`) ; cache **en mémoire** `{session_id: (extraction, research)}` ; liste blanche d'entrée revalidée par `extraction_checks`.
**Débloque :** les lots 5 et 6. Sans lui, chaque nouvelle branche juridique pose des questions auxquelles on ne peut répondre qu'en re-téléversant le billet — livrer le lot 5 avant serait une **régression d'usage**.
**Pourquoi ici :** c'est le point de non-retour ergonomique. Il touche le code le plus testé du dépôt, donc il vient après le filet du lot 0 et avant que cinq branches juridiques s'y greffent.

### Lot 4 — Le règlement dans le dépôt, le modèle sans la main sur les URL, le hors ligne réel · **semaines**
**Pour l'utilisateur :** une lettre qui cite l'alinéa applicable mot pour mot est payée plus souvent qu'une lettre qui dit « selon le règlement européen ». Et câble débranché, la lettre devient **plus** vérifiable qu'en ligne aujourd'hui, où elle ne cite que deux URL constantes (`tools.py:18-26`).
**Contenu, en quatre commits :** (a) `knowledge/regulation/eu261_fr.json` — 12 à 15 unités, **uniquement celles qu'une branche du moteur peut émettre**, avec `sha256`, URL ELI, `retrieved_on`, plus l'attribution EUR-Lex / décision 2011/833/UE dans `NOTICE` (qui n'en parle pas) ; (b) `legal_basis: [...]` émis par `eu261.py` sur la branche même qui calcule le montant — la citation devient une jointure par clé primaire, jamais un choix du modèle ; (c) `fetch_official_source(source_id)` remplace la recherche : liste blanche d'**URL**, pas de domaines, et `find_claim_channel` cesse d'aller en réseau chercher une URL déjà présente dans `knowledge/airline_policies/easyjet.json` ; (d) `DROIT_DE_RETARD_OFFLINE=1` + repli du canal lu **dans la fiche**, pas dans la sortie de `retrieve_airline_policy` (qui vide `procedures` dès `stale`, `tools.py:469-487` — le repli mourrait précisément au 91ᵉ jour).
**Dépend de :** lot 0 (zone assainie). **Débloque :** lot 5 (les seuils de l'art. 5(1)(c) et de l'art. 7(2) viennent du corpus et sont ancrés par un test), lot 6 (le PDF/`.eml` cite par identifiant).

### Lot 5 — Les quatre types d'incident chiffrés · **semaines**
**Pour l'utilisateur :** `docs/EVALUATION.md:116` dit « 1 sur 4 ». L'annulation est le cas le plus fréquent après le retard et renvoie `not_covered`. Pire : `assess_ticket_reimbursement` renvoie `not_assessed` pour `denied_boarding` (`eu261.py:446`) alors que l'art. 4(3) renvoie à l'art. 8 — donc **aucune lettre n'est produite du tout** sur le droit le plus solide du règlement.
**Ordre interne :** socle (`_scope()` extrait de `eu261.py:326-363`, `code` stable sur chaque décision, table `DECLARED_FIELDS`) → annulation → refus d'embarquement → correspondance manquée.
**Piège bloquant à traiter dans le lot :** `_derive_arrival_delay` (`agent.py:1188`) calcule le retard depuis les horaires du **premier segment**. Router `missed_connection` vers `qualify_delay` avec `destination := final_destination` sans neutraliser ce calcul produirait un retard de segment 1 qualifié à la distance finale — montant faux, silencieusement, dans les deux sens.
**Dépend de :** lots 1, 3 et 4.

### Lot 6 — Le dossier sort de la machine · **quelques soirées**
**Pour l'utilisateur :** `lettre.txt`, `dossier.json` réimportable (remplace un historique persistant), `suivi.md` daté avec la relance calculée, `relance.txt` par gabarit, « copier la lettre », `@media print` pour le PDF. Plus le **pied de lettre** — mention d'assistance automatisée, date, fondement, `RULESET.verified_on` (`eu261.py:17`) — inséré côté Python après `_validate_claim` (`agent.py:1094`). `ROADMAP.md:428` l'annonce livré en semaine 8 : `grep -n "automatis" agent.py static/index.html` ne renvoie **rien**. Cette ligne du ROADMAP est fausse et se corrige dans le même commit.
**Dépend de :** lot 4 (citation par identifiant) et impérativement du pied de lettre — distribuer des fichiers sans mention d'assistance automatisée serait le pire cas de figure.

### Lot 7 — Publier le chiffre qui manque · **quelques soirées**
**Pour l'utilisateur :** rien directement. Pour le dépôt : `docs/EVALUATION.md:125` reconnaît qu'**aucun taux d'exactitude par champ n'est mesuré sur l'extraction**. `eval/incident_cases.json` (31 cas) mesure le parseur de déclaration, pas la vision. Ce lot livre `eval/tickets/ground_truth.json` (billet existant + 2 mises en page + 6 variantes hostiles dérivées à l'exécution par `pdftoppm`/`ffmpeg`) et publie deux métriques par champ : exactitude et **taux d'erreur silencieuse**. Valeur de départ mesurée aujourd'hui : 1/1 sur les deux chemins.
**Pourquoi pas plus tôt :** il exige que « faible » soit typé (lot 1) et que les sources exactes existent (lot 2), sinon il ne mesure rien d'exploitable. **Pourquoi pas plus tard :** c'est lui qui dit s'il faut investir dans un générateur de billets, dans la relance ciblée ou dans rien du tout.
**Dans le même lot :** la provenance visible dans l'interface (`extraction_provenance` en structure **sœur** de `extraction`), bornée à six champs — vol, origine, destination, date, heure prévue, référence.

### Lot 8 — Découper le god-module · **semaines**
**Pour l'utilisateur :** rien. Pour le projet : `agent.py` porte huit responsabilités (`_chat` 311-364, ingestion 227-308 et 365-423, prompts/schémas 48-220, tâches modèle 426/464/1015, parseur de déclaration 522-728, registre+dispatch 788-1012, validation 1067-1148, orchestration 1254-1500).
**Pourquoi en dernier :** un refactor transverse fait *avant* les lots 1 à 6 serait à refaire, et il ne produit aucune ligne visible sur GitHub. Le contrepoison est appliqué dès le lot 1 : **tout code neuf va dans un module neuf** (`extraction_checks.py`, `sources.py`, `legal.py`, `claim_pack.py`), donc `agent.py` ne grossit pas pendant six lots.
**Point de vigilance chiffré :** le recensement réel des cibles de `patch` dans `test_agent.py` donne **40 substitutions d'attribut de module** (`agent.extract_flight` ×8, `agent.research_case` ×7, `agent._chat` ×7, `agent.draft_claim` ×6, `agent.verify_air_passenger_rule` ×5, `agent.find_claim_channel` ×5, `agent.retrieve_airline_policy` ×2), pas 7. Chacune devient un test vert connecté au réseau dès que son appelant déménage. Et `test_agent.py:28-50` importe 9 noms depuis `eu261` + 10 depuis `tools`, `eval/corpus.py:19-20` importe depuis les deux : sans shims temporaires à la racine, le commit « mécanique » casse 20 imports.

### Lot 9 — Optionnel, à décider sur les chiffres du lot 7 · **semaines**
`.eml` de confirmation (le format le plus hétérogène : aller **et** retour, deux langues, pieds de page marketing → si plus d'un segment détecté, on **demande**), multi-passagers (`passenger_count` dans `DECLARED_FIELDS`, jamais dans `FLIGHT_SCHEMA`), art. 9. Générateur complet de billets synthétiques : **ne se fait que si** le lot 7 montre que le classement des chemins d'ingestion dépend de la mise en page.

### Graphe de dépendances

```
Lot 0 ──┬─→ Lot 1 ──┬─→ Lot 2 ──┐
        │           │            ├─→ Lot 7 ──→ Lot 9 (conditionnel)
        │           └─→ Lot 3 ───┤
        └─→ Lot 4 ──────────────┬┴─→ Lot 5 ──→ Lot 6
                                 └─→ Lot 6
                                      Lot 8 : après 6, indépendant de 7
```

---

## 3. Le premier lot, détaillé

**Lot 0 — Assainir et poser le filet.** Cinq commits, une soirée et demie. À commencer demain sans rien rouvrir.

### Commit 1 — Refermer la fuite de la liste blanche d'URL
*Fichiers : `agent.py`, `tools.py`, `test_agent.py`*

1. Dans `_allowed_claim_urls` (`agent.py:1071-1092`), **supprimer** la boucle `for entry in channel.get("results")` (lignes 1080-1082). Garder `channel["channel"]` (1078-1079), les `rights.sources` (1074-1077) et les `procedures[].channel_url` / `.sources` (1084-1091) : ceux-là ont passé un filtre.
2. Dans `tools.py`, retirer la clé `results` des deux retours `unverified_channel` (`tools.py:568-577`) et `no_official_match` (`tools.py:578-587`). Le champ `message` porte déjà toute l'information utile.
3. Deux tests neufs : lettre citant une URL d'intermédiaire sous `unverified_channel` → violation signalée par `_validate_claim` ; idem sous `no_official_match`.

*Écrire le pourquoi dans le message de commit* : `tools.py:562-565` documente que cette requête est dominée par les commissionnaires à 25-35 %, et le code les autorisait ensuite dans la lettre.

### Commit 2 — Rendre la garantie « zéro dépendance » réellement portée par la CI
*Fichier : `.github/workflows/tests.yml`*

Ligne 42 construit déjà `LOCAL` avec `rglob("*.py")`, mais **ligne 47 itère sur `glob("*.py")`** — racine seulement. `scripts/`, `eval/` et tout module futur sont hors du garde-fou. Passer en `rglob("*.py")` avec exclusion nommée de `.venv/`, `__pycache__/` et `tmp/`. À faire **avant** que `eval/tickets/` et `sources.py` existent, sinon l'argument identitaire du dépôt cesse d'être vérifié au moment exact où le plan l'invoque.

### Commit 3 — Supprimer la branche morte `step.fallback`
*Fichiers : `static/index.html`, `test_agent.py`*

`static/index.html:405` lit `step.fallback` ; `grep '"fallback"' *.py` ne renvoie rien. Supprimer la branche JS, et ajouter le test de contrat : **les clés de trace émises ⊇ les clés lues par `static/index.html`**, extraites par regex sur le JS (11 clés de `step`, 13 clés de `data` aujourd'hui). Ce test échoue immédiatement sur `fallback` — c'est sa démonstration.

### Commit 4 — Le témoin de régression, horloge gelée
*Fichiers : `test_agent.py`, `examples/sample_output.json`*

Test qui rejoue `process()` sur `billet_avion_fictif.png` avec trois réponses `_chat` scriptées et compare à `examples/sample_output.json`.
**Deux pièges à traiter dans le commit, sans quoi le filet devient une bombe :** le fichier contient `"duration_seconds": 10.69` (mesure réelle → normaliser toutes les durées à 0 avant comparaison) et une étape `check_flight_date` dont l'issue dépend de `date.today()` face à `departure_date: 2026-09-14` (→ geler l'horloge). Sans ces deux gestes, le test devient rouge tout seul le 14 septembre 2026, dans le filet censé sécuriser six lots de refactor.

### Commit 5 — Corriger la documentation qui surestime l'état
*Fichiers : `ROADMAP.md`, `docs/EVALUATION.md`*

`ROADMAP.md:428` annonce « Pied de lettre inséré côté serveur, avec le test qui échoue s'il manque » en semaine 8 : ni l'un ni l'autre n'existent. Le déplacer en travaux prévus (lot 6). Dans un dépôt dont l'argument central est de dire ce qu'il ne sait pas faire, une feuille de route qui surestime l'état est un défaut de la même classe que la sous-réclamation qu'elle décrit.

**Critère de fin du lot 0 :** 108+ tests verts en < 0,1 s, `python -m unittest` sans réseau, et une lettre produite sous `unverified_channel` ne peut plus citer d'URL non filtrée.

---

## 4. Les arbitrages tranchés

### A. Recherche en ligne : lire des URL nommées, pas interroger un moteur
**Retenu :** `fetch_official_source(source_id)` sur une liste blanche d'**URL** dans `knowledge/sources.json`, avec marqueurs attendus, cache daté et SHA-256. **Écarté :** SerpApi sur le chemin d'inférence (conservé en outil de mainteneur, backend par défaut `none`).
**Raison, en trois faits :** (1) `verify_air_passenger_rule` (`tools.py:289-325`) ne télécharge jamais le corps d'une page — il garde `title`/`link`/`snippet` d'un intermédiaire payant ; (2) `find_claim_channel` (`tools.py:544-602`) va chercher en réseau une URL **déjà présente** dans `knowledge/airline_policies/easyjet.json` ; (3) il n'existe plus de socle de recherche hébergée gratuite — Brave a supprimé son palier gratuit en février 2026, Google Custom Search JSON est fermée aux nouveaux clients depuis 2025 et s'arrête le 1ᵉʳ janvier 2027. Une liste blanche d'URL est **strictement plus forte** qu'une liste blanche de domaines (`tools.py:272-286`).
**Écarté aussi :** monter une instance SearXNG. « Un conteneur, pas un import » est un sophisme dans un projet dont l'argument identitaire est l'absence de dépendance, pour un script lancé trois fois par an.

### B. Le seuil du RAG : jointure par clé, et les seuils écrits noir sur blanc
**Retenu :** le corpus juridique est un magasin d'unités **adressables par identifiant**, `eu261.py` émettant `legal_basis: ["art_7_1_b"]` sur la branche qui calcule le montant. Aucun retriever. **Écarté :** index vectoriel, embeddings, sqlite-vec.
**Raison chiffrée :** le corpus procédural mesure 13 595 octets et se charge en 0,090 ms ; le corpus juridique visé fait 12 à 15 unités courtes. Les seuils, à écrire dans `docs/RAG_SPEC.md` (qui existe, 70 lignes, et dont la section « Récupération MVP » impose aujourd'hui la correspondance exacte) : scan linéaire < ~200 fragments (on y est, facteur ~15), BM25 stdlib jusqu'à ~5 000, SQLite FTS5 au-delà (sqlite 3.51.0 vérifié ici, FTS5 disponible — mais option de compilation, donc contrôle à l'exécution obligatoire), embeddings **seulement si** recall@5 lexical mesuré tombe sous 0,85 avec plus de 1 000 fragments. Documenter un seuil qu'on a mesuré et qu'on ne franchit pas est un meilleur argument d'ingénierie qu'une base vectorielle.
**Corollaire non négociable :** le modèle ne choisit jamais l'article qu'il cite. Un retriever lui rendrait le pouvoir de décision que `_validate_tool_call` (`agent.py:810`) lui a retiré sur les arguments d'outil.

### C. Jusqu'où sur le remplissage : on produit des fichiers, on ne pilote pas le formulaire d'autrui
**Retenu :** `.eml` via `email.message.EmailMessage` avec `X-Unsent: 1`, `lettre.txt`, `dossier.json`, `suivi.md`, `relance.txt`, et l'impression navigateur avec `@media print` pour le PDF. **Écarté :** pré-remplissage par deep-link, POST forgé, navigateur headless, surimpression sur le PDF officiel.
**Raison, trois impasses vérifiées :** le formulaire de plainte UE est un PDF **plat** (`/AcroForm` absent, 0 `/Widget`) ; le formulaire easyJet est un POST rendu serveur protégé par `__RequestVerificationToken` — c'est le jeton anti-CSRF lui-même qui dit non ; `wwws.airfrance.fr` part en **timeout** sur `urllib` depuis ce poste. Et `@media print` coûte ~25 lignes de CSS contre 400-600 pour un générateur PDF en stdlib.
**Conséquence côté serveur :** `app.py` se lie à 127.0.0.1 et contrôle l'en-tête `Host` (`app.py:50-54`). L'export reste **intégralement côté navigateur** (`Blob` + lien `download`) ; sinon « aucune donnée personnelle » devient « des données personnelles dans le répertoire de travail, protégées par le seul `.gitignore` ».

### D. Découper `agent.py` : nouveaux modules tout de suite, extraction du god-module en dernier
**Retenu :** tout code neuf naît dans un module neuf dès le lot 1 ; l'éclatement de l'existant en paquet `droit/` est le lot 8, avec shims de compatibilité temporaires à la racine. **Écarté :** refactor d'architecture en tête de plan.
**Raison chiffrée :** treize étapes de refactor, dix à douze soirées, **zéro ligne visible** pour un visiteur GitHub ou pour un vrai billet — et il faudrait le refaire après les lots 1 à 6 qui ajoutent cinq modules. À l'inverse, les 40 substitutions d'attribut de module recensées dans `test_agent.py` doivent être traitées **avant** tout déplacement, sinon on obtient des tests verts qui appellent le réseau — panne silencieuse découverte des semaines plus tard.
**Écarté explicitement :** `domain/`/`application/`/`infrastructure/`, décorateur `@register` pour les outils (il rouvre l'espace de noms que la chaîne de `if` littérale ferme), pytest, pydantic, `mypy --strict` global sur 48 `dict[str, Any]`.

### E. Le zéro-dépendance : conservé, mais reformulé pour être vrai
**Retenu :** la revendication devient « **zéro dépendance Python à l'exécution** ; deux binaires externes optionnels, chacun avec un repli explicite et testé ». **Écarté :** Pillow, pypdf, pdfplumber, pytesseract, reportlab, requests, beautifulsoup — sur le chemin d'inférence **comme dans `eval/`**.
**Raison :** le dépôt dépend déjà de `pdftoppm` (`agent.py:229`), `ffmpeg` (`agent.py:263, 372`) et `sips` (`agent.py:269`, macOS uniquement), et `grep '_image_bytes\|_render_pdf_first_page\|_webp_as_png\|shutil.which' test_agent.py` renvoie **zéro résultat** : la couche dont dépend « lire les billets des gens » n'est couverte par aucun des 106 tests. Le repli WEBP pourrait ne fonctionner que sur macOS, et rien ne le vérifie. Ce lot ajoute `capabilities()` (sonde `shutil.which`), des `ConfigError` qui nomment le binaire **et** le repli, et des tests substituant `shutil.which` sur les six chemins d'absence.

### F. La priorité des sources se décide champ par champ, pas globalement
**Retenu :** champs à exactitude caractère par caractère (PNR, nom, n° de vol) → couche texte et BCBP dominent ; champs d'association ligne/colonne (heures, dates) → retenus **seulement** s'ils passent les validateurs déterministes ; champs à référentiel (aéroports, compagnies) → recalés par Python, le libellé lu est jeté. **Écarté :** « la couche texte gagne, la vision complète les champs nuls ».
**Raison mesurée, même PDF, même modèle :** chemin texte → PNR juste, horaires **inversés** et non nuls ; chemin vision → PNR faux, horaires justes. Aucun chemin ne domine. La règle écartée figerait l'inversion, puisque les deux champs sont non nuls et faux.

---

## 5. Ce qu'il ne faut pas faire

1. **Traiter `uncertain_fields` comme un score de confiance.** Deux mesures, deux erreurs différentes, **zéro** auto-signalement pertinent : il est vide dans les deux cas. Il est injecté par Python (`agent.py:511-514`), lu à `agent.py:1024` et `1263`, affiché comme un booléen (`static/index.html:499`). Les validateurs Python sont le juge.
2. **Rejouer N fois le même appel d'extraction pour faire de l'auto-cohérence.** À `temperature: 0` (`agent.py:498`), deux appels identiques donnent une sortie strictement identique. Seule la diversité de **modalité** produit un signal — et c'est déjà ce que fait le couple texte/vision.
3. **Coder la relance ciblée avant la mesure du lot 7.** Trois vues du même PNR ont donné trois valeurs différentes, **toutes fausses**. Une seconde lecture produit un désaccord, donc un champ faible, donc une question — le même résultat qu'en marquant le champ faible sans rien relancer, pour 10 à 15 s de plus.
4. **Convertir le HEIC.** iOS Safari transcode déjà en JPEG sur un `<input type="file">` ; `sips` n'existe pas sur ubuntu, donc la branche serait non testable en CI, pour un cas de bord. Le sniffer le reconnaît et le refuse avec un message actionnable.
5. **Écrire un décodeur PDF417 ou Aztec.** Des centaines de lignes de correction d'erreurs Reed-Solomon pour lire un code-barres dont le contenu est déjà disponible en texte dans un `.pkpass` ou une couche texte. Un parseur BCBP à décalages fixes fait ~80 lignes.
6. **Injecter le règlement ou un arrêt entier dans le prompt.** `draft_claim` sérialise **tout** le dict `research` (`agent.py:1030`) avec `num_ctx: 8192, num_predict: 2048` (`agent.py:1050`). Le règlement seul fait 31 Ko de texte ≈ 9-10 k tokens, soit plus que la fenêtre entière ; les six arrêts mesurés font 189 Ko. Grain point/paragraphe, **3 unités maximum**, budget compté et testé — le commentaire `agent.py:1046-1048` documente déjà un incident de troncature.
7. **Étendre `_validate_claim` pour vérifier qu'une phrase citée existe dans le texte.** Le modèle paraphrase et réaccentue : on finirait par écrire un comparateur flou, donc par réintroduire du jugement là où le dépôt a bâti de l'exactitude à l'octet près. Retirer au modèle la main sur les URL (`citations: [source_id]`, bloc « Sources » composé par Python) est moins cher et strictement plus fort.
8. **Accepter un bloc `research` fourni par le client dans `/api/refine`.** Il alimente `_allowed_claim_urls` (`agent.py:1071-1092`) : le client pourrait faire citer n'importe quelle URL dans la lettre. Le cache en mémoire côté `app.py` coûte ~15 lignes et ne crée aucune surface. Note : `build_research_context` (`tools.py:183-212`) filtre déjà 7 champs et tronque à 80/100 caractères, donc **ce n'est pas SerpApi qui est exposé** — c'est le prompt et la lettre.
9. **Écrire un détecteur de consignes injectées par regex** sur `disruption_cause` (recopié dans le prompt via `agent.py:1029-1034`). Sur du français libre il produira des faux positifs (« il faut que vous compreniez que… ») et une confiance imméritée. Ce qui protège est structurel : montants recalculés, URL en liste blanche, arguments d'outils recalculés.
10. **Bloquer un dossier en `needs_information` sur une information que le transporteur détient.** L'art. 5(4) met la charge de la preuve du préavis d'annulation sur lui ; le relevé d'enregistrement lui appartient aussi. Préavis inconnu → indemnisation retenue + question + note, jamais un blocage.
11. **Appliquer `cause_risk` au refus d'embarquement par symétrie.** L'art. 5(3) exonère l'annulation et, par *Sturgeon*, le retard — pas le refus, dont l'art. 4(3) est inconditionnel (CJUE *Finnair*, C-22/11). Un moteur « symétrique » transformerait le droit le plus solide en `conditional`.
12. **Dupliquer les bornes de tranche.** `_article_7_2_threshold` doit lire les **mêmes** bornes que `compensation_amount` (`eu261.py:255`), avec un test qui échoue si elles divergent. Même règle pour les marqueurs de surbooking : `CAUSE_PATTERNS` (`eu261.py:275-297`) contient déjà `surbooking`, `surreservation`, `overbooking` — un second classifieur avec sa propre liste divergerait silencieusement.
13. **Constituer un jeu de 30 à 50 vrais billets de tiers.** Donnée personnelle, déjà refusé. Et un PDF conserve sa couche texte **sous** un rectangle noir : tout caviardage se vérifie sur le contenu extrait, pas sur l'apparence. Synthétique + holdout privé dans `eval/real/` (agrégat seul publié, avec son n et sa date).
14. **Laisser un script écrire `verified_on`.** Une empreinte stable dit « les octets n'ont pas bougé » ; `verified_on` affirme « un humain a lu cette page ce jour-là ». Si la première information est utile, elle mérite `content_unchanged_on`, pas l'usurpation de la seconde.
15. **Une Action hebdomadaire de revérification des sources.** À ~25 URL dont plusieurs derrière Cloudflare, elle criera au loup chaque semaine jusqu'à être ignorée. `workflow_dispatch` manuel.
16. **Annoncer un objectif de fiches dans le README.** Publier le nombre livré. Un « objectif : 15 compagnies » sur un dépôt figé à 4 est le signal exactement inverse de celui recherché. Viser 6 fiches (Ryanair, Lufthansa, KLM), en excluant British Airways (UK261 post-Brexit) et Swiss (accord bilatéral) que `eu261.py` ne calcule pas.
17. **Envoyer la lettre, ou tenir un historique dans `localStorage`.** Le premier suppose identifiants, prestataire et responsabilité sur un envoi qui échoue en silence ; le second met nom, référence et trajet dans le profil du navigateur — l'inverse exact de l'argument de confidentialité. `dossier.json` réimportable + le système de fichiers du passager.
18. **Vider `UNCOVERED_CASES`.** Après le lot 5 il est **repointé** sur les trous restants (art. 10(2) déclassement, art. 8(3) aéroport de substitution), jamais supprimé. C'est ce mécanisme qui donne sa valeur au reste — `eval/` applique déjà la doctrine en documentant 3 trous sur 31.

---

## 6. Le critère de fin

Le projet est « fini et présentable » quand ces onze assertions sont vérifiables par un tiers qui clone le dépôt :

**Vérifiable en CI, sans réseau ni Ollama**
1. `python -m unittest` passe en < 0,2 s, sans aucune sortie réseau — garanti par un interrupteur au niveau `socket` actif par défaut sur toute la suite, pas par des mocks au niveau des fonctions.
2. Le job anti-dépendance scanne l'arborescence entière (`rglob`, exclusions nommées) et non la seule racine.
3. Un test échoue si un `legal_basis` émis par `eu261.py` n'existe pas dans `knowledge/regulation/eu261_fr.json`, **ou** si le texte de l'unité citée ne contient pas littéralement le montant appliqué (« 250 euros », « 400 euros », « 600 euros » sont dans le texte officiel — vérifié).
4. Un test échoue si une lettre sort sans son pied de mention d'assistance automatisée.
5. Un test échoue si le modèle produit une URL dans sa sortie (toute occurrence est une violation, sans exception).
6. Un test échoue si les clés de trace émises ne couvrent plus les clés lues par `static/index.html`.

**Vérifiable par une commande, sur la machine du lecteur**
7. `DROIT_DE_RETARD_OFFLINE=1 ./demo.sh` produit un dossier complet : verdict, montant, article cité verbatim, canal officiel issu du corpus local, chacun avec sa date de fraîcheur et son mode explicitement tracé.
8. Un `.pkpass` et un PDF à couche texte produisent une extraction dont les champs exacts sont marqués comme tels, sans qu'aucune valeur ne vienne du modèle.
9. Corriger un champ faux dans le panneau de faits et relancer coûte < 25 s et **zéro** appel SerpApi supplémentaire (contre 42,7 s aujourd'hui, `docs/EVALUATION.md:87-92`).

**Vérifiable dans les documents publiés**
10. `docs/EVALUATION.md` porte deux tableaux datés : « Types d'incident chiffrés : **4 sur 4** » (ligne 116, aujourd'hui « 1 sur 4 ») et un taux d'exactitude **par champ et par classe de source**, avec le **taux d'erreur silencieuse** — la case aujourd'hui déclarée vide en ligne 125. Le chiffre publié peut être mauvais ; il ne peut pas être absent.
11. Aucune ligne de `README.md` ou `ROADMAP.md` n'annonce une capacité que `grep` ne trouve pas dans le code — le contre-exemple actuel étant `ROADMAP.md:428`.

**Le test de la thèse, à passer une fois avant de déclarer fini :** débrancher Ollama et vérifier que le verdict, le montant, le fondement juridique et l'adresse d'envoi restent identiques, seule la prose disparaissant au profit d'un gabarit. Si c'est vrai, alors le modèle n'a effectivement jamais décidé — et c'est la seule affirmation du dépôt qui mérite d'être mise en avant.
