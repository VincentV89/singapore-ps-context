# Life Events Navigator: five-minute presenter script

## Before the session

Open the deployed CloudFront site and verify Cognito sign-in with your demo account. Use a desktop browser at about 1440 pixels wide for the household controls and graph; scroll down to the support pathways and assistant. Start with **Job loss · household of four** and **Amazon Bedrock synthesis off**. The explicit screening and evidence story works without a model call; use the optional model only after rehearsing it in the deployed account.

Have the source repository and `backend/data/ontology.ttl` available in a second tab/editor if the audience asks how this relates to the accelerator. Use the file export for an architectural discussion, not an unplanned deployment during the presentation.

The demo is hosted in **`us-east-1`**, as selected for this demonstration. All profiles, schemes, offices, benefits, thresholds, and policy evidence are fictional. No real citizen records or documents are needed.

## 0:00–0:35 — Establish the problem and sign in

**Action:** Show the login page, click **Sign in to explore**, and complete Cognito sign-in. If the session is already authenticated, briefly point to the workspace account control and move on.

**Say:**

> A life change often affects several services at once. A resident should not have to understand every agency boundary before finding the right next step. This demonstration connects household context, programme rules, supporting policy evidence, and agency responsibility in one inspectable picture.
>
> The profiles and programmes here are fictional. We are demonstrating how context changes an explanation and a service pathway, not making a government eligibility decision.

**Visible proof:** The deployed site is served through CloudFront and the login uses Cognito. Keep infrastructure details for a later question; the opening story is about the resident's experience.

## 0:35–1:25 — Discover the starting pathways

**Action:** Select **Job loss · household of four**. Point to the citizen context, the S$900 income-per-member calculation, and the support pathway cards. Click the **Household Bridge Grant** title to highlight its connections in the graph.

**Say:**

> This fictional resident is 42, recently lost employment, and lives in a household of four with monthly household income of S$3,600. The useful context is not income alone: S$3,600 divided by four gives S$900 per person.
>
> That combination matches Household Bridge Grant and Skills Restart Support. Caregiver Relief does not match because there is no caregiving responsibility; Accessible Living Support does not match because the accessibility flag is off. The explanation identifies the condition, rather than only giving a score.

**Expected result:** Two `Likely eligible`, two `Not eligible`, zero `Needs review`. Seventeen rules are evaluated across the four fictional schemes. The card benefits are illustrative, not actual Singapore assistance amounts.

**Audience takeaway:** The same household facts can connect to different services because each service uses a different set of conditions.

## 1:25–2:20 — Explain the graph and show the evidence

**Action:** Click **View reasoning** on Household Bridge Grant. Show the four observed/required checks. Click the evidence icon beside the income rule. Close the evidence/modal, then expand **Trace the reasoning** in the assistant.

**Say:**

> Here is the basis for the pathway: citizen status, age, recent job loss, and the S$1,000-per-person ceiling all pass. Each criterion points back to a versioned fictional policy excerpt. The graph also connects the programme to its administering office and the documents needed for verification.
>
> A document search could return the paragraph about the S$1,000 ceiling. The graph adds the relationship: this household has four members, this derived income is the value used by this rule, this rule belongs to this scheme, and this scheme has these evidence requirements.
>
> The screening checks are explicit SPARQL rule results. A language model can express the explanation, but it does not set the scheme status.

**Visible proof:** Actual and required values are inspectable, source evidence is clickable, and the reasoning contains the recorded assessment steps. Do not present the graph's visual connections as independent proof of a policy's correctness: its definitions are authored fictional data.

## 2:20–3:20 — Change the context and compare

**Action:** Select **New caregiving responsibility**, then click **Compare changes**. Point to S$5,400 income divided by four = S$1,350 per person. Open Caregiver Relief's reasoning if time allows.

**Say:**

> Now the household context changes: there is a caregiving responsibility, and household income is S$5,400. Income per member is S$1,350.
>
> Household Bridge Grant no longer passes its S$1,000 ceiling. Caregiver Relief now matches because caregiving is present and its different S$1,800 ceiling is met. Skills Restart Support still matches: its fictional rules depend on the employment transition and age, not this income ceiling.
>
> We can explain both changes without hiding them inside a generated answer. The before-and-after comparison shows which pathways changed and their reasons.

**Expected result:** Household Bridge Grant changes from likely eligible to not eligible; Caregiver Relief changes from not eligible to likely eligible. Skills Restart Support stays likely eligible. Accessible Living Support stays not eligible. There are still two likely-eligible schemes, but they are a different pair.

**Optional manual variation:** Keep the default profile, change household income to S$4,100, and click **Update context**. Income per member becomes S$1,025, causing Household Bridge Grant to fail while Skills Restart Support stays likely eligible. Manually edited facts are not applied until the update button is clicked.

## 3:20–4:05 — Make missing information visible

**Action:** Select **Missing income · needs review**. Point to `Unknown` income per member and the review states. Open Household Bridge Grant's rule details.

**Say:**

