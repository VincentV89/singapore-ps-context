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
     "excerpt": "Resident and household facts come from the current editable synthetic profile. The validated request is authoritative for this screening; no household size, employment or life event is assumed. Missing facts remain unknown.", "updatedAt": TIMESTAMP},
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


def individual_fixture():
    nodes = [
        {"id": "resident-demo", "label": "Demo resident", "type": "resident", "description": "Fictional profile; no name, NRIC or other personal identifiers."},
        {"id": "household-demo", "label": "Household context", "type": "household", "description": "Income and household size form the per-person income context."},
        {"id": "event-jobloss", "label": "Recent job loss", "type": "event", "description": "Editable synthetic life event."},
        {"id": "event-caregiving", "label": "Caregiving responsibility", "type": "event", "description": "Editable synthetic life event."},
        {"id": "event-accessibility", "label": "Accessibility need", "type": "event", "description": "Editable synthetic support need."},
        {"id": "event-education", "label": "Student education", "type": "event", "description": "Editable synthetic education context."},
        {"id": "event-senior-health", "label": "Senior healthcare", "type": "event", "description": "Editable synthetic senior healthcare context."},
    ]
    agencies = {"agency-support": "Demo Social Support Office", "agency-workforce": "Demo Workforce Office", "agency-care": "Demo Care Services Office", "agency-access": "Demo Accessibility Office", "agency-education-support": "Demo Student Support Office", "agency-senior-health": "Demo Senior Health Office"}
    docs = {"doc-income": "Income statement", "doc-household": "Household declaration", "doc-employment": "Employment transition record", "doc-training": "Training plan", "doc-caregiving": "Caregiving declaration", "doc-accessibility": "Accessibility assessment", "doc-enrolment": "Student enrolment record", "doc-senior-health": "Senior care assessment"}
    nodes.extend({"id": k, "label": v, "type": "agency", "description": "Fictional demo agency."} for k, v in agencies.items())
    nodes.extend({"id": k, "label": v, "type": "document", "description": "Illustrative evidence type; do not upload personal documents to this demo."} for k, v in docs.items())
    edges = []

    def edge(source, target, label, evidence):
        edges.append({"id": f"edge-{len(edges)+1}", "source": source, "target": target, "label": label, "evidenceId": evidence})

    edge("resident-demo", "household-demo", "belongs to", "ev-profile")
    for event in ("event-jobloss", "event-caregiving", "event-accessibility", "event-education", "event-senior-health"):
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
        {"id": "student-education", "label": "Student education support", "profile": {**PROFILE, "age": 20, "employmentStatus": "student", "recentJobLoss": False, "householdIncome": 4800}},
        {"id": "senior-healthcare", "label": "Senior healthcare support", "profile": {**PROFILE, "age": 70, "employmentStatus": "retired", "recentJobLoss": False, "householdIncome": 4800}},
    ]
    return {"scenario": {"id": "life-events-navigator", "title": "Life Events Navigator", "timestamp": TIMESTAMP, "description": "Connected context for citizen services: discover fictional support, explain every rule and assemble a next-step evidence checklist.", "synthetic": True, "disclaimer": DISCLAIMER}, "profile": deepcopy(PROFILE), "nodes": nodes, "edges": edges, "evidence": deepcopy(EVIDENCE), "presets": presets}


# These journeys intentionally share an RDF vocabulary, not applicant facts.
# All catalogue content is invented, including agency names and thresholds.
def field(key, label, type_, options=None, minimum=None, maximum=None, step=None):
    value = {"key": key, "label": label, "type": type_, "allowUnknown": True}
    if options:
        value["options"] = [{"value": key, "label": label} for key, label in options]
    for name, item in (("min", minimum), ("max", maximum), ("step", step)):
        if item is not None:
            value[name] = item
    return value


def categories(*items):
    return [{"id": key, "label": label} for key, label in items]


