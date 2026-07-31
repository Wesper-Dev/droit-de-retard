"""Tests déterministes du routage de dossiers aériens."""
from __future__ import annotations

import ast
import datetime
import io
import json
import pathlib
import re
import unittest
from unittest.mock import patch
import wave
from zoneinfo import ZoneInfo

from agent import (
    AgentError,
    CLAIM_SCHEMA,
    _chat,
    _implausible_date,
    _pending_questions,
    _validate_claim,
    draft_claim,
    merge_incident_statement,
    process,
    research_case,
    route_case,
    transcribe_audio,
)
from eu261 import (
    AIRPORTS,
    arrival_delay_from_times,
    assess_ticket_reimbursement,
    classify_cause,
    compensation_amount,
    compute_distance,
    qualify_case,
    qualify_delay,
    resolve_airport,
)
from eval import corpus
from tools import (
    RESEARCH_TOOL_DEFINITIONS,
    _api_key,
    _is_official_url,
    build_research_context,
    build_rule_query,
    find_claim_channel,
    identify_carrier,
    official_domains,
    retrieve_airline_policy,
    verify_air_passenger_rule,
)


COMPLETE_FLIGHT = {
    "flight_number": "AU 3127",
    "origin": "Paris CDG",
    "destination": "Lisbonne LIS",
    "departure_date": "2026-09-14",
}


class AudioTranscriptionTests(unittest.TestCase):
    @staticmethod
    def wav_bytes() -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(16000)
            recording.writeframes(b"\x00\x00" * 1600)
        return output.getvalue()

    @patch("agent._chat")
    def test_transcription_uses_local_gemma_audio(self, chat):
        chat.return_value = {
            "message": {
                "content": "Le vol est arrivé avec 3 h 25 de retard.\n"
            }
        }

        transcription = transcribe_audio(self.wav_bytes())

        self.assertEqual(
            transcription,
            "Le vol est arrivé avec 3 h 25 de retard.",
        )
        payload = chat.call_args.args[0]
        self.assertEqual(payload["model"], "gemma4:12b")
        self.assertFalse(payload["think"])
        self.assertEqual(len(payload["messages"][0]["images"]), 1)
        self.assertNotIn("audios", payload["messages"][0])

    def test_transcription_rejects_invalid_audio(self):
        with self.assertRaises(AgentError):
            transcribe_audio(b"pas un enregistrement")


class RouteCaseTests(unittest.TestCase):
    def test_ticket_without_disruption_requests_context(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
        }

        decision = route_case(extracted)

        self.assertEqual(decision["status"], "needs_information")
        self.assertIsNone(decision["next_tool"])
        self.assertIn("Que s'est-il passé", decision["questions"][0])

    def test_delay_without_duration_requests_arrival_delay(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "delay",
            "delay_minutes": None,
        }

        decision = route_case(extracted)

        self.assertEqual(decision["status"], "needs_information")
        self.assertIn("arrivée réelle", decision["questions"][0])

    def test_complete_incident_is_ready_for_research(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "delay",
            "delay_minutes": 205,
        }

        decision = route_case(extracted)

        self.assertEqual(decision["status"], "ready_for_research")
        self.assertEqual(decision["next_tool"], "verify_air_passenger_rule")

    def test_incident_statement_normalizes_hours_and_minutes(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol est arrivé avec 3 h 25 de retard après un problème technique.",
        )

        self.assertEqual(extracted["disruption_type"], "delay")
        self.assertEqual(extracted["delay_minutes"], 205)
        self.assertEqual(extracted["arrival_delay_minutes"], 205)
        self.assertIn("problème technique", extracted["disruption_cause"])

    def test_departure_delay_is_not_treated_as_arrival_delay(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol avait 5 h 10 de retard au départ.",
        )

        self.assertEqual(extracted["departure_delay_minutes"], 310)
        self.assertIsNone(extracted["delay_minutes"])

    def test_statement_distinguishes_two_delay_durations(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "arrival_delay_minutes": None,
            "departure_delay_minutes": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol avait 5 h de retard au départ et 2 h 30 à l'arrivée.",
        )

        self.assertEqual(extracted["departure_delay_minutes"], 300)
        self.assertEqual(extracted["arrival_delay_minutes"], 150)
        self.assertEqual(extracted["delay_minutes"], 150)

    def test_statement_records_an_explicitly_abandoned_trip(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "arrival_delay_minutes": None,
            "departure_delay_minutes": None,
            "trip_completed": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol avait 5 h de retard au départ, j'ai renoncé au voyage.",
        )

        self.assertEqual(extracted["departure_delay_minutes"], 300)
        self.assertFalse(extracted["trip_completed"])

    def test_statement_without_explicit_choice_clears_model_inference(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "trip_completed": False,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol est arrivé avec 3 h 25 de retard.",
        )

        self.assertIsNone(extracted["trip_completed"])

    @patch("agent.extract_flight")
    def test_incomplete_case_does_not_call_research(self, extract_flight):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "disruption_type": "unknown",
                "delay_minutes": None,
            },
            1.2,
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertIsNone(result["research"])
        self.assertIsNone(result["claim"])

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_ticket_refund_is_not_masked_by_compensation_refusal(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                "disruption_type": "delay",
                "delay_minutes": 150,
                "arrival_delay_minutes": 150,
                "departure_delay_minutes": 300,
                "trip_completed": False,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True},
                "claim_channel": {"status": "demo_carrier"},
            },
            [],
        )
        draft_claim.return_value = ({"summary": "Remboursement possible."}, 1.0)

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "non_eligible")
        self.assertEqual(result["reimbursement"]["status"], "likely")
        self.assertEqual(result["decision"]["status"], "ready_for_claim")
        self.assertIsNone(result["refusal"])
        self.assertIsNotNone(result["claim"])

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_ticket_refund_survives_an_unqualifiable_compensation(
        self, extract_flight, research_case_mock, draft_claim
    ):
        """Un aéroport non référencé ne doit pas effacer un remboursement acquis."""
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                # Code volontairement hors table : la qualification doit alors
                # renvoyer needs_information au lieu d'estimer une distance.
                "origin": "Tel Aviv TLV",
                "disruption_type": "delay",
                "delay_minutes": 200,
                "arrival_delay_minutes": 200,
                "departure_delay_minutes": 310,
                "trip_completed": False,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True},
                "claim_channel": {"status": "demo_carrier"},
                "airline_policy": {"status": "not_found"},
            },
            [],
        )
        draft_claim.return_value = ({"summary": "Remboursement possible."}, 1.0)

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "needs_information")
        self.assertEqual(result["reimbursement"]["status"], "likely")
        self.assertEqual(result["decision"]["status"], "ready_for_claim")
        self.assertIsNotNone(result["claim"])
        # La question sur l'indemnisation reste posée, sans bloquer la lettre.
        self.assertTrue(result["decision"]["questions"])

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_unqualifiable_compensation_without_refund_still_asks(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                # Code volontairement hors table : la qualification doit alors
                # renvoyer needs_information au lieu d'estimer une distance.
                "origin": "Tel Aviv TLV",
                "disruption_type": "delay",
                "delay_minutes": 200,
                "arrival_delay_minutes": 200,
                "departure_delay_minutes": None,
                "trip_completed": True,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True},
                "claim_channel": {"status": "demo_carrier"},
                "airline_policy": {"status": "not_found"},
            },
            [],
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["decision"]["status"], "needs_information")
        self.assertIsNone(result["claim"])
        draft_claim.assert_not_called()

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_successful_pipeline_finishes_ready_for_claim(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                "disruption_type": "delay",
                "delay_minutes": 205,
                "arrival_delay_minutes": 205,
                "departure_delay_minutes": None,
                "trip_completed": None,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True},
                "claim_channel": {"status": "demo_carrier"},
            },
            [],
        )
        draft_claim.return_value = ({"summary": "Dossier prêt."}, 1.0)

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "likely")
        self.assertEqual(result["decision"]["status"], "ready_for_claim")
        self.assertIsNotNone(result["claim"])
        self.assertIsNone(result["decision"]["next_tool"])

    def test_cdg_lis_distance_and_amount(self):
        distance = compute_distance("CDG", "LIS")

        self.assertGreater(distance, 1400)
        self.assertLess(distance, 1500)
        self.assertEqual(compensation_amount(distance, intra_eu=True), 250)

    def test_intra_eu_over_1500_is_400(self):
        distance = compute_distance("CDG", "ATH")

        self.assertGreater(distance, 1500)
        self.assertEqual(compensation_amount(distance, intra_eu=True), 400)

    def test_long_non_eu_route_is_600(self):
        distance = compute_distance("CDG", "JFK")

        self.assertGreater(distance, 3500)
        self.assertEqual(compensation_amount(distance, intra_eu=False), 600)

    def test_delay_below_three_hours_is_non_eligible(self):
        qualification = qualify_delay(
            {
                "origin": "PARIS CDG",
                "destination": "LISBONNE LIS",
                "delay_minutes": 130,
            }
        )

        self.assertEqual(qualification["status"], "non_eligible")
        self.assertEqual(qualification["compensation_eur"], 0)

    def test_arrival_delay_alone_does_not_prove_ticket_reimbursement(self):
        assessment = assess_ticket_reimbursement(
            {
                "disruption_type": "delay",
                "arrival_delay_minutes": 205,
            }
        )

        self.assertEqual(assessment["status"], "needs_information")
        self.assertIn("retard au départ", assessment["reason"])

    def test_five_hour_delay_requires_the_passenger_choice(self):
        assessment = assess_ticket_reimbursement(
            {
                "disruption_type": "delay",
                "departure_delay_minutes": 310,
            },
            reference_source_reachable=True,
        )

        self.assertEqual(assessment["status"], "needs_information")
        self.assertIn("renoncé", assessment["reason"])

    def test_five_hour_delay_and_abandoned_trip_can_trigger_reimbursement(self):
        assessment = assess_ticket_reimbursement(
            {
                "disruption_type": "delay",
                "departure_delay_minutes": 310,
                "trip_completed": False,
            },
            reference_source_reachable=True,
        )

        self.assertEqual(assessment["status"], "likely")
        self.assertIsNone(assessment["amount_eur"])

    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_refund_question_is_not_masked_by_compensation_refusal(
        self, extract_flight, research_case_mock
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                "disruption_type": "delay",
                "delay_minutes": 150,
                "arrival_delay_minutes": 150,
                "departure_delay_minutes": 300,
                "trip_completed": None,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True},
                "claim_channel": {"status": "demo_carrier"},
            },
            [],
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "non_eligible")
        self.assertEqual(result["reimbursement"]["status"], "needs_information")
        self.assertEqual(result["decision"]["status"], "needs_information")
        self.assertIn("renoncé", result["decision"]["questions"][0])
        self.assertIsNone(result["refusal"])
        self.assertIsNone(result["claim"])

    def test_serpapi_rule_query_excludes_personal_data(self):
        query = build_rule_query(
            {
                "passenger_name": "MARTIN LEA",
                "booking_reference": "FQ7T2K",
                "disruption_type": "delay",
                "delay_minutes": 205,
                "origin": "PARIS CDG",
                "destination": "LISBONNE LIS",
            }
        )

        self.assertNotIn("MARTIN", query)
        self.assertNotIn("FQ7T2K", query)
        self.assertIn("retard", query)
        self.assertIn("site:europa.eu", query)
        self.assertNotIn(" OR ", query)


