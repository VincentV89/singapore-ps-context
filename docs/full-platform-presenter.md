# Presenting SG Support Navigator

Use this walkthrough after full-platform provisioning, source ingestion and live checks have passed. The [compact presenter guide](presenter.md) covers the separate fictional local demo. Do not use a compact validation result or cached answer to represent a full-platform query.

Before presenting, sign in through Cognito, confirm the **Singapore agency sources** badge, and verify that the page's full-platform runtime configuration points to the intended namespace. Keep administrator credentials private. Check source capture dates and agency pages for material programme changes or call deadlines. The corpus contains 20 programmes; confirm which policy documents have completed ingestion for the session.

## Five-minute journey

1. **Start with the four audiences.** Explain that individuals, businesses, community organisations and researchers have different needs but share programme, agency and evidence concepts. The Singapore identity is custom demo branding. The service uses public agency information and hypothetical applicant context.
2. **Choose Individuals & Families.** Use the hypothetical household example and ask, “Which programmes should this household explore, and what requirements should they check?” Let the live platform answer. Open the returned evidence and its agency link; show the capture date and distinguish a summary from the quoted policy wording.
3. **Follow the returned graph.** Click connected entities and inspect their relationships. Explain the specific connections visible in this response. When the caption says **Live Neptune ontology schema**, explain that the display shows the model's classes and properties; it is not an applicant's factual record or a retrieved instance graph.
4. **Inspect execution.** Open **Trace the reasoning**. Show actual step status, duration and tools from this request. Explain only the paths that ran. A short request may use fewer tools than a deep request; a tier number alone does not prove that all graph, structured and document paths executed.
5. **Change context and ask again.** For example, use a caregiving household or a business sustainability project. Compare the evidence and requirements returned. Programme cards continue to say **Agency assessment required**. A different answer does not establish an entitlement, approved grant amount or submitted application.

The assistant's **Deep context reasoning** option uses AgentCore streaming and may take longer. Choose a prepared question whose relevant documents and mappings have been validated, then show the actual streamed outcome. If the platform marks an answer partial or reports a failure, present that status and investigate it; do not substitute a scripted trace.

## Questions for the other audiences

| Audience | Useful live question | Evidence to inspect |
| --- | --- | --- |
| Businesses & Entrepreneurs | “Which current Enterprise Singapore programmes should this digitalisation project explore, and what requirements need checking?” | EDGE scope, applicant/project conditions, transition dates and official application information |
| Nonprofits & Community Organisations | “Which NCSS or NAC programmes should this organisation explore for capability building, and what conditions should it verify?” | Agency attribution, organisation scope, project requirements and current call information |
| Researchers & Educational Institutions | “Which NRF or A*STAR programmes could support this industry-academia project, and where are the detailed requirements?” | Programme purpose, institution/applicant scope and links to full call documentation |

These are prompts, not guaranteed output scripts. Use the answer's citations to determine what can be claimed. Some overview pages omit complete eligibility requirements. For example, the NRF Competitive Research Programme overview points to the Research Grants Portal; missing criteria must remain missing.

## Explaining the difference from a grant chatbot

A grant chatbot can retrieve a passage and summarise it. This platform also maintains a reviewed model of programmes, agencies, audiences and evidence; maps that model to the structured catalogue; and can combine document, graph and structured context in one request. The inspection points are concrete: a relationship returned from Neptune, a source-linked excerpt from retrieval, or a structured result produced through Athena/Ontop. Show those actual artifacts to substantiate the story.

**Scan** discovers and processes the source documents and tables. **Model** grounds induced ontology proposals in the Singapore vocabulary, validates them and publishes accepted mappings. **Serve** retrieves connected context and explains it with Bedrock. Public programme discovery still requires the administering agency's assessment. This demo does not implement a statutory eligibility decision engine.

The services run in **us-east-1**, and configured US inference profiles may route within the United States. State that deployment choice when discussing customer architectures. The [operations guide](full-platform-operations.md) covers live checks, dated source refresh, standing costs and teardown.
