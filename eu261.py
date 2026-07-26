"""Qualification EU261 simplifiée et déterministe pour la démonstration.

Référentiel : règlement (CE) no 261/2004, vérifié le 25 juillet 2026.
Cette table ne remplace pas une analyse juridique et couvre uniquement les
cas nécessaires à la démo.
"""
from __future__ import annotations

import re
from math import asin, cos, radians, sin, sqrt
from typing import Any

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
    "CDG": {"lat": 49.0097, "lon": 2.5479, "eu": True},
    "ORY": {"lat": 48.7233, "lon": 2.3794, "eu": True},
    "NCE": {"lat": 43.6584, "lon": 7.2159, "eu": True},
    "LYS": {"lat": 45.7256, "lon": 5.0811, "eu": True},
    "MRS": {"lat": 43.4393, "lon": 5.2214, "eu": True},
    "TLS": {"lat": 43.6293, "lon": 1.3638, "eu": True},
    "BOD": {"lat": 44.8283, "lon": -0.7156, "eu": True},
    "NTE": {"lat": 47.1532, "lon": -1.6107, "eu": True},
    # Péninsule ibérique
    "LIS": {"lat": 38.7742, "lon": -9.1342, "eu": True},
    "OPO": {"lat": 41.2481, "lon": -8.6814, "eu": True},
    "MAD": {"lat": 40.4719, "lon": -3.5626, "eu": True},
    "BCN": {"lat": 41.2974, "lon": 2.0833, "eu": True},
    "AGP": {"lat": 36.6749, "lon": -4.4991, "eu": True},
    "PMI": {"lat": 39.5517, "lon": 2.7388, "eu": True},
    # Europe de l'Ouest et du Nord
    "AMS": {"lat": 52.3105, "lon": 4.7683, "eu": True},
    "BRU": {"lat": 50.9014, "lon": 4.4844, "eu": True},
    "FRA": {"lat": 50.0379, "lon": 8.5622, "eu": True},
    "MUC": {"lat": 48.3538, "lon": 11.7861, "eu": True},
    "BER": {"lat": 52.3667, "lon": 13.5033, "eu": True},
    "DUS": {"lat": 51.2895, "lon": 6.7668, "eu": True},
    "VIE": {"lat": 48.1103, "lon": 16.5697, "eu": True},
    "ZRH": {"lat": 47.4647, "lon": 8.5492, "eu": True},
    "GVA": {"lat": 46.2381, "lon": 6.1090, "eu": True},
    "DUB": {"lat": 53.4213, "lon": -6.2701, "eu": True},
    "CPH": {"lat": 55.6180, "lon": 12.6560, "eu": True},
    "ARN": {"lat": 59.6519, "lon": 17.9186, "eu": True},
    "OSL": {"lat": 60.1939, "lon": 11.1004, "eu": True},
    "HEL": {"lat": 60.3172, "lon": 24.9633, "eu": True},
    "KEF": {"lat": 63.9850, "lon": -22.6056, "eu": True},
    # Europe du Sud et de l'Est
    "FCO": {"lat": 41.8003, "lon": 12.2389, "eu": True},
    "MXP": {"lat": 45.6306, "lon": 8.7281, "eu": True},
    "NAP": {"lat": 40.8843, "lon": 14.2908, "eu": True},
    "ATH": {"lat": 37.9364, "lon": 23.9475, "eu": True},
    "PRG": {"lat": 50.1008, "lon": 14.2600, "eu": True},
    "WAW": {"lat": 52.1657, "lon": 20.9671, "eu": True},
    "BUD": {"lat": 47.4369, "lon": 19.2556, "eu": True},
    "OTP": {"lat": 44.5711, "lon": 26.0850, "eu": True},
    # Royaume-Uni : hors champ EU261 depuis le Brexit.
    "LHR": {"lat": 51.4700, "lon": -0.4543, "eu": False},
    "LGW": {"lat": 51.1537, "lon": -0.1821, "eu": False},
    "STN": {"lat": 51.8860, "lon": 0.2389, "eu": False},
    "MAN": {"lat": 53.3537, "lon": -2.2750, "eu": False},
    "EDI": {"lat": 55.9500, "lon": -3.3725, "eu": False},
    # Hors UE
    "JFK": {"lat": 40.6413, "lon": -73.7781, "eu": False},
    "EWR": {"lat": 40.6895, "lon": -74.1745, "eu": False},
    "BOS": {"lat": 42.3656, "lon": -71.0096, "eu": False},
    "ORD": {"lat": 41.9742, "lon": -87.9073, "eu": False},
    "MIA": {"lat": 25.7959, "lon": -80.2870, "eu": False},
    "LAX": {"lat": 33.9416, "lon": -118.4085, "eu": False},
    "SFO": {"lat": 37.6213, "lon": -122.3790, "eu": False},
    "YUL": {"lat": 45.4706, "lon": -73.7408, "eu": False},
    "YYZ": {"lat": 43.6777, "lon": -79.6248, "eu": False},
    "IST": {"lat": 41.2753, "lon": 28.7519, "eu": False},
    "DXB": {"lat": 25.2532, "lon": 55.3657, "eu": False},
    "CMN": {"lat": 33.3675, "lon": -7.5898, "eu": False},
    "TUN": {"lat": 36.8510, "lon": 10.2272, "eu": False},
    "ALG": {"lat": 36.6910, "lon": 3.2154, "eu": False},
    "DKR": {"lat": 14.6700, "lon": -17.0733, "eu": False},
    "ABJ": {"lat": 5.2614, "lon": -3.9263, "eu": False},
    "NRT": {"lat": 35.7720, "lon": 140.3929, "eu": False},
    "SIN": {"lat": 1.3644, "lon": 103.9915, "eu": False},
    "BKK": {"lat": 13.6900, "lon": 100.7501, "eu": False},
}


