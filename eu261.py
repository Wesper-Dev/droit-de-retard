"""Qualification EU261 simplifiée et déterministe pour la démonstration.

Référentiel : règlement (CE) no 261/2004, vérifié le 25 juillet 2026.
Cette table ne remplace pas une analyse juridique et couvre uniquement les
cas nécessaires à la démo.
"""
from __future__ import annotations

import datetime
import re
from math import asin, cos, radians, sin, sqrt
from typing import Any
from zoneinfo import ZoneInfo

RULESET = {
    "name": "EU261 simplified demo rules",
    "verified_on": "2026-07-25",
    "source": (
        "https://europa.eu/youreurope/citizens/travel/"
        "passenger-rights/air/index_fr.htm"
    ),
}

# `eu` signifie « dans le champ géographique du règlement 261/2004 », c'est-à-dire
# l'Union européenne, l'Islande, la Norvège et la Suisse. Le Royaume-Uni en est
# sorti au Brexit et relève désormais du UK261 : ses aéroports sont donc à False.
# Cette table reste un sous-ensemble : un code absent produit `needs_information`,
# jamais une estimation approximative.
AIRPORTS = {
    # France
    "CDG": {"lat": 49.0097, "lon": 2.5479, "eu": True, "tz": "Europe/Paris"},
    "ORY": {"lat": 48.7233, "lon": 2.3794, "eu": True, "tz": "Europe/Paris"},
    "NCE": {"lat": 43.6584, "lon": 7.2159, "eu": True, "tz": "Europe/Paris"},
    "LYS": {"lat": 45.7256, "lon": 5.0811, "eu": True, "tz": "Europe/Paris"},
    "MRS": {"lat": 43.4393, "lon": 5.2214, "eu": True, "tz": "Europe/Paris"},
    "TLS": {"lat": 43.6293, "lon": 1.3638, "eu": True, "tz": "Europe/Paris"},
    "BOD": {"lat": 44.8283, "lon": -0.7156, "eu": True, "tz": "Europe/Paris"},
    "NTE": {"lat": 47.1532, "lon": -1.6107, "eu": True, "tz": "Europe/Paris"},
    # Péninsule ibérique
    "LIS": {"lat": 38.7742, "lon": -9.1342, "eu": True, "tz": "Europe/Lisbon"},
    "OPO": {"lat": 41.2481, "lon": -8.6814, "eu": True, "tz": "Europe/Lisbon"},
    "MAD": {"lat": 40.4719, "lon": -3.5626, "eu": True, "tz": "Europe/Madrid"},
    "BCN": {"lat": 41.2974, "lon": 2.0833, "eu": True, "tz": "Europe/Madrid"},
    "AGP": {"lat": 36.6749, "lon": -4.4991, "eu": True, "tz": "Europe/Madrid"},
    "PMI": {"lat": 39.5517, "lon": 2.7388, "eu": True, "tz": "Europe/Madrid"},
    # Europe de l'Ouest et du Nord
    "AMS": {"lat": 52.3105, "lon": 4.7683, "eu": True, "tz": "Europe/Amsterdam"},
    "BRU": {"lat": 50.9014, "lon": 4.4844, "eu": True, "tz": "Europe/Brussels"},
    "FRA": {"lat": 50.0379, "lon": 8.5622, "eu": True, "tz": "Europe/Berlin"},
    "MUC": {"lat": 48.3538, "lon": 11.7861, "eu": True, "tz": "Europe/Berlin"},
    "BER": {"lat": 52.3667, "lon": 13.5033, "eu": True, "tz": "Europe/Berlin"},
    "DUS": {"lat": 51.2895, "lon": 6.7668, "eu": True, "tz": "Europe/Berlin"},
    "VIE": {"lat": 48.1103, "lon": 16.5697, "eu": True, "tz": "Europe/Vienna"},
    "ZRH": {"lat": 47.4647, "lon": 8.5492, "eu": True, "tz": "Europe/Zurich"},
    "GVA": {"lat": 46.2381, "lon": 6.1090, "eu": True, "tz": "Europe/Zurich"},
    "DUB": {"lat": 53.4213, "lon": -6.2701, "eu": True, "tz": "Europe/Dublin"},
    "CPH": {"lat": 55.6180, "lon": 12.6560, "eu": True, "tz": "Europe/Copenhagen"},
    "ARN": {"lat": 59.6519, "lon": 17.9186, "eu": True, "tz": "Europe/Stockholm"},
    "OSL": {"lat": 60.1939, "lon": 11.1004, "eu": True, "tz": "Europe/Oslo"},
    "HEL": {"lat": 60.3172, "lon": 24.9633, "eu": True, "tz": "Europe/Helsinki"},
    "KEF": {"lat": 63.9850, "lon": -22.6056, "eu": True, "tz": "Atlantic/Reykjavik"},
    # Europe du Sud et de l'Est
    "FCO": {"lat": 41.8003, "lon": 12.2389, "eu": True, "tz": "Europe/Rome"},
    "MXP": {"lat": 45.6306, "lon": 8.7281, "eu": True, "tz": "Europe/Rome"},
    "NAP": {"lat": 40.8843, "lon": 14.2908, "eu": True, "tz": "Europe/Rome"},
    "ATH": {"lat": 37.9364, "lon": 23.9475, "eu": True, "tz": "Europe/Athens"},
    "PRG": {"lat": 50.1008, "lon": 14.2600, "eu": True, "tz": "Europe/Prague"},
    "WAW": {"lat": 52.1657, "lon": 20.9671, "eu": True, "tz": "Europe/Warsaw"},
    "BUD": {"lat": 47.4369, "lon": 19.2556, "eu": True, "tz": "Europe/Budapest"},
    "OTP": {"lat": 44.5711, "lon": 26.0850, "eu": True, "tz": "Europe/Bucharest"},
    # Royaume-Uni : hors champ EU261 depuis le Brexit.
    "LHR": {"lat": 51.4700, "lon": -0.4543, "eu": False, "tz": "Europe/London"},
    "LGW": {"lat": 51.1537, "lon": -0.1821, "eu": False, "tz": "Europe/London"},
    "STN": {"lat": 51.8860, "lon": 0.2389, "eu": False, "tz": "Europe/London"},
    "MAN": {"lat": 53.3537, "lon": -2.2750, "eu": False, "tz": "Europe/London"},
    "EDI": {"lat": 55.9500, "lon": -3.3725, "eu": False, "tz": "Europe/London"},
    # Hors UE
    "JFK": {"lat": 40.6413, "lon": -73.7781, "eu": False, "tz": "America/New_York"},
    "EWR": {"lat": 40.6895, "lon": -74.1745, "eu": False, "tz": "America/New_York"},
    "BOS": {"lat": 42.3656, "lon": -71.0096, "eu": False, "tz": "America/New_York"},
    "ORD": {"lat": 41.9742, "lon": -87.9073, "eu": False, "tz": "America/Chicago"},
    "MIA": {"lat": 25.7959, "lon": -80.2870, "eu": False, "tz": "America/New_York"},
    "LAX": {"lat": 33.9416, "lon": -118.4085, "eu": False, "tz": "America/Los_Angeles"},
    "SFO": {"lat": 37.6213, "lon": -122.3790, "eu": False, "tz": "America/Los_Angeles"},
    "YUL": {"lat": 45.4706, "lon": -73.7408, "eu": False, "tz": "America/Toronto"},
    "YYZ": {"lat": 43.6777, "lon": -79.6248, "eu": False, "tz": "America/Toronto"},
    "IST": {"lat": 41.2753, "lon": 28.7519, "eu": False, "tz": "Europe/Istanbul"},
    "DXB": {"lat": 25.2532, "lon": 55.3657, "eu": False, "tz": "Asia/Dubai"},
    "CMN": {"lat": 33.3675, "lon": -7.5898, "eu": False, "tz": "Africa/Casablanca"},
    "TUN": {"lat": 36.8510, "lon": 10.2272, "eu": False, "tz": "Africa/Tunis"},
    "ALG": {"lat": 36.6910, "lon": 3.2154, "eu": False, "tz": "Africa/Algiers"},
    "DKR": {"lat": 14.6700, "lon": -17.0733, "eu": False, "tz": "Africa/Dakar"},
    "ABJ": {"lat": 5.2614, "lon": -3.9263, "eu": False, "tz": "Africa/Abidjan"},
    "NRT": {"lat": 35.7720, "lon": 140.3929, "eu": False, "tz": "Asia/Tokyo"},
    "SIN": {"lat": 1.3644, "lon": 103.9915, "eu": False, "tz": "Asia/Singapore"},
    "BKK": {"lat": 13.6900, "lon": 100.7501, "eu": False, "tz": "Asia/Bangkok"},
}


