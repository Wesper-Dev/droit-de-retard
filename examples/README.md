# Sorties réelles

Ces fichiers sont la sortie **verbatim** du pipeline, versionnée pour qu'on
puisse voir ce que produit l'agent sans installer Ollama ni télécharger huit
gigaoctets de modèle.

| Fichier | Contenu |
| --- | --- |
| `sample_output.json` | Réponse complète de `POST /api/analyze` sur le billet de démonstration |
| `sample_trace.json` | La seule trace d'agent, extraite du fichier ci-dessus |
| `sample_airline_policy.json` | Sortie de l'outil `retrieve_airline_policy` pour Air France |

## Scénario

Billet fictif `billet_avion_fictif.png`, compagnie inventée « Aurora Airlines »,
passagère fictive. Incident déclaré : « Le vol est arrivé avec 3 h 25 de retard
après un problème technique. »

Résultat : `ready_for_claim`, éligibilité `likely`, 250 € potentiels sur
1470,2 km, lettre produite. Function calling : trois appels demandés, zéro
rejeté.

## Ce qu'on y voit d'intéressant

**La trace montre les garde-fous en action**, y compris quand ils contredisent
le reste du dossier :

- `VRAISEMBLANCE_DATE` passe en `implausible` — le billet de démonstration est
  daté du 14 septembre 2026, donc dans le futur. L'agent le dit au lieu de
  laisser passer.
- `CORPUS_LOCAL` renvoie `not_found` : « Aurora Airlines » n'existe pas, et
  l'agent refuse d'inventer une procédure. `sample_airline_policy.json` montre
  le cas inverse, avec une vraie compagnie et ses sources datées.
- `VALIDATION_LETTRE` est à `ok` : le montant écrit par le modèle a été recoupé
  avec celui du moteur déterministe.

**L'extraction n'est pas parfaite, et on ne le cache pas.** Le champ
`destination` vaut `LIONNONE LIS` au lieu de « LISBONNE LIS » : une erreur de
lecture de Gemma sur le visuel. Le calcul reste juste parce qu'il s'appuie sur
le code IATA `LIS` et ignore le libellé — mais ce nom déformé se retrouve dans
la lettre. C'est exactement le genre de défaut qu'un harnais d'évaluation
mesurerait, et il n'existe pas encore.

## Régénérer

```bash
./demo.sh          # dans un terminal
python3 agent.py billet_avion_fictif.png \
  --incident "Le vol est arrivé avec 3 h 25 de retard après un problème technique." \
  --booking-reference FQ7T2K > examples/sample_output.json
```
