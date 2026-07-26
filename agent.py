"""Pipeline local-first pour analyser une preuve de voyage aérien.

Usage:
    .venv/bin/python agent.py billet_avion_fictif.pdf
    .venv/bin/python agent.py billet_avion_fictif.pdf \
        --incident "Le vol est arrivé avec 3 h 25 de retard."
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

from eu261 import assess_ticket_reimbursement, qualify_case
from tools import (
    OFFICIAL_RIGHTS_URL,
    REGULATION_URL,
    RESEARCH_TOOL_DEFINITIONS,
    build_research_context,
    find_claim_channel,
    retrieve_airline_policy,
    verify_air_passenger_rule,
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("DR_MODEL", "gemma4:12b")
MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_AUDIO_SECONDS = 30

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_INTEGER = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
NULLABLE_BOOLEAN = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}

FLIGHT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_type": {
            "type": "string",
            "enum": ["boarding_pass", "booking", "delay_notice", "other"],
        },
        "passenger_name": NULLABLE_STRING,
        "airline": NULLABLE_STRING,
        "flight_number": NULLABLE_STRING,
        "origin": NULLABLE_STRING,
        "destination": NULLABLE_STRING,
        "departure_date": NULLABLE_STRING,
        "scheduled_departure": NULLABLE_STRING,
        "scheduled_arrival": NULLABLE_STRING,
        "actual_arrival": NULLABLE_STRING,
        "boarding_time": NULLABLE_STRING,
        "booking_reference": NULLABLE_STRING,
        "seat": NULLABLE_STRING,
        "gate": NULLABLE_STRING,
        "disruption_type": {
            "type": "string",
            "enum": [
                "delay",
                "cancellation",
                "denied_boarding",
                "missed_connection",
                "none",
                "unknown",
            ],
        },
        "delay_minutes": NULLABLE_INTEGER,
        "arrival_delay_minutes": NULLABLE_INTEGER,
        "departure_delay_minutes": NULLABLE_INTEGER,
        "trip_completed": NULLABLE_BOOLEAN,
        "disruption_cause": NULLABLE_STRING,
        "evidence": {"type": "array", "items": {"type": "string"}},
        "uncertain_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "document_type",
        "passenger_name",
        "airline",
        "flight_number",
        "origin",
        "destination",
        "departure_date",
        "scheduled_departure",
        "scheduled_arrival",
        "actual_arrival",
        "boarding_time",
        "booking_reference",
        "seat",
        "gate",
        "disruption_type",
        "delay_minutes",
        "arrival_delay_minutes",
        "departure_delay_minutes",
        "trip_completed",
        "disruption_cause",
        "evidence",
        "uncertain_fields",
    ],
}

CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "eligibility": {
            "type": "string",
            "enum": ["likely", "uncertain", "unlikely"],
        },
        "summary": {"type": "string"},
        "estimated_compensation_eur": NULLABLE_INTEGER,
        # Chaque tableau est borné : sans maxItems, le décodage contraint laisse
        # le modèle produire une liste infinie, ce qui tronque la réponse au
        # milieu du JSON et se présente à tort comme un modèle défaillant.
        "reasoning": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "letter_subject": {"type": "string"},
        "letter_body": {"type": "string"},
        "checklist": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 12,
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "source_indices": {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": 6,
        },
    },
    "required": [
        "eligibility",
        "summary",
        "estimated_compensation_eur",
        "reasoning",
        "letter_subject",
        "letter_body",
        "checklist",
        "warnings",
        "source_indices",
    ],
}

EXTRACTION_SYSTEM = """Tu extrais des faits depuis des justificatifs de voyage.
Règles absolues :
- utilise uniquement ce qui est visible dans le document ou explicitement fourni ;
- n'invente jamais un retard, une annulation, une heure d'arrivée ou une cause ;
- distingue le retard au départ du retard à l'arrivée ; ne les déduis pas l'un
  de l'autre ;
- marque trip_completed uniquement si le voyageur dit explicitement avoir pris
  le vol ou, au contraire, avoir renoncé au voyage ;
- retourne null lorsqu'une valeur manque ;
- utilise le format ISO YYYY-MM-DD pour une date si elle est non ambiguë ;
- recopie dans evidence de courts éléments visibles qui justifient l'extraction ;
- marque dans uncertain_fields tout champ ambigu.
Le document peut être fictif. Cela ne change pas les règles d'extraction."""

