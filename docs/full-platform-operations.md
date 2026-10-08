# Singapore Support Navigator: full platform operations

This deployment uses AWS Context Ontology Accelerator **v0.3.4**, pinned to commit `c84a3043a989c30fe33658c763f5f279c6981aba`, in account `879594333699`, region **`us-east-1`**. The 16 core stacks use `sgsupport-demo-*`; project configuration lives under `/sgsupport/config`. The Singapore scenario does not imply Singapore data residency. The configured `us.*` Bedrock inference profiles can route requests within the United States.

The branded navigator and accelerator console use private S3 origins behind CloudFront and Cognito authentication. The administrator is `vincenoh@amazon.com`; invitation emails are suppressed. Generated passwords stay in ignored, permission-`0600` local files. Keep credentials, tokens, signed URLs, build archives and ingestion checkpoints out of Git.

## What the platform does

| Stage | Operational result | Verification |
| --- | --- | --- |
| Scan | Registers public-source documents and the Glue catalogue; extracts document context and discovers structured schemas | Approved sources, exact columns, row counts, provenance and completed document ingestion |
| Model | Imports the Singapore reference vocabulary, induces an ontology from scanned tables, validates its proposal and publishes accepted OWL/R2RML | Proposal artifacts, blocking validation results, mapped source identifiers and publication state |
| Serve | Combines document retrieval, graph context and queries over the structured source through the deployed services | Actual citations, Neptune relationships, Athena results, Ontop mappings and query traces |

Neptune stores graph and ontology context. OpenSearch Serverless stores derived retrieval indexes. The virtual knowledge graph uses accepted R2RML mappings to query structured rows through Ontop and Athena. Uploading a vocabulary alone does not populate those rows or establish executable policy rules.

Public agency information supports programme discovery. Applicant profiles remain hypothetical, and results require **agency assessment**. A page being published does not prove that an application window is open. Preserve the published criteria, exceptions, programme status, retrieval date and application link when presenting a recommendation. The custom Singapore mark is independent demo branding; it is not the government crest or an official government service.

## Deployment and updates

The project-owned CodeBuild job supplies JDK 21 and mixed ARM64/AMD64 Docker builds. Privileged Docker and ARM emulation are confined to that disposable AWS build host. The `build` phase publishes assets and saves a cloud assembly; the `deploy` phase deploys that same assembly. The source packager excludes credentials, caches and generated files.

From this repository, using an accelerator checkout at the pinned commit with [the project patch](../platform/patches/0001-singapore-demo.patch) applied:

```bash
python platform/deploy-full.py package --source /workspace/context-ontology-accelerator
env -u AWS_PROFILE python platform/deploy-full.py prepare
env -u AWS_PROFILE python platform/deploy-full.py start --phase build
env -u AWS_PROFILE python platform/deploy-full.py status --build-id 'sgsupport-full-platform:<build-id>'
env -u AWS_PROFILE python platform/deploy-full.py start --phase deploy --assembly 's3://<project-build-bucket>/builds/<completed-build-artifact>.zip'
```

Install operator dependencies with `python -m pip install -r platform/requirements.txt`. The AWS subcommands require `boto3` and use the normal SDK credential chain. `env -u AWS_PROFILE` addresses this session's missing injected profile while retaining the explicitly selected environment credentials; on a normally configured workstation, use its intended profile instead. The helper restricts deployment to the account and region above. Inspect failed CodeBuild phases and the matching CloudFormation resource events before rerunning. A successful asset build is not a successful platform deployment.

If every service build and asset upload succeeded but the final reporter alone failed with `KeyError: stackName`, the helper supports `start --phase deploy --assembly <original-artifact> --recover-diagnostics-only --assembly-file artifacts/full-platform-assembly.zip`. It verifies the phase statuses, exact diagnostic, all 16 expected stack templates, asset destinations and the original archive before recording a recovery receipt. It preserves the original build failure status and refuses broader failures.

For the pinned assembly's AOSS **32-character name constraint**, [the narrow repair tool](../platform/repair-aoss-names.py) shortens the collection-group and two data-access-policy names in the storage, sources and metric-service templates. It also updates the collection's group reference and the three content-addressed template hashes in their asset manifests and assembly manifest. Docker images and other application assets remain unchanged; a Docker rebuild is unnecessary.

Use the original **asset-build** ID and its actual reported S3 artifact URI:

```bash
env -u AWS_PROFILE python platform/deploy-full.py download \
  --build-id 'sgsupport-full-platform:<original-asset-build-id>' \
  --output artifacts/full-platform-assembly.zip
env -u AWS_PROFILE python platform/repair-aoss-names.py \
  --input artifacts/full-platform-assembly.zip \
  --output artifacts/full-platform-assembly-aoss-fixed.zip \
  --original-build-id 'sgsupport-full-platform:<original-asset-build-id>' \
  --original-uri 's3://<project-build-bucket>/builds/<original-artifact>.zip' \
  --publish
env -u AWS_PROFILE python platform/deploy-full.py start --phase deploy \
  --assembly 's3://<project-build-bucket>/builds/aoss-name-repair-<derived-sha256>.zip'
```