PERSONAS = {
    "individuals": {"id": "individuals", "name": "Individuals & Families", "tagline": "Support for everyday life", "description": "Explore fictional financial assistance, education, healthcare, training, caregiving and accessibility support using household context.", "segments": ["Parents", "Students", "Seniors", "Caregivers", "Jobseekers", "Persons with disabilities"], "contextTitle": "Household context", "profileTitle": "Your household profile", "prompts": ["What support could this household receive?", "What evidence should this household prepare?", "Why does this household need review?"], "supportCategories": categories(("financial-assistance", "Financial assistance"), ("employment", "Employment & training"), ("caregiving", "Caregiving"), ("accessibility", "Accessibility"), ("education", "Education"), ("healthcare", "Healthcare")), "fields": [field("householdIncome", "Monthly household income (S$)", "number", minimum=0, maximum=1000000, step=0.01), field("householdSize", "Household size", "number", minimum=1, maximum=20, step=1), field("age", "Age", "number", minimum=0, maximum=120, step=1), field("citizenship", "Residency status", "select", [("citizen", "Citizen"), ("permanent-resident", "Permanent resident"), ("other", "Other eligible resident")]), field("employmentStatus", "Employment status", "select", [("unemployed", "Unemployed"), ("employed", "Employed"), ("retired", "Retired"), ("student", "Student")]), field("caregiver", "Caregiving responsibility", "boolean"), field("disability", "Accessibility need", "boolean"), field("recentJobLoss", "Recent job loss", "boolean")]},
    "businesses": {"id": "businesses", "name": "Businesses & Entrepreneurs", "tagline": "Grow and transform", "description": "Explore fictional digitalisation, AI adoption, workforce and sustainability support using business and project context.", "segments": ["Startup founders", "SME owners", "Self-employed", "Employers", "Exporters"], "contextTitle": "Business & project context", "profileTitle": "Your business profile", "prompts": ["What support could this business qualify for?", "What documents should this business prepare?", "Why does the Digital Spark Grant need review?"], "supportCategories": categories(("digital-ai", "Digitalisation & AI"), ("workforce", "Workforce development"), ("sustainability", "Sustainability")), "fields": [field("organizationType", "Business type", "select", [("sme", "SME"), ("startup", "Startup"), ("self-employed", "Self-employed"), ("enterprise", "Larger enterprise")]), field("localRegistration", "Registered locally", "boolean"), field("localOwnership", "Local ownership (%)", "number", minimum=0, maximum=100, step=0.1), field("employeeCount", "Number of employees", "number", minimum=0, maximum=100000, step=1), field("annualRevenue", "Annual revenue (S$)", "number", minimum=0, maximum=10000000000, step=0.01), field("projectArea", "Project focus", "select", [("digitalisation", "Digitalisation"), ("ai", "AI adoption"), ("workforce", "Workforce development"), ("sustainability", "Sustainability"), ("internationalisation", "International expansion"), ("rd", "Research & development")]), field("coFunding", "Applicant co-funding (%)", "number", minimum=0, maximum=100, step=0.1)]},
    "community": {"id": "community", "name": "Nonprofits & Community Organisations", "tagline": "Fund social impact", "description": "Explore fictional community projects, social-service capability and arts or youth programmes using organisation and public-benefit context.", "segments": ["Registered charities", "Social service agencies", "Voluntary welfare organisations", "Religious organisations", "Community initiatives", "Arts groups"], "contextTitle": "Community & project context", "profileTitle": "Your organisation profile", "prompts": ["What support could this community organisation receive?", "What evidence should this organisation prepare?", "Which agencies support this project?"], "supportCategories": categories(("community-projects", "Community & social services"), ("capability", "Capability building"), ("arts-youth", "Arts & youth")), "fields": [field("organizationType", "Organisation type", "select", [("registered-charity", "Registered charity"), ("social-service-agency", "Social service agency"), ("religious-organisation", "Religious organisation"), ("community-group", "Community group"), ("arts-group", "Arts group")]), field("localRegistration", "Registered locally", "boolean"), field("registeredCharity", "Registered charity status", "boolean"), field("publicBenefit", "Project has public benefit", "boolean"), field("projectArea", "Project focus", "select", [("community", "Community projects"), ("social-services", "Social services"), ("capability", "Capability building"), ("arts", "Arts"), ("youth", "Youth programmes")]), field("projectBudget", "Project budget (S$)", "number", minimum=0, maximum=10000000, step=0.01)]},
    "research": {"id": "research", "name": "Researchers & Educational Institutions", "tagline": "Advance knowledge", "description": "Explore fictional research, industry-academia collaboration and education innovation funding using institution and project context.", "segments": ["University researchers", "Educators", "Research institutes", "Schools", "Industry-academia partnerships"], "contextTitle": "Research & institution context", "profileTitle": "Your institution profile", "prompts": ["What funding could this research project qualify for?", "What evidence should the lead applicant prepare?", "Why does this project need review?"], "supportCategories": categories(("research-funding", "Research funding"), ("collaboration", "Innovation & collaboration"), ("education", "Education & scholarships")), "fields": [field("institutionType", "Institution type", "select", [("university", "University"), ("research-institute", "Research institute"), ("school", "School"), ("industry-partner", "Industry partner")]), field("localRegistration", "Institution registered locally", "boolean"), field("leadApplicant", "Lead applicant", "select", [("local-researcher", "Local researcher"), ("educator", "Educator"), ("industry-lead", "Industry lead"), ("international-researcher", "International researcher")]), field("projectArea", "Project focus", "select", [("fundamental-research", "Fundamental research"), ("applied-research", "Applied research"), ("education-innovation", "Education innovation"), ("scholarship", "Scholarship programme")]), field("collaboration", "Industry-academia collaboration", "boolean"), field("ethicsApproval", "Required ethics approval obtained", "boolean"), field("projectBudget", "Project budget (S$)", "number", minimum=0, maximum=100000000, step=0.01)]},
}