# Codes pays ISO-3166 alpha-3 qui peuvent apparaître en fin de libellé. `FRA`
# est le cas critique : Francfort en IATA, la France en code pays. Sans cette
# liste, « Nice NCE, FRA » se résout en Francfort.
ISO_COUNTRY_CODES = frozenset(
    """ABW AFG AGO ALB AND ARE ARG ARM AUS AUT AZE BEL BEN BGD BGR BHR BIH BLR
    BOL BRA BRB CAN CHE CHL CHN CIV CMR COL CRI CUB CYP CZE DEU DNK DOM DZA ECU
    EGY ESP EST ETH FIN FRA GBR GEO GHA GRC GTM HKG HND HRV HUN IDN IND IRL IRN
    IRQ ISL ISR ITA JAM JOR JPN KAZ KEN KOR KWT LBN LKA LTU LUX LVA MAR MDA MEX
    MKD MLT MNE MYS NGA NLD NOR NPL NZL OMN PAK PAN PER PHL POL PRT PRY QAT ROU
    RUS RWA SAU SEN SGP SRB SVK SVN SWE SYR TCD THA TUR TWN TZA UKR URY USA UZB
    VEN VNM ZAF""".split()
)


def iata_candidates(value: str | None) -> list[str]:
    """Groupes de trois lettres du libellé, hors codes pays en position finale.

    Un libellé de la forme « Ville XXX, PAYS » est fréquent en sortie de modèle.
    Le code pays est écarté seulement lorsqu'il suit une virgule, afin de ne pas
    disqualifier un aéroport dont le code coïncide avec un code pays cité seul.
    """
    text = (value or "").upper()
    candidates = []
    for match in re.finditer(r"\b[A-Z]{3}\b", text):
        code = match.group(0)
        preceded_by_comma = re.search(r",\s*$", text[: match.start()]) is not None
        if code in ISO_COUNTRY_CODES and preceded_by_comma:
            continue
        candidates.append(code)
    return candidates