class NativeToolCallingTests(unittest.TestCase):
    def setUp(self):
        self.extracted = {
            **COMPLETE_FLIGHT,
            "passenger_name": "MARTIN LEA",
            "booking_reference": "FQ7T2K",
            "airline": "Aurora Airlines",
            "disruption_type": "delay",
            "arrival_delay_minutes": 205,
            "departure_delay_minutes": None,
        }
        self.rights = {
            "status": "online",
            "reference_source_reachable": True,
            "reason": None,
            "sources": [],
        }
        self.channel = {
            "status": "demo_carrier",
            "channel": None,
            "message": "Compagnie fictive.",
        }
        self.policy = {
            "status": "not_found",
            "source": "local_corpus",
            "company": None,
            "procedures": [],
            "message": "Aucune fiche locale pour cette compagnie.",
        }

    @patch("agent.retrieve_airline_policy")
    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_gemma_tool_calls_are_parsed_and_dispatched(
        self, chat, verify_rule, find_channel, retrieve_policy
    ):
        chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "verify_air_passenger_rule",
                            "arguments": {
                                "disruption_type": "delay",
                                "origin": "Paris CDG",
                                "destination": "Lisbonne LIS",
                                "arrival_delay_minutes": 205,
                                "departure_delay_minutes": None,
                            },
                        }
                    },
                    {
                        "function": {
                            "name": "find_claim_channel",
                            "arguments": {"airline": "Aurora Airlines"},
                        }
                    },
                    {
                        "function": {
                            "name": "retrieve_airline_policy",
                            "arguments": {
                                "airline": "Aurora Airlines",
                                "incident": "flight_delay",
                            },
                        }
                    },
                ]
            }
        }
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel
        retrieve_policy.return_value = self.policy

        research, trace = research_case(self.extracted)

        self.assertEqual(research["rights"]["status"], "online")
        self.assertEqual(research["airline_policy"]["status"], "not_found")
        verify_rule.assert_called_once()
        find_channel.assert_called_once_with({"airline": "Aurora Airlines"})
        retrieve_policy.assert_called_once_with(
            {"airline": "Aurora Airlines", "incident": "flight_delay"}
        )
        self.assertEqual(trace[0]["outcome"], "gemma_tool_calls")
        self.assertEqual(trace[1]["selected_by"], "gemma_tool_call")
        self.assertEqual(trace[2]["selected_by"], "gemma_tool_call")
        self.assertEqual(trace[3]["selected_by"], "gemma_tool_call")
        self.assertEqual(trace[3]["state"], "CORPUS_LOCAL")
        payload = chat.call_args.args[0]
        self.assertEqual(payload["tools"], RESEARCH_TOOL_DEFINITIONS)
        serialized_messages = str(payload["messages"])
        self.assertNotIn("MARTIN LEA", serialized_messages)
        self.assertNotIn("FQ7T2K", serialized_messages)

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_no_tool_call_uses_deterministic_fallback(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {"message": {"content": "Je propose une recherche."}}
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        verify_rule.assert_called_once()
        find_channel.assert_called_once()
        self.assertEqual(trace[0]["outcome"], "deterministic_fallback")
        self.assertIn("aucun outil", trace[0]["details"])
        self.assertEqual(trace[1]["selected_by"], "deterministic_fallback")

    @patch("agent.retrieve_airline_policy")
    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_tool_result_is_returned_before_second_tool_call(
        self, chat, verify_rule, find_channel, retrieve_policy
    ):
        chat.side_effect = [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "verify_air_passenger_rule",
                                "arguments": {
                                    "disruption_type": "delay",
                                    "origin": "Paris CDG",
                                    "destination": "Lisbonne LIS",
                                    "arrival_delay_minutes": 205,
                                    "departure_delay_minutes": None,
                                },
                            }
                        }
                    ]
                }
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "find_claim_channel",
                                "arguments": {"airline": "Aurora Airlines"},
                            }
                        }
                    ]
                }
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "retrieve_airline_policy",
                                "arguments": {
                                    "airline": "Aurora Airlines",
                                    "incident": "flight_delay",
                                },
                            }
                        }
                    ]
                }
            },
        ]
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel
        retrieve_policy.return_value = self.policy

        _, trace = research_case(self.extracted)

        self.assertEqual(chat.call_count, 3)
        second_messages = chat.call_args_list[1].args[0]["messages"]
        tool_messages = [
            message for message in second_messages if message["role"] == "tool"
        ]
        self.assertEqual(tool_messages[0]["tool_name"], "verify_air_passenger_rule")
        self.assertIn('"status": "online"', tool_messages[0]["content"])
        self.assertEqual(trace[0]["outcome"], "gemma_tool_calls")
        self.assertEqual(trace[0]["tool_result_round_trips"], 2)

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_unknown_tool_is_rejected_by_allow_list(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_private_file",
                            "arguments": {"path": ".env"},
                        }
                    }
                ]
            }
        }
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        self.assertEqual(trace[0]["rejected_tool_calls"], 1)
        self.assertEqual(trace[0]["outcome"], "deterministic_fallback")
        verify_rule.assert_called_once()
        find_channel.assert_called_once()

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_extra_personal_argument_is_rejected(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "find_claim_channel",
                            "arguments": {
                                "airline": "Aurora Airlines",
                                "booking_reference": "FQ7T2K",
                            },
                        }
                    }
                ]
            }
        }
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        self.assertEqual(trace[0]["rejected_tool_calls"], 1)
        find_channel.assert_called_once_with({"airline": "Aurora Airlines"})
        self.assertEqual(trace[2]["selected_by"], "deterministic_fallback")

    def test_tool_schemas_forbid_additional_properties(self):
        for declaration in RESEARCH_TOOL_DEFINITIONS:
            parameters = declaration["function"]["parameters"]
            self.assertFalse(parameters["additionalProperties"])
            self.assertEqual(
                set(parameters["required"]),
                set(parameters["properties"]),
            )

    def test_research_context_is_minimized(self):
        context = build_research_context(self.extracted)

        self.assertNotIn("passenger_name", context)
        self.assertNotIn("booking_reference", context)
        self.assertEqual(context["arrival_delay_minutes"], 205)

    @patch("tools._dotenv_value")
    @patch("tools.os.getenv")
    def test_environment_key_has_priority_over_dotenv(self, getenv, dotenv_value):
        getenv.side_effect = (
            lambda name: "environment-value" if name == "SERPAPI_KEY" else None
        )

        self.assertEqual(_api_key(), "environment-value")
        dotenv_value.assert_not_called()

    @patch("tools.web_search", return_value=[])
    def test_empty_search_result_uses_offline_reference(self, _web_search):
        result = verify_air_passenger_rule(self.extracted)

        self.assertEqual(result["status"], "offline")
        self.assertFalse(result["reference_source_reachable"])
        self.assertEqual(len(result["sources"]), 2)

    @patch(
        "tools.web_search",
        return_value=[
            {
                "title": "Résultat hors sujet",
                "link": "https://europa.eu/example",
                "snippet": "Sans rapport avec les passagers aériens.",
            },
            {
                "title": "Droits des passagers aériens - Your Europe",
                "link": (
                    "https://europa.eu/youreurope/citizens/travel/"
                    "passenger-rights/air/index_fr.htm"
                ),
                "snippet": "Référentiel officiel.",
            },
        ],
    )
    def test_live_rule_verification_filters_irrelevant_sources(
        self, _web_search
    ):
        result = verify_air_passenger_rule(self.extracted)

        self.assertEqual(result["status"], "online")
        self.assertTrue(result["reference_source_reachable"])
        self.assertEqual(len(result["sources"]), 1)
        self.assertIn("passenger-rights/air", result["sources"][0]["link"])


