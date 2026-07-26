"""Outils réseau compacts avec récupération explicite hors ligne."""
from __future__ import annotations

import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "knowledge" / "airline_policies"
MAX_POLICY_AGE_DAYS = 90

SERPAPI_URL = "https://serpapi.com/search.json"
OFFICIAL_RIGHTS_URL = (
    "https://europa.eu/youreurope/citizens/travel/"
    "passenger-rights/air/index_fr.htm"
)
REGULATION_URL = (
    "https://eur-lex.europa.eu/legal-content/FR/TXT/"
    "?uri=CELEX%3A32004R0261"
)


class SerpUnavailable(RuntimeError):
    """La recherche temps réel ne peut pas être exécutée."""


RESEARCH_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "verify_air_passenger_rule",
            "description": (
                "Vérifie les règles officielles de droits des passagers "
                "applicables au type d'incident, sans envoyer de donnée personnelle."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "disruption_type": {
                        "type": "string",
                        "enum": [
                            "delay",
                            "cancellation",
                            "denied_boarding",
                            "missed_connection",
                        ],
                    },
                    "origin": {"type": "string", "maxLength": 80},
                    "destination": {"type": "string", "maxLength": 80},
                    "arrival_delay_minutes": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}]
                    },
                    "departure_delay_minutes": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}]
                    },
                },
                "required": [
                    "disruption_type",
                    "origin",
                    "destination",
                    "arrival_delay_minutes",
                    "departure_delay_minutes",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_claim_channel",
            "description": (
                "Trouve le canal officiel de réclamation de la compagnie, "
                "sans envoyer les données du passager ou de sa réservation."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "airline": {"type": "string", "maxLength": 100},
                },
                "required": ["airline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_airline_policy",
            "description": (
                "Consulte le corpus procédural local de la compagnie, sans "
                "aucun accès réseau et sans donnée du passager. Décrit "
                "uniquement comment déposer une demande, jamais un droit."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "airline": {"type": "string", "maxLength": 100},
                    "incident": {
                        "type": "string",
                        "enum": [
                            "flight_delay",
                            "flight_cancellation",
                            "denied_boarding",
                            "flight_rescheduling",
                            "",
                        ],
                    },
                },
                "required": ["airline", "incident"],
            },
        },
    },
]

ALLOWED_DISRUPTIONS = {
    "delay",
    "cancellation",
    "denied_boarding",
    "missed_connection",
}

ALLOWED_POLICY_INCIDENTS = {
    "flight_delay",
    "flight_cancellation",
    "denied_boarding",
    "flight_rescheduling",
}

POLICY_INCIDENT_BY_DISRUPTION = {
    "delay": "flight_delay",
    "cancellation": "flight_cancellation",
    "denied_boarding": "denied_boarding",
    # Une correspondance manquée est documentée par les compagnies sous le
    # libellé « retard » : aucune fiche ne lui donne une procédure distincte.
    "missed_connection": "flight_delay",
}


def _dotenv_value(path: Path, names: tuple[str, ...]) -> str | None:
    """Lit une valeur autorisée d'un .env sans modifier ni afficher l'environnement."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if not separator or key.strip() not in names:
            continue
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        return value or None
    return None


def _api_key() -> str | None:
    """Privilégie l'environnement, puis le .env local non versionné."""
    environment_value = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY")
    if environment_value:
        return environment_value
    return _dotenv_value(
        Path(__file__).resolve().parent / ".env",
        ("SERPAPI_KEY", "SERPAPI_API_KEY"),
    )


def build_research_context(extracted: dict[str, Any]) -> dict[str, Any]:
    """Expose à Gemma uniquement les champs nécessaires aux outils de recherche."""
    disruption = extracted.get("disruption_type")
    if disruption not in ALLOWED_DISRUPTIONS:
        disruption = ""

    def limited_string(field: str, limit: int) -> str:
        value = extracted.get(field)
        return value.strip()[:limit] if isinstance(value, str) else ""

    def limited_minutes(field: str) -> int | None:
        value = extracted.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            return value if 0 <= value < 24 * 60 else None
        return None

    arrival_delay = limited_minutes("arrival_delay_minutes")
    if arrival_delay is None:
        arrival_delay = limited_minutes("delay_minutes")
    return {
        "disruption_type": disruption,
        "origin": limited_string("origin", 80),
        "destination": limited_string("destination", 80),
        "arrival_delay_minutes": arrival_delay,
        "departure_delay_minutes": limited_minutes("departure_delay_minutes"),
        "airline": limited_string("airline", 100),
        # Dérivé, jamais choisi par le modèle : la validation stricte des
        # arguments impose que chaque valeur vienne de ce contexte.
        "policy_incident": POLICY_INCIDENT_BY_DISRUPTION.get(disruption, ""),
    }