CLAIM_SYSTEM = """Tu aides un passager à préparer une réclamation aérienne.
Tu ne fournis pas de conseil juridique et tu ne garantis jamais une indemnisation.
Utilise uniquement les faits et sources fournis. Cite les sources avec [n].
Les indices [n] désignent uniquement les sources juridiques de RECHERCHE :
ne cite pas un indice après un fait venant du billet ou du voyageur.
estimated_compensation_eur doit reprendre exactement compensation_eur
d'INDEMNISATION_EU261, ou null si ce droit n'est pas marqué likely ou
conditional. N'écris aucun autre montant en euros dans la lettre, et ne cite
aucune URL absente de RECHERCHE. Ne transforme jamais une source de référence
non vérifiée en règle confirmée. La lettre doit rester factuelle, polie,
demander confirmation à la compagnie et ne contenir aucun fait inventé.
Si INDEMNISATION_EU261.cause_risk vaut high, indique que le transporteur pourra
invoquer des circonstances extraordinaires et que la preuve lui incombe : ce
n'est jamais un motif de renoncer à la demande. Si cause_risk vaut low, rappelle
que la cause déclarée n'exonère en principe pas le transporteur.
Si INDEMNISATION_EU261.status vaut not_covered, écris explicitement qu'une
indemnisation forfaitaire est peut-être due mais que cet outil ne la chiffre
pas, sans avancer le moindre montant.
INDEMNISATION_EU261 et REMBOURSEMENT_BILLET sont deux décisions indépendantes :
un refus d'indemnisation n'annule pas un remboursement indiqué likely ou
conditional. La lettre ne demande que les droits marqués likely ou conditional.
Si RECHERCHE.airline_policy.status vaut found, la checklist doit reprendre les
étapes de dépôt de cette fiche et citer son channel_url tel quel, sans le
modifier. Si le statut vaut not_found, n'invente aucun formulaire ni aucune
adresse : indique seulement d'adresser la demande au transporteur."""

RESEARCH_TOOL_SYSTEM = """Tu routes un dossier aérien vers des outils.
Tu dois demander les trois outils disponibles, une fois chacun :
1. verify_air_passenger_rule pour les règles officielles ;
2. find_claim_channel pour le canal de réclamation ;
3. retrieve_airline_policy pour la procédure locale de la compagnie.
Recopie exactement les valeurs du CONTEXTE_MINIMISE dans les arguments.
N'ajoute aucune donnée, ne qualifie pas toi-même le dossier et ne réponds pas
en prose : utilise uniquement les appels d'outils."""

RESEARCH_TOOL_ORDER = (
    "verify_air_passenger_rule",
    "find_claim_channel",
    "retrieve_airline_policy",
)


class AgentError(RuntimeError):
    """Erreur attendue et présentable à l'utilisateur."""