def resolve_airport(value: str | None) -> tuple[str | None, str | None]:
    """Résout un libellé libre en un seul aéroport référencé.

    Retourne `(code, motif_de_rejet)`. Le libellé vient du modèle en texte
    libre : « Nice NCE, FRA » contient deux codes référencés, et retenir le
    dernier ferait passer un Nice–Lisbonne de 250 € à un Francfort–Lisbonne de
    400 €, silencieusement et du côté qui sur-réclame. En cas d'ambiguïté, on
    pose une question au lieu de choisir.
    """
    candidates = iata_candidates(value)
    known: list[str] = []
    for code in candidates:
        if code in AIRPORTS and code not in known:
            known.append(code)
    if len(known) == 1:
        return known[0], None
    if len(known) > 1:
        return None, (
            "Le libellé contient plusieurs aéroports référencés "
            f"({', '.join(known)}) : précise lequel correspond au vol."
        )
    if candidates:
        return None, f"Aéroport non référencé : {candidates[-1]}"
    return None, "Aucun code IATA à trois lettres n'a été trouvé."


def extract_iata(value: str | None) -> str | None:
    """Retourne l'unique aéroport référencé du libellé, sinon None."""
    return resolve_airport(value)[0]


_CLOCK = re.compile(r"^\s*(\d{1,2})\s*[:hH]\s*(\d{2})\s*$")


def parse_clock(value: str | None) -> tuple[int, int] | None:
    """Lit une heure locale « 23h50 » ou « 23:50 » sans rien deviner."""
    match = _CLOCK.match(value or "")
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours, minutes