class VerdictIntegrityTests(unittest.TestCase):
    """Le verdict ne doit dépendre que des faits, jamais du réseau."""

    BASE = {
        "origin": "Paris CDG",
        "destination": "Lisbonne LIS",
        "disruption_type": "delay",
        "arrival_delay_minutes": 205,
    }

    def test_status_does_not_depend_on_source_reachability(self):
        offline = qualify_delay(self.BASE, reference_source_reachable=False)
        online = qualify_delay(self.BASE, reference_source_reachable=True)

        self.assertEqual(offline["status"], online["status"])
        self.assertEqual(offline["compensation_eur"], online["compensation_eur"])
        # La joignabilité reste exposée, mais comme provenance seulement.
        self.assertFalse(offline["reference_source_reachable"])
        self.assertTrue(online["reference_source_reachable"])

    def test_extraordinary_cause_downgrades_without_refusing(self):
        result = qualify_delay({**self.BASE, "disruption_cause": "tempête de neige"})

        self.assertEqual(result["cause_risk"], "high")
        self.assertEqual(result["status"], "conditional")
        # Le droit reste chiffré : la charge de la preuve pèse sur le transporteur.
        self.assertEqual(result["compensation_eur"], 250)

    def test_technical_cause_is_not_extraordinary(self):
        """CJUE Wallentin-Hermann C-549/07."""
        result = qualify_delay({**self.BASE, "disruption_cause": "problème technique"})

        self.assertEqual(result["cause_risk"], "low")
        self.assertEqual(result["status"], "likely")

    def test_own_staff_strike_is_not_extraordinary(self):
        """CJUE Krüsemann C-195/17 : la grève interne n'exonère pas."""
        self.assertEqual(
            classify_cause("grève du personnel de la compagnie"), "low"
        )
        # Mais une grève du contrôle aérien est bien externe au transporteur.
        self.assertEqual(classify_cause("grève des contrôleurs aériens"), "high")

    def test_unknown_cause_stays_neutral(self):
        for cause in (None, "", "   "):
            self.assertEqual(classify_cause(cause), "unknown")


class UncoveredRightTests(unittest.TestCase):
    """Un cas non implémenté ne doit pas se déguiser en information manquante."""

    def test_cancellation_is_flagged_as_not_covered(self):
        result = qualify_case({"disruption_type": "cancellation"})

        self.assertEqual(result["status"], "not_covered")
        self.assertEqual(result["uncovered_disruption"], "cancellation")
        self.assertIn("art. 5(1)(c)", result["reason"])

    def test_denied_boarding_is_flagged_as_not_covered(self):
        result = qualify_case({"disruption_type": "denied_boarding"})

        self.assertEqual(result["status"], "not_covered")
        self.assertIn("art. 4", result["reason"])

    def test_missing_disruption_type_remains_needs_information(self):
        result = qualify_case({"disruption_type": None})

        self.assertEqual(result["status"], "needs_information")

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_cancellation_surfaces_the_uncovered_right(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Air France",
                "disruption_type": "cancellation",
                "delay_minutes": None,
                "trip_completed": False,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True, "sources": []},
                "claim_channel": {"status": "demo_carrier"},
                "airline_policy": {"status": "not_found"},
            },
            [],
        )
        draft_claim.return_value = (
            {
                "estimated_compensation_eur": None,
                "letter_body": "Corps de lettre.",
                "letter_subject": "Objet",
                "checklist": [],
                "warnings": [],
            },
            1.0,
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "not_covered")
        self.assertIsNotNone(result["uncovered_right"])
        states = [step.get("state") for step in result["trace"]]
        self.assertIn("DROIT_NON_COUVERT", states)


class ClaimValidationTests(unittest.TestCase):
    """La lettre rédigée par le modèle est recoupée avec le moteur."""

    RESEARCH = {
        "rights": {
            "reference_source_reachable": True,
            "sources": [{"link": "https://europa.eu/youreurope/x"}],
        },
        "claim_channel": {"status": "online", "channel": "https://exemple.test/form"},
        "airline_policy": {"status": "not_found", "procedures": []},
    }
    QUALIFICATION = {"status": "likely", "compensation_eur": 250}
    REIMBURSEMENT = {"status": "not_assessed", "amount_eur": None}

    def test_wrong_amount_is_replaced_by_the_engine_value(self):
        claim, violations = _validate_claim(
            {
                "estimated_compensation_eur": 600,
                "letter_body": "Je demande 250 €.",
                "checklist": [],
                "warnings": [],
            },
            self.RESEARCH,
            self.QUALIFICATION,
            self.REIMBURSEMENT,
        )

        self.assertEqual(claim["estimated_compensation_eur"], 250)
        self.assertTrue(violations)
        self.assertTrue(claim["warnings"])

    def test_amount_invented_in_the_letter_body_is_reported(self):
        _, violations = _validate_claim(
            {
                "estimated_compensation_eur": 250,
                "letter_body": "Je demande 600 € au titre du règlement.",
                "checklist": [],
                "warnings": [],
            },
            self.RESEARCH,
            self.QUALIFICATION,
            self.REIMBURSEMENT,
        )

        self.assertTrue(any("600" in violation for violation in violations))

    def test_unverified_url_is_reported(self):
        _, violations = _validate_claim(
            {
                "estimated_compensation_eur": 250,
                "letter_body": "Déposez sur https://www.airhelp.com/fr/",
                "checklist": [],
                "warnings": [],
            },
            self.RESEARCH,
            self.QUALIFICATION,
            self.REIMBURSEMENT,
        )

        self.assertTrue(any("airhelp" in violation for violation in violations))

    def test_unverified_channel_letter_cannot_cite_an_intermediary(self):
        """Canal refusé faute de domaine connu : rien du moteur n'est citable."""
        research = {
            "rights": {"sources": []},
            "claim_channel": {
                "status": "unverified_channel",
                "channel": None,
                "message": "Transporteur absent du registre local.",
            },
            "airline_policy": {},
        }

        _, violations = _validate_claim(
            {
                "estimated_compensation_eur": None,
                "letter_body": "Déposez sur https://www.airhelp.com/fr/",
                "checklist": [],
                "warnings": [],
            },
            research,
            {"status": "not_covered"},
            {"status": "not_assessed", "amount_eur": None},
        )

        self.assertTrue(any("airhelp" in violation for violation in violations))

    def test_no_official_match_letter_cannot_cite_an_intermediary(self):
        """Même refus quand le registre existe mais qu'aucun résultat n'en vient."""
        research = {
            "rights": {"sources": []},
            "claim_channel": {
                "status": "no_official_match",
                "channel": None,
                "message": "Aucun résultat ne provient d'un domaine officiel.",
            },
            "airline_policy": {},
        }

        _, violations = _validate_claim(
            {
                "estimated_compensation_eur": None,
                "letter_body": "Déposez sur https://www.flightright.fr/air-france",
                "checklist": [],
                "warnings": [],
            },
            research,
            {"status": "not_covered"},
            {"status": "not_assessed", "amount_eur": None},
        )

        self.assertTrue(any("flightright" in violation for violation in violations))

    def test_rejected_channel_results_never_become_citable(self):
        """Second rempart, sur une charge utile que `tools` n'émet plus.

        Les statuts de rejet ne transportent plus de résultats bruts, mais la
        liste blanche ne doit pas dépendre de cette discipline en amont : un
        dossier rejoué, ou un outil futur moins prudent, ne doit pas rouvrir la
        porte à un intermédiaire à commission que le filtre avait écarté.
        """
        research = {
            "rights": {"sources": []},
            "claim_channel": {
                "status": "no_official_match",
                "channel": None,
                "results": [{"link": "https://www.airhelp.com/fr/"}],
            },
            "airline_policy": {},
        }

        _, violations = _validate_claim(
            {
                "estimated_compensation_eur": None,
                "letter_body": "Déposez sur https://www.airhelp.com/fr/",
                "checklist": [],
                "warnings": [],
            },
            research,
            {"status": "not_covered"},
            {"status": "not_assessed", "amount_eur": None},
        )

        self.assertTrue(any("airhelp" in violation for violation in violations))

    def test_verified_channel_results_stay_citable(self):
        research = {
            "rights": {"sources": []},
            "claim_channel": {
                "status": "online",
                "channel": "https://wwws.airfrance.fr/contact",
                "results": [{"link": "https://wwws.airfrance.fr/contact"}],
            },
            "airline_policy": {},
        }

        _, violations = _validate_claim(
            {
                "estimated_compensation_eur": None,
                "letter_body": "Déposez sur https://wwws.airfrance.fr/contact",
                "checklist": [],
                "warnings": [],
            },
            research,
            {"status": "not_covered"},
            {"status": "not_assessed", "amount_eur": None},
        )

        self.assertEqual(violations, [])

    def test_faithful_letter_passes_without_violation(self):
        claim, violations = _validate_claim(
            {
                "estimated_compensation_eur": 250,
                "letter_body": (
                    "Je demande 250 € en application du règlement, voir "
                    "https://europa.eu/youreurope/x"
                ),
                "checklist": ["https://exemple.test/form"],
                "warnings": [],
            },
            self.RESEARCH,
            self.QUALIFICATION,
            self.REIMBURSEMENT,
        )

        self.assertEqual(violations, [])
        self.assertEqual(claim["warnings"], [])

    def test_amount_is_cleared_when_the_right_is_not_claimable(self):
        claim, violations = _validate_claim(
            {
                "estimated_compensation_eur": 400,
                "letter_body": "Corps neutre.",
                "checklist": [],
                "warnings": [],
            },
            self.RESEARCH,
            {"status": "not_covered"},
            self.REIMBURSEMENT,
        )

        self.assertIsNone(claim["estimated_compensation_eur"])
        self.assertTrue(violations)