def _render_pdf_first_page(source: Path, destination: Path) -> None:
    """Rend la première page d'un PDF en PNG avec Poppler."""
    executable = shutil.which("pdftoppm")
    if not executable:
        raise AgentError(
            "PDF non pris en charge : installe Poppler (`brew install poppler`) "
            "ou fournis une image PNG/JPEG."
        )
    prefix = destination.with_suffix("")
    environment = os.environ.copy()
    environment.setdefault("XDG_CACHE_HOME", str(destination.parent))
    completed = subprocess.run(
        [
            executable,
            "-f",
            "1",
            "-singlefile",
            "-png",
            "-r",
            "220",
            str(source),
            str(prefix),
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0 or not destination.exists():
        detail = completed.stderr.strip().splitlines()[-1:] or ["erreur inconnue"]
        raise AgentError(f"Impossible de convertir le PDF : {detail[0]}")


def _webp_as_png(document: Path) -> bytes:
    """Convertit un WEBP en PNG : Ollama refuse le WEBP avec une erreur 400."""
    converter = shutil.which("ffmpeg")
    command_for = {
        "ffmpeg": lambda source, target: [
            converter, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), str(target),
        ],
        "sips": lambda source, target: [
            converter, "-s", "format", "png", str(source), "--out", str(target),
        ],
    }
    kind = "ffmpeg"
    if converter is None:
        converter, kind = shutil.which("sips"), "sips"
    if converter is None:
        raise AgentError(
            "La lecture d'un WEBP nécessite ffmpeg sur cette machine. "
            "Convertis le billet en PNG ou JPEG."
        )
    with tempfile.TemporaryDirectory(prefix="droit-retard-image-") as folder:
        target = Path(folder) / "page.png"
        try:
            completed = subprocess.run(
                command_for[kind](document, target),
                capture_output=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise AgentError("La conversion de l'image a expiré.") from exc
        if completed.returncode or not target.is_file():
            raise AgentError("Ce fichier WEBP n'a pas pu être converti.")
        return target.read_bytes()


def _image_bytes(document: Path) -> bytes:
    suffix = document.suffix.lower()
    if suffix == ".webp":
        return _webp_as_png(document)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return document.read_bytes()
    if suffix != ".pdf":
        raise AgentError("Formats acceptés : PDF, PNG, JPG, JPEG ou WEBP.")
    with tempfile.TemporaryDirectory(prefix="droit-retard-") as directory:
        image_path = Path(directory) / "page.png"
        _render_pdf_first_page(document, image_path)
        return image_path.read_bytes()


def _chat(payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # HTTPError hérite de URLError : sans cette branche, une réponse 400
        # d'Ollama serait annoncée comme un serveur injoignable.
        try:
            detail = json.loads(exc.read()).get("error", "")
        except (ValueError, OSError):
            detail = ""
        if isinstance(detail, str) and detail.startswith("{"):
            try:
                detail = json.loads(detail).get("error", {}).get("message", detail)
            except ValueError:
                pass
        raise AgentError(
            f"Ollama a refusé la requête (HTTP {exc.code})"
            + (f" : {str(detail)[:160]}" if detail else ".")
        ) from exc
    except urllib.error.URLError as exc:
        raise AgentError(
            "Ollama est inaccessible. Vérifie qu'il est lancé et que "
            f"`{MODEL}` est installé."
        ) from exc


def _audio_as_wav(audio_bytes: bytes) -> bytes:
    """Normalise un enregistrement navigateur en WAV PCM pour Gemma 4."""
    if not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AgentError("L'enregistrement audio est vide ou trop volumineux.")
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        wav_bytes = audio_bytes
    else:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise AgentError(
                "La dictée nécessite ffmpeg sur cette machine. "
                "La saisie manuelle reste disponible."
            )
        with tempfile.TemporaryDirectory(prefix="droit-retard-audio-") as folder:
            source = Path(folder) / "recording.webm"
            target = Path(folder) / "recording.wav"
            source.write_bytes(audio_bytes)
            try:
                completed = subprocess.run(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(source),
                        "-t",
                        str(MAX_AUDIO_SECONDS),
                        "-ac",
                        "2",
                        "-ar",
                        "48000",
                        "-c:a",
                        "pcm_s16le",
                        str(target),
                    ],
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
            except subprocess.TimeoutExpired as exc:
                raise AgentError("La conversion audio a expiré.") from exc
            if completed.returncode or not target.is_file():
                raise AgentError(
                    "Format audio non reconnu. Saisis l'incident manuellement."
                )
            wav_bytes = target.read_bytes()

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as recording:
            rate = recording.getframerate()
            frames = recording.getnframes()
            duration = frames / rate if rate else 0
    except (wave.Error, EOFError) as exc:
        raise AgentError("Le fichier audio WAV est invalide.") from exc
    if not 0 < duration <= MAX_AUDIO_SECONDS + 0.5:
        raise AgentError("La dictée doit durer au maximum 30 secondes.")
    return wav_bytes


def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcrit localement une courte dictée avec Gemma 4 via Ollama."""
    wav_bytes = _audio_as_wav(audio_bytes)
    response = _chat(
        {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Transcribe the following speech segment in French "
                        "into French text. Only output the transcription, "
                        "with no newlines. When transcribing numbers, write "
                        "digits."
                    ),
                    # Ollama 0.32 détecte les WAV par leur signature dans son
                    # canal multimodal, également utilisé pour les images.
                    "images": [base64.b64encode(wav_bytes).decode("ascii")],
                }
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_ctx": 8192},
            "keep_alive": "10m",
        },
        timeout=180,
    )
    try:
        transcription = " ".join(response["message"]["content"].split()).strip()
    except (KeyError, TypeError, AttributeError) as exc:
        raise AgentError("Gemma n'a pas renvoyé de transcription.") from exc
    if not transcription:
        raise AgentError("Aucune parole n'a été reconnue.")
    if len(transcription) > 1200:
        raise AgentError("La transcription produite est anormalement longue.")
    return transcription


def extract_flight(
    document: Path, incident_text: str | None = None
) -> tuple[dict, float]:
    """Extrait un billet ou justificatif en JSON strict avec Gemma."""
    if not document.is_file():
        raise AgentError(f"Fichier introuvable : {document}")

    user_text = (
        "Analyse ce justificatif de voyage. Un billet seul ne prouve pas qu'un "
        "incident a eu lieu."
    )
    if incident_text:
        user_text += (
            "\nContexte déclaré par le voyageur, distinct du document : "
            f"{incident_text}"
        )

    started = time.perf_counter()
    response = _chat(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {
                    "role": "user",
                    "content": user_text,
                    "images": [
                        base64.b64encode(_image_bytes(document)).decode("ascii")
                    ],
                },
            ],
            "format": FLIGHT_SCHEMA,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
            "keep_alive": "10m",
        }
    )
    duration = time.perf_counter() - started
    try:
        extracted = json.loads(response["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AgentError("Gemma n'a pas renvoyé un JSON exploitable.") from exc
    # Un billet ou une inférence du modèle ne prouve jamais que le voyage a
    # été effectué ou abandonné. Seule une déclaration explicite peut fixer ce
    # fait via merge_incident_statement().
    extracted["trip_completed"] = None
    if extracted.get("booking_reference"):
        uncertain = extracted.setdefault("uncertain_fields", [])
        if "booking_reference_requires_confirmation" not in uncertain:
            uncertain.append("booking_reference_requires_confirmation")
    if incident_text:
        merge_incident_statement(extracted, incident_text)
    return extracted, duration


# Une négation ne porte que sur sa propre proposition : dans « mon vol n'a pas
# été annulé, juste 3 h de retard », le « pas » nie l'annulation, pas le retard.
NEGATION_MARKERS = ("pas ", "plus ", "jamais", "sans ", "aucun")
CLAUSE_BREAKS = (",", ";", ".", " mais ", " juste ", " seulement ", " par contre ")

# Une heure d'horloge n'est pas une durée. « arrivé à 23 h 50 » ne doit jamais
# produire 1430 minutes de retard.
CLOCK_CONTEXT = re.compile(r"\b(?:à|a|vers|au lieu de|prévue?\s+à|prevue?\s+a)\s*$")
DELAY_MARKERS = ("retard", "décalage", "decalage")

WORDED_HOURS = {
    "une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12,
}
WORDED_DURATION = re.compile(
    r"\b(" + "|".join(WORDED_HOURS) + r")\s+heures?"
    r"(?:\s+et\s+(demie?|quart))?",
)


def _clause_before(text: str, position: int, window: int = 48) -> str:
    """Fragment qui précède, tronqué à la dernière rupture de proposition."""
    fragment = text[max(0, position - window) : position]
    cut = 0
    for separator in CLAUSE_BREAKS:
        index = fragment.rfind(separator)
        if index >= 0:
            cut = max(cut, index + len(separator))
    return fragment[cut:]


def _find_unnegated(text: str, marker: str) -> int:
    """Position du premier marqueur qui n'est pas nié dans sa proposition."""
    start = 0
    while True:
        index = text.find(marker, start)
        if index < 0:
            return -1
        clause = _clause_before(text, index)
        if not any(negation in clause for negation in NEGATION_MARKERS):
            return index
        start = index + 1


def _spell_out_durations(text: str) -> str:
    """Convertit « trois heures et demie » en « 3 h 30 » avant l'analyse."""

    def replace(match: re.Match[str]) -> str:
        hours = WORDED_HOURS[match.group(1)]
        extra = {"demi": 30, "demie": 30, "quart": 15}.get(match.group(2) or "", 0)
        return f"{hours} h {extra}" if extra else f"{hours} h"

    return WORDED_DURATION.sub(replace, text)


def merge_incident_statement(extracted: dict[str, Any], statement: str) -> None:
    """Normalise les faits simples déclarés sans ajouter un tour de modèle."""
    normalized = _spell_out_durations(statement.casefold())
    extracted["trip_completed"] = None
    if _find_unnegated(normalized, "annul") >= 0:
        extracted["disruption_type"] = "cancellation"
    elif _find_unnegated(normalized, "refus") >= 0 and "embarquement" in normalized:
        extracted["disruption_type"] = "denied_boarding"
    elif _find_unnegated(normalized, "correspondance") >= 0 and (
        "rat" in normalized or "manqu" in normalized
    ):
        extracted["disruption_type"] = "missed_connection"
    elif _find_unnegated(normalized, "retard") >= 0:
        extracted["disruption_type"] = "delay"

    duration_pattern = re.compile(
        r"(?:(\d+)\s*h(?:eures?)?"
        r"(?:\s*(\d+)\s*(?:min(?:ute)?s?)?)?"
        r"|(\d+)\s*min(?:ute)?s?)"
    )
    # Premier passage : ne retenir que les durées réellement présentées comme un
    # retard. Le compte des durées retenues pilote ensuite l'attribution, sinon
    # une heure d'horloge écartée fausserait le raisonnement sur les positions.
    duration_matches = []
    for match in duration_pattern.finditer(normalized):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or match.group(3) or 0)
        delay_minutes = hours * 60 + minutes
        if not 0 < delay_minutes < 24 * 60:
            continue
        context_before = normalized[max(0, match.start() - 20) : match.start()]
        if CLOCK_CONTEXT.search(context_before):
            continue
        neighbourhood = (
            normalized[max(0, match.start() - 45) : match.start()]
            + normalized[match.end() : match.end() + 45]
        )
        if not any(marker in neighbourhood for marker in DELAY_MARKERS):
            continue
        duration_matches.append((match, delay_minutes))

    for match, delay_minutes in duration_matches:
        before = normalized[max(0, match.start() - 45) : match.start()]
        after = normalized[match.end() : match.end() + 45]
        trailing_marker = re.match(
            r"\s*(?:de\s+retard\s*)?"
            r"(?:(?:au\s+)?(?:départ|depart|décoll\w*|decoll\w*)"
            r"|(?:à|a)\s+(?:l['’]?\s*)?(?:arriv\w*|atterr\w*))",
            after,
        )
        trailing_text = trailing_marker.group(0) if trailing_marker else ""
        departure_markers = ("départ", "depart", "décoll", "decoll")
        if any(marker in trailing_text for marker in departure_markers):
            direction = "departure"
        elif "arriv" in trailing_text or "atterr" in trailing_text:
            direction = "arrival"
        else:
            departure_position = max(
                before.rfind("départ"),
                before.rfind("depart"),
                before.rfind("décoll"),
                before.rfind("decoll"),
            )
            arrival_position = max(
                before.rfind("arriv"),
                before.rfind("atterr"),
            )
            if departure_position > arrival_position:
                direction = "departure"
            elif arrival_position >= 0:
                direction = "arrival"
            elif len(duration_matches) == 1:
                direction = "arrival"
            else:
                direction = "unknown"

        if direction == "departure":
            extracted["departure_delay_minutes"] = delay_minutes
        elif direction == "arrival":
            extracted["delay_minutes"] = delay_minutes
            extracted["arrival_delay_minutes"] = delay_minutes

    known_causes = {
        "problème technique": "problème technique déclaré par le voyageur",
        "probleme technique": "problème technique déclaré par le voyageur",
        "météo": "météo déclarée par le voyageur",
        "meteo": "météo déclarée par le voyageur",
        "grève": "grève déclarée par le voyageur",
        "greve": "grève déclarée par le voyageur",
    }
    for marker, cause in known_causes.items():
        if marker in normalized:
            extracted["disruption_cause"] = cause
            break

    abandoned_trip_markers = (
        "je n'ai pas pris le vol",
        "je n’ai pas pris le vol",
        "je n'ai pas voyagé",
        "je n’ai pas voyagé",
        "je n'ai pas voyage",
        "je n’ai pas voyage",
        "j'ai renoncé",
        "j’ai renoncé",
        "j'ai renonce",
        "j’ai renonce",
        "voyage abandonné",
        "voyage abandonne",
    )
    completed_trip_markers = (
        "j'ai pris le vol",
        "j’ai pris le vol",
        "j'ai voyagé",
        "j’ai voyagé",
        "j'ai voyage",
        "j’ai voyage",
        "je suis arrivé",
        "je suis arrivée",
        "je suis arrive",
        "je suis arrivee",
    )
    if any(marker in normalized for marker in abandoned_trip_markers):
        extracted["trip_completed"] = False
    elif any(marker in normalized for marker in completed_trip_markers):
        extracted["trip_completed"] = True

    evidence = extracted.setdefault("evidence", [])
    evidence.append(f"Déclaration du voyageur (non vérifiée) : {statement}")


def route_case(extracted: dict[str, Any]) -> dict[str, Any]:
    """Choisit la prochaine étape sans laisser le modèle inventer des faits."""
    questions: list[str] = []
    missing_identity = [
        field
        for field in ("flight_number", "origin", "destination", "departure_date")
        if not extracted.get(field)
    ]
    if missing_identity:
        questions.append(
            "Le document ne permet pas d'identifier complètement le vol : "
            + ", ".join(missing_identity)
            + "."
        )

    disruption = extracted.get("disruption_type")
    if disruption in {None, "none", "unknown"}:
        questions.append(
            "Que s'est-il passé : retard, annulation, refus d'embarquement "
            "ou correspondance manquée ?"
        )
    elif (
        disruption == "delay"
        and extracted.get("arrival_delay_minutes") is None
        and extracted.get("delay_minutes") is None
    ):
        questions.append(
            "Quelle était l'heure d'arrivée réelle, ou combien de minutes de "
            "retard y avait-il à l'arrivée ?"
        )

    if questions:
        return {
            "status": "needs_information",
            "message": (
                "Le trajet est identifiable, mais les preuves sont insuffisantes "
                "pour évaluer une réclamation sans inventer."
            ),
            "questions": questions,
            "next_tool": None,
        }

    return {
        "status": "ready_for_research",
        "message": (
            "Les faits minimaux sont présents ; les règles doivent être vérifiées."
        ),
        "questions": [],
        "next_tool": "verify_air_passenger_rule",
        "search_query": (
            "official air passenger rights "
            f"{extracted.get('disruption_type')} "
            f"{extracted.get('origin')} {extracted.get('destination')}"
        ),
    }


def _expected_tool_arguments(
    tool_name: str, context: dict[str, Any]
) -> dict[str, Any]:
    """Construit les seuls arguments autorisés pour chaque outil."""
    if tool_name == "verify_air_passenger_rule":
        return {
            "disruption_type": context["disruption_type"],
            "origin": context["origin"],
            "destination": context["destination"],
            "arrival_delay_minutes": context["arrival_delay_minutes"],
            "departure_delay_minutes": context["departure_delay_minutes"],
        }
    if tool_name == "find_claim_channel":
        return {"airline": context["airline"]}
    if tool_name == "retrieve_airline_policy":
        return {
            "airline": context["airline"],
            "incident": context["policy_incident"],
        }
    raise ValueError("outil non autorisé")


def _validate_tool_call(
    tool_call: Any, context: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Valide nom et arguments sans jamais résoudre un nom arbitraire."""
    if not isinstance(tool_call, dict):
        raise ValueError("appel d'outil non structuré")
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("fonction absente")
    name = function.get("name")
    if name not in RESEARCH_TOOL_ORDER:
        raise ValueError("outil hors liste blanche")
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("arguments JSON invalides") from exc
    if not isinstance(arguments, dict):
        raise ValueError("arguments non structurés")
    expected = _expected_tool_arguments(name, context)
    if set(arguments) != set(expected):
        raise ValueError("champs d'arguments invalides")
    if arguments != expected:
        raise ValueError("arguments différents du contexte minimisé")
    return name, expected


def _execute_research_tool(
    tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Dispatche uniquement vers les trois fonctions explicitement autorisées."""
    if tool_name == "verify_air_passenger_rule":
        return verify_air_passenger_rule(arguments)
    if tool_name == "find_claim_channel":
        return find_claim_channel(arguments)
    if tool_name == "retrieve_airline_policy":
        return retrieve_airline_policy(arguments)
    raise ValueError("outil non autorisé")


def research_case(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[dict]]:
    """Laisse Gemma choisir les outils, puis sécurise et exécute chaque appel."""
    context = build_research_context(extracted)
    selector_started = time.perf_counter()
    selector_error: str | None = None
    executed: dict[str, dict[str, Any]] = {}
    selection_source: dict[str, str] = {}
    invalid_calls = 0
    requested_calls = 0
    result_round_trips = 0
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": RESEARCH_TOOL_SYSTEM},
        {
            "role": "user",
            "content": (
                "CONTEXTE_MINIMISE:\n"
                + json.dumps(context, ensure_ascii=False)
            ),
        },
    ]
    for _round in range(len(RESEARCH_TOOL_ORDER)):
        try:
            response = _chat(
                {
                    "model": MODEL,
                    "messages": messages,
                    "tools": RESEARCH_TOOL_DEFINITIONS,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0},
                    "keep_alive": "10m",
                },
                timeout=120,
            )
        except AgentError:
            selector_error = "sélection Gemma indisponible"
            break
        candidate_calls = response.get("message", {}).get("tool_calls", [])
        if not isinstance(candidate_calls, list):
            selector_error = "tool_calls non structuré"
            break
        if not candidate_calls:
            if requested_calls == 0:
                selector_error = "Gemma n'a demandé aucun outil"
            break

        valid_round_calls: list[tuple[str, dict[str, Any]]] = []
        requested_calls += len(candidate_calls)
        for tool_call in candidate_calls:
            try:
                name, arguments = _validate_tool_call(tool_call, context)
            except ValueError:
                invalid_calls += 1
                continue
            if name in executed:
                invalid_calls += 1
                continue
            executed[name] = _execute_research_tool(name, arguments)
            selection_source[name] = "gemma_tool_call"
            valid_round_calls.append((name, arguments))

        if len(executed) == len(RESEARCH_TOOL_ORDER) or not valid_round_calls:
            break

        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                    for name, arguments in valid_round_calls
                ],
            }
        )
        for name, _arguments in valid_round_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(
                        executed[name],
                        ensure_ascii=False,
                    ),
                }
            )
        result_round_trips += 1

    fallback_reason: str | None = None
    if selector_error:
        fallback_reason = selector_error
    elif invalid_calls:
        fallback_reason = f"{invalid_calls} appel(s) Gemma rejeté(s)"

    for name in RESEARCH_TOOL_ORDER:
        if name in executed:
            continue
        arguments = _expected_tool_arguments(name, context)
        executed[name] = _execute_research_tool(name, arguments)
        selection_source[name] = "deterministic_fallback"
        if fallback_reason is None:
            fallback_reason = "outil manquant dans les appels Gemma"

    rights = executed["verify_air_passenger_rule"]
    channel = executed["find_claim_channel"]
    policy = executed["retrieve_airline_policy"]
    selector_outcome = (
        "gemma_tool_calls"
        if all(
            selection_source[name] == "gemma_tool_call"
            for name in RESEARCH_TOOL_ORDER
        )
        else "deterministic_fallback"
    )
    trace = [
        {
            "step": "select_research_tools",
            "state": "SELECTION_OUTILS_GEMMA",
            "tool": "ollama.chat.tools",
            "duration_seconds": round(time.perf_counter() - selector_started, 2),
            "outcome": selector_outcome,
            "details": fallback_reason,
            "requested_tool_calls": requested_calls,
            "rejected_tool_calls": invalid_calls,
            "tool_result_round_trips": result_round_trips,
        },
        {
            "step": "verify_rule",
            "state": (
                "RECHERCHE_REGLES"
                if rights["status"] == "online"
                else "MODE_DEGRADE"
            ),
            "tool": "verify_air_passenger_rule",
            "selected_by": selection_source["verify_air_passenger_rule"],
            "outcome": rights["status"],
            "details": rights.get("reason"),
        },
        {
            "step": "find_claim_channel",
            "state": "RECHERCHE_CANAL",
            "tool": "find_claim_channel",
            "selected_by": selection_source["find_claim_channel"],
            "outcome": channel["status"],
            "details": channel.get("message"),
        },
        {
            "step": "retrieve_airline_policy",
            "state": "CORPUS_LOCAL",
            "tool": "retrieve_airline_policy",
            "selected_by": selection_source["retrieve_airline_policy"],
            "outcome": policy["status"],
            "details": policy.get("message"),
        },
    ]
    return {
        "rights": rights,
        "claim_channel": channel,
        "airline_policy": policy,
    }, trace


