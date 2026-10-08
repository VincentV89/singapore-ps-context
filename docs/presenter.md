# Life Events Navigator: five-minute presenter script

## Before the session

Open the deployed CloudFront site and verify Cognito sign-in with your demo account. Use a desktop browser at about 1440 pixels wide for the context controls and graph. Start at **Find Government Support** with **Amazon Bedrock synthesis off**. The explicit screening and evidence story works without a model call; use the optional model only after rehearsing it in the deployed account.

Have the source repository and `backend/data/ontology.ttl` available in a second tab/editor if the audience asks how this relates to the accelerator. Use the file export for an architectural discussion, not an unplanned deployment during the presentation.

The demo is hosted in **`us-east-1`**, as selected for this demonstration. Every profile, organisation, scheme, office, benefit, threshold, and policy excerpt is fictional. No real citizen records or documents are needed. The example catalogue is deliberately small; it is not a comprehensive listing of Singapore schemes.

## 0:00–0:40 — Sign in and choose an audience

**Action:** Complete Cognito sign-in and show **Find Government Support**. Point to the four entry cards: **Individuals & Families**, **Businesses & Entrepreneurs**, **Nonprofits & Community Organisations**, and **Researchers & Educational Institutions**. Choose Individuals & Families.

**Say:**

> Different applicants need different starting points. A household, an SME, a community organisation, and a university researcher should each see a relevant support journey. These four entry points organise discovery without asking applicants to navigate agency boundaries first.
>
> Everything here is fictional. We are demonstrating how context changes the explanation and the next step, not making a government eligibility decision.

**Visible proof:** The entry point offers four audiences. A support-type chip can narrow the displayed catalogue and graph; it does not change a screening rule or assume facts about the applicant. There are no separate personalised segment filters. The context form collects the facts used in assessment.

## 0:40–1:35 — Connect household facts to rules and evidence

**Action:** Use **Job loss · household of four**. Point to S$3,600 household income, four household members, and the derived S$900 income per member. Open **Household Bridge Grant** and its reasoning; inspect the income criterion's fictional evidence.

**Say:**

> The useful context is not income alone: S$3,600 divided by four gives S$900 per person. This fictional programme also checks citizenship, age, and recent job loss. Every condition is visible, with the observed value and the policy evidence that defines the requirement.
>
> A document search might find the income ceiling. The graph connects the household fact to the derived value, the particular programme rule, its administering office, and the required documents.

**Action:** Select **New caregiving responsibility**, then **Compare changes**.

**Expected change:** Income per member rises to S$1,350. Household Bridge Grant fails its S$1,000 ceiling; Caregiver Relief matches its different S$1,800 ceiling and the caregiving condition. The comparison shows why the pathways changed.

**Audience takeaway:** The screening status comes from explicit SPARQL rule results. The language model can explain those results, but it does not decide them.

**Optional audience variation:** **Student education support** opens Student Pathways Bursary for a fictional 20-year-old student; **Senior healthcare support** opens Senior Health Access for a fictional 70-year-old resident. Both use S$4,800 household income across four people. These broaden the individual journey without adding separate student or senior entry cards.

## 1:35–2:30 — Show a business project changing the pathway

**Action:** Switch to **Businesses & Entrepreneurs** and use **SME digital transformation**. Inspect **Digital Spark Grant**. Show the optional support-type chips, clear any filter, then change **Project focus** from **Digitalisation** to **Sustainability** and apply the context update. Keep applicant co-funding at 40%. Open **Green Launch Support** and inspect its project-focus criterion.

**Say:**

> Now the applicant is an organisation. Household size and caregiving are no longer the useful questions. The relevant context is the organisation and its proposed project.
>
> With the same SME facts and 40% applicant co-funding, digitalisation matches Digital Spark Grant. Changing the project focus to sustainability closes that pathway and opens Green Launch Support. We can inspect the required activity and the submitted activity, and follow the same evidence path. This is a change in assessed context; selecting a discovery filter only narrows what we display.

**Expected change:** Digital Spark Grant changes from likely eligible to not eligible; Green Launch Support changes from not eligible to likely eligible. Workforce Lift Support remains not eligible because the project is not workforce development. Use **Compare changes** to show the pathway changes. **SME sustainability transition** is a preset shortcut for the same transition. **Missing ownership · needs review** shows an unresolved required business fact.

## 2:30–3:10 — Show community support

**Action:** Switch to **Nonprofits & Community Organisations** and use **Charity social-service project**. Open **Community Impact Seed Fund** and inspect its organisation/project criteria and document requirements. If time permits, select **Community arts initiative** and inspect **Creative Youth Connections**.

**Say:**

> A community organisation needs a different pathway again. The same shared model connects an organisation, a project, a support programme, its criteria, policy evidence, and the next-step documents.
>
> The audience choice scopes the catalogue and context form. It does not make an organisation eligible merely because it selected a card.

**Visible proof:** The context, programmes, and graph correspond to the community audience. Individuals' and businesses' schemes do not leak into this assessment.