PROFILES = {
    "individuals": PROFILE,
    "businesses": {"organizationType": "sme", "localRegistration": True, "localOwnership": 60, "employeeCount": 25, "annualRevenue": 4500000, "projectArea": "digitalisation", "coFunding": 40},
    "community": {"organizationType": "registered-charity", "localRegistration": True, "registeredCharity": True, "publicBenefit": True, "projectArea": "social-services", "projectBudget": 80000},
    "research": {"institutionType": "university", "localRegistration": True, "leadApplicant": "local-researcher", "projectArea": "fundamental-research", "collaboration": False, "ethicsApproval": True, "projectBudget": 250000},
}

for item, category in zip(SCHEMES, ["financial-assistance", "employment", "caregiving", "accessibility"]):
    item.update(persona="individuals", categories=[category])

ADDITIONAL_SCHEMES = [
    {"id": "scheme-digital-spark", "persona": "businesses", "categories": ["digital-ai"], "name": "Digital Spark Grant", "benefit": "Up to S$30,000 transformation credit · fictional", "agencyId": "agency-enterprise-demo", "evidenceId": "ev-digital-spark", "eventId": "event-business-digital", "documents": ["doc-business-registration", "doc-business-ownership", "doc-business-financials", "doc-business-project"], "rules": [("localRegistration", "eq", True, "Locally registered business"), ("organizationType", "in", "sme|startup|self-employed", "SME, startup or self-employed applicant"), ("localOwnership", "gte", 30, "Local ownership ≥ 30%"), ("employeeCount", "lte", 200, "At most 200 employees"), ("annualRevenue", "lte", 100000000, "Annual revenue ≤ S$100 million"), ("projectArea", "in", "digitalisation|ai", "Digitalisation or AI project"), ("coFunding", "gte", 30, "Applicant co-funding ≥ 30%")]},
    {"id": "scheme-workforce-lift", "persona": "businesses", "categories": ["workforce"], "name": "Workforce Lift Support", "benefit": "Up to S$12,000 workforce training credit · fictional", "agencyId": "agency-enterprise-workforce-demo", "evidenceId": "ev-workforce-lift", "eventId": "event-business-workforce", "documents": ["doc-business-registration", "doc-business-workforce", "doc-business-project"], "rules": [("localRegistration", "eq", True, "Locally registered business"), ("employeeCount", "gte", 1, "At least one employee"), ("projectArea", "eq", "workforce", "Workforce development project"), ("coFunding", "gte", 20, "Applicant co-funding ≥ 20%")]},
    {"id": "scheme-green-launch", "persona": "businesses", "categories": ["sustainability"], "name": "Green Launch Support", "benefit": "Up to S$40,000 sustainability project credit · fictional", "agencyId": "agency-enterprise-green-demo", "evidenceId": "ev-green-launch", "eventId": "event-business-green", "documents": ["doc-business-registration", "doc-business-ownership", "doc-business-financials", "doc-business-project"], "rules": [("localRegistration", "eq", True, "Locally registered business"), ("localOwnership", "gte", 30, "Local ownership ≥ 30%"), ("annualRevenue", "lte", 100000000, "Annual revenue ≤ S$100 million"), ("projectArea", "eq", "sustainability", "Sustainability project"), ("coFunding", "gte", 40, "Applicant co-funding ≥ 40%")]},
    {"id": "scheme-community-impact", "persona": "community", "categories": ["community-projects"], "name": "Community Impact Seed Fund", "benefit": "Up to S$50,000 community project funding · fictional", "agencyId": "agency-community-demo", "evidenceId": "ev-community-impact", "eventId": "event-community-impact", "documents": ["doc-community-registration", "doc-community-project", "doc-community-benefit"], "rules": [("localRegistration", "eq", True, "Locally registered organisation"), ("organizationType", "in", "registered-charity|social-service-agency|religious-organisation|community-group", "Community or social-service organisation"), ("publicBenefit", "eq", True, "Project provides public benefit"), ("projectArea", "in", "community|social-services", "Community or social-service project"), ("projectBudget", "lte", 100000, "Project budget ≤ S$100,000")]},
    {"id": "scheme-community-capability", "persona": "community", "categories": ["capability"], "name": "Social Capability Bridge", "benefit": "Up to S$25,000 capability-building funding · fictional", "agencyId": "agency-community-capability-demo", "evidenceId": "ev-community-capability", "eventId": "event-community-capability", "documents": ["doc-community-registration", "doc-community-charity", "doc-community-project", "doc-community-benefit"], "rules": [("localRegistration", "eq", True, "Locally registered organisation"), ("registeredCharity", "eq", True, "Registered charity status"), ("publicBenefit", "eq", True, "Project provides public benefit"), ("projectArea", "eq", "capability", "Capability-building project"), ("projectBudget", "lte", 50000, "Project budget ≤ S$50,000")]},
    {"id": "scheme-creative-youth", "persona": "community", "categories": ["arts-youth"], "name": "Creative Youth Connections", "benefit": "Up to S$20,000 arts or youth programme funding · fictional", "agencyId": "agency-community-creative-demo", "evidenceId": "ev-creative-youth", "eventId": "event-community-creative", "documents": ["doc-community-registration", "doc-community-project", "doc-community-benefit"], "rules": [("localRegistration", "eq", True, "Locally registered organisation"), ("organizationType", "in", "registered-charity|community-group|arts-group", "Charity, community or arts organisation"), ("publicBenefit", "eq", True, "Project provides public benefit"), ("projectArea", "in", "arts|youth", "Arts or youth programme"), ("projectBudget", "lte", 40000, "Project budget ≤ S$40,000")]},
    {"id": "scheme-discovery-catalyst", "persona": "research", "categories": ["research-funding"], "name": "Discovery Catalyst Fund", "benefit": "Up to S$200,000 research funding · fictional", "agencyId": "agency-research-demo", "evidenceId": "ev-discovery-catalyst", "eventId": "event-research-discovery", "documents": ["doc-research-registration", "doc-research-proposal", "doc-research-lead", "doc-research-ethics"], "rules": [("localRegistration", "eq", True, "Locally registered institution"), ("institutionType", "in", "university|research-institute", "University or research institute"), ("leadApplicant", "eq", "local-researcher", "Local researcher leads the project"), ("projectArea", "eq", "fundamental-research", "Fundamental research project"), ("ethicsApproval", "eq", True, "Required ethics approval obtained"), ("projectBudget", "lte", 300000, "Project budget ≤ S$300,000")]},
    {"id": "scheme-collaboration-forge", "persona": "research", "categories": ["collaboration"], "name": "Collaboration Forge Grant", "benefit": "Up to S$300,000 applied innovation funding · fictional", "agencyId": "agency-research-innovation-demo", "evidenceId": "ev-collaboration-forge", "eventId": "event-research-collaboration", "documents": ["doc-research-registration", "doc-research-proposal", "doc-research-partnership", "doc-research-ethics"], "rules": [("localRegistration", "eq", True, "Locally registered institution"), ("institutionType", "in", "university|research-institute|industry-partner", "Research institution or industry partner"), ("projectArea", "eq", "applied-research", "Applied research project"), ("collaboration", "eq", True, "Industry-academia collaboration"), ("ethicsApproval", "eq", True, "Required ethics approval obtained"), ("projectBudget", "lte", 500000, "Project budget ≤ S$500,000")]},
    {"id": "scheme-learning-futures", "persona": "research", "categories": ["education"], "name": "Learning Futures Programme", "benefit": "Up to S$60,000 education programme funding · fictional", "agencyId": "agency-education-demo", "evidenceId": "ev-learning-futures", "eventId": "event-research-learning", "documents": ["doc-research-registration", "doc-research-proposal", "doc-research-lead"], "rules": [("localRegistration", "eq", True, "Locally registered institution"), ("institutionType", "in", "school|university", "School or university"), ("leadApplicant", "in", "local-researcher|educator", "Local researcher or educator leads the programme"), ("projectArea", "in", "education-innovation|scholarship", "Education innovation or scholarship programme"), ("projectBudget", "lte", 100000, "Project budget ≤ S$100,000")]},
]
SCHEMES.extend([
    {"id": "scheme-student-pathways", "persona": "individuals", "categories": ["education"], "name": "Student Pathways Bursary", "benefit": "S$1,500 education credit · fictional", "agencyId": "agency-education-support", "evidenceId": "ev-student-pathways", "eventId": "event-education", "documents": ["doc-enrolment", "doc-income", "doc-household"], "rules": [("citizenship", "in", "citizen|permanent-resident", "Citizen or permanent resident"), ("employmentStatus", "eq", "student", "Currently a student"), ("age", "gte", 16, "Age 16 or above"), ("age", "lte", 30, "Age 30 or below"), ("perCapitaIncome", "lte", 1600, "Income per person ≤ S$1,600")]},
    {"id": "scheme-senior-health", "persona": "individuals", "categories": ["healthcare"], "name": "Senior Health Access", "benefit": "S$800 healthcare support credit · fictional", "agencyId": "agency-senior-health", "evidenceId": "ev-senior-health", "eventId": "event-senior-health", "documents": ["doc-senior-health", "doc-income", "doc-household"], "rules": [("citizenship", "in", "citizen|permanent-resident", "Citizen or permanent resident"), ("age", "gte", 65, "Age 65 or above"), ("perCapitaIncome", "lte", 1800, "Income per person ≤ S$1,800")]},
])
EVIDENCE.extend([
    {"id": "ev-student-pathways", "title": "Student Pathways Bursary · fictional rules", "source": "Synthetic policy catalogue v2 · SPB", "excerpt": "Fictional education support: citizen or permanent resident, currently a student, age 16–30 inclusive, and gross monthly household income per person at most S$1,600. Benefit: S$1,500 education credit. Student enrolment, income and household evidence are required.", "updatedAt": TIMESTAMP},
    {"id": "ev-senior-health", "title": "Senior Health Access · fictional rules", "source": "Synthetic policy catalogue v2 · SHA", "excerpt": "Fictional healthcare support: citizen or permanent resident, age 65 or older, and gross monthly household income per person at most S$1,800. Benefit: S$800 healthcare support credit. Senior care assessment, income and household evidence are required.", "updatedAt": TIMESTAMP},
])

