"""Tests déterministes du routage de dossiers aériens."""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch
import wave
from zoneinfo import ZoneInfo

from agent import (
    AgentError,
    CLAIM_SCHEMA,
    _chat,
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
from tools import (
    RESEARCH_TOOL_DEFINITIONS,
    _api_key,
    build_research_context,
    build_rule_query,
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


if __name__ == "__main__":
    unittest.main()