class AirportResolutionTests(unittest.TestCase):
    """Un libellé libre ne doit jamais produire un aéroport deviné."""

    def test_single_referenced_code_is_resolved(self):
        for label, expected in (
            ("Paris CDG", "CDG"),
            ("BARCELONE T1 (BCN)", "BCN"),
            ("Munich (MUC)", "MUC"),
            ("New York JFK", "JFK"),
            ("Francfort FRA", "FRA"),
        ):
            self.assertEqual(resolve_airport(label)[0], expected, label)

    def test_country_code_after_a_comma_is_not_an_airport(self):
        """« Nice NCE, FRA » désignait Francfort : +150 € silencieusement."""
        code, problem = resolve_airport("Nice NCE, FRA")

        self.assertEqual(code, "NCE")
        self.assertIsNone(problem)

    def test_several_referenced_codes_ask_instead_of_guessing(self):
        code, problem = resolve_airport("Vol CDG puis MUC")

        self.assertIsNone(code)
        self.assertIn("plusieurs aéroports", problem)

    def test_unreferenced_code_is_named_in_the_reason(self):
        code, problem = resolve_airport("Tel Aviv TLV")

        self.assertIsNone(code)
        self.assertIn("TLV", problem)

    def test_label_without_any_code_is_reported(self):
        code, problem = resolve_airport("Aéroport Charles de Gaulle, Paris, FRA")

        self.assertIsNone(code)
        self.assertIn("Aucun code IATA", problem)

    def test_ambiguous_label_does_not_reach_the_distance_computation(self):
        result = qualify_delay(
            {
                "origin": "Vol CDG puis MUC",
                "destination": "Lisbonne LIS",
                "disruption_type": "delay",
                "arrival_delay_minutes": 205,
            }
        )

        self.assertEqual(result["status"], "needs_information")
        self.assertNotIn("compensation_eur", result)


class IncidentStatementRobustnessTests(unittest.TestCase):
    """Le parseur déterministe face à des formulations non coopératives."""

    @staticmethod
    def parse(statement: str) -> dict:
        extracted = {
            "disruption_type": None,
            "delay_minutes": None,
            "arrival_delay_minutes": None,
            "departure_delay_minutes": None,
            "trip_completed": None,
            "disruption_cause": None,
            "evidence": [],
        }
        merge_incident_statement(extracted, statement)
        return extracted

    def test_negation_does_not_create_a_cancellation(self):
        extracted = self.parse("mon vol n'a pas été annulé, juste 3h30 de retard")

        self.assertEqual(extracted["disruption_type"], "delay")
        self.assertEqual(extracted["arrival_delay_minutes"], 210)

    def test_negated_denied_boarding_is_ignored(self):
        extracted = self.parse(
            "on ne m'a pas refusé l'embarquement, le vol avait 4 h de retard"
        )

        self.assertEqual(extracted["disruption_type"], "delay")

    def test_clock_time_is_not_a_duration(self):
        extracted = self.parse("arrivée 23h50 au lieu de 20h25")

        self.assertIsNone(extracted["arrival_delay_minutes"])
        self.assertIsNone(extracted["departure_delay_minutes"])

    def test_clock_time_after_a_real_delay_is_not_absorbed(self):
        extracted = self.parse("3h30 de retard, je suis arrivé à 23h50")

        self.assertEqual(extracted["arrival_delay_minutes"], 210)

    def test_written_out_durations_are_understood(self):
        for statement, expected in (
            ("trois heures et demie de retard", 210),
            ("deux heures de retard", 120),
            ("quatre heures et quart de retard", 255),
        ):
            self.assertEqual(
                self.parse(statement)["arrival_delay_minutes"], expected, statement
            )

    def test_a_duration_without_delay_marker_is_ignored(self):
        extracted = self.parse("le vol dure 2 h 30")

        self.assertIsNone(extracted["arrival_delay_minutes"])

    def test_both_delays_survive_a_missing_apostrophe(self):
        for statement in (
            "Le vol avait 5 h de retard au départ et 2 h 30 à l'arrivée.",
            "Le vol avait 5 h de retard au départ et 2 h 30 à l arrivée.",
        ):
            extracted = self.parse(statement)
            self.assertEqual(extracted["departure_delay_minutes"], 300, statement)
            self.assertEqual(extracted["arrival_delay_minutes"], 150, statement)