ALL_SCHEMES = SCHEMES + ADDITIONAL_SCHEMES

STORIES = {
    "businesses": {"root": ("business-demo", "Demo business", "organization"), "context": ("business-context", "Business & project context"), "events": {"event-business-digital": "Digital & AI transformation", "event-business-workforce": "Workforce development", "event-business-green": "Sustainability transition"}, "agencies": {"agency-enterprise-demo": "Demo Enterprise Transformation Office", "agency-enterprise-workforce-demo": "Demo Employer Development Office", "agency-enterprise-green-demo": "Demo Green Enterprise Office"}, "docs": {"doc-business-registration": "Business registration record", "doc-business-ownership": "Ownership declaration", "doc-business-financials": "Business financial statement", "doc-business-project": "Project proposal and co-funding plan", "doc-business-workforce": "Workforce training plan"}, "presets": [("digital-sme", "SME digital transformation", {}), ("ai-startup", "Startup adopting AI", {"organizationType": "startup", "projectArea": "ai", "employeeCount": 8}), ("workforce-project", "Employer workforce development", {"projectArea": "workforce", "coFunding": 20}), ("green-project", "SME sustainability transition", {"projectArea": "sustainability"}), ("unknown-ownership", "Missing ownership · needs review", {"localOwnership": None})]},
    "community": {"root": ("community-demo", "Demo community organisation", "organization"), "context": ("community-context", "Community & project context"), "events": {"event-community-impact": "Community & social-service project", "event-community-capability": "Organisation capability building", "event-community-creative": "Arts & youth programme"}, "agencies": {"agency-community-demo": "Demo Community Partnership Office", "agency-community-capability-demo": "Demo Social Capability Office", "agency-community-creative-demo": "Demo Arts and Youth Office"}, "docs": {"doc-community-registration": "Organisation registration record", "doc-community-charity": "Charity status record", "doc-community-project": "Project proposal and budget", "doc-community-benefit": "Public-benefit statement"}, "presets": [("social-service", "Charity social-service project", {}), ("capability-project", "Charity capability building", {"projectArea": "capability", "projectBudget": 40000}), ("arts-project", "Community arts initiative", {"organizationType": "arts-group", "registeredCharity": False, "projectArea": "arts", "projectBudget": 30000}), ("youth-project", "Community youth programme", {"organizationType": "community-group", "registeredCharity": False, "projectArea": "youth", "projectBudget": 35000}), ("unknown-benefit", "Missing public benefit · needs review", {"publicBenefit": None})]},
    "research": {"root": ("research-demo", "Demo research institution", "institution"), "context": ("research-context", "Research & project context"), "events": {"event-research-discovery": "Fundamental research", "event-research-collaboration": "Industry-academia innovation", "event-research-learning": "Education innovation & scholarships"}, "agencies": {"agency-research-demo": "Demo Research Discovery Office", "agency-research-innovation-demo": "Demo Innovation Partnership Office", "agency-education-demo": "Demo Education Futures Office"}, "docs": {"doc-research-registration": "Institution registration record", "doc-research-proposal": "Research or programme proposal and budget", "doc-research-lead": "Lead applicant affiliation record", "doc-research-ethics": "Required ethics approval record", "doc-research-partnership": "Industry-academia partnership agreement"}, "presets": [("university-research", "University fundamental research", {}), ("industry-collaboration", "Industry-academia applied research", {"projectArea": "applied-research", "collaboration": True, "projectBudget": 450000}), ("education-project", "School education innovation", {"institutionType": "school", "leadApplicant": "educator", "projectArea": "education-innovation", "projectBudget": 80000}), ("scholarship-project", "University scholarship programme", {"leadApplicant": "educator", "projectArea": "scholarship", "projectBudget": 90000}), ("unknown-ethics", "Missing ethics approval · needs review", {"ethicsApproval": None})]},
}