def extract_iata(value: str | None) -> str | None:
    """Retourne le dernier code IATA à trois lettres trouvé."""
    matches = re.findall(r"\b[A-Z]{3}\b", (value or "").upper())
    return matches[-1] if matches else None


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


def qualify_delay(
    extracted: dict[str, Any], *, verified_live: bool = False
) -> dict[str, Any]:
    """Qualifie un retard à l'arrivée sans déléguer le calcul au modèle."""
    origin = extract_iata(extracted.get("origin"))
    destination = extract_iata(extracted.get("destination"))
    if not origin or not destination:
        return {
            "status": "needs_information",
            "reason": "Codes IATA de départ ou d'arrivée manquants.",
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
    return {
        "status": "likely" if verified_live else "conditional",
        "right_type": "eu261_compensation",
        "reason": (
            "Le seuil de retard et la distance sont satisfaits, sous réserve "
            "de la cause, des preuves et des exceptions applicables."
        ),
        "distance_km": round(distance, 1),
        "compensation_eur": amount,
        "rule": (
            f"Retard à l'arrivée >= 3 h ; tranche de distance donnant {amount} €."
        ),
        "ruleset": RULESET,
    }


def assess_ticket_reimbursement(
    extracted: dict[str, Any], *, verified_live: bool = False
) -> dict[str, Any]:
    """Évalue séparément le remboursement du billet pour un retard au départ."""
    disruption = extracted.get("disruption_type")
    if disruption == "cancellation":
        return {
            "status": "likely" if verified_live else "conditional",
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
        "status": "likely" if verified_live else "conditional",
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


def qualify_case(
    extracted: dict[str, Any], *, verified_live: bool = False
) -> dict[str, Any]:
    """Route vers la qualification déterministe disponible."""
    disruption = extracted.get("disruption_type")
    if disruption == "delay":
        return qualify_delay(extracted, verified_live=verified_live)
    return {
        "status": "needs_information",
        "reason": (
            "Le prototype déterministe couvre pour l'instant uniquement les "
            "retards à l'arrivée."
        ),
        "ruleset": RULESET,
    }
