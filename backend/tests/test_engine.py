import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rdflib import Graph, Literal, RDF, OWL, URIRef
from app import dispatch, lambda_handler
from engine import BASE_GRAPH, NS, SCENARIO, InputError, analyze, context_graph, evaluate
from fixture import PROFILE


def scheme_map(result):
    return {scheme["id"]: scheme for scheme in result["schemes"]}


class EligibilityTests(unittest.TestCase):
    def test_default_profile_rule_trace_and_real_accelerator_context(self):
        result = analyze({"profile": PROFILE})
        schemes = scheme_map(result)
        self.assertEqual(schemes["scheme-bridge"]["status"], "likely-eligible")
        self.assertEqual(schemes["scheme-skills"]["status"], "likely-eligible")
        self.assertEqual(schemes["scheme-caregiver"]["status"], "not-eligible")
        self.assertEqual(result["metrics"]["perCapitaIncome"], 900)
        self.assertGreater(result["metrics"]["contextEntities"], 0)
        self.assertTrue(any(entity["id"].startswith("rule-") for entity in result["context"]))
        self.assertEqual(result["engine"]["ruleEvaluation"], "SPARQL tri-state criteria")
        self.assertEqual(len(schemes["scheme-bridge"]["ruleResults"]), 4)

    def test_income_and_household_size_change_decision(self):
        above = analyze({"profile": {**PROFILE, "householdIncome": 4000.01}})
        self.assertEqual(scheme_map(above)["scheme-bridge"]["status"], "not-eligible")
        # Preserve the exact quotient in evidence; presentation may round it.
        self.assertAlmostEqual(above["metrics"]["perCapitaIncome"], 1000.0025)
        self.assertAlmostEqual(scheme_map(above)["scheme-bridge"]["ruleResults"][-1]["actual"], 1000.0025)
        boundary = analyze({"profile": {**PROFILE, "householdIncome": 4000}})
        self.assertEqual(scheme_map(boundary)["scheme-bridge"]["status"], "likely-eligible")
        larger_household = analyze({"profile": {**PROFILE, "householdIncome": 5000, "householdSize": 5}})
        self.assertEqual(scheme_map(larger_household)["scheme-bridge"]["status"], "likely-eligible")

    def test_caregiving_reveals_connected_path(self):
        before = analyze({"profile": PROFILE})
        after = analyze({"profile": {**PROFILE, "caregiver": True, "householdIncome": 5400}})
        self.assertEqual(scheme_map(after)["scheme-caregiver"]["status"], "likely-eligible")
        self.assertEqual(scheme_map(after)["scheme-bridge"]["status"], "not-eligible")
        self.assertNotIn("scheme-caregiver", before["affectedNodeIds"])
        self.assertIn("scheme-caregiver", after["affectedNodeIds"])
        self.assertIn("event-caregiving", after["affectedNodeIds"])
        self.assertIn("doc-caregiving", after["affectedNodeIds"])

    def test_unknown_facts_require_review_not_approval(self):
        result = analyze({"profile": {**PROFILE, "householdIncome": None, "caregiver": True}})
        schemes = scheme_map(result)
        self.assertEqual(schemes["scheme-bridge"]["status"], "needs-review")
        self.assertEqual(schemes["scheme-caregiver"]["status"], "needs-review")
        self.assertEqual(schemes["scheme-skills"]["status"], "likely-eligible")
        self.assertIsNone(result["metrics"]["perCapitaIncome"])
        omitted = analyze({"profile": {}})
        self.assertEqual(omitted["metrics"]["needsReview"], 4)
        self.assertEqual(omitted["metrics"]["likelyEligible"], 0)

    def test_known_failure_precedes_unknown_in_conjunction(self):
        result = analyze({"profile": {**PROFILE, "householdIncome": None, "citizenship": "other"}})
        self.assertTrue(all(s["status"] == "not-eligible" for s in result["schemes"]))

    def test_permanent_resident_and_age_boundaries(self):
        eligible = scheme_map(analyze({"profile": {**PROFILE, "citizenship": "pr", "age": 60}}))
        self.assertEqual(eligible["scheme-skills"]["status"], "likely-eligible")
        self.assertEqual(eligible["scheme-bridge"]["status"], "not-eligible")
        ineligible = scheme_map(analyze({"profile": {**PROFILE, "citizenship": "permanent-resident", "age": 61}}))
        self.assertEqual(ineligible["scheme-skills"]["status"], "not-eligible")

    def test_policy_change_in_rdf_alters_decision_without_code_change(self):
        graph, _ = context_graph(PROFILE)
        original = next(s for s in evaluate(graph) if s["id"] == "scheme-bridge")
        self.assertEqual(original["status"], "likely-eligible")
        graph.set((NS["rule-bridge-4"], NS.expected, Literal(800)))
        changed = next(s for s in evaluate(graph) if s["id"] == "scheme-bridge")
        self.assertEqual(changed["status"], "not-eligible")
        self.assertEqual(changed["ruleResults"][-1]["expected"], 800)

    def test_graph_paths_and_citations_are_linked(self):
        result = analyze({"profile": PROFILE, "question": "Why am I eligible for the Household Bridge Grant?"})
        cited = {item["id"] for item in result["citations"]}
        self.assertIn("ev-bridge", cited)
        self.assertNotIn("ev-caregiver", cited)
        self.assertIn("[ev-bridge]", result["answer"])
        edge_ids = {edge["id"] for edge in SCENARIO["edges"]}
        self.assertTrue(set(result["highlightedEdgeIds"]) <= edge_ids)
        for scheme in result["schemes"]:
            for rule in scheme["ruleResults"]:
                linked = [edge for edge in SCENARIO["edges"] if edge["source"] == scheme["id"] and edge["target"] == rule["id"]]
                self.assertEqual(linked[0]["evidenceId"], rule["evidenceId"])

    def test_bounded_question_never_calls_bedrock(self):
        with patch("engine.bedrock_synthesis") as model:
            result = analyze({"profile": PROFILE, "question": "Who won the World Cup?", "useBedrock": True})
        model.assert_not_called()
        self.assertFalse(result["questionSupported"])
        self.assertIn("cannot support", result["answer"])
        self.assertEqual(result["citations"], [])

    def test_documents_question_returns_only_relevant_evidence(self):
        result = analyze({"profile": PROFILE, "question": "What income documents should this household prepare?"})
        self.assertIn("Employment transition record", result["answer"])
        self.assertNotIn("Caregiving declaration", result["answer"])

    def test_household_support_question_includes_non_income_scheme(self):
        result = analyze({"profile": PROFILE, "question": "What support could this household receive?"})
        self.assertIn("Skills Restart Support", result["answer"])
        self.assertIn("ev-skills", {item["id"] for item in result["citations"]})
        self.assertIn("scheme-skills", result["affectedNodeIds"])
        self.assertNotIn("scheme-caregiver", result["affectedNodeIds"])
        changed = analyze({"profile": {**PROFILE, "caregiver": True, "householdIncome": 5400}, "question": "What support could this household receive?"})
        self.assertIn("scheme-caregiver", changed["affectedNodeIds"])
        self.assertNotIn("scheme-bridge", changed["affectedNodeIds"])
        self.assertNotEqual(result["highlightedEdgeIds"], changed["highlightedEdgeIds"])

    def test_bedrock_failure_sanitized_and_explicit(self):
        with patch("engine.bedrock_synthesis", side_effect=RuntimeError("secret-token-should-not-leak")):
            result = analyze({"profile": PROFILE, "useBedrock": True})
        self.assertEqual(result["engine"]["synthesis"], "deterministic")
        self.assertIn("unavailable", " ".join(result["warnings"]))
        self.assertNotIn("secret-token", json.dumps(result))
        self.assertEqual(scheme_map(result)["scheme-bridge"]["status"], "likely-eligible")

    def test_actual_traversed_context_is_passed_to_synthesis(self):
        with patch("engine.bedrock_synthesis", return_value=("Fictional screening [ev-bridge].", "test-model")) as model:
            result = analyze({"profile": PROFILE, "useBedrock": True})
        context = model.call_args.args[4]
        self.assertEqual(len(context), result["metrics"]["contextEntities"])
        self.assertEqual(context, result["context"])
        self.assertTrue(any(e["id"] == "agency-support" for e in context))
        self.assertTrue(any(e["id"] == "doc-employment" for e in context))
        self.assertEqual(model.call_args.args[5], PROFILE)

    def test_traversed_relationship_direction_matches_authoritative_graph(self):
        result = analyze({"profile": PROFILE, "question": "Explain the Household Bridge Grant"})
        agency = next(e for e in result["context"] if e["id"] == "agency-support")
        relationship = next(r for r in agency["relationships"] if r["predicate"] == str(NS.administeredBy))
        self.assertEqual(relationship["source_uri"], str(NS["scheme-bridge"]))
        self.assertEqual(relationship["target_uri"], str(NS["agency-support"]))
        self.assertEqual(relationship["direction"], "incoming")
        for entity in result["context"]:
            for edge in entity["relationships"]:
                self.assertIn(tuple(URIRef(edge[k]) for k in ("source_uri", "predicate", "target_uri")), BASE_GRAPH)

    def test_profile_evidence_does_not_assert_outdated_household_facts(self):
        changed = {**PROFILE, "householdSize": 2, "recentJobLoss": False, "employmentStatus": "employed", "caregiver": True}
        result = analyze({"profile": changed, "question": "What documents should this household prepare?"})
        evidence = next(e for e in result["citations"] if e["id"] == "ev-profile")
        self.assertIn("current editable synthetic profile", evidence["excerpt"])
        self.assertNotIn("household of four", evidence["excerpt"])
        self.assertEqual(result["profile"]["householdSize"], 2)

    def test_environment_can_disable_synthesis(self):
        with patch.dict(os.environ, {"ENABLE_BEDROCK": "false"}), patch("engine.bedrock_synthesis") as model:
            result = analyze({"profile": PROFILE, "useBedrock": True})
        model.assert_not_called()
        self.assertEqual(result["engine"]["synthesis"], "deterministic")
        self.assertIn("disabled", " ".join(result["warnings"]))