`--publish` verifies the known reporter-only failure, uploads only the three changed templates plus the derived assembly and receipt, and records the repair for the deployment helper. Use the returned `derivedArtifactS3Uri` in the final command. The original archive and actual **`FAILED`** build status remain intact; receipts retain the diagnostic proof, original and derived SHA-256 values, changed properties and unchanged-asset verification. The helper accepts only a matching recorded receipt and the exact allowlisted changes. This recovery does not establish deployment success or live query validation; check the subsequent deployment, ingestion and service results separately. Future full builds include the same short names in the project source patch.

Before deploying a new VPC, verify regional VPC headroom and that the selected Availability Zones offer the accelerator's endpoint services. The initial account check found five VPCs against a quota of five and requested an increase to ten. Check the current quota/request state; it is a prerequisite check, not a permanent deployment status. Do not remove unrelated VPCs to make room. Reusing a VPC requires explicitly prepared private subnets and endpoints because the upstream imported-VPC path does not create them.

The demo settings use Neptune `db.t4g.medium`, ontology ECS **2 vCPU / 8 GiB / one task**, and an OpenSearch NEXTGEN collection group with standby replicas enabled. Search and indexing each have a **2-OCU minimum and 4-OCU maximum**. The small ontology task is sized for this bounded catalogue; larger inductions require revisiting memory and CPU. Keep embedding producers and retrieval consumers on the same model and **1,024 dimensions**. Current configuration uses Sonnet 5, Haiku 4.5 and Cohere Embed v4, and the hand-rolled Tier 3 strategy consults the formal ontology.

## Administrator and branded frontend

After the full stacks complete, initialize the private login and collect the deployed endpoints:

```bash
env -u AWS_PROFILE python scripts/full_platform_frontend.py --bootstrap
```

This suppresses invitation emails and saves the administrator password once in `artifacts/full-platform-login.local.json` with mode `0600`. Repeated runs reuse it. The full Cognito client permits both the accelerator console and the branded navigator callbacks.

After source ingestion, reviewed ontology publication and live query checks succeed:

```bash
cd frontend && npm run build && cd ..
env -u AWS_PROFILE python scripts/full_platform_frontend.py --publish
```

Publishing checks the actual accepted proposal and source states, updates the navigator's exact API/login CSP origins, uploads the public catalogue and full-platform configuration, and invalidates CloudFront. The accelerator console is retained. The initial assembly's gateway error responses select the console origin; the publisher updates only those two owned full-web CloudFormation custom resources to `*`, matching the demo's existing authenticated success/OPTIONS responses, and redeploys the API after both updates. The source patch carries the same origin setting for future synths. Tokens remain required for platform access.

## Source refresh and validation

[The source catalogue](../data/official/catalogue.json) carries official URLs, exact attributed excerpts, source hashes and capture dates. The reviewed seeds distinguish curated summaries from verbatim evidence. Refresh verifies that the expected excerpts still occur; a changed or removed passage must be reviewed and updated deliberately.

```bash
python scripts/official_sources.py refresh
python scripts/official_sources.py verify
```

Review programme changes, deadlines and exceptions before publishing refreshed exports. Retain the previous snapshot for comparison. For example, Enterprise Singapore's October 2026 snapshot directs users from EDG, PSG and MRA, which ceased on 29 September 2026, to EDGE. A stale grant catalogue could otherwise recommend a closed programme.

Ingestion uses the full platform's real APIs and a private Cognito login file:

```bash
env -u AWS_PROFILE python scripts/full_platform_ingest.py \
  --metadata artifacts/full-platform.json \
  --credentials artifacts/full-platform-login.local.json \
  --state artifacts/full-platform-ingest.local.json \
  --stage all --document-limit 0 --wait-seconds 30
```

Exit code `2` means asynchronous work is pending; rerun with the same checkpoint. The initial bounded document run can use the default limit of six, covering all four audiences. The script validates the controlled source schema and proposal artifacts before accepting them; that technical review is not an agency policy approval. A changed corpus hash deliberately stops an existing checkpoint. Review the differences and perform an explicit source rescan/model update rather than deleting the checkpoint to conceal a change.

```bash
env -u AWS_PROFILE python scripts/full_platform_checks.py \
  --metadata artifacts/full-platform.json \
  --credentials artifacts/full-platform-login.local.json --check all
env -u AWS_PROFILE python scripts/full_platform_checks.py \
  --metadata artifacts/full-platform.json \
  --credentials artifacts/full-platform-login.local.json --check deep
```

The first command checks source, schema, graph, Athena, structured query and document paths. Deep reasoning is a separate, longer AgentCore streaming check. Preserve the redacted reports and verify that displayed evidence resolves to inspected official sources. Display actual pipeline errors and traces; do not replace failed platform calls with compact-demo assessments.

## Standing cost