def web_search(query: str, num: int = 5) -> list[dict[str, str]]:
    """Recherche Google via SerpApi et limite le contexte aux champs utiles."""
    api_key = _api_key()
    if not api_key:
        raise SerpUnavailable("clé SerpApi absente")
    params = {
        "engine": "google_light",
        "q": query,
        "num": max(1, min(num, 5)),
        "hl": "fr",
        "gl": "fr",
        "api_key": api_key,
    }
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Droit-de-Retard/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload: dict[str, Any] = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise SerpUnavailable("quota SerpApi épuisé") from exc
        raise SerpUnavailable(f"SerpApi HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SerpUnavailable("recherche temps réel indisponible") from exc

    error = payload.get("error")
    if error:
        raise SerpUnavailable(str(error)[:160])
    return [
        {
            "title": result.get("title", ""),
            "link": result.get("link", ""),
            "snippet": result.get("snippet", ""),
        }
        for result in payload.get("organic_results", [])[:num]
    ]


def build_rule_query(extracted: dict[str, Any]) -> str:
    """Construit une requête sans identité ni référence de réservation."""
    context = build_research_context(extracted)
    disruption_terms = {
        "delay": "retard",
        "cancellation": "annulation",
        "denied_boarding": "refus embarquement",
        "missed_connection": "correspondance manquée",
    }
    disruption = disruption_terms.get(context["disruption_type"], "incident")
    return (
        "site:europa.eu/youreurope/citizens/travel/passenger-rights/air "
        f"droits passagers aériens {disruption}"
    ).strip()


def _filter_official_rule_sources(
    sources: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Conserve uniquement le référentiel aérien officiel de Your Europe."""
    official_path = "/youreurope/citizens/travel/passenger-rights/air/"
    filtered = []
    for source in sources:
        parsed = urllib.parse.urlparse(source.get("link", ""))
        if (
            parsed.hostname == "europa.eu"
            and parsed.path.startswith(official_path)
            and parsed.path.endswith("/index_fr.htm")
        ):
            filtered.append(source)
    return filtered


def verify_air_passenger_rule(extracted: dict[str, Any]) -> dict[str, Any]:
    """Cherche uniquement des sources institutionnelles sur le cas extrait."""
    query = build_rule_query(extracted)
    try:
        sources = _filter_official_rule_sources(web_search(query, num=5))
        if not sources:
            raise SerpUnavailable("aucune source officielle pertinente retournée")
    except SerpUnavailable as exc:
        return {
            "status": "offline",
            "reason": str(exc),
            "reference_source_reachable": False,
            "sources": [
                {
                    "title": "Droits des passagers aériens - Your Europe",
                    "link": OFFICIAL_RIGHTS_URL,
                    "snippet": (
                        "Source institutionnelle de référence à vérifier dès que "
                        "la connexion revient."
                    ),
                },
                {
                    "title": "Règlement (CE) no 261/2004",
                    "link": REGULATION_URL,
                    "snippet": (
                        "Texte réglementaire de référence ; aucune conclusion "
                        "automatique n'est tirée hors ligne."
                    ),
                },
            ],
        }
    return {
        "status": "online",
        "reason": None,
        "reference_source_reachable": True,
        "sources": sources,
    }


def _load_policy_files() -> list[dict[str, Any]]:
    """Charge les fiches locales en ignorant silencieusement un fichier illisible."""
    fiches = []
    try:
        paths = sorted(POLICY_DIR.glob("*.json"))
    except OSError:
        return fiches
    for path in paths:
        try:
            fiche = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(fiche, dict) and fiche.get("company"):
            fiches.append(fiche)
    return fiches


def _match_policy(airline: str, fiches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Correspondance exacte sur le nom ou un alias, insensible à la casse."""
    needle = airline.casefold().strip()
    if not needle:
        return None
    for fiche in fiches:
        names = [fiche.get("company", "")]
        names.extend(fiche.get("aliases") or [])
        if any(
            isinstance(name, str) and name.casefold().strip() == needle
            for name in names
        ):
            return fiche
    return None


def _policy_freshness(fiche: dict[str, Any], today: datetime.date) -> tuple[str, str | None]:
    """Renvoie fresh ou stale sans jamais présenter une fiche périmée comme à jour."""
    verified_on = (fiche.get("freshness") or {}).get("verified_on")
    if not isinstance(verified_on, str):
        return "unknown", None
    try:
        verified = datetime.date.fromisoformat(verified_on)
    except ValueError:
        return "unknown", None
    age = (today - verified).days
    return ("fresh" if 0 <= age <= MAX_POLICY_AGE_DAYS else "stale"), verified_on


def retrieve_airline_policy(extracted: dict[str, Any]) -> dict[str, Any]:
    """Lit le corpus procédural local. Aucun réseau, aucune donnée personnelle."""
    context = build_research_context(extracted)
    airline = context["airline"]
    # Appelée par le dispatcher, la fonction reçoit les arguments déjà
    # minimisés et validés ; appelée sur un dossier complet, elle dérive
    # l'incident du type d'incident extrait.
    incident = extracted.get("incident")
    if not isinstance(incident, str) or incident not in ALLOWED_POLICY_INCIDENTS:
        incident = context["policy_incident"]
    fiche = _match_policy(airline, _load_policy_files())
    if fiche is None:
        return {
            "status": "not_found",
            "source": "local_corpus",
            "company": None,
            "procedures": [],
            "message": (
                "Aucune fiche locale pour cette compagnie : le corpus couvre "
                "seulement quelques transporteurs et n'invente rien."
            ),
        }

    freshness, verified_on = _policy_freshness(fiche, datetime.date.today())
    sources_by_id = {
        source.get("id"): source
        for source in fiche.get("sources") or []
        if isinstance(source, dict)
    }
    all_procedures = [
        procedure
        for procedure in fiche.get("procedures") or []
        if isinstance(procedure, dict)
    ]
    matching = [
        procedure
        for procedure in all_procedures
        if incident and incident in (procedure.get("incidents") or [])
    ]
    # Une fiche sans procédure pour cet incident reste utile : on la rend
    # entière, en signalant qu'elle n'est pas spécifique à l'incident.
    selected = matching or all_procedures

    procedures = []
    for procedure in selected:
        channel = procedure.get("channel") or {}
        procedures.append(
            {
                "topic": procedure.get("topic"),
                "channel_label": channel.get("label"),
                "channel_url": channel.get("url"),
                "steps": procedure.get("steps") or [],
                "required_information": procedure.get("required_information") or [],
                "required_documents": procedure.get("required_documents") or [],
                "limits": procedure.get("limits") or [],
                "sources": [
                    {
                        "title": sources_by_id[source_id].get("title"),
                        "link": sources_by_id[source_id].get("url"),
                        "verified_on": sources_by_id[source_id].get("verified_on"),
                    }
                    for source_id in procedure.get("source_ids") or []
                    if source_id in sources_by_id
                ],
            }
        )

    return {
        "status": "found",
        "source": "local_corpus",
        "company": fiche.get("company"),
        "incident_specific": bool(matching),
        "freshness": freshness,
        "verified_on": verified_on,
        "legal_scope": fiche.get("legal_scope"),
        "procedures": procedures,
        "message": None,
    }


def find_claim_channel(extracted: dict[str, Any]) -> dict[str, Any]:
    """Cherche le canal officiel de réclamation de la compagnie."""
    airline = build_research_context(extracted)["airline"]
    if airline.casefold() == "aurora airlines":
        return {
            "status": "demo_carrier",
            "channel": None,
            "message": (
                "Aurora Airlines est fictive : aucun formulaire de réclamation "
                "réel ne sera inventé."
            ),
        }
    try:
        results = web_search(
            f"{airline} site officiel formulaire réclamation retard vol",
            num=3,
        )
    except SerpUnavailable as exc:
        return {
            "status": "offline",
            "channel": None,
            "message": str(exc),
        }
    return {
        "status": "online",
        "channel": results[0]["link"] if results else None,
        "results": results,
    }