class ApiTests(unittest.TestCase):
    def test_preflight_returns_no_citizen_data_or_analysis(self):
        with patch("app.analyze") as evaluate_request:
            result = dispatch("OPTIONS", "/api/scenario")
        self.assertEqual(result["statusCode"], 204)
        self.assertEqual(result["body"], "")
        evaluate_request.assert_not_called()

    def test_invalid_and_bounded_input(self):
        payloads = [None, [], {"profile": []}, {"profile": {"householdSize": 0}}, {"profile": {"householdSize": 2.5}}, {"profile": {"householdIncome": -1}}, {"profile": {"householdIncome": float("inf")}}, {"profile": {"age": True}}, {"profile": {"caregiver": "yes"}}, {"profile": {"citizenship": []}}, {"profile": {"nrIc": "private"}}, {"profile": PROFILE, "question": "a" * 1501}, {"profile": PROFILE, "useBedrock": "true"}]
        for payload in payloads:
            with self.subTest(payload=payload):
                result = dispatch("POST", "/api/analyze", json.dumps(payload))
                self.assertEqual(result["statusCode"], 400)
        self.assertEqual(dispatch("POST", "/api/analyze", "{bad-json")["statusCode"], 400)
        self.assertEqual(dispatch("POST", "/api/analyze", "x" * 16001)["statusCode"], 400)

    def test_lambda_http_v2_and_base64(self):
        result = lambda_handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/api/scenario"}, None)
        self.assertEqual(result["statusCode"], 200)
        self.assertTrue(json.loads(result["body"])["scenario"]["synthetic"])
        body = base64.b64encode(json.dumps({"profile": PROFILE}).encode()).decode()
        result = lambda_handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": "/api/analyze", "body": body, "isBase64Encoded": True}, None)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["metrics"]["likelyEligible"], 2)
        invalid = lambda_handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": "/api/analyze", "body": "not base64!", "isBase64Encoded": True}, None)
        self.assertEqual(invalid["statusCode"], 400)

    def test_ontology_export_schema_separate_from_instances(self):
        schema = dispatch("GET", "/api/ontology", query={"kind": "schema"})
        graph = Graph().parse(data=schema["body"], format="turtle")
        self.assertTrue(list(graph.subjects(RDF.type, OWL.Ontology)))
        self.assertFalse(list(graph.subjects(RDF.type, NS.Resident)))
        self.assertTrue(list(BASE_GRAPH.subjects(RDF.type, NS.Resident)))
        self.assertIn("text/turtle", schema["headers"]["content-type"])


if __name__ == "__main__":
    unittest.main()