**Planning estimate: approximately US$1,180–1,900 per 730-hour month before usage and storage**, or roughly **US$39–62 per day**. These are a subtotal for the settings below, not a total-bill guarantee or a budget cap. The platform incurs substantial charges while idle.

Rates were checked through the AWS Price List API on **8 October 2026** for `us-east-1`, on-demand USD pricing, excluding tax, discounts and credits:

| Component | Rate and assumption | 730-hour subtotal |
| --- | --- | ---: |
| OpenSearch indexing and search | US$0.24/OCU-hour; 2 indexing + 2 search minimum, up to 4 + 4 | US$700.80–1,401.60 |
| Interface VPC endpoints | US$0.01/endpoint/AZ-hour; 20 services in two AZs | US$292.00 |
| Ontology ECS task | 2 × US$0.04048/vCPU-hour + 8 × US$0.004445/GiB-hour, Linux x86 | US$85.06 |
| Neptune primary | `db.t4g.medium`, US$0.093/hour | US$67.89 |
| NAT gateway | One at US$0.045/hour | US$32.85 |
| Public IPv4 | One NAT address at US$0.005/hour | US$3.65 |
| **Subtotal** | Excludes the items below | **US$1,182.25–1,883.05** |

Active per-namespace VKG services add ARM Fargate usage: **US$0.03238/vCPU-hour + US$0.00356/GiB-hour**. One continuously active 1-vCPU/2-GiB task adds approximately US$28.84/month. Scan/extraction tasks are additional usage. CodeBuild `BUILD_GENERAL1_LARGE` Linux compute costs **US$0.02/build minute**; a 90-minute build is US$1.80 before associated storage and logs.

Also budget for Bedrock tokens and embeddings, AgentCore runtime/memory usage, Neptune storage/I/O/burst credits where applicable, OpenSearch storage, NAT and endpoint data processing, Glue, Athena, DataZone, Lambda, API Gateway, Step Functions, Cognito, S3/ECR, CloudWatch, KMS, WAF and CloudFront. Exact Sonnet 5/Haiku 4.5/Embed v4 inference rates were not established by this price lookup and are excluded; use the current model pricing and measured token counts. AgentCore pricing has multiple consumption variants, so use the actual billed usage type rather than assuming a per-request flat rate. Existing compact-demo resources are additional.

The OCU maximum is a compute capacity limit for this collection group; it does not cap the AWS bill. Reconcile actual endpoint counts, active tasks and OCU metrics against this estimate after deployment. Use project tags and Cost Explorer to track actual spending.

Pricing references: [OpenSearch](https://aws.amazon.com/opensearch-service/pricing/), [PrivateLink](https://aws.amazon.com/privatelink/pricing/), [Fargate](https://aws.amazon.com/fargate/pricing/), [Neptune](https://aws.amazon.com/neptune/pricing/), [VPC/NAT/IPv4](https://aws.amazon.com/vpc/pricing/), [CodeBuild](https://aws.amazon.com/codebuild/pricing/), [Bedrock](https://aws.amazon.com/bedrock/pricing/) and [AgentCore](https://aws.amazon.com/bedrock/agentcore/pricing/). Price List product identifiers for the core rates are `4GTYCPXPAQWXNTQ4`/`TV5CBXF5VXP698KT` (OpenSearch indexing/search), `EN2N5TATXE673A3B` (endpoints), `8CESGAFWKAJ98PME`/`PBZNQUSEXZUC34C9` (x86 Fargate), `CH3E3XZENXTF7AHY` (Neptune), `M2YSHUBETB3JX4M4` (NAT), `4GQUNXTFWVSGPUZK` (IPv4) and `8MTWRQ8M475YQT7D` (CodeBuild).

## Teardown

When this full deployment is no longer needed, use the pinned accelerator's teardown script from its checkout, with its generated packages and dependencies available:

```bash
env -u AWS_PROFILE SCL_PREFIX=sgsupport AWS_DEFAULT_REGION=us-east-1 \
  bash scripts/destroy.sh demo
```

This removes `sgsupport-demo-*`. The script first deletes AgentCore runtimes and waits for their network interfaces, removes dynamically created namespace VKG/Cloud Map resources, deletes the retained DataZone domain, removes matching connector stacks, then destroys CDK stacks and verifies leftovers. If AgentCore interfaces remain attached, the script stops; wait for detachment and rerun. Direct `cdk destroy --all` can fail while those resources remain.

The build stack `sgsupport-full-platform-build` and its retained, versioned bucket are separate. So are the ingestion-created source bucket `sgsupport-demo-official-879594333699-us-east-1` and Glue database `sgsupport_official`. Inventory their ownership tags, object versions, tables and any Athena result locations before explicitly removing them. Removing a versioned bucket requires deleting versions and delete markers. The shared `CDKToolkit` bootstrap resources and the separately deployed `singapore-ps-context-demo` compact app are outside this teardown's scope. Check remaining tagged resources and subsequent billing after stack deletion.