class ArrivalTimingTests(unittest.TestCase):
    """Les horaires d'arrivée valent mieux qu'une durée déduite d'une phrase."""

    def test_delay_is_computed_from_local_times(self):
        minutes, problem = arrival_delay_from_times(
            "20:25", "23:50", "2026-06-11", "LIS"
        )

        self.assertEqual(minutes, 205)
        self.assertIsNone(problem)

    def test_arrival_after_midnight_is_the_next_day(self):
        minutes, _ = arrival_delay_from_times("23:50", "01:30", "2026-06-11", "LIS")

        self.assertEqual(minutes, 100)

    def test_daylight_saving_night_is_measured_in_real_time(self):
        """CPython soustrait naïvement deux datetime au même tzinfo.

        Sans conversion en UTC, la nuit du passage à l'heure d'hiver renverrait
        90 minutes là où le passager en a réellement attendu 150.
        """
        minutes, _ = arrival_delay_from_times("01:30", "03:00", "2026-10-25", "CDG")

        self.assertEqual(minutes, 150)
        # Même horloge, une nuit ordinaire : l'écart reste de 90 minutes.
        ordinary, _ = arrival_delay_from_times("01:30", "03:00", "2026-06-11", "LIS")
        self.assertEqual(ordinary, 90)

    def test_unusable_inputs_are_reported_not_guessed(self):
        for scheduled, actual, date, destination in (
            ("pas une heure", "23:50", "2026-06-11", "LIS"),
            ("20:25", "23:50", None, "LIS"),
            ("20:25", "23:50", "2026-06-11", "XXX"),
            ("25:99", "23:50", "2026-06-11", "LIS"),
        ):
            minutes, problem = arrival_delay_from_times(
                scheduled, actual, date, destination
            )
            self.assertIsNone(minutes)
            self.assertTrue(problem)

    def test_every_airport_carries_a_valid_timezone(self):
        for code, airport in AIRPORTS.items():
            self.assertIn("tz", airport, code)
            ZoneInfo(airport["tz"])

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_declared_delay_is_kept_but_divergence_is_traced(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Air France",
                "disruption_type": "delay",
                "delay_minutes": 205,
                "arrival_delay_minutes": 205,
                "departure_delay_minutes": None,
                "scheduled_arrival": "20:25",
                # Le passager a déclaré 205 min, les horaires en donnent 100.
                "actual_arrival": "22:05",
                "trip_completed": None,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"reference_source_reachable": True, "sources": []},
                "claim_channel": {"status": "demo_carrier"},
                "airline_policy": {"status": "not_found"},
            },
            [],
        )
        draft_claim.return_value = (
            {
                "estimated_compensation_eur": 250,
                "letter_body": "Corps.",
                "letter_subject": "Objet",
                "checklist": [],
                "warnings": [],
            },
            1.0,
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        # La déclaration du voyageur n'est jamais écrasée en silence.
        self.assertEqual(result["extraction"]["arrival_delay_minutes"], 205)
        timing = [s for s in result["trace"] if s["state"] == "HORAIRES_RECOUPES"]
        self.assertEqual(len(timing), 1)
        self.assertEqual(timing[0]["outcome"], "divergent")


class ChatErrorContractTests(unittest.TestCase):
    """Une panne d'Ollama ne doit jamais passer pour une faute de l'utilisateur."""

    def test_unreadable_response_becomes_an_agent_error(self):
        class FakeResponse:
            def read(self):
                return b"<html>proxy</html>"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("agent.urllib.request.urlopen", return_value=FakeResponse()):
            with self.assertRaises(AgentError) as raised:
                _chat({"model": "x"})

        self.assertIn("illisible", str(raised.exception))

    def test_timeout_becomes_an_agent_error(self):
        with patch("agent.urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(AgentError) as raised:
                _chat({"model": "x"}, timeout=7)

        self.assertIn("7 s", str(raised.exception))

    def test_socket_failure_becomes_an_agent_error(self):
        with patch("agent.urllib.request.urlopen", side_effect=OSError("broken pipe")):
            with self.assertRaises(AgentError):
                _chat({"model": "x"})


class CarrierIdentityTests(unittest.TestCase):
    """Une compagnie doit être reconnue sous toutes ses écritures."""

    def test_spelling_variants_reach_the_same_carrier(self):
        for label in ("Air France", "AirFrance", "AIR  FRANCE", "Air France KLM"):
            carrier = identify_carrier(label)
            self.assertIsNotNone(carrier, label)
            self.assertEqual(carrier["airline_id"], "air_france", label)

    def test_iata_code_printed_on_the_ticket_is_recognised(self):
        """easyJet s'écrit U2 en IATA ; le corpus ne listait que l'OACI EZY."""
        for code in ("U2", "EZY"):
            self.assertEqual(identify_carrier(code)["airline_id"], "easyjet", code)

    def test_unknown_carrier_has_no_domains(self):
        self.assertIsNone(identify_carrier("Ryanair"))
        self.assertEqual(official_domains("Ryanair"), ())


class ClaimChannelAllowListTests(unittest.TestCase):
    """Le canal publié dans la lettre doit venir du transporteur lui-même."""

    def test_only_official_domains_are_accepted(self):
        domains = official_domains("Air France")
        for url, expected in (
            ("https://wwws.airfrance.fr/contact/topic/refund", True),
            ("https://www.airfrance.fr/", True),
            ("https://www.airhelp.com/fr/air-france/", False),
            ("https://www.flightright.fr/air-france", False),
            # Usurpation par suffixe : la comparaison porte sur les composants
            # du nom d'hôte, jamais sur une inclusion de chaîne.
            ("https://airfrance.fr.exemple-arnaque.com/form", False),
            ("https://notairfrance.fr/", False),
        ):
            self.assertEqual(_is_official_url(url, domains), expected, url)

    @patch("tools.web_search")
    def test_intermediary_never_becomes_the_official_channel(self, search):
        search.return_value = [
            {"title": "Indemnisation Air France", "link": "https://www.airhelp.com/fr/"},
            {"title": "Flightright", "link": "https://www.flightright.fr/air-france"},
        ]

        result = find_claim_channel({"airline": "Air France"})

        self.assertEqual(result["status"], "no_official_match")
        self.assertIsNone(result["channel"])

    @patch("tools.web_search")
    def test_official_result_is_selected_even_if_not_first(self, search):
        search.return_value = [
            {"title": "AirHelp", "link": "https://www.airhelp.com/fr/"},
            {
                "title": "Air France",
                "link": "https://wwws.airfrance.fr/contact/topic/refund",
            },
        ]

        result = find_claim_channel({"airline": "Air France"})

        self.assertEqual(result["status"], "online")
        self.assertIn("airfrance.fr", result["channel"])

    @patch("tools.web_search")
    def test_unknown_carrier_refuses_to_confirm_a_channel(self, search):
        search.return_value = [{"title": "x", "link": "https://exemple.test/"}]

        result = find_claim_channel({"airline": "Ryanair"})

        self.assertEqual(result["status"], "unverified_channel")
        self.assertIsNone(result["channel"])

    @patch("tools.web_search")
    def test_rejection_payload_carries_no_url_at_all(self, search):
        """La charge utile part entière dans le prompt de rédaction.

        Y laisser les résultats écartés reviendrait à souffler au modèle les
        adresses que le filtre vient de refuser ; la liste blanche de sortie les
        bloquerait, mais une défense à un seul rempart n'en est pas une.
        """
        search.return_value = [
            {"title": "AirHelp", "link": "https://www.airhelp.com/fr/"},
            {"title": "Flightright", "link": "https://www.flightright.fr/"},
        ]

        for airline, status in (
            ("Ryanair", "unverified_channel"),
            ("Air France", "no_official_match"),
        ):
            result = find_claim_channel({"airline": airline})

            self.assertEqual(result["status"], status, airline)
            self.assertNotIn("results", result)
            self.assertNotIn("http", json.dumps(result, ensure_ascii=False))


class PolicyFreshnessTests(unittest.TestCase):
    def test_stale_sheet_withholds_its_steps(self):
        class FrozenDate(datetime.date):
            @classmethod
            def today(cls):
                return datetime.date(2027, 1, 1)

        with patch.object(datetime, "date", FrozenDate):
            result = retrieve_airline_policy(
                {"airline": "Air France", "disruption_type": "delay"}
            )

        self.assertEqual(result["status"], "needs_verification")
        self.assertEqual(result["procedures"], [])
        self.assertEqual(result["freshness"], "stale")

    def test_fresh_sheet_still_serves_its_steps(self):
        result = retrieve_airline_policy(
            {"airline": "Air France", "disruption_type": "delay"}
        )

        self.assertEqual(result["status"], "found")
        self.assertTrue(result["procedures"])


class PendingQuestionsTests(unittest.TestCase):
    def test_every_open_question_is_surfaced(self):
        questions = _pending_questions(
            {"status": "needs_information", "reason": "Aéroport non référencé : TLV"},
            {"status": "needs_information", "question": "Retard au départ ?"},
        )

        self.assertEqual(len(questions), 2)

    def test_settled_assessments_ask_nothing(self):
        self.assertEqual(
            _pending_questions({"status": "likely", "reason": "ok"}), []
        )

    def test_duplicates_are_removed(self):
        questions = _pending_questions(
            {"status": "needs_information", "reason": "Même question"},
            {"status": "needs_information", "reason": "Même question"},
        )

        self.assertEqual(questions, ["Même question"])


class FlightDatePlausibilityTests(unittest.TestCase):
    TODAY = datetime.date(2026, 7, 26)

    def test_future_flight_is_flagged(self):
        warning = _implausible_date({"departure_date": "2026-09-14"}, self.TODAY)

        self.assertIsNotNone(warning)
        self.assertIn("futur", warning)

    def test_very_old_flight_warns_without_concluding(self):
        warning = _implausible_date({"departure_date": "2021-01-05"}, self.TODAY)

        self.assertIn("quatre ans", warning)
        # On alerte, on ne déclare jamais la prescription acquise.
        self.assertNotIn("prescrit", warning.lower())

    def test_recent_past_flight_is_accepted(self):
        self.assertIsNone(
            _implausible_date({"departure_date": "2026-07-25"}, self.TODAY)
        )

    def test_unparseable_date_is_not_a_warning(self):
        for value in ("pas une date", None, ""):
            self.assertIsNone(_implausible_date({"departure_date": value}, self.TODAY))


class IncidentCorpusTests(unittest.TestCase):
    """Le corpus de déclarations, appliqué par la CI comme un test ordinaire.

    Il mesure ce que la couche déterministe comprend d'une phrase écrite par un
    voyageur — la seule couche entre le langage libre et les faits chiffrés, et
    celle qui se trompait en silence avant d'être mesurée.
    """

    @classmethod
    def setUpClass(cls):
        cls.results = corpus.run_all()

    def test_every_supported_case_passes(self):
        failures = [
            f"{r['id']} — « {r['statement']} » : {'; '.join(r['mismatches'])}"
            for r in self.results
            if r["status"] == "supported" and not r["passed"]
        ]

        self.assertEqual(failures, [])

    def test_known_gaps_still_fail(self):
        """Un trou qui se met à passer doit être promu, pas oublié.

        Sans cette assertion, le corpus documenterait éternellement des limites
        qui n'existent plus.
        """
        resolved = [
            r["id"]
            for r in self.results
            if r["status"] == "known_gap" and r["passed"]
        ]

        self.assertEqual(
            resolved,
            [],
            "ces cas passent désormais : passe-les en status 'supported' "
            "dans eval/incident_cases.json",
        )

    def test_corpus_is_substantial_and_documented(self):
        self.assertGreaterEqual(len(self.results), 25)
        undocumented = [r["id"] for r in self.results if not r["why"]]
        self.assertEqual(undocumented, [], "chaque cas doit dire pourquoi il existe")


class DocumentedFiguresTests(unittest.TestCase):
    """Les chiffres publiés doivent rester vrais sans intervention manuelle."""

    ROOT = pathlib.Path(__file__).resolve().parent

    def test_documented_test_count_is_accurate(self):
        """Quatre documents ont déjà annoncé quatre comptes différents.

        Compter les méthodes par analyse syntaxique plutôt qu'en relançant la
        découverte évite toute récursion : ce test fait partie du total qu'il
        vérifie.
        """
        source = (self.ROOT / "test_agent.py").read_text(encoding="utf-8")
        actual = sum(
            1
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        )
        documented = (self.ROOT / "docs" / "EVALUATION.md").read_text(encoding="utf-8")
        match = re.search(r"compte \*\*(\d+)\*\* tests déterministes", documented)

        self.assertIsNotNone(match, "docs/EVALUATION.md n'annonce plus de compte")
        self.assertEqual(
            int(match.group(1)),
            actual,
            "docs/EVALUATION.md doit être mis à jour après ajout ou retrait d'un test",
        )

    def test_documented_port_matches_the_server_default(self):
        documented = (self.ROOT / "docs" / "EVALUATION.md").read_text(encoding="utf-8")
        source = (self.ROOT / "app.py").read_text(encoding="utf-8")
        default_port = re.search(r'"--port", default=(\d+)', source)

        self.assertIsNotNone(default_port)
        self.assertIn(f"**{default_port.group(1)}**", documented)


class BrowserContractTests(unittest.TestCase):
    """L'interface ne doit lire que des champs que le serveur émet vraiment.

    Un champ jamais émis ne casse rien à l'écran : la condition qui le teste
    est simplement toujours fausse, et le bloc d'affichage survit des mois
    sans que personne le remarque. Les deux inventaires sont donc dérivés du
    code, jamais recopiés à la main : c'est l'écart entre le JavaScript et le
    Python qui doit faire échouer, pas une liste figée dans ce fichier.

    Portée exacte, à ne pas surestimer : ce contrat couvre la **frontière**
    entre le serveur et la page — les clés lues directement sur `step` et sur
    `data` — et non l'intérieur des blocs qu'elle laisse passer. `_browser_reads`
    dit quelles formes lui échappent, et il y en a de bien réelles.
    """

    ROOT = pathlib.Path(__file__).resolve().parent

    def _browser_reads(self, variable: str, source: str | None = None) -> set[str]:
        """Les clés lues directement sur `variable` : `x.clé` et `x["clé"]`.

        Trois formes restent invisibles, et elles existent aujourd'hui dans la
        page : l'alias (`const decision = data.decision;` puis `decision.status`,
        l. 413), la clé calculée (`data.extraction[key]` dans une boucle sur
        `Object.entries`, l. 488), et la traversée imbriquée
        (`data.research.claim_channel`, l. 522). Élargir la regex à ces cas
        reviendrait à écrire un analyseur JavaScript ; le vrai remède est un
        rendu piloté par un schéma, qui relève du lot 8. En attendant, ce test
        garde la frontière, ce qui est déjà ce par quoi une clé morte entre.
        """
        if source is None:
            source = (self.ROOT / "static" / "index.html").read_text(encoding="utf-8")
        # Le point interdit avant le nom écarte `event.data.size`, qui désigne
        # un morceau d'enregistrement audio et non une réponse du serveur.
        dotted = re.findall(rf"(?<![\w.$]){variable}\.([a-zA-Z_]+)", source)
        bracketed = re.findall(
            rf"(?<![\w.$]){variable}\[[\"']([a-zA-Z_]+)[\"']\]", source
        )
        return set(dotted) | set(bracketed)

    def test_both_direct_access_forms_are_seen(self):
        """`step["x"]` doit compter autant que `step.x`.

        Sans quoi il suffirait d'écrire la lecture avec des crochets pour
        qu'une clé morte traverse le contrat sans être vue.
        """
        source = 'step.pointe; step["crochets"]; event.data.size; autre.step.exclu;'

        self.assertEqual(
            self._browser_reads("step", source), {"pointe", "crochets"}
        )

    def test_trace_fields_read_by_the_page_are_all_emitted(self):
        """Les étapes de trace dépendent du chemin suivi par le dossier.

        Rejouer un scénario ne prouverait donc rien sur les branches non
        empruntées : on relit tous les littéraux d'étape de `agent.py`, ce qui
        couvre l'union des traces possibles.
        """
        source = (self.ROOT / "agent.py").read_text(encoding="utf-8")
        emitted: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Dict):
                continue
            literal = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if {"step", "outcome"} <= literal:
                emitted |= literal

        self.assertTrue(emitted, "plus aucun littéral d'étape reconnu dans agent.py")
        self.assertEqual(
            sorted(self._browser_reads("step") - emitted),
            [],
            "l'interface lit un champ d'étape que la trace ne produit jamais",
        )

    @patch("agent.extract_flight")
    def test_payload_fields_read_by_the_page_are_all_emitted(self, extract_flight):
        """La charge utile de premier niveau, elle, est complète dès sa
        construction : un dossier incomplet suffit à l'observer en vrai,
        ce qui vaut mieux qu'une relecture syntaxique.
        """
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "disruption_type": "unknown",
                "delay_minutes": None,
            },
            1.0,
        )
        emitted = set(process(pathlib.Path("unused.pdf")))
        # La transcription et les erreurs répondent sans passer par `process` :
        # leurs charges utiles littérales complètent la source de vérité.
        server = (self.ROOT / "app.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(server)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_send_json"
            ):
                for argument in node.args:
                    if isinstance(argument, ast.Dict):
                        emitted |= {
                            key.value
                            for key in argument.keys
                            if isinstance(key, ast.Constant)
                            and isinstance(key.value, str)
                        }

        self.assertEqual(
            sorted(self._browser_reads("data") - emitted),
            [],
            "l'interface lit un champ de réponse que le serveur n'envoie jamais",
        )


