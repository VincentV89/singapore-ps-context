"""Synthetic Singapore citizen-services story. No real benefits or personal data."""
from copy import deepcopy

TIMESTAMP = "2026-10-08T09:00:00+08:00"
PROFILE = {
    "householdIncome": 3600, "householdSize": 4, "age": 42,
    "citizenship": "citizen", "employmentStatus": "unemployed",
    "caregiver": False, "disability": False, "recentJobLoss": True,
}
DISCLAIMER = (
    "All residents, schemes, agencies, benefits and thresholds are fictional demo data. "
    "This is not Singapore benefits advice or an eligibility approval."
)

EVIDENCE = [
    {"id": "ev-profile", "title": "Synthetic household context", "source": "Demo household scenario v1",
     "excerpt": "A fictional adult resident in a household of four recently lost employment. All inputs are editable synthetic facts; missing facts must not be assumed.", "updatedAt": TIMESTAMP},
    {"id": "ev-bridge", "title": "Household Bridge Grant · fictional rules", "source": "Synthetic policy catalogue v1 · HBG",
     "excerpt": "Fictional grant: citizen, age 21 or older, recent job loss, and gross monthly household income per person at most S$1,000. Benefit: S$450 monthly for three months. Income, household composition and employment evidence are required.", "updatedAt": TIMESTAMP},
    {"id": "ev-skills", "title": "Skills Restart Support · fictional rules", "source": "Synthetic policy catalogue v1 · SRS",
     "excerpt": "Fictional training support: citizen or permanent resident, age 18–60 inclusive, currently unemployed, with recent job loss. Benefit: S$600 training credit. Employment evidence and a training plan are required.", "updatedAt": TIMESTAMP},
    {"id": "ev-caregiver", "title": "Caregiver Relief · fictional rules", "source": "Synthetic policy catalogue v1 · CR",
     "excerpt": "Fictional caregiver support: citizen, age 21 or older, caregiver responsibility, and gross monthly household income per person at most S$1,800. Benefit: S$250 monthly respite credit. Caregiving and household income evidence are required.", "updatedAt": TIMESTAMP},
    {"id": "ev-accessible", "title": "Accessible Living Support · fictional rules", "source": "Synthetic policy catalogue v1 · ALS",
     "excerpt": "Fictional accessibility support: citizen, age 21 or older, accessibility need represented by the synthetic disability flag, and gross monthly household income per person at most S$2,200. Benefit: S$1,200 home adaptation credit. Accessibility and household income evidence are required.", "updatedAt": TIMESTAMP},
    {"id": "ev-calculation", "title": "Context calculation and uncertainty", "source": "Demo reasoning specification v1",
     "excerpt": "Per-person income is gross monthly household income divided by household size. Scheme criteria are conjunctive. A failing criterion excludes a scheme; unknown required facts produce needs review when no criterion fails. Likely eligible is a screening result, never an approval.", "updatedAt": TIMESTAMP},
]

# Criteria are stored as RDF rule individuals by build_graph.py and read through
# SPARQL by engine.py. The engine has no hard-coded scheme-specific decisions.
SCHEMES = [
    {"id": "scheme-bridge", "name": "Household Bridge Grant", "benefit": "S$450 / month for 3 months · fictional", "agencyId": "agency-support", "evidenceId": "ev-bridge", "eventId": "event-jobloss", "documents": ["doc-income", "doc-household", "doc-employment"],
     "rules": [("citizenship", "eq", "citizen", "Citizen status"), ("age", "gte", 21, "Age 21 or above"), ("recentJobLoss", "eq", True, "Recent job loss"), ("perCapitaIncome", "lte", 1000, "Income per person ≤ S$1,000")]},
    {"id": "scheme-skills", "name": "Skills Restart Support", "benefit": "S$600 training credit · fictional", "agencyId": "agency-workforce", "evidenceId": "ev-skills", "eventId": "event-jobloss", "documents": ["doc-employment", "doc-training"],
     "rules": [("citizenship", "in", "citizen|permanent-resident", "Citizen or permanent resident"), ("age", "gte", 18, "Age 18 or above"), ("age", "lte", 60, "Age 60 or below"), ("employmentStatus", "eq", "unemployed", "Currently unemployed"), ("recentJobLoss", "eq", True, "Recent job loss")]},
    {"id": "scheme-caregiver", "name": "Caregiver Relief", "benefit": "S$250 / month respite credit · fictional", "agencyId": "agency-care", "evidenceId": "ev-caregiver", "eventId": "event-caregiving", "documents": ["doc-caregiving", "doc-income", "doc-household"],
     "rules": [("citizenship", "eq", "citizen", "Citizen status"), ("age", "gte", 21, "Age 21 or above"), ("caregiver", "eq", True, "Caregiving responsibility"), ("perCapitaIncome", "lte", 1800, "Income per person ≤ S$1,800")]},
    {"id": "scheme-accessible", "name": "Accessible Living Support", "benefit": "S$1,200 home adaptation credit · fictional", "agencyId": "agency-access", "evidenceId": "ev-accessible", "eventId": "event-accessibility", "documents": ["doc-accessibility", "doc-income", "doc-household"],
     "rules": [("citizenship", "eq", "citizen", "Citizen status"), ("age", "gte", 21, "Age 21 or above"), ("disability", "eq", True, "Accessibility need"), ("perCapitaIncome", "lte", 2200, "Income per person ≤ S$2,200")]},
]


