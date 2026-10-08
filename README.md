# Singapore Life Events Navigator

A public sector demonstration of knowledge graphs and context intelligence: see how a resident's changing circumstances affect discovery of relevant services, with an inspectable path from household facts to eligibility rules, policy evidence, documents, and agencies.

**All resident profiles, programmes, policy thresholds, benefits, and agency workflows are synthetic. This is an illustrative demo, not Singapore government eligibility advice or an approval system.** No personal data is required.

## Deployment target

- Region: `us-east-1`, as selected for this demo.
- Frontend: private Amazon S3 bucket, served over HTTPS by Amazon CloudFront using Origin Access Control.
- Login: Amazon Cognito hosted sign-in, authorization code flow with PKCE.
- API: Amazon API Gateway with a Cognito JWT authorizer, AWS Lambda.
- Context: RDF/OWL ontology, SPARQL-derived rule evaluation, components from [AWS Context Ontology Accelerator](https://github.com/aws/context-ontology-accelerator) release `v0.3.4`.
- Optional grounded narrative: Amazon Bedrock. Eligibility is evaluated by explicit rules, separately from narrative generation.

This compact demo reuses accelerator components; it is **not a deployment of the complete accelerator platform**. Separate schema and instance data exports support a later integration with its Scan → Model → Serve workflow.

## Demo story

1. Discover support for a synthetic household after a job transition.
2. Inspect the graph linking the household to scheme rules and supporting policy evidence.
3. Change income or caregiving context and compare the assessment.
4. Inspect unmet or unknown conditions, prepare a document checklist, and ask a grounded question.

Build, deployment, presenter, and integration instructions will be added as the implementation lands.