> What if income has not been supplied yet? The system keeps that fact unknown. It does not replace missing income with zero or assume the previous value.
>
> Household Bridge Grant and Caregiver Relief now need review because their income conditions are unresolved. Skills Restart Support can still pass because its rules do not require income. Accessible Living Support still fails its known accessibility condition.

**Expected result:** One likely eligible, two need review, one not eligible. An unknown fact does not override a known failed condition. This is the useful distinction between missing evidence and an actual disqualifying condition.

## 4:05–4:40 — Give an evidence-backed next step

**Action:** Ask **What documents should this household prepare?** in the question box. Click a citation chip, then click **Prepare checklist** to download the illustrative text checklist.

**Say:**

> The next step follows the same connected model. We can prepare the evidence checklist for pathways that pass or need review, including the employment transition record, training plan, household and income evidence, and caregiving declaration.
>
> The checklist carries the scheme status and policy evidence. This demo has prepared information for the resident; it has not submitted an application or created an agency case.

**Optional model moment:** If rehearsed, enable **Use Amazon Bedrock synthesis** and send the same question. Describe the prose as a grounded narrative over the same assessment and evidence. Show the synthesis indicator. If it remains deterministic or reports a fallback, explain that the explicit assessment and evidence remain available; do not claim a model invocation succeeded.

## 4:40–5:00 — Connect the experience to the accelerator

**Action:** Open **How it works**, then return to the graph for the closing statement.

**Say:**

> This compact demo executes real graph traversal code from AWS Context Ontology Accelerator and uses its serializer to produce an importable OWL schema. The full accelerator can expand this into Scan, Model, and Serve over governed data sources, ontology mappings, graph context, and retrieved documents.
>
> The result shown here is a service pathway that changes with the resident's context, with each rule and source evidence available for inspection.

**Do not overstate scope:** This stack does not deploy Neptune, OpenSearch Serverless, DataZone, Ontop, or AgentCore. The current graph store is RDFLib, hosted in the Lambda. The full integration design is documented separately.

## Rehearsal result card

All thresholds and benefits in this card are fictional. Other inputs remain the default profile unless stated.

| Preset | Income per person | Household Bridge Grant | Skills Restart Support | Caregiver Relief | Accessible Living Support |
| --- | ---: | --- | --- | --- | --- |
| Job loss · household of four | S$900 | Likely eligible | Likely eligible | Not eligible | Not eligible |
| New caregiving responsibility | S$1,350 | Not eligible | Likely eligible | Likely eligible | Not eligible |
| Accessibility support need | S$900 | Likely eligible | Likely eligible | Not eligible | Likely eligible |
| Higher household income | S$2,500 | Not eligible | Likely eligible | Not eligible | Not eligible |
| Missing income · needs review | Unknown | Needs review | Likely eligible | Needs review | Not eligible |

## Short answers to likely audience questions

**Why an ontology instead of only a chatbot?** The ontology names the concepts and relationships consistently; the rule data defines which facts a programme needs; the graph exposes the links used to assemble context. A chatbot can provide the conversational surface over those inspectable definitions.

**Is this using actual Singapore policy?** No. The agencies, schemes, thresholds, and benefits are fictional. A real adoption would load steward-reviewed programme definitions and source evidence, then evaluate them against a meaningful benchmark and application process.

**Is the AI deciding eligibility?** Scheme status comes from the explicit conjunctive rule checks. Optional Bedrock synthesis expresses the assessment in prose. The result remains a fictional screening, not an approval.

**What part comes from the accelerator?** The executed `GraphTraverser`, its query/namespace helpers and `GraphClient` protocol, and the Turtle serializer. The RDFLib adapter and the synthetic eligibility experience are added here. The complete accelerator deployment is a documented future integration.

**Does the question assistant search a document corpus?** This compact version grounds answers in authored policy evidence associated with the graph. It does not deploy a vector index. The full accelerator path adds actual document ingestion, retrieval, and orchestration.

**Does changing a profile affect other residents?** The assessment is hypothetical request context. The demo does not persist a real citizen record or submit a case.

**Can it run in Singapore?** The current demo region is `us-east-1`, selected for this session. The compact AWS services can be configured for a future Singapore deployment, with regional/model checks. A full accelerator deployment additionally requires checking AgentCore Runtime, DataZone, Neptune, OpenSearch Serverless, and the chosen Bedrock models.

**What does it cost?** The compact stack primarily incurs API/Lambda requests, CloudFront delivery, S3 storage, Cognito usage, logs, and optional model tokens. The complete accelerator adds standing managed-graph/vector/container/network costs. Quote current account-specific estimates rather than a fixed figure from this script.

## Recovery during a live demonstration

If an API call fails, keep the current visible assessment, use **Retry**, and describe only the last completed result. If Cognito expires, sign in again. If a Bedrock call cannot complete, use the deterministic mode and show its actual indicator. Do not substitute a screenshot for a live result without saying it is a saved view.

**Reset** restores the default profile. **Compare changes** compares against the starting household loaded for the session, not against the immediately preceding edit. Questions explain the currently applied context; asking about a life change does not itself change the profile. Apply a preset or edit the input controls to demonstrate the change.
