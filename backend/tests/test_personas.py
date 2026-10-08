"""Persona screening, uncertainty, and graph isolation across applicant types."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rdflib import Literal
from app import dispatch, lambda_handler
from engine import InputError, NS, analyze, context_graph, evaluate
from fixture import ALL_SCHEMES, PERSONAS, PROFILE, PROFILES, scenario_fixture


ROOTS = {
    "individuals": {"resident-demo", "household-demo"},
    "businesses": {"business-demo", "business-context"},
    "community": {"community-demo", "community-context"},
    "research": {"research-demo", "research-context"},
}
DEFAULT_MATCHES = {
    "individuals": {"scheme-bridge", "scheme-skills"},
    "businesses": {"scheme-digital-spark"},
    "community": {"scheme-community-impact"},
    "research": {"scheme-discovery-catalyst"},
}
PRESET_MATCHES = {
    "businesses": {
        "digital-sme": {"scheme-digital-spark"},
        "ai-startup": {"scheme-digital-spark"},
        "workforce-project": {"scheme-workforce-lift"},
        "green-project": {"scheme-green-launch"},
        "unknown-ownership": set(),
    },
    "community": {
        "social-service": {"scheme-community-impact"},
        "capability-project": {"scheme-community-capability"},
        "arts-project": {"scheme-creative-youth"},
        "youth-project": {"scheme-creative-youth"},
        "unknown-benefit": set(),
    },
    "research": {
        "university-research": {"scheme-discovery-catalyst"},
        "industry-collaboration": {"scheme-collaboration-forge"},
        "education-project": {"scheme-learning-futures"},
        "scholarship-project": {"scheme-learning-futures"},
        "unknown-ethics": set(),
    },
}


def schemes_by_id(result):
    return {scheme["id"]: scheme for scheme in result["schemes"]}


def screen(persona_id, changes=None, **options):
    return analyze({"persona": persona_id, "profile": {**PROFILES[persona_id], **(changes or {})}, **options})


class PersonaScreeningTests(unittest.TestCase):
    def assert_scoped(self, result, persona_id):
        own = scenario_fixture(persona_id)
        own_node_ids = {node["id"] for node in own["nodes"]}
        foreign_node_ids = {
            node["id"] for other in PERSONAS if other != persona_id
            for node in scenario_fixture(other)["nodes"]
        }
        own_evidence = {item["id"] for item in own["evidence"]}
        expected_schemes = {scheme["id"] for scheme in ALL_SCHEMES if scheme["persona"] == persona_id}
        self.assertEqual(result["persona"], persona_id)
        self.assertEqual(set(schemes_by_id(result)), expected_schemes)
        self.assertTrue(ROOTS[persona_id] <= set(result["affectedNodeIds"]))
        self.assertTrue(set(result["affectedNodeIds"]) <= own_node_ids)
        self.assertTrue({item["id"] for item in result["citations"]} <= own_evidence)
        self.assertTrue(set(result["highlightedEdgeIds"]) <= {edge["id"] for edge in own["edges"]})
        self.assertFalse({item["id"] for item in result["context"]} & foreign_node_ids)
        for entity in result["context"]:
            for relationship in entity["relationships"]:
                for endpoint in ("source_uri", "target_uri"):
                    self.assertNotIn(relationship[endpoint].removeprefix(str(NS)), foreign_node_ids)
        for scheme in result["schemes"]:
            self.assertTrue(set(scheme["pathNodeIds"]) <= own_node_ids)
            self.assertTrue(set(scheme["evidenceIds"]) <= own_evidence)
            self.assertTrue(set(scheme["documentIds"]) <= own_node_ids)
        if persona_id != "individuals":
            self.assertFalse(ROOTS["individuals"] & set(result["affectedNodeIds"]))
            self.assertNotIn("ev-profile", {item["id"] for item in result["citations"]})
            self.assertNotIn("ev-calculation", {item["id"] for item in result["citations"]})

    def test_default_profiles_match_their_own_support_paths(self):
        for persona_id in PERSONAS:
            with self.subTest(persona=persona_id):
                result = screen(persona_id)
                self.assert_scoped(result, persona_id)
                self.assertEqual({scheme["id"] for scheme in result["schemes"] if scheme["status"] == "likely-eligible"}, DEFAULT_MATCHES[persona_id])
                self.assertEqual(result["metrics"]["needsReview"], 0)
                self.assertGreater(result["metrics"]["contextEntities"], 0)
                self.assertEqual(result["engine"]["ruleEvaluation"], "SPARQL tri-state criteria")

    def test_omitted_persona_preserves_individual_default(self):
        result = analyze({"profile": PROFILE})
        self.assert_scoped(result, "individuals")
        self.assertEqual(result["metrics"]["perCapitaIncome"], 900)
        self.assertEqual(result["metrics"]["likelyEligible"], 2)

    def test_presets_change_matches_and_connected_paths_without_cross_persona_leakage(self):
        for persona_id, expected_presets in PRESET_MATCHES.items():
            previous_paths = set()
            for preset in scenario_fixture(persona_id)["presets"]:
                with self.subTest(persona=persona_id, preset=preset["id"]):
                    result = analyze({"persona": persona_id, "profile": preset["profile"]})
                    self.assert_scoped(result, persona_id)
                    self.assertEqual({scheme["id"] for scheme in result["schemes"] if scheme["status"] == "likely-eligible"}, expected_presets[preset["id"]])
                    matched_ids = {scheme["id"] for scheme in result["schemes"] if scheme["status"] != "not-eligible"}
                    self.assertTrue(matched_ids <= set(result["affectedNodeIds"]))
                    previous_paths.add(tuple(result["highlightedEdgeIds"]))
                    if preset["id"].startswith("unknown-"):
                        self.assertEqual(result["metrics"]["needsReview"], 1)
            self.assertGreaterEqual(len(previous_paths), 3)

    def test_omitted_facts_are_unknown_for_every_persona(self):
        for persona_id, persona in PERSONAS.items():
            with self.subTest(persona=persona_id):
                result = analyze({"persona": persona_id, "profile": {}})
                self.assertEqual(set(result["profile"]), {field["key"] for field in persona["fields"]})
                self.assertTrue(all(value is None for value in result["profile"].values()))
                self.assertTrue(all(scheme["status"] == "needs-review" for scheme in result["schemes"]))
                self.assertTrue(all(rule["actual"] is None and rule["result"] == "unknown" for scheme in result["schemes"] for rule in scheme["ruleResults"]))
                self.assert_scoped(result, persona_id)

    def test_known_registration_failure_precedes_unknown_facts(self):
        for persona_id in ("businesses", "community", "research"):
            with self.subTest(persona=persona_id):
                result = analyze({"persona": persona_id, "profile": {"localRegistration": False}})
                self.assertTrue(all(scheme["status"] == "not-eligible" for scheme in result["schemes"]))
                self.assertEqual(result["metrics"]["needsReview"], 0)
                self.assert_scoped(result, persona_id)

    def test_business_numeric_rule_boundaries_are_inclusive(self):
        cases = [
            ("localOwnership", 30, 29.99),
            ("employeeCount", 200, 201),
            ("annualRevenue", 100000000, 100000000.01),
            ("coFunding", 30, 29.99),
        ]
        for field, boundary, beyond in cases:
            with self.subTest(field=field):
                for value, expected in ((boundary, "likely-eligible"), (beyond, "not-eligible")):
                    graph, _ = context_graph({**PROFILES["businesses"], field: value}, "businesses")
                    scheme = next(item for item in evaluate(graph, "businesses") if item["id"] == "scheme-digital-spark")
                    self.assertEqual(scheme["status"], expected)
                    rule = next(item for item in scheme["ruleResults"] if item["field"] == field)
                    self.assertEqual(rule["actual"], value)

    def test_community_and_research_budget_boundaries(self):
        cases = [
            ("community", "social-service", "scheme-community-impact", 100000),
            ("community", "capability-project", "scheme-community-capability", 50000),
            ("community", "arts-project", "scheme-creative-youth", 40000),
            ("research", "university-research", "scheme-discovery-catalyst", 300000),
            ("research", "industry-collaboration", "scheme-collaboration-forge", 500000),
            ("research", "education-project", "scheme-learning-futures", 100000),
        ]
        for persona_id, preset_id, scheme_id, boundary in cases:
            profile = next(item["profile"] for item in scenario_fixture(persona_id)["presets"] if item["id"] == preset_id)
            with self.subTest(persona=persona_id, scheme=scheme_id):
                for budget, expected in ((boundary, "likely-eligible"), (boundary + 0.01, "not-eligible")):
                    graph, _ = context_graph({**profile, "projectBudget": budget}, persona_id)
                    scheme = next(item for item in evaluate(graph, persona_id) if item["id"] == scheme_id)
                    self.assertEqual(scheme["status"], expected)
                    self.assertEqual(next(rule["actual"] for rule in scheme["ruleResults"] if rule["field"] == "projectBudget"), budget)

    def test_student_and_senior_journeys_have_distinct_evidence_and_boundaries(self):
        cases = [
            ("student-education", "scheme-student-pathways", "education", "doc-enrolment", "age", 16, 15),
            ("student-education", "scheme-student-pathways", "education", "doc-enrolment", "age", 30, 31),
            ("student-education", "scheme-student-pathways", "education", "doc-enrolment", "householdIncome", 6400, 6400.01),
            ("senior-healthcare", "scheme-senior-health", "healthcare", "doc-senior-health", "age", 65, 64),
            ("senior-healthcare", "scheme-senior-health", "healthcare", "doc-senior-health", "householdIncome", 7200, 7200.01),
        ]
        for preset_id, scheme_id, category, document_id, field, boundary, beyond in cases:
            profile = next(item["profile"] for item in scenario_fixture("individuals")["presets"] if item["id"] == preset_id)
            with self.subTest(preset=preset_id, field=field, boundary=boundary):
                for value, expected in ((boundary, "likely-eligible"), (beyond, "not-eligible")):
                    graph, _ = context_graph({**profile, field: value}, "individuals")
                    scheme = next(item for item in evaluate(graph, "individuals") if item["id"] == scheme_id)
                    self.assertEqual(scheme["status"], expected)
                    self.assertEqual(scheme["categories"], [category])
                    self.assertIn(document_id, scheme["documentIds"])
        for preset_id, scheme_id in (("student-education", "scheme-student-pathways"), ("senior-healthcare", "scheme-senior-health")):
            profile = next(item["profile"] for item in scenario_fixture("individuals")["presets"] if item["id"] == preset_id)
            result = analyze({"persona": "individuals", "profile": profile})
            self.assert_scoped(result, "individuals")
            self.assertEqual({scheme["id"] for scheme in result["schemes"] if scheme["status"] == "likely-eligible"}, {scheme_id})
            self.assertIn(scheme_id, result["affectedNodeIds"])

    def test_policy_threshold_and_category_are_read_from_rdf(self):
        graph, _ = context_graph(PROFILES["businesses"], "businesses")
        original = next(item for item in evaluate(graph, "businesses") if item["id"] == "scheme-digital-spark")
        self.assertEqual(original["status"], "likely-eligible")
        graph.set((NS["rule-digital-spark-3"], NS.expected, Literal(65)))
        graph.set((NS["scheme-digital-spark"], NS.category, Literal("updated-category")))
        changed = next(item for item in evaluate(graph, "businesses") if item["id"] == "scheme-digital-spark")
        self.assertEqual(changed["status"], "not-eligible")
        self.assertEqual(next(rule["expected"] for rule in changed["ruleResults"] if rule["field"] == "localOwnership"), 65)
        self.assertEqual(changed["categories"], ["updated-category"])

    def test_scoped_prompts_and_citations_follow_each_persona(self):
        for persona_id, persona in PERSONAS.items():
            for question in persona["prompts"]:
                with self.subTest(persona=persona_id, question=question):
                    result = screen(persona_id, question=question)
                    self.assertTrue(result["questionSupported"])
                    self.assert_scoped(result, persona_id)
                    self.assertTrue(result["citations"])

    def test_unsupported_questions_are_bounded_for_organisation_personas(self):
        for persona_id in ("businesses", "community", "research"):
            with self.subTest(persona=persona_id), patch("engine.bedrock_synthesis") as synthesis:
                result = screen(persona_id, question="Who won the World Cup?", useBedrock=True)
                synthesis.assert_not_called()
                self.assertFalse(result["questionSupported"])
                self.assertEqual(result["citations"], [])
                self.assertEqual(result["context"], [])
                self.assertIn("cannot support", result["answer"])
                self.assertIn(PERSONAS[persona_id]["name"], result["answer"])
                self.assertNotIn("household", result["answer"].lower())
                self.assertNotIn("citizen", result["answer"].lower())
                self.assert_scoped(result, persona_id)


class PersonaApiValidationTests(unittest.TestCase):
    def test_scenario_api_exposes_four_entries_and_only_selected_graph(self):
        for persona_id in PERSONAS:
            with self.subTest(persona=persona_id):
                response = dispatch("GET", "/api/scenario", query={"persona": persona_id})
                self.assertEqual(response["statusCode"], 200)
                body = json.loads(response["body"])
                self.assertEqual(body["persona"]["id"], persona_id)
                self.assertEqual({item["id"] for item in body["personas"]}, set(PERSONAS))
                self.assertEqual(body["profile"], PROFILES[persona_id])
                self.assertTrue(body["scenario"]["synthetic"])
                self.assertEqual({node["id"] for node in body["nodes"] if node["type"] == "scheme"}, {scheme["id"] for scheme in ALL_SCHEMES if scheme["persona"] == persona_id})
                self.assertTrue(ROOTS[persona_id] <= {node["id"] for node in body["nodes"]})
        default = json.loads(dispatch("GET", "/api/scenario")["body"])
        self.assertEqual(default["persona"]["id"], "individuals")

    def test_lambda_forwards_persona_query_parameters(self):
        response = lambda_handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/api/scenario", "queryStringParameters": {"persona": "research"}}, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["persona"]["id"], "research")

    def assert_invalid(self, payload):
        with self.assertRaises(InputError):
            analyze(payload)
        self.assertEqual(dispatch("POST", "/api/analyze", json.dumps(payload))["statusCode"], 400)

    def test_unknown_personas_and_invalid_persona_types_are_rejected(self):
        for persona_id in ("unknown", "", "Businesses", None, False, 1, [], {}):
            with self.subTest(persona=persona_id):
                self.assert_invalid({"persona": persona_id, "profile": PROFILE})
                response = dispatch("GET", "/api/scenario", query={"persona": persona_id})
                self.assertEqual(response["statusCode"], 400)

    def test_profile_fields_cannot_be_shared_accidentally_between_personas(self):
        for persona_id in PERSONAS:
            for other in PERSONAS:
                if other != persona_id:
                    with self.subTest(persona=persona_id, profile=other):
                        self.assert_invalid({"persona": persona_id, "profile": PROFILES[other]})

    def test_every_persona_field_rejects_invalid_types_and_out_of_range_values(self):
        for persona_id, persona in PERSONAS.items():
            for field in persona["fields"]:
                key = field["key"]
                if field["type"] == "boolean":
                    invalid_values = ["true", 0, 1, [], {}]
                elif field["type"] == "select":
                    invalid_values = ["unsupported-option", False, 123, [], {}]
                else:
                    invalid_values = [True, "1", [], {}, -1, field["max"] + 1, float("inf"), float("nan")]
                    if field.get("step") == 1:
                        invalid_values.append(2.5)
                for invalid in invalid_values:
                    with self.subTest(persona=persona_id, field=key, value=invalid):
                        self.assert_invalid({"persona": persona_id, "profile": {**PROFILES[persona_id], key: invalid}})

    def test_null_is_preserved_instead_of_silently_using_scenario_defaults(self):
        cases = [
            ("businesses", "localOwnership", "scheme-digital-spark"),
            ("community", "publicBenefit", "scheme-community-impact"),
            ("research", "ethicsApproval", "scheme-discovery-catalyst"),
        ]
        for persona_id, field, scheme_id in cases:
            with self.subTest(persona=persona_id):
                result = screen(persona_id, {field: None})
                self.assertIsNone(result["profile"][field])
                scheme = schemes_by_id(result)[scheme_id]
                self.assertEqual(scheme["status"], "needs-review")
                self.assertEqual(next(rule["result"] for rule in scheme["ruleResults"] if rule["field"] == field), "unknown")
                self.assertIn(field, " ".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