def arrival_delay_from_times(
    scheduled: str | None,
    actual: str | None,
    departure_date: str | None,
    destination: str | None,
) -> tuple[int | None, str | None]:
    """Déduit le retard à l'arrivée de deux heures locales à destination.

    Les deux horaires sont exprimés dans le même fuseau, celui de l'aéroport
    d'arrivée : leur écart ne dépend donc pas du fuseau, sauf sur deux points
    qui imposent quand même de dater le calcul. Un vol prévu à 23 h 50 et arrivé
    à 01 h 30 a 100 minutes de retard, pas moins d'un jour ; et une nuit de
    changement d'heure décale l'écart réel d'une heure par rapport à la simple
    soustraction des horloges. On construit donc des instants localisés.

    Retourne `(minutes, motif_de_rejet)`.
    """
    start = parse_clock(scheduled)
    end = parse_clock(actual)
    if start is None or end is None:
        return None, "Horaires d'arrivée prévue et réelle non exploitables."
    airport = AIRPORTS.get(destination or "")
    if airport is None:
        return None, "Fuseau de l'aéroport d'arrivée inconnu."
    try:
        day = datetime.date.fromisoformat((departure_date or "").strip())
    except ValueError:
        return None, "Date du vol absente ou non normalisée."

    zone = ZoneInfo(airport["tz"])
    scheduled_at = datetime.datetime.combine(
        day, datetime.time(*start), tzinfo=zone
    )
    actual_at = datetime.datetime.combine(day, datetime.time(*end), tzinfo=zone)
    if actual_at < scheduled_at:
        # Arrivée après minuit : le lendemain, pas la veille. La comparaison
        # porte ici sur l'horloge locale, ce qui est bien l'intention.
        actual_at += datetime.timedelta(days=1)

    # Conversion en UTC avant soustraction : quand deux datetime partagent le
    # même objet tzinfo, CPython soustrait les horloges sans corriger le
    # décalage. Une nuit de changement d'heure donnerait alors 90 minutes là où
    # le passager a réellement attendu 150.
    elapsed = actual_at.astimezone(datetime.timezone.utc) - scheduled_at.astimezone(
        datetime.timezone.utc
    )
    minutes = round(elapsed.total_seconds() / 60)
    if not 0 < minutes < 24 * 60:
        return None, "Écart d'horaires hors des bornes plausibles."
    return minutes, None


def compute_distance(origin: str, destination: str) -> float:
    """Calcule la distance orthodromique entre deux aéroports connus."""
    try:
        departure = AIRPORTS[origin]
        arrival = AIRPORTS[destination]
    except KeyError as exc:
        raise ValueError(f"Aéroport non référencé : {exc.args[0]}") from exc

    lat1, lon1, lat2, lon2 = map(
        radians,
        (
            departure["lat"],
            departure["lon"],
            arrival["lat"],
            arrival["lon"],
        ),
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(haversine))


def compensation_amount(distance_km: float, intra_eu: bool) -> int:
    """Applique le barème forfaitaire à la distance."""
    if distance_km <= 1500:
        return 250
    if intra_eu or distance_km <= 3500:
        return 400
    return 600


# Classification de la cause déclarée. L'ordre compte : un motif spécifique est
# testé avant un motif générique, « grève des contrôleurs aériens » ne devant pas
# être confondu avec « grève du personnel de la compagnie ».
#
# `low` signifie « imputable au transporteur selon la jurisprudence », donc sans
# effet exonératoire :
#   - problème technique : CJUE Wallentin-Hermann, C-549/07 ;
#   - grève du personnel propre : CJUE Krüsemann e.a., C-195/17.
# `high` signale une circonstance potentiellement extraordinaire au sens de
# l'art. 5(3). Ce n'est JAMAIS un refus : la charge de la preuve pèse sur le
# transporteur, pas sur le passager.
CAUSE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "low",
        (
            "probleme technique", "probleme mecanique", "panne", "maintenance",
            "defaut technique", "incident technique", "technical", "mechanical",
            "greve du personnel", "greve des salaries", "greve interne",
            "greve de la compagnie", "greve des pilotes", "greve des hotesses",
            "surbooking", "surreservation", "overbooking",
        ),
    ),
    (
        "high",
        (
            "meteo", "meteorologique", "tempete", "orage", "neige", "verglas",
            "brouillard", "vent violent", "cyclone", "ouragan", "weather",
            "storm", "fog", "snow",
            "greve des controleurs", "greve du controle aerien", "greve atc",
            "controle aerien", "air traffic control",
            "collision aviaire", "peril aviaire", "bird strike",
            "volcan", "cendres", "espace aerien ferme", "fermeture de l espace",
            "sureté", "surete", "securite aeroportuaire", "menace",
            "instabilite politique", "guerre",
        ),
    ),
)


def _fold(value: str) -> str:
    """Minuscule sans accents, pour comparer une cause libre à des motifs."""
    lowered = value.casefold()
    replacements = {
        "à": "a", "â": "a", "ä": "a", "é": "e", "è": "e", "ê": "e", "ë": "e",
        "î": "i", "ï": "i", "ô": "o", "ö": "o", "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
    }
    return "".join(replacements.get(char, char) for char in lowered)


def classify_cause(cause: str | None) -> str:
    """Range une cause déclarée en low, high ou unknown."""
    if not isinstance(cause, str) or not cause.strip():
        return "unknown"
    folded = _fold(cause)
    for risk, patterns in CAUSE_PATTERNS:
        if any(pattern in folded for pattern in patterns):
            return risk
    return "unknown"