class ClaimSchemaTests(unittest.TestCase):
    def test_every_array_is_bounded(self):
        """Un tableau sans maxItems laisse le décodage contraint boucler.

        Constaté en conditions réelles : `source_indices` produisait
        251, 252, 253… jusqu'à épuiser la limite de génération, tronquant le
        JSON au milieu et faisant passer un défaut de schéma pour une
        défaillance du modèle.
        """
        unbounded = [
            name
            for name, spec in CLAIM_SCHEMA["properties"].items()
            if spec.get("type") == "array" and "maxItems" not in spec
        ]

        self.assertEqual(unbounded, [])

    @patch("agent._chat")
    def test_truncated_generation_is_reported_as_such(self, chat):
        chat.return_value = {
            "done_reason": "length",
            "message": {"content": '{"eligibility": "lik'},
        }

        with self.assertRaises(AgentError) as raised:
            draft_claim({}, {}, {}, {})

        self.assertIn("tronquée", str(raised.exception))


class AirportCoverageTests(unittest.TestCase):
    """La table d'aéroports doit rester géographiquement correcte."""

    def test_uk_airports_are_outside_the_eu261_scope_since_brexit(self):
        for code in ("LHR", "LGW", "STN", "MAN", "EDI"):
            self.assertFalse(AIRPORTS[code]["eu"], code)

    def test_eea_and_switzerland_are_inside_the_scope(self):
        for code in ("OSL", "KEF", "ZRH", "GVA"):
            self.assertTrue(AIRPORTS[code]["eu"], code)

    def test_added_airports_produce_plausible_distances(self):
        # Références orthodromiques connues, tolérance 3 %.
        for origin, destination, expected in (
            ("CDG", "MUC", 682),
            ("JFK", "LHR", 5540),
            ("CDG", "LIS", 1470),
        ):
            distance = compute_distance(origin, destination)
            self.assertAlmostEqual(distance, expected, delta=expected * 0.03)

    def test_unknown_code_still_refuses_to_estimate(self):
        with self.assertRaises(ValueError) as raised:
            compute_distance("TLV", "CDG")
        self.assertIn("TLV", str(raised.exception))

    def test_coordinates_are_within_valid_ranges(self):
        for code, airport in AIRPORTS.items():
            self.assertTrue(-90 <= airport["lat"] <= 90, code)
            self.assertTrue(-180 <= airport["lon"] <= 180, code)
            self.assertIsInstance(airport["eu"], bool, code)