## 3:10–3:50 — Show research and education support

**Action:** Switch to **Researchers & Educational Institutions** and use **University fundamental research**. Open **Discovery Catalyst Fund**. If time permits, select **Industry-academia applied research** and inspect **Collaboration Forge Grant** and the collaboration requirement.

**Say:**

> For a researcher or institution, the relevant facts concern the institution and the proposed activity. We keep the experience familiar, while the graph supplies different criteria and evidence.
>
> This is one reusable relationship model serving four journeys, rather than one generated answer with four different introductory prompts.

**Visible proof:** The graph and rule details use the research audience's programmes and facts. Point to a policy excerpt and its document requirements; do not describe a fictional programme as an official research funding scheme.

## 3:50–4:35 — Show uncertainty and a practical next step

**Action:** Return to **Individuals & Families**, choose **Missing income · needs review**, and inspect an unknown income condition. Ask **What documents should this household prepare?** Click a citation and use **Prepare checklist** to download the illustrative checklist.

**Say:**

> Missing income stays unknown. It does not become zero or inherit an earlier profile's value. If no known condition fails but a required fact is missing, the pathway needs review.
>
> The checklist follows the current assessment and evidence. We have prepared information for the applicant; we have not submitted an application or created an agency case.

**Optional model moment:** If rehearsed, enable **Use Amazon Bedrock synthesis** and send the same question. Show the actual synthesis indicator. If the response reports a fallback, explain that the explicit assessment and evidence remain available; do not claim a model invocation succeeded.

## 4:35–5:00 — Explain the current scope and accelerator path

**Action:** Open **How it works**, then return to the graph.

**Say:**

> This compact demo loads authored RDF files into an in-memory graph and executes real graph traversal code from AWS Context Ontology Accelerator. It also uses the accelerator's serializer for an importable OWL schema.
>
> The full accelerator adds Scan, Model, and Serve: discovering connected sources, proposing and reviewing the knowledge model, and serving governed context to applications and agents. Those platform services are a documented next stage; this deployment demonstrates the four applicant experiences and their inspectable assessments.

**Do not overstate scope:** This stack does not deploy Neptune, OpenSearch Serverless, DataZone, Ontop, AgentCore, or live agency connectors. Its current graph store is an in-memory RDFLib dataset in Lambda. Changing the bundled catalogue or policies requires updating the files and redeploying. Changing applicant context recomputes a hypothetical assessment at request time.

## Short answers to likely audience questions

**Are the support filters personalised?** They are discovery filters for the selected audience. They narrow visible schemes and graph relationships. Screening depends on the applied context facts and authored criteria, not the selected filter.

**Why an ontology instead of only a chatbot?** The ontology names concepts and relationships consistently; rule data defines which facts a programme needs; the graph exposes the links used to assemble context. A chatbot can provide the conversational surface over those inspectable definitions.

**Is this using actual Singapore policy?** No. The agencies, schemes, thresholds, and benefits are fictional. A real adoption would load steward-reviewed programme definitions and source evidence, then evaluate them against a meaningful benchmark and application process.

**Is the AI deciding eligibility?** Scheme status comes from explicit conjunctive rule checks. Optional Bedrock synthesis expresses the assessment in prose. The result remains a fictional screening, not an approval.

**What part comes from the accelerator?** The executed `GraphTraverser`, its query/namespace helpers and `GraphClient` protocol, and the Turtle serializer. The RDFLib adapter, persona-scoped catalogue, and synthetic screening experience are added here. The complete accelerator deployment is a documented future integration.

**Does the question assistant search a document corpus?** This compact version grounds answers in authored policy evidence associated with the graph. It does not deploy a vector index. The full accelerator path adds document ingestion, retrieval, and orchestration.

**Does changing a profile affect other applicants?** The assessment uses hypothetical request context. The demo does not persist an authoritative applicant record or submit a case.

**Can it run in Singapore?** The current region is `us-east-1`, selected for this session. A future Singapore deployment requires regional service and model checks. A full accelerator deployment additionally requires checking AgentCore Runtime, DataZone, Neptune, OpenSearch Serverless, and the chosen Bedrock models.

**What does it cost?** The compact stack primarily incurs API/Lambda requests, CloudFront delivery, S3 storage, Cognito usage, logs, and optional model tokens. The complete accelerator adds standing managed-graph/vector/container/network costs. Quote current account-specific estimates rather than a fixed figure from this script.

## Recovery during a live demonstration

If an API call fails, keep the last completed assessment, use **Retry**, and describe only that result. If Cognito expires, sign in again. If a Bedrock call cannot complete, use deterministic mode and show its actual indicator. Do not substitute a screenshot for a live result without saying it is a saved view.

**Reset** restores the selected audience's default profile. **Compare changes** compares against that audience's starting profile, not the immediately preceding edit. Switching audiences or returning to **All audiences** clears the workspace context, questions, filters, comparison baseline, and open detail views. Questions explain the currently applied context; asking about a different activity does not itself change the profile. Apply a preset or edit and update the context to demonstrate the change.