def organization_fixture(persona_id):
    story = STORIES[persona_id]
    root, context = story["root"][0], story["context"][0]
    nodes = [{"id": root, "label": story["root"][1], "type": story["root"][2], "description": "Fictional applicant; no real organisation or applicant identifiers."}, {"id": context, "label": story["context"][1], "type": "context", "description": "Request-scoped synthetic organisation and project facts."}]
    nodes.extend({"id": key, "label": value, "type": "need", "description": "Illustrative support need; project focus is supplied in the editable profile."} for key, value in story["events"].items())
    nodes.extend({"id": key, "label": value, "type": "agency", "description": "Fictional demo agency."} for key, value in story["agencies"].items())
    nodes.extend({"id": key, "label": value, "type": "document", "description": "Illustrative evidence type; do not upload real documents to this demo."} for key, value in story["docs"].items())
    evidence = [{"id": f"ev-{persona_id}-profile", "title": f"Synthetic {PERSONAS[persona_id]['contextTitle'].lower()}", "source": f"Demo {persona_id} scenario v2", "excerpt": "Applicant and project facts come from the current editable synthetic profile. The validated request is authoritative; missing facts remain unknown and are never filled from another persona or a default profile.", "updatedAt": TIMESTAMP}, {"id": f"ev-{persona_id}-calculation", "title": "Context evaluation and uncertainty", "source": "Demo reasoning specification v2", "excerpt": "Scheme criteria are conjunctive. A failing criterion excludes a scheme; unknown required facts produce needs review when no criterion fails. Likely eligible is fictional screening, never an approval. Thresholds are evaluated against supplied applicant and project facts without inferred citizenship or household income.", "updatedAt": TIMESTAMP}]
    edges = []
    def edge(source, target, label, evidence_id):
        edges.append({"id": f"edge-{persona_id}-{len(edges)+1}", "source": source, "target": target, "label": label, "evidenceId": evidence_id})
    edge(root, context, "operates with", f"ev-{persona_id}-profile")
    for event in story["events"]:
        edge(root, event, "has need", f"ev-{persona_id}-profile")
    for scheme in (item for item in ALL_SCHEMES if item["persona"] == persona_id):
        nodes.append({"id": scheme["id"], "label": scheme["name"], "type": "scheme", "agency": story["agencies"][scheme["agencyId"]], "description": scheme["benefit"]})
        edge(scheme["eventId"], scheme["id"], "may connect to", scheme["evidenceId"])
        edge(scheme["id"], scheme["agencyId"], "administered by", scheme["evidenceId"])
        for doc in scheme["documents"]:
            edge(scheme["id"], doc, "requires evidence", scheme["evidenceId"])
        for index, (field_, operator, expected, label) in enumerate(scheme["rules"], 1):
            rule_id = f"rule-{scheme['id'].removeprefix('scheme-')}-{index}"
            nodes.append({"id": rule_id, "label": label, "type": "rule", "description": "Fictional screening criterion."})
            edge(scheme["id"], rule_id, "evaluated against", scheme["evidenceId"])
            edge(context, rule_id, "provides fact", f"ev-{persona_id}-profile")
        criteria = "; ".join(label for _, _, _, label in scheme["rules"])
        evidence.append({"id": scheme["evidenceId"], "title": scheme["name"] + " · fictional rules", "source": "Synthetic policy catalogue v2 · " + scheme["id"], "excerpt": f"Fictional scheme criteria: {criteria}. Benefit: {scheme['benefit']}. Required illustrative evidence: " + ", ".join(story["docs"][doc] for doc in scheme["documents"]) + ". All criteria must pass; documentary verification and officer review are required.", "updatedAt": TIMESTAMP})
    presets = [{"id": key, "label": label, "profile": {**PROFILES[persona_id], **changes}} for key, label, changes in story["presets"]]
    return {"scenario": {"id": f"support-navigator-{persona_id}", "title": "Government Support Navigator", "timestamp": TIMESTAMP, "description": PERSONAS[persona_id]["description"], "synthetic": True, "disclaimer": DISCLAIMER}, "profile": deepcopy(PROFILES[persona_id]), "nodes": nodes, "edges": edges, "evidence": evidence, "presets": presets}


def scenario_fixture(persona_id="individuals"):
    if persona_id not in PERSONAS:
        raise ValueError("Unsupported persona.")
    result = individual_fixture() if persona_id == "individuals" else organization_fixture(persona_id)
    result.update(persona=deepcopy(PERSONAS[persona_id]), personas=deepcopy(list(PERSONAS.values())))
    return result
