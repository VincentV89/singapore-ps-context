# Integrating with the complete Context Ontology Accelerator

## Current scope and target

The runnable Life Events Navigator vendors real components from [AWS Context Ontology Accelerator](https://github.com/aws/context-ontology-accelerator), release **`v0.3.4`**, commit **`c84a3043a989c30fe33658c763f5f279c6981aba`**. Its backend executes the upstream `GraphTraverser` through an RDFLib `GraphClient` adapter and uses the upstream serializer for its OWL/Turtle schema export. The demo's policy evaluator, visual frontend, API, and synthetic data are purpose-built additions.

The complete accelerator has **Scan → Model → Serve** services including Neptune, OpenSearch Serverless, DataZone/SageMaker Unified Studio, ontology induction, Ontop virtual knowledge graph mappings, and AgentCore-hosted context orchestration. Those services are **future integration work**, not services deployed by this compact demo. The recipes below were checked against the named release's source contracts and routing code; they have not been executed against a live full-accelerator deployment as part of this implementation.

Both the compact deployment and this proposed expansion use **`us-east-1`**, as selected by the user. A Singapore-resident deployment would require regional service/model checks and different Bedrock model routing. The default US inference profiles cannot simply be invoked from Singapore.

## 1. Prepare a separate full accelerator environment

Use the tagged release rather than an arbitrary current `main`. Follow the release's [deployment guide](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/external-docs/content/deploying.md) for Python 3.12, Node 22, pnpm, uv, Java/Gradle, Docker, CDK bootstrap, administrator-equivalent deployment permissions, model access, and quota checks. ARM64 container builds require a native ARM builder or configured emulation.

The documented entry points are `make setup`, `make build`, and `make deploy-dev`. Set both `AWS_DEFAULT_REGION` and `CDK_DEFAULT_REGION` to `us-east-1`. Choose an isolated `SCL_PREFIX`, and configure `SCL_SMUS_ADMIN_ARNS` when the account does not have the accelerator's fallback `Admin` role. The user selected the compact implementation first; these commands are guidance for a later, separately scoped full deployment.

Choose the **`opensearch_neptune`** ontology backend when demonstrating structured queries. The release's `na_only` backend does not persist the `coa:isMapped` marker and therefore cannot demonstrate its normal Tier-2 mapped structured-query path.

For a formal-ontology context story, configure CDK context **`tier3_strategy=hand-rolled`** or **`tier3_strategy=deep-reasoning`**. The default `lexical-baseline` traverses the document lexical graph but does not consult accepted OWL classes/domain/range definitions. Consult the release's Serve documentation before setting this context; the `scripts/deploy.sh` helper does not expose every CDK context through an environment-variable alias. Verify the chosen context in the synthesized Serve runtime configuration.

A fresh full deployment provisions approximately sixteen stacks. Upstream documentation estimates about 1.5 hours for CloudFormation provisioning after dependencies and image builds. Neptune `db.r8g.large`, OpenSearch Serverless capacity, NAT/endpoints, Fargate, and runtimes produce a different cost profile from the compact request-based stack. The default AOSS OCU range is 2–96; choose an appropriate demonstration ceiling rather than accepting it blindly. Use current regional prices for an estimate.

## 2. Create an authorized namespace

Use the full accelerator's Cognito login and platform/namespace grants. A JWT alone does not imply namespace access: its Cedar authorizer also evaluates the caller's role. The demo's independent Cognito app client/user pool is not automatically trusted by the accelerator. For a standalone frontend, add its CloudFront callback origin and a permitted client configuration, or use the accelerator's own login/client configuration.

Verified REST operation, from `models/src/main/smithy/namespace.smithy`:

```http
POST /namespaces
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "name": "sg-life-events",
  "displayName": "Singapore Life Events Demo",
  "description": "Fictional citizen-service context and screening rules",
  "owner": "<your-valid-demo-owner-email>"
}
```

Read `namespace.namespaceId` from the response. Use this UUID consistently as `{namespaceId}` in the paths below. A namespace's display name, its short name, and its UUID serve different purposes; the named-graph writers use the namespace value passed to their services.

## 3. Upload the schema, with explicit ingest polling

Generate the exported files with `python backend/build_graph.py` from this repository. Use `backend/data/ontology.ttl` for the formal schema. Keep `backend/data/instances.ttl` separate: it contains concrete synthetic records and rule individuals.

The verified public path is **presigned upload → S3 PUT → ingest-from-s3 → ingest-status**. Although `UploadOntology` appears in Smithy, the release's `api_proxy_handler.py` does not route the legacy direct `/upload` operation, so this guide uses the supported presigned flow.

1. Request an upload URL:

```http
POST /namespaces/{namespaceId}/ontologies/upload-url
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "filename": "ontology.ttl",
  "contentType": "text/turtle",
  "ontologyId": "urn:demo:life-events:v1",
  "title": "Life Events Navigator reference ontology"
}
```

The response supplies `uploadUrl`, `s3Key`, and `ontologyId`. The explicit URN is a convenient registry identifier with no slash or fragment; the ontology's class/property IRIs remain those in the Turtle.

2. PUT the raw file bytes to `uploadUrl`, using exactly `Content-Type: text/turtle`. A presigned URL authorizes this upload; do not add the Cognito bearer token to that S3 request. It expires after fifteen minutes in the inspected router.

3. Trigger asynchronous ingest using the returned identifier and key:

```http
POST /namespaces/{namespaceId}/ontologies/{urlEncodedOntologyId}/ingest-from-s3
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "s3Key": "<returned-s3Key>",
  "format": "turtle",
  "title": "Life Events Navigator reference ontology",
  "ontologyType": "user_created"
}
```

Use `encodeURIComponent(ontologyId)` for the path segment. This responds with HTTP 202 and an object `result` containing `jobId`, `ontologyId`, and `status`.

4. Poll `GET /namespaces/{namespaceId}/ontologies/{urlEncodedOntologyId}/ingest-status/{jobId}`. The statuses are `pending`, `running`, `embeddings_sync`, `completed`, and `failed`. Continue only after `result.status` is `completed`; surface `result.error` on failure. Successful parsing alone is insufficient because vectors become searchable asynchronously.

5. Confirm the registered ontology with `GET /namespaces/{namespaceId}/ontologies` and inspect `GET /namespaces/{namespaceId}/schema`. The latter returns queryable class/property metadata, not resident facts or computed eligibility.

**Named graphs.** `coa_ontology/stores/neptune_db_graph.py` stores each ontology under:

```text
{NDB_GRAPH_URI_BASE}/{namespace}/{percentEncodedOntologyId}
```

The default graph base is `https://ontology-workbench.local` (`infra/lib/constants.ts`). Serve receives `GRAPH_URI_TEMPLATE = <same-base>/{namespace}`. Its `namespace_graph_prefix()` adds the trailing `/`, and traversal selects `GRAPH ?g` with `STRSTARTS(STR(?g), <namespace-prefix>)`. The ontology IRI, registry ID, and named graph IRI are related but distinct. Use the ingest/registry response as the authority for the stored graph location instead of guessing a Neptune graph URI.

Do not set a custom Serve-only graph prefix: it would no longer match the graphs written by ingestion. The old `graph_uri_template` CDK context is deliberately rejected by the release for this reason.

## 4. Supply queryable facts and grounded mappings

The schema upload enables ontology browsing and grounding. It **does not** create Glue tables, synthetic resident rows, or R2RML mappings. The compact backend's generic evaluator is also not automatically installed into the accelerator.

For a genuine Scan/Model demonstration, a practical next step is to convert the fixture into a small S3/Glue dataset. The following table design is a proposed mapping, not an exporter already implemented here:

| Proposed table | Suggested keys and columns | Ontology concept |
| --- | --- | --- |
| `households` | PK `household_id`; `household_income`, `household_size` | Household |
| `residents` | PK `resident_id`; FK `household_id`; age, citizenship, employment, caregiving, accessibility and job-loss flags | Resident |
| `schemes` | PK `scheme_id`; name, benefit; FK `agency_id` | Scheme |
| `eligibility_rules` | PK `rule_id`; FK `scheme_id`; field, operator, typed expected value, rule order, FK `evidence_id` | EligibilityRule |
| `agencies` | PK `agency_id`; name | Agency |
| `documents` | PK `document_id`; name | Document |
| `scheme_documents` | Composite PK `scheme_id`, `document_id`; FKs to both | Scheme → Document relationship |
| `evidence` | PK `evidence_id`; title, excerpt, source, revision timestamp | Evidence |

Declare keys and relationships during steward review. Glue's table metadata alone may not contain the business meaning of all joins; the accelerator can infer relationships, but review them against the intended model. Preserve types instead of treating Boolean/numeric expected values as indistinguishable strings. Keep missing income null.

After S3 files and Glue tables exist, register the source using the verified `CreateSource` body:

```http
POST /namespaces/{namespaceId}/sources
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "sourceType": "DATABASE",
  "databaseSource": {
    "name": "Synthetic life events tables",
    "glueConfiguration": {
      "catalogId": "<12-digit-account-id>",
      "region": "us-east-1",
      "databaseName": "sg_life_events"
    },
    "metadataEnrichmentEnabled": true
  }
}
```

The response supplies `sourceId`, `status`, and usually `scanJobId`. Poll `GET /namespaces/{namespaceId}/sources/{sourceId}` and the scan operations. Review tables/columns and metadata while the source is in review, then `POST /namespaces/{namespaceId}/sources/{sourceId}/approve` with an empty JSON body. Approval is asynchronous; poll until `APPROVED`, and inspect failures.

Run ontology induction grounded to the uploaded reference ontology:

```http
POST /namespaces/{namespaceId}/induce
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "datasourceIds": ["<sourceId>"],
  "ontologyUriPrefix": "https://demo.example.gov.sg/life-events/induced/",
  "label": "Synthetic service catalogue",
  "strategy": "table_to_ontology",
  "groundingOntologyIds": ["urn:demo:life-events:v1"],
  "groundingMode": "ENHANCED"
}
```

Poll `GET /namespaces/{namespaceId}/induce/jobs/{jobId}`, inspect the proposal, and validate the proposed vocabulary and join paths. Accept with `POST /namespaces/{namespaceId}/proposals/{proposalId}/accept` and `{}` to use the proposal's ontology ID. Poll `GET /namespaces/{namespaceId}/proposals/{proposalId}` until accepted. The `ontop` query strategy requires accepted, published R2RML mappings; a reference ontology without mappings does not satisfy it.

The upstream demo's `parse_ddl_to_config.py` and `stage_fixtures.py` can stage schemas into its local mock data catalog for induction development. That fixture service is not an actual SQL database: staging metadata is insufficient to demonstrate an executed structured query. No citizen-table exporter or R2RML generator for this repository is claimed to be complete.

If the desired architecture instead imports RDF instance facts directly into Neptune, design that as a separate ingestion operation with explicit named-graph placement, provenance, and access scope. It is not equivalent to uploading a T-Box reference ontology, and it does not create a virtual mapping to an operational source.

## 5. Add document retrieval alongside graph context

For the full document story, place clearly labelled fictional policy documents in an accessible source S3 bucket and register a DOCUMENTS source:

```http
POST /namespaces/{namespaceId}/sources
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "sourceType": "DOCUMENTS",
  "documentSource": {
    "name": "Fictional eligibility policy documents",
    "sourceBucketArn": "arn:aws:s3:::<policy-source-bucket>",
    "s3Prefixes": ["fictional-policies/"],
    "extractionConfig": {
      "preferredEntityClassifications": ["Resident", "Household", "Scheme", "EligibilityRule", "Agency", "Document", "Evidence"],
      "useBatchInference": false
    }
  }
}
```

Use an appropriate source-access role if the bucket is cross-account. Poll the source's actual ingestion state. Entity classification hints guide extraction; they do not guarantee that every extracted instance is formally linked to an accepted OWL class. Inspect the resulting graph and provenance.

This produces the full comparison: document retrieval returns policy passages; ontology lookup and graph traversal establish how concepts and relationships connect; structured source queries supply current facts. The compact demo already visualizes authored evidence relationships, while this step adds real ingestion/retrieval services.

## 6. Adapt the frontend to Serve

The full accelerator's contract differs from the compact demo's `/api/scenario` and `/api/analyze` API. Implement an adapter; changing an API URL alone is insufficient. Keep the explicit, deterministic screening evaluator for the fictional policy logic, and use Serve for retrieval and context assembly. Formal class modelling and a natural-language answer are not substitutes for executing those policy rules.

### Short REST query

Verified shape from `models/src/main/smithy/serve.smithy` and `packages/data-layer/src/coa_data_layer/handler.py`: options are **flat in the REST body**.

```http
POST /namespaces/{namespaceId}/query
Authorization: Bearer <accelerator-user-token>
Content-Type: application/json

{
  "query": "Which fictional schemes require household income evidence?",
  "mode": "standard",
  "includeSupporting": true,
  "maxResults": 20
}
```

`strategy` selects a Tier-2 engine (`ontop`, `nl_to_sql`, `ontop_first`, `nl_to_sql_first`, `best`, or `deep-reasoning`); it is distinct from `mode`. `includeDebugInfo: true` exposes internal SQL/SPARQL and should be a deliberate demonstrator setting.

REST has a 29-second API Gateway integration ceiling. Use it for short schema/graph/structured operations. Multi-step retrieval and synthesis should use SSE.

### Interactive SSE query

The inspected v0.3.4 browser hook uses a **Cognito ID token**, matching `serve-stack.ts`'s AgentCore `allowedAudience` configuration. Its data-layer README still mentions access tokens; the current infrastructure and web client use ID tokens on the browser paths. Match the deployed runtime's actual authorizer configuration if integrating a different release or identity provider.

```ts
const endpoint = `https://bedrock-agentcore.${region}.amazonaws.com/runtimes/${encodeURIComponent(serveRuntimeArn)}/invocations?qualifier=DEFAULT`;
const response = await fetch(endpoint, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${idToken}`,
    "Content-Type": "application/json",
    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": runtimeSessionId,
  },
  body: JSON.stringify({
    query: "Explain the fictional caregiver support rules using the published policy evidence.",
    namespace: namespaceId,
    options: { mode: "deep-reasoning", includeSupporting: true },
    stream: true,
  }),
});
```

Use a stable user-scoped runtime session ID of at least 33 characters; mirror the upstream `deriveRuntimeSessionId` helper rather than inventing one. Parse the SSE stream with a proper streaming parser and handle `step`, `token`, `rows`, `done`, and `error` events. The upstream files `use-playground-stream.ts`, `build-query-endpoint.ts`, and `app-types/playground.ts` provide the working browser pattern, cancellation behavior, and event shapes. Configure the runtime's allowed origin for the custom CloudFront frontend.

Map Serve `graphContext.entities[].uri` and relationship `sourceUri`/`predicateUri`/`targetUri` to graph nodes and edges. Map `supportingContent` to evidence cards, and `trace` to the visible processing steps. Display the ontology version and partial-result indicator when supplied. Maintain a stable URI-to-demo-ID mapping if reusing the compact frontend's node identities.

`deep-reasoning` can call structured, graph, and document tools, but the planner does not guarantee that all evidence channels are consulted on every request. The release also does not return the structured leg's SQL/data-source provenance fully in this mode. Use the actual execution trace and cited content to explain what happened; do not animate tool steps that did not run.

### Direct graph and schema operations

The verified paths are:

```text
GET  /namespaces/{namespaceId}/schema
POST /namespaces/{namespaceId}/graph/traverse
POST /namespaces/{namespaceId}/kb/search
POST /namespaces/{namespaceId}/translate
```

Example traversal body:

```json
{
  "startUri": "https://demo.example.gov.sg/life-events/Scheme",
  "maxDepth": 2,
  "direction": "both",
  "maxResults": 30
}
```

Optional `relationshipFilter` restricts predicate IRIs. The response has `entities`, `relationships`, and `trace`. The schema class example operates on the uploaded ontology; a concrete resident URI works only after its instance graph is actually ingested. `kb/search` accepts `query`, `topK`, optional `minScore`, `sourceFilter`, and `entityFilter`; it returns `chunks` and `trace`.

## Acceptance checks for the expansion

- An authorized user can sign in to the custom CloudFront frontend and query only the intended namespace.
- The imported reference ontology appears in `/schema` and ontology inventory after completed ingestion.
- At least one source-backed question executes against synthetic Glue/Athena rows; its trace and outputs establish which source was queried.
- An `ontop` demonstration succeeds through accepted R2RML mappings rather than an unnoticed NL-to-SQL fallback.
- A context question returns inspected graph relationships and a real retrieved fictional policy passage.
- Missing income remains unknown; the explicit screening evaluator's regression cases remain unchanged after the retrieval adapter is added.
- No UI describes a screening outcome as an approval or claims that an application/case was submitted.

## Source references checked

- [Serve Smithy contract](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/models/src/main/smithy/serve.smithy)
- [Ontology graph/upload contract](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/models/src/main/smithy/ontology-graph.smithy)
- [Unified sources contract](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/models/src/main/smithy/unified-sources.smithy)
- [Induction contract](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/models/src/main/smithy/ontology-induction.smithy)
- [Ontology API route proxy](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/packages/ontology-engine/src/coa_ontology/api_proxy_handler.py)
- [Neptune named-graph writer](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/packages/ontology-engine/src/coa_ontology/stores/neptune_db_graph.py)
- [Current SSE browser client](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/packages/web-app/src/api-hooks/use-playground-stream.ts)
- [AgentCore token configuration](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/infra/lib/stacks/services/serve-stack.ts)
- [Serve execution modes and limitations](https://github.com/aws/context-ontology-accelerator/blob/v0.3.4/external-docs/content/serve.md)
