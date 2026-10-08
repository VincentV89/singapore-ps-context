"""Generate importable TBox and synthetic ABox using COA's real serializer."""
from datetime import datetime
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal
from serializer import serialize
from fixture import ALL_SCHEMES, PERSONAS, TIMESTAMP, scenario_fixture

NS = Namespace("https://demo.example.gov.sg/life-events/")
CLASSES = {"resident": "Resident", "organization": "Organization", "institution": "Institution", "context": "ApplicantContext", "need": "SupportNeed", "household": "Household", "event": "LifeEvent", "scheme": "Scheme", "rule": "EligibilityRule", "document": "Document", "agency": "Agency", "evidence": "Evidence", "edge": "Relationship"}
RELATIONS = {"operates with": ("hasApplicantContext", "Applicant", "ApplicantContext"), "has need": ("hasSupportNeed", "Applicant", "SupportNeed"), "belongs to": ("memberOf", "Resident", "Household"), "has context": ("hasLifeEvent", "Resident", "LifeEvent"), "may connect to": ("relatedScheme", "SupportNeed", "Scheme"), "administered by": ("administeredBy", "Scheme", "Agency"), "requires evidence": ("requiresDocument", "Scheme", "Document"), "evaluated against": ("hasRule", "Scheme", "EligibilityRule"), "provides fact": ("providesFact", None, "EligibilityRule")}


def build():
    schema = Graph()
    for label in [*CLASSES.values(), "Applicant"]:
        schema.add((NS[label], RDF.type, OWL.Class))
        schema.add((NS[label], RDFS.label, Literal(label)))
    for label in ("Resident", "Organization", "Institution"):
        schema.add((NS[label], RDFS.subClassOf, NS.Applicant))
    schema.add((NS.LifeEvent, RDFS.subClassOf, NS.SupportNeed))
    for prop, domain, range_ in RELATIONS.values():
        schema.add((NS[prop], RDF.type, OWL.ObjectProperty))
        schema.add((NS[prop], RDFS.label, Literal(prop)))
        if domain:
            schema.add((NS[prop], RDFS.domain, NS[domain]))
        schema.add((NS[prop], RDFS.range, NS[range_]))
    for prop, domain, range_ in [("persona", None, XSD.string), ("category", "Scheme", XSD.string), ("field", "EligibilityRule", XSD.string), ("operator", "EligibilityRule", XSD.string), ("expected", "EligibilityRule", RDFS.Literal), ("benefit", "Scheme", XSD.string), ("evidenceId", "Relationship", XSD.string), ("source", "Evidence", XSD.string), ("excerpt", "Evidence", XSD.string)]:
        schema.add((NS[prop], RDF.type, OWL.DatatypeProperty))
        schema.add((NS[prop], RDFS.label, Literal(prop)))
        if domain:
            schema.add((NS[prop], RDFS.domain, NS[domain]))
        schema.add((NS[prop], RDFS.range, range_))
    # COA's upstream serializer adds ontology metadata and verifies isomorphic
    # Turtle round trips. This is a schema-only ontology, not an instance dump.
    schema_ttl, _ = serialize(schema, "life-events", str(NS), datetime.fromisoformat(TIMESTAMP))
    fixtures = {persona_id: scenario_fixture(persona_id) for persona_id in PERSONAS}
    fixture = {key: [item for story in fixtures.values() for item in story[key]] for key in ("nodes", "edges", "evidence")}
    graph = Graph()
    graph.bind("demo", NS)
    for node in fixture["nodes"]:
        graph.add((NS[node["id"]], RDF.type, NS[CLASSES[node["type"]]]))
        graph.add((NS[node["id"]], RDFS.label, Literal(node["label"])))
        graph.add((NS[node["id"]], NS.description, Literal(node["description"])))
    for edge in fixture["edges"]:
        graph.add((NS[edge["source"]], NS[RELATIONS[edge["label"]][0]], NS[edge["target"]]))
        uri = NS[edge["id"]]
        graph.add((uri, RDF.type, NS.Relationship))
        graph.add((uri, NS.edgeSource, NS[edge["source"]]))
        graph.add((uri, NS.edgeTarget, NS[edge["target"]]))
        graph.add((uri, NS.edgePredicate, NS[RELATIONS[edge["label"]][0]]))
        graph.add((uri, NS.evidenceId, Literal(edge["evidenceId"])))
    for persona_id, story in fixtures.items():
        for item in [*story["nodes"], *story["edges"], *story["evidence"]]:
            graph.add((NS[item["id"]], NS.persona, Literal(persona_id)))
    for scheme in ALL_SCHEMES:
        for category in scheme["categories"]:
            graph.add((NS[scheme["id"]], NS.category, Literal(category)))
        graph.add((NS[scheme["id"]], NS.benefit, Literal(scheme["benefit"])))
        graph.add((NS[scheme["id"]], NS.evidenceId, Literal(scheme["evidenceId"])))
        for index, (field, operator, expected, _) in enumerate(scheme["rules"], 1):
            rule = NS[f"rule-{scheme['id'].removeprefix('scheme-')}-{index}"]
            graph.add((rule, NS.field, Literal(field)))
            graph.add((rule, NS.operator, Literal(operator)))
            graph.add((rule, NS.expected, Literal(expected)))
            graph.add((rule, NS.ruleOrder, Literal(index)))
    for evidence in fixture["evidence"]:
        uri = NS[evidence["id"]]
        graph.add((uri, RDF.type, NS.Evidence))
        graph.add((uri, RDFS.label, Literal(evidence["title"])))
        for field in ("source", "excerpt", "updatedAt"):
            graph.add((uri, NS[field], Literal(evidence[field])))
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "ontology.ttl").write_text(schema_ttl)
    (ROOT / "data" / "instances.ttl").write_text(graph.serialize(format="turtle"))
    (ROOT / "data" / "scenario.json").write_text(json.dumps(fixtures["individuals"], indent=2, ensure_ascii=False))
    (ROOT / "data" / "scenarios.json").write_text(json.dumps(fixtures, indent=2, ensure_ascii=False))
    return len(schema), len(graph)


if __name__ == "__main__":
    print("Generated TBox/ABox triple counts:", build())