def qualify_delay(
    extracted: dict[str, Any], *, reference_source_reachable: bool = False
) -> dict[str, Any]:
    """Qualifie un retard à l'arrivée sans déléguer le calcul au modèle."""
    origin, origin_problem = resolve_airport(extracted.get("origin"))
    destination, destination_problem = resolve_airport(extracted.get("destination"))
    if not origin or not destination:
        problems = [
            f"Départ : {origin_problem}" if origin_problem else "",
            f"Arrivée : {destination_problem}" if destination_problem else "",
        ]
        return {
            "status": "needs_information",
            "reason": " ".join(problem for problem in problems if problem),
            "ruleset": RULESET,
        }
    try:
        distance = compute_distance(origin, destination)
    except ValueError as exc:
        return {
            "status": "needs_information",
            "reason": str(exc),
            "ruleset": RULESET,
        }

    departure_eu = bool(AIRPORTS[origin]["eu"])
    arrival_eu = bool(AIRPORTS[destination]["eu"])
    if not departure_eu:
        return {
            "status": "needs_information" if arrival_eu else "non_eligible",
            "reason": (
                "Pour un vol arrivant dans l'UE depuis un pays tiers, le statut "
                "communautaire du transporteur doit être vérifié."
                if arrival_eu
                else "Le trajet est hors du champ géographique simplifié EU261."
            ),
            "distance_km": round(distance, 1),
            "ruleset": RULESET,
        }

    delay_minutes = extracted.get("arrival_delay_minutes")
    if delay_minutes is None:
        # Compatibilité avec les premières extractions du prototype.
        delay_minutes = extracted.get("delay_minutes")
    if delay_minutes is None:
        return {
            "status": "needs_information",
            "reason": "Le retard à l'arrivée doit être renseigné.",
            "distance_km": round(distance, 1),
            "ruleset": RULESET,
        }
    if delay_minutes < 180:
        return {
            "status": "non_eligible",
            "reason": (
                f"Le retard déclaré à l'arrivée est de {delay_minutes} minutes, "
                "sous le seuil de 180 minutes de ce prototype."
            ),
            "distance_km": round(distance, 1),
            "compensation_eur": 0,
            "rule": "Retard à l'arrivée inférieur à 3 heures.",
            "ruleset": RULESET,
        }

    intra_eu = departure_eu and arrival_eu
    amount = compensation_amount(distance, intra_eu)
    cause_risk = classify_cause(extracted.get("disruption_cause"))
    cause_note = {
        "high": (
            "La cause déclarée peut relever des circonstances extraordinaires "
            "de l'art. 5(3). Le transporteur devra le prouver ; la demande "
            "reste légitime."
        ),
        "low": (
            "La cause déclarée est en principe imputable au transporteur et "
            "n'exonère pas de l'indemnisation."
        ),
        "unknown": "La cause n'est pas renseignée ; elle sera à préciser.",
    }[cause_risk]
    return {
        # Le statut dépend de la cause déclarée, jamais de la joignabilité d'une
        # source en ligne : celle-ci est une information de provenance, pas un
        # élément de qualification juridique.
        "status": "conditional" if cause_risk == "high" else "likely",
        "right_type": "eu261_compensation",
        "reason": (
            "Le seuil de retard et la distance sont satisfaits, sous réserve "
            "de la cause, des preuves et des exceptions applicables."
        ),
        "distance_km": round(distance, 1),
        "compensation_eur": amount,
        "cause_risk": cause_risk,
        "cause_note": cause_note,
        "reference_source_reachable": reference_source_reachable,
        "rule": (
            f"Retard à l'arrivée >= 3 h ; tranche de distance donnant {amount} €."
        ),
        "ruleset": RULESET,
    }