class LocalAirlinePolicyTests(unittest.TestCase):
    """Le corpus procédural local doit fonctionner sans réseau ni identité."""

    def test_known_airline_returns_sourced_procedures(self):
        result = retrieve_airline_policy(
            {"airline": "Air France", "disruption_type": "delay"}
        )

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["company"], "Air France")
        self.assertTrue(result["incident_specific"])
        self.assertTrue(result["procedures"])
        procedure = result["procedures"][0]
        self.assertTrue(procedure["steps"])
        self.assertTrue(procedure["sources"])
        self.assertTrue(procedure["sources"][0]["link"].startswith("https://"))
        self.assertTrue(procedure["sources"][0]["verified_on"])

    def test_alias_matching_is_case_insensitive(self):
        for alias in ("TAP", "tap air portugal", "  TAP  "):
            result = retrieve_airline_policy(
                {"airline": alias, "disruption_type": "cancellation"}
            )
            self.assertEqual(result["status"], "found", alias)
            self.assertEqual(result["company"], "TAP Air Portugal", alias)

    def test_unknown_airline_never_invents_a_procedure(self):
        result = retrieve_airline_policy(
            {"airline": "Aurora Airlines", "disruption_type": "delay"}
        )

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["procedures"], [])
        self.assertIsNone(result["company"])

    def test_freshness_is_reported_and_never_assumed(self):
        result = retrieve_airline_policy(
            {"airline": "easyJet", "disruption_type": "delay"}
        )

        self.assertIn(result["freshness"], {"fresh", "stale"})
        self.assertTrue(result["verified_on"])

    def test_minimized_arguments_are_accepted_without_disruption_type(self):
        """Le dispatcher n'envoie que les arguments validés, sans le dossier."""
        result = retrieve_airline_policy(
            {"airline": "easyJet", "incident": "flight_delay"}
        )

        self.assertEqual(result["status"], "found")
        self.assertTrue(result["incident_specific"])

    def test_retrieval_never_touches_the_network(self):
        with patch("tools.urllib.request.urlopen") as urlopen:
            retrieve_airline_policy(
                {"airline": "Air France", "disruption_type": "delay"}
            )
        urlopen.assert_not_called()

    def test_context_derives_incident_and_carries_no_identity(self):
        context = build_research_context(
            {
                "airline": "Air France",
                "disruption_type": "cancellation",
                "passenger_name": "MARTIN LEA",
                "booking_reference": "FQ7T2K",
            }
        )

        self.assertEqual(context["policy_incident"], "flight_cancellation")
        self.assertNotIn("MARTIN LEA", str(context))
        self.assertNotIn("FQ7T2K", str(context))

    def test_tool_schema_is_declared_and_restricted(self):
        declaration = next(
            item["function"]
            for item in RESEARCH_TOOL_DEFINITIONS
            if item["function"]["name"] == "retrieve_airline_policy"
        )
        parameters = declaration["parameters"]

        self.assertFalse(parameters["additionalProperties"])
        self.assertEqual(set(parameters["required"]), {"airline", "incident"})
        self.assertIn("flight_delay", parameters["properties"]["incident"]["enum"])


# Le témoin de régression rejoue le scénario de démonstration en substituant les
# deux seules frontières non déterministes du pipeline : le modèle
# (`agent._chat`) et le réseau (`tools.web_search`). Tout ce qui se trouve entre
# les deux — extraction, routage, sélection d'outils, filtrage des sources,
# qualification, remboursement, validation de la lettre, trace — reste dans la
# surface comparée. Mocker `verify_air_passenger_rule` en entier aurait sorti le
# filtre de sources officielles du champ de vision ; comparer `sample_output.json`
# moins des exclusions aurait fait un trou exactement là où le mode dégradé se
# décide, et six lots de refactor auraient pu le franchir sans bruit.
WITNESS_DOCUMENT = "billet_avion_fictif.png"
WITNESS_INCIDENT = (
    "Le vol est arrivé avec 3 h 25 de retard après un problème technique."
)
WITNESS_BOOKING_REFERENCE = "FQ7T2K"

# Avant le 14 septembre 2026, donc `check_flight_date` conclut `implausible`.
# Sans ce gel, le filet censé protéger six lots de refactor virerait au rouge le
# jour du vol de démonstration, sans qu'une ligne de code ait bougé.
WITNESS_TODAY = datetime.date(2026, 7, 25)


class _WitnessDate(datetime.date):
    """Horloge du témoin, figée à `WITNESS_TODAY`."""

    frozen = WITNESS_TODAY

    @classmethod
    def today(cls):
        return cls.frozen


# Sortie brute de Gemma sur le billet, telle qu'observée : « LIONNONE LIS » au
# lieu de « LISBONNE LIS ». Le défaut de lecture est conservé volontairement. Le
# témoin fige ce que le pipeline fait, pas ce qu'on voudrait qu'il fasse, et ce
# libellé déformé se propage jusqu'aux arguments d'outils : le jour où le lot 1
# le corrigera, c'est ce fichier qui devra bouger, sciemment.
WITNESS_EXTRACTION_RESPONSE = {
    "message": {
        "content": json.dumps(
            {
                "document_type": "boarding_pass",
                "passenger_name": "MARTIN LEA",
                "airline": "AURORA AIRLINES",
                "flight_number": "AU 3127",
                "origin": "PARIS CDG",
                "destination": "LIONNONE LIS",
                "departure_date": "2026-09-14",
                "scheduled_departure": "09:25",
                "scheduled_arrival": None,
                "actual_arrival": None,
                "boarding_time": "08:55",
                "booking_reference": "FQ7T2K",
                "seat": "14C",
                "gate": "B7",
                "disruption_type": "unknown",
                "delay_minutes": None,
                "arrival_delay_minutes": None,
                "departure_delay_minutes": None,
                "trip_completed": None,
                "disruption_cause": None,
                "evidence": [
                    "Date: 14 SEPT. 2026",
                    "Heure: 09:25",
                    "Vol: AU 3127",
                ],
                "uncertain_fields": ["scheduled_arrival"],
            },
            ensure_ascii=False,
        )
    }
}

# Un outil par tour : c'est ce que fait le modèle en vrai, et c'est le seul
# scénario qui exerce les allers-retours de résultats vers le prompt. Les
# arguments sont écrits en dur plutôt que dérivés de `_expected_tool_arguments`,
# sinon la validation stricte se comparerait à elle-même.
WITNESS_TOOL_RESPONSES = [
    {
        "message": {
            "tool_calls": [
                {
                    "function": {
                        "name": "verify_air_passenger_rule",
                        "arguments": {
                            "disruption_type": "delay",
                            "origin": "PARIS CDG",
                            "destination": "LIONNONE LIS",
                            "arrival_delay_minutes": 205,
                            "departure_delay_minutes": None,
                        },
                    }
                }
            ]
        }
    },
    {
        "message": {
            "tool_calls": [
                {
                    "function": {
                        "name": "find_claim_channel",
                        "arguments": {"airline": "AURORA AIRLINES"},
                    }
                }
            ]
        }
    },
    {
        "message": {
            "tool_calls": [
                {
                    "function": {
                        "name": "retrieve_airline_policy",
                        "arguments": {
                            "airline": "AURORA AIRLINES",
                            "incident": "flight_delay",
                        },
                    }
                }
            ]
        }
    },
]

WITNESS_CLAIM_RESPONSE = {
    "message": {
        "content": json.dumps(
            {
                "eligibility": "likely",
                "summary": (
                    "Le vol AU 3127 a subi un retard de 205 minutes (3h25) à "
                    "l'arrivée à Lisbonne. Ce retard dépasse le seuil de 3 "
                    "heures, ce qui ouvre droit à une indemnisation forfaitaire "
                    "selon le règlement EU261."
                ),
                "estimated_compensation_eur": 250,
                "reasoning": [
                    "Le retard constaté est de 205 minutes "
                    "[INDEMNISATION_EU261].",
                    "La distance du vol (1470.2 km) et la durée du retard "
                    "permettent d'envisager une indemnisation forfaitaire "
                    "[INDEMNISATION_EU261].",
                    "Bien qu'un problème technique soit mentionné, cette cause "
                    "déclarée n'exonère en principe pas le transporteur de son "
                    "obligation d'indemnisation [INDEMNISATION_EU261].",
                ],
                "letter_subject": (
                    "Réclamation pour retard de vol - Vol AU 3127 du 14/09/2026"
                ),
                "letter_body": (
                    "Madame, Monsieur,\n\nJe vous contacte concernant mon "
                    "voyage sur le vol AU 3127 en provenance de Paris (CDG) à "
                    "destination de Lisbonne (LIS) le 14 septembre 2026 "
                    "(Référence de réservation : FQ7T2K).\n\nMon vol est arrivé "
                    "avec un retard de 205 minutes. En raison de ce retard "
                    "supérieur à trois heures sur un trajet de cette distance, "
                    "je sollicite une indemnisation forfaitaire conformément au "
                    "règlement européen applicable [INDEMNISATION_EU261].\n\n"
                    "Dans l'attente de votre retour,\n\nCordialement,\n\n"
                    "MARTIN LEA"
                ),
                "checklist": ["Adresser la demande au transporteur."],
                "warnings": [],
            },
            ensure_ascii=False,
        )
    }
}

WITNESS_CHAT_RESPONSES = [
    WITNESS_EXTRACTION_RESPONSE,
    *WITNESS_TOOL_RESPONSES,
    WITNESS_CLAIM_RESPONSE,
]

# Réponse SerpApi figée. Le troisième résultat est un intermédiaire à commission
# que `_filter_official_rule_sources` doit écarter : le témoin échouerait si un
# refactor rouvrait la lettre à ces adresses.
WITNESS_SEARCH_RESULTS = [
    {
        "title": "Droits des passagers aériens - Your Europe",
        "link": (
            "https://europa.eu/youreurope/citizens/travel/passenger-rights/"
            "air/index_fr.htm"
        ),
        "snippet": (
            "Ces droits sont proportionnels à la durée du retard et à la "
            "distance du vol."
        ),
    },
    {
        "title": "FAQ|Droits des passagers aériens - Your Europe",
        "link": (
            "https://europa.eu/youreurope/citizens/travel/passenger-rights/"
            "air/faq/index_fr.htm"
        ),
        "snippet": (
            "Si votre vol a deux heures de retard ou plus au départ, la "
            "compagnie aérienne doit vous offrir une assistance."
        ),
    },
    {
        "title": "Indemnisation vol retardé",
        "link": "https://www.airhelp.com/fr/",
        "snippet": "Réclamez jusqu'à 600 € par passager.",
    },
]