def draft_claim(
    extracted: dict[str, Any],
    research: dict[str, Any],
    qualification: dict[str, Any],
    reimbursement: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    """Génère un dossier prudent à partir des faits et recherches contrôlés."""
    facts_for_claim = dict(extracted)
    if "booking_reference_requires_confirmation" in extracted.get(
        "uncertain_fields", []
    ):
        facts_for_claim["booking_reference"] = None
    prompt = (
        "Prépare le dossier au format demandé.\n\n"
        f"FAITS:\n{json.dumps(facts_for_claim, ensure_ascii=False, indent=2)}\n\n"
        f"RECHERCHE:\n{json.dumps(research, ensure_ascii=False, indent=2)}\n\n"
        "INDEMNISATION_EU261:\n"
        f"{json.dumps(qualification, ensure_ascii=False, indent=2)}\n\n"
        "REMBOURSEMENT_BILLET:\n"
        f"{json.dumps(reimbursement, ensure_ascii=False, indent=2)}"
    )
    started = time.perf_counter()
    response = _chat(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": CLAIM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "format": CLAIM_SCHEMA,
            "stream": False,
            "think": False,
            # Une lettre complète plus sa checklist dépassent la fenêtre par
            # défaut : sans cela, Ollama tronque la réponse au milieu du JSON et
            # l'échec se présente comme un modèle défaillant.
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 2048},
            "keep_alive": "10m",
        }
    )
    duration = time.perf_counter() - started
    if response.get("done_reason") == "length":
        raise AgentError(
            "La rédaction a été tronquée par la limite de génération. "
            "Le dossier n'est pas exploitable ; relance l'analyse."
        )
    try:
        claim = json.loads(response["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AgentError("Gemma n'a pas produit un dossier JSON exploitable.") from exc
    return claim, duration


_EURO_AMOUNT = re.compile(r"(\d[\d\s .,]*)\s*(?:€|EUR\b|euros?\b)", re.IGNORECASE)
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'\)\],;]+")


def _allowed_claim_urls(research: dict[str, Any]) -> set[str]:
    """URLs que la lettre a le droit de citer : celles réellement récupérées."""
    allowed: set[str] = {OFFICIAL_RIGHTS_URL, REGULATION_URL}
    rights = research.get("rights") or {}
    for source in rights.get("sources") or []:
        if isinstance(source, dict) and source.get("link"):
            allowed.add(source["link"])
    channel = research.get("claim_channel") or {}
    if channel.get("channel"):
        allowed.add(channel["channel"])
    for entry in channel.get("results") or []:
        if isinstance(entry, dict) and entry.get("link"):
            allowed.add(entry["link"])
    policy = research.get("airline_policy") or {}
    for procedure in policy.get("procedures") or []:
        if procedure.get("channel_url"):
            allowed.add(procedure["channel_url"])
        for source in procedure.get("sources") or []:
            if isinstance(source, dict) and source.get("link"):
                allowed.add(source["link"])
    return allowed


def _validate_claim(
    claim: dict[str, Any],
    research: dict[str, Any],
    qualification: dict[str, Any],
    reimbursement: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Recoupe la lettre produite par Gemma avec les décisions déterministes.

    Le modèle rédige, il ne décide pas : tout montant et toute URL qu'il produit
    doivent déjà exister côté Python, sinon ils sont corrigés ou signalés. C'est
    le pendant, côté sortie, de la liste blanche appliquée aux appels d'outils.
    """
    violations: list[str] = []
    claim = dict(claim)

    engine_amount = qualification.get("compensation_eur")
    claimable = qualification.get("status") in {"likely", "conditional"}
    expected_amount = engine_amount if claimable else None
    if claim.get("estimated_compensation_eur") != expected_amount:
        violations.append(
            f"montant annoncé {claim.get('estimated_compensation_eur')!r} "
            f"remplacé par {expected_amount!r} issu du moteur"
        )
        claim["estimated_compensation_eur"] = expected_amount

    allowed_amounts = {expected_amount} if expected_amount is not None else set()
    if reimbursement.get("amount_eur"):
        allowed_amounts.add(reimbursement["amount_eur"])
    body = claim.get("letter_body") or ""
    for raw in _EURO_AMOUNT.findall(body):
        digits = re.sub(r"[^\d]", "", raw.split(",")[0].split(".")[0])
        if not digits:
            continue
        if int(digits) not in allowed_amounts:
            violations.append(
                f"montant {digits} € cité dans la lettre hors des montants "
                "calculés par le moteur"
            )

    allowed_urls = _allowed_claim_urls(research)
    texts = [body, claim.get("letter_subject") or ""]
    texts.extend(claim.get("checklist") or [])
    for text in texts:
        for url in _URL_IN_TEXT.findall(str(text)):
            if url.rstrip(".") not in allowed_urls:
                violations.append(f"URL non vérifiée citée dans la lettre : {url}")

    if violations:
        warnings = list(claim.get("warnings") or [])
        warnings.append(
            "Des éléments rédigés par le modèle ont été corrigés ou signalés "
            "après recoupement avec le calcul déterministe."
        )
        claim["warnings"] = warnings
    return claim, violations


def process(
    document: Path,
    incident_text: str | None = None,
    confirmed_booking_reference: str | None = None,
) -> dict[str, Any]:
    """Exécute l'extraction et le routage du dossier."""
    extracted, duration = extract_flight(document, incident_text)
    if confirmed_booking_reference:
        extracted["booking_reference"] = confirmed_booking_reference.strip().upper()
        extracted["uncertain_fields"] = [
            field
            for field in extracted.get("uncertain_fields", [])
            if field != "booking_reference_requires_confirmation"
        ]
    route = route_case(extracted)
    result = {
        "model": MODEL,
        "document": str(document),
        "extraction": extracted,
        "decision": route,
        "research": None,
        "qualification": None,
        "reimbursement": None,
        "refusal": None,
        "uncovered_right": None,
        "claim": None,
        "trace": [
            {
                "step": "extract_flight",
                "state": "EXTRACTION",
                "tool": "ollama.chat",
                "duration_seconds": round(duration, 2),
                "outcome": "ok",
            },
            {
                "step": "route_case",
                "state": "VALIDATION_CHAMPS",
                "tool": "deterministic_router",
                "duration_seconds": 0,
                "outcome": route["status"],
            },
        ],
    }
    if route["status"] != "ready_for_research":
        return result

    research, tool_trace = research_case(extracted)
    result["research"] = research
    result["trace"].extend(tool_trace)
    source_reachable = bool(research["rights"].get("reference_source_reachable"))
    qualification = qualify_case(
        extracted, reference_source_reachable=source_reachable
    )
    result["qualification"] = qualification
    reimbursement = assess_ticket_reimbursement(
        extracted, reference_source_reachable=source_reachable
    )
    result["reimbursement"] = reimbursement
    result["trace"].append(
        {
            "step": "qualify_eu261",
            "state": "QUALIFICATION_EU261",
            "tool": "deterministic_rules",
            "duration_seconds": 0,
            "outcome": qualification["status"],
        }
    )
    result["trace"].append(
        {
            "step": "assess_ticket_reimbursement",
            "state": "REMBOURSEMENT_BILLET",
            "tool": "deterministic_rules",
            "duration_seconds": 0,
            "outcome": reimbursement["status"],
        }
    )
    reimbursement_actionable = reimbursement["status"] in {
        "likely",
        "conditional",
    }
    if (
        qualification["status"] == "non_eligible"
        and reimbursement["status"] == "needs_information"
    ):
        result["decision"] = {
            "status": "needs_information",
            "message": (
                "L'indemnisation forfaitaire n'est pas retenue, mais une "
                "information manque pour évaluer le remboursement du billet."
            ),
            "questions": [
                reimbursement.get("question") or reimbursement["reason"]
            ],
            "next_tool": None,
        }
        return result
    if qualification["status"] == "non_eligible" and not reimbursement_actionable:
        result["decision"] = {
            "status": "non_eligible",
            "message": "Le dossier n'atteint pas le seuil d'indemnisation retenu.",
            "questions": [],
            "next_tool": None,
        }
        result["refusal"] = {
            "title": "Aucune lettre de réclamation générée",
            "explanation": qualification["reason"],
            "rule": qualification.get("rule"),
        }
        return result
    if qualification["status"] == "non_eligible" and reimbursement_actionable:
        result["decision"] = {
            "status": "ready_for_claim",
            "message": (
                "Pas d'indemnisation forfaitaire sur les faits déclarés, mais "
                "le remboursement du billet peut être demandé."
            ),
            "questions": [],
            "next_tool": None,
        }
    if qualification["status"] == "not_covered":
        # Le moteur ne sait pas chiffrer ce cas. On ne le maquille pas en
        # information manquante : le passager doit savoir qu'un droit existe
        # peut-être et que cet outil ne le calcule pas.
        result["uncovered_right"] = {
            "title": "Un droit possible n'est pas calculé par cet outil",
            "explanation": qualification["reason"],
            "disruption_type": qualification.get("uncovered_disruption"),
        }
        result["trace"].append(
            {
                "step": "flag_uncovered_right",
                "state": "DROIT_NON_COUVERT",
                "tool": "deterministic_rules",
                "duration_seconds": 0,
                "outcome": "not_covered",
                "details": qualification["reason"],
            }
        )
        if not reimbursement_actionable:
            result["decision"] = {
                "status": "not_covered",
                "message": (
                    "Cet outil ne calcule pas encore l'indemnisation pour ce "
                    "type d'incident et ne génère donc aucune lettre."
                ),
                "questions": [],
                "next_tool": None,
            }
            return result
        result["decision"] = {
            "status": "ready_for_claim",
            "message": (
                "Le remboursement du billet peut être demandé. L'indemnisation "
                "forfaitaire éventuelle n'est pas chiffrée par cet outil."
            ),
            "questions": [],
            "next_tool": None,
        }
    if qualification["status"] == "needs_information" and not reimbursement_actionable:
        result["decision"] = {
            "status": "needs_information",
            "message": "Une information manque avant la qualification EU261.",
            "questions": [qualification["reason"]],
            "next_tool": None,
        }
        return result
    if qualification["status"] == "needs_information" and reimbursement_actionable:
        # Une indemnisation non qualifiable ne doit pas effacer un remboursement
        # déjà actionnable : les deux droits restent indépendants.
        result["decision"] = {
            "status": "ready_for_claim",
            "message": (
                "L'indemnisation forfaitaire n'est pas encore qualifiable, mais "
                "le remboursement du billet peut être demandé."
            ),
            "questions": [qualification["reason"]],
            "next_tool": None,
        }

    claim, claim_duration = draft_claim(
        extracted,
        research,
        qualification,
        reimbursement,
    )
    claim, claim_violations = _validate_claim(
        claim, research, qualification, reimbursement
    )
    result["claim"] = claim
    result["trace"].append(
        {
            "step": "validate_claim",
            "state": "VALIDATION_LETTRE",
            "tool": "deterministic_rules",
            "duration_seconds": 0,
            "outcome": "corrected" if claim_violations else "ok",
            "details": " ; ".join(claim_violations) or None,
        }
    )
    if result["decision"]["status"] == "ready_for_research":
        result["decision"] = {
            "status": "ready_for_claim",
            "message": (
                "L'indemnisation a été qualifiée et le dossier de réclamation "
                "est préparé."
            ),
            "questions": (
                [reimbursement.get("question") or reimbursement["reason"]]
                if reimbursement["status"] == "needs_information"
                else []
            ),
            "next_tool": None,
        }
    result["trace"].append(
        {
            "step": "draft_claim",
            "state": (
                "REDACTION"
                if qualification["status"] == "likely"
                else "REDACTION_CONDITIONNELLE"
            ),
            "tool": "ollama.chat",
            "duration_seconds": round(claim_duration, 2),
            "outcome": "ok",
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyse locale d'un justificatif de voyage aérien."
    )
    parser.add_argument("document", type=Path)
    parser.add_argument(
        "--incident",
        help="Contexte déclaré par le voyageur, par exemple le retard à l'arrivée.",
    )
    parser.add_argument(
        "--booking-reference",
        help="Référence confirmée manuellement pour éviter une erreur de lecture.",
    )
    args = parser.parse_args()
    try:
        result = process(
            args.document,
            args.incident,
            confirmed_booking_reference=args.booking_reference,
        )
    except AgentError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