def assess_ticket_reimbursement(
    extracted: dict[str, Any], *, reference_source_reachable: bool = False
) -> dict[str, Any]:
    """Évalue séparément le remboursement du billet pour un retard au départ."""
    disruption = extracted.get("disruption_type")
    if disruption == "cancellation":
        return {
            # Le droit au remboursement ou réacheminement de l'art. 8 s'applique
            # quelle que soit la cause : une circonstance extraordinaire exonère
            # de l'indemnisation, pas de la prise en charge.
            "status": "likely",
            "right_type": "ticket_reimbursement",
            "reason": (
                "En cas d'annulation, le passager doit pouvoir choisir entre "
                "remboursement, réacheminement ou nouvelle réservation."
            ),
            "rule": "Annulation : remboursement proposé comme option.",
            "amount_eur": None,
            "ruleset": RULESET,
        }
    if disruption != "delay":
        return {
            "status": "not_assessed",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Cette vérification couvre les retards au départ et les "
                "annulations."
            ),
            "amount_eur": None,
            "ruleset": RULESET,
        }

    departure_delay = extracted.get("departure_delay_minutes")
    if departure_delay is None:
        return {
            "status": "needs_information",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Le retard à l'arrivée ne suffit pas : indique le retard au "
                "départ pour vérifier le seuil de remboursement de 5 heures."
            ),
            "question": "Combien de retard le vol avait-il au départ ?",
            "amount_eur": None,
            "ruleset": RULESET,
        }
    if departure_delay < 300:
        return {
            "status": "non_eligible",
            "right_type": "ticket_reimbursement",
            "reason": (
                f"Le retard déclaré au départ est de {departure_delay} minutes, "
                "sous le seuil de remboursement de 300 minutes."
            ),
            "rule": "Retard au départ inférieur à 5 heures.",
            "amount_eur": 0,
            "ruleset": RULESET,
        }
    trip_completed = extracted.get("trip_completed")
    if trip_completed is None:
        return {
            "status": "needs_information",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Le seuil de 5 heures au départ est atteint. Indique si le "
                "passager a renoncé au voyage ou s'il a finalement pris le vol."
            ),
            "question": (
                "Avez-vous renoncé au voyage ou avez-vous finalement pris le vol ?"
            ),
            "amount_eur": None,
            "ruleset": RULESET,
        }
    if trip_completed:
        return {
            "status": "non_eligible",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Le vol a été pris : le remboursement du billet inutilisé lié "
                "au renoncement après 5 heures n'est pas retenu."
            ),
            "rule": "Retard au départ d'au moins 5 heures et voyage abandonné.",
            "amount_eur": 0,
            "ruleset": RULESET,
        }
    return {
        # Comme pour l'annulation, ce droit ne dépend pas de la cause ni de la
        # joignabilité d'une source en ligne.
        "status": "likely",
        "right_type": "ticket_reimbursement",
        "reason": (
            "Le retard déclaré au départ atteint 5 heures et le passager a "
            "renoncé au voyage. Le remboursement porte sur le prix du billet, "
            "qui doit être justifié."
        ),
        "rule": "Retard au départ d'au moins 5 heures et voyage abandonné.",
        "amount_eur": None,
        "ruleset": RULESET,
    }


# Droits que le règlement ouvre mais que ce moteur ne calcule pas encore. Les
# distinguer d'un `needs_information` est essentiel : aucune information
# supplémentaire du passager ne débloquerait ces cas, c'est l'implémentation qui
# manque. Les confondre laisserait croire que le dossier est complet.
UNCOVERED_CASES = {
    "cancellation": (
        "L'annulation ouvre en principe une indemnisation forfaitaire au titre "
        "des art. 5(1)(c) et 7, en plus du remboursement ou du réacheminement. "
        "Ce moteur ne la calcule pas encore : le montant n'est ni chiffré, ni "
        "demandé dans la lettre."
    ),
    "denied_boarding": (
        "Le refus d'embarquement involontaire ouvre en principe une "
        "indemnisation au titre de l'art. 4. Ce moteur ne la calcule pas "
        "encore : le montant n'est ni chiffré, ni demandé dans la lettre."
    ),
    "missed_connection": (
        "Une correspondance manquée s'apprécie sur le retard à l'arrivée finale. "
        "Ce moteur ne traite pas encore ce cas de façon distincte."
    ),
}


def qualify_case(
    extracted: dict[str, Any], *, reference_source_reachable: bool = False
) -> dict[str, Any]:
    """Route vers la qualification déterministe disponible."""
    disruption = extracted.get("disruption_type")
    if disruption == "delay":
        return qualify_delay(
            extracted, reference_source_reachable=reference_source_reachable
        )
    if disruption in UNCOVERED_CASES:
        return {
            "status": "not_covered",
            "right_type": "eu261_compensation",
            "reason": UNCOVERED_CASES[disruption],
            "uncovered_disruption": disruption,
            "ruleset": RULESET,
        }
    return {
        "status": "needs_information",
        "reason": (
            "Le type d'incident n'est pas renseigné : précise s'il s'agit d'un "
            "retard, d'une annulation ou d'un refus d'embarquement."
        ),
        "ruleset": RULESET,
    }