def replay_witness_pipeline(today: datetime.date = WITNESS_TODAY) -> dict:
    """Rejoue le pipeline de démonstration hors ligne, horloge gelée."""
    root = pathlib.Path(__file__).resolve().parent

    class FrozenDate(_WitnessDate):
        frozen = today

    with patch("agent._chat", side_effect=list(WITNESS_CHAT_RESPONSES)), patch(
        "tools.web_search", return_value=list(WITNESS_SEARCH_RESULTS)
    ), patch("agent.date", FrozenDate):
        return process(
            root / WITNESS_DOCUMENT,
            WITNESS_INCIDENT,
            confirmed_booking_reference=WITNESS_BOOKING_REFERENCE,
        )


def witness_comparable(value, key: str | None = None):
    """Neutralise les deux valeurs qui ne se reproduisent jamais à l'identique.

    `duration_seconds` est une mesure d'horloge murale : 10,69 s derrière un
    vrai Ollama, 0,0 s ici, et 0,01 s le jour où le runner d'intégration est
    chargé — un témoin qui la compare mesure la machine, pas le code. `document`
    porte un chemin absolu propre au poste. Rien d'autre n'est neutralisé : un
    témoin qui compare trois champs est pire qu'inutile, il donne une fausse
    sécurité pendant six lots de refactor.
    """
    if isinstance(value, dict):
        return {
            name: witness_comparable(item, name) for name, item in value.items()
        }
    if isinstance(value, list):
        return [witness_comparable(item) for item in value]
    if key == "duration_seconds":
        return 0
    if key == "document":
        return pathlib.PurePath(str(value)).name
    return value


def witness_paths(value, prefix: str = ""):
    """Aplatit un document JSON en chemins pointés, feuilles comprises.

    Un conteneur vide est sa propre feuille, sinon la disparition du dernier
    élément d'une liste passerait pour une absence de chemin des deux côtés.
    """
    if isinstance(value, dict) and value:
        for name, item in value.items():
            yield from witness_paths(item, f"{prefix}.{name}" if prefix else name)
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from witness_paths(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def build_witness() -> dict:
    """Le témoin tel qu'il est versionné : la sortie réelle, forme comparée.

    Le fichier de référence n'est jamais écrit à la main. Le versionner sous sa
    forme neutralisée évite d'y figer un chemin absolu et des mesures d'horloge
    qu'aucune relecture ne pourrait valider.
    """
    return witness_comparable(replay_witness_pipeline())


def _witness_extract(value) -> str:
    """Repr tronquée : la lettre fait 900 caractères, l'écart en fait vingt."""
    rendered = repr(value)
    return rendered if len(rendered) <= 110 else rendered[:107] + "..."


def _witness_gap(expected, produced) -> str:
    """Situe l'écart de deux textes longs, au lieu de les tronquer par la gauche.

    Deux lettres qui divergent au 600e caractère donnent, coupées à 110, deux
    extraits rigoureusement identiques : le message d'échec dirait « ceci
    diffère de cela » en affichant deux fois la même phrase.
    """
    plain = f"{_witness_extract(expected)} -> {_witness_extract(produced)}"
    if not (isinstance(expected, str) and isinstance(produced, str)):
        return plain
    if max(len(expected), len(produced)) <= 108:
        return plain
    offset = next(
        (
            index
            for index, (left, right) in enumerate(zip(expected, produced))
            if left != right
        ),
        min(len(expected), len(produced)),
    )
    start = max(0, offset - 30)
    return (
        f"au caractère {offset}, {_witness_extract(expected[start:offset + 50])} "
        f"-> {_witness_extract(produced[start:offset + 50])}"
    )


def witness_differences(reference, produced) -> list[str]:
    """Nomme chaque champ qui diverge, plutôt que « les dicts diffèrent »."""
    expected = dict(witness_paths(reference))
    actual = dict(witness_paths(produced))
    differences = []
    for path in sorted(set(expected) | set(actual)):
        if path not in actual:
            differences.append(
                f"- {path} : disparu (témoin : {_witness_extract(expected[path])})"
            )
        elif path not in expected:
            differences.append(f"+ {path} : apparu ({_witness_extract(actual[path])})")
        elif expected[path] != actual[path]:
            gap = _witness_gap(expected[path], actual[path])
            differences.append(f"~ {path} : {gap}")
    return differences


class RegressionWitnessTests(unittest.TestCase):
    """Le pipeline complet, rejoué hors ligne et comparé champ par champ.

    Six lots de refactor vont réécrire `agent.py`. Un test qui vérifierait trois
    clés les laisserait tous passer : la comparaison porte sur le document
    entier — extraction, décision, montant, qualification, remboursement, refus,
    droit non couvert, lettre et trace.
    """

    ROOT = pathlib.Path(__file__).resolve().parent
    WITNESS = ROOT / "examples" / "regression_witness.json"
    REGENERATE = (
        "python3 -c \"import json, test_agent as t; "
        "print(json.dumps(t.build_witness(), ensure_ascii=False, indent=2))\" "
        "> examples/regression_witness.json"
    )

    def test_pipeline_output_matches_the_frozen_witness(self):
        reference = json.loads(self.WITNESS.read_text(encoding="utf-8"))

        differences = witness_differences(
            witness_comparable(reference),
            witness_comparable(replay_witness_pipeline()),
        )

        if differences:
            # `assertEqual` sur deux listes ferait précéder le diff lisible de
            # son propre diff de listes, illisible sur un dossier de cette
            # taille. On échoue avec le seul message qui nomme les champs.
            self.fail(
                "la sortie du pipeline diverge du témoin :\n"
                + "\n".join(differences)
                + "\n\nSi l'écart est voulu, régénérer sciemment :\n"
                + self.REGENERATE
            )

    def test_the_witness_pins_every_block_of_the_answer(self):
        """Un témoin amputé donnerait une fausse sécurité pendant six lots."""
        reference = json.loads(self.WITNESS.read_text(encoding="utf-8"))
        covered = {path for path, _ in witness_paths(witness_comparable(reference))}

        for field in (
            "extraction.flight_number",
            "extraction.arrival_delay_minutes",
            "decision.status",
            "research.rights.status",
            "qualification.status",
            "qualification.compensation_eur",
            "reimbursement.status",
            "refusal",
            "uncovered_right",
            "claim.letter_body",
            "trace[0].step",
        ):
            self.assertIn(field, covered, field)

    def test_replay_never_touches_the_network(self):
        """Ni Ollama, ni clé SerpApi, ni socket : le filet doit tourner partout.

        `agent.urllib` et `tools.urllib` désignent le même module, donc une
        seule substitution couvre les deux sorties réseau du dépôt.
        """
        with patch("agent.urllib.request.urlopen") as urlopen:
            replay_witness_pipeline()

        urlopen.assert_not_called()

    def test_the_frozen_clock_is_load_bearing(self):
        """Le 14 septembre 2026, l'étape de vraisemblance disparaît d'elle-même.

        Sans gel, ce test-ci serait le témoin, et il virerait au rouge ce jour-là
        sur un dossier inchangé.
        """
        before = replay_witness_pipeline()
        after = replay_witness_pipeline(datetime.date(2026, 9, 15))

        self.assertIn(
            "check_flight_date", [step["step"] for step in before["trace"]]
        )
        self.assertNotIn(
            "check_flight_date", [step["step"] for step in after["trace"]]
        )

    def test_durations_are_neutralised_at_every_depth(self):
        normalised = witness_comparable(
            {
                "duration_seconds": 22.57,
                "trace": [{"step": "extract_flight", "duration_seconds": 10.69}],
            }
        )

        self.assertEqual(normalised["duration_seconds"], 0)
        self.assertEqual(normalised["trace"][0]["duration_seconds"], 0)
        self.assertEqual(normalised["trace"][0]["step"], "extract_flight")

    def test_a_divergence_names_the_field_and_both_values(self):
        differences = witness_differences(
            {"qualification": {"compensation_eur": 250, "status": "likely"}},
            {"qualification": {"compensation_eur": 400, "status": "likely"}},
        )

        self.assertEqual(len(differences), 1)
        self.assertIn("qualification.compensation_eur", differences[0])
        self.assertIn("250", differences[0])
        self.assertIn("400", differences[0])

    def test_a_divergence_inside_a_long_letter_stays_readable(self):
        """Tronquée par la gauche, une lettre de 900 signes cache son écart."""
        letter = "Madame, Monsieur, " + "je vous écris. " * 60
        differences = witness_differences(
            {"claim": {"letter_body": letter + "250 €."}},
            {"claim": {"letter_body": letter + "400 €."}},
        )

        self.assertEqual(len(differences), 1)
        self.assertIn("claim.letter_body", differences[0])
        self.assertIn("250", differences[0])
        self.assertIn("400", differences[0])


if __name__ == "__main__":
    unittest.main()