def scenario_fixture():
    nodes = [
        {"id": "resident-demo", "label": "Demo resident", "type": "resident", "description": "Fictional profile; no name, NRIC or other personal identifiers."},
        {"id": "household-demo", "label": "Household context", "type": "household", "description": "Income and household size form the per-person income context."},
        {"id": "event-jobloss", "label": "Recent job loss", "type": "event", "description": "Editable synthetic life event."},
        {"id": "event-caregiving", "label": "Caregiving responsibility", "type": "event", "description": "Editable synthetic life event."},
        {"id": "event-accessibility", "label": "Accessibility need", "type": "event", "description": "Editable synthetic support need."},
    ]
    agencies = {"agency-support": "Demo Social Support Office", "agency-workforce": "Demo Workforce Office", "agency-care": "Demo Care Services Office", "agency-access": "Demo Accessibility Office"}
    docs = {"doc-income": "Income statement", "doc-household": "Household declaration", "doc-employment": "Employment transition record", "doc-training": "Training plan", "doc-caregiving": "Caregiving declaration", "doc-accessibility": "Accessibility assessment"}
    nodes.extend({"id": k, "label": v, "type": "agency", "description": "Fictional demo agency."} for k, v in agencies.items())
    nodes.extend({"id": k, "label": v, "type": "document", "description": "Illustrative evidence type; do not upload personal documents to this demo."} for k, v in docs.items())
    edges = []

    def edge(source, target, label, evidence):
        edges.append({"id": f"edge-{len(edges)+1}", "source": source, "target": target, "label": label, "evidenceId": evidence})

    edge("resident-demo", "household-demo", "belongs to", "ev-profile")
    for event in ("event-jobloss", "event-caregiving", "event-accessibility"):
        edge("resident-demo", event, "has context", "ev-profile")
    for scheme in SCHEMES:
        nodes.append({"id": scheme["id"], "label": scheme["name"], "type": "scheme", "agency": agencies[scheme["agencyId"]], "description": scheme["benefit"]})
        edge(scheme["eventId"], scheme["id"], "may connect to", scheme["evidenceId"])
        edge(scheme["id"], scheme["agencyId"], "administered by", scheme["evidenceId"])
        for doc in scheme["documents"]:
            edge(scheme["id"], doc, "requires evidence", scheme["evidenceId"])
        for index, (field, operator, expected, label) in enumerate(scheme["rules"], 1):
            rule_id = f"rule-{scheme['id'].removeprefix('scheme-')}-{index}"
            nodes.append({"id": rule_id, "label": label, "type": "rule", "description": "Fictional screening criterion."})
            edge(scheme["id"], rule_id, "evaluated against", scheme["evidenceId"])
            edge("household-demo" if field == "perCapitaIncome" else "resident-demo", rule_id, "provides fact", "ev-calculation" if field == "perCapitaIncome" else "ev-profile")
    presets = [
        {"id": "job-loss", "label": "Job loss · household of four", "profile": deepcopy(PROFILE)},
        {"id": "caregiving", "label": "New caregiving responsibility", "profile": {**PROFILE, "caregiver": True, "householdIncome": 5400}},
        {"id": "accessibility", "label": "Accessibility support need", "profile": {**PROFILE, "disability": True}},
        {"id": "higher-income", "label": "Higher household income", "profile": {**PROFILE, "householdIncome": 10000}},
        {"id": "unknown-income", "label": "Missing income · needs review", "profile": {**PROFILE, "householdIncome": None, "caregiver": True}},
    ]
    return {"scenario": {"id": "life-events-navigator", "title": "Life Events Navigator", "timestamp": TIMESTAMP, "description": "Connected context for citizen services: discover fictional support, explain every rule and assemble a next-step evidence checklist.", "synthetic": True, "disclaimer": DISCLAIMER}, "profile": deepcopy(PROFILE), "nodes": nodes, "edges": edges, "evidence": deepcopy(EVIDENCE), "presets": presets}
