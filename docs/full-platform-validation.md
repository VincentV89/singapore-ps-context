# Full-platform deployment and validation

Validated on **8 October 2026** in AWS account `879594333699`, region **`us-east-1`**. The deployed platform has completed actual **Scan → Model → Serve** checks over the Singapore official-source corpus. The branded frontend was published at **08:35:16 UTC**, and real Cognito hosted-login/PKCE passed. Full browser verification of all four audience journeys and mobile layout is still in progress.

| Endpoint | Purpose and current state |
| --- | --- |
| [SG Support Navigator](https://d1pbdc1b2fpdk2.cloudfront.net) | Published Singapore branded full-platform frontend; Cognito sign-in required |
| [Accelerator console](https://d1nupu5vkgc6el.cloudfront.net) | Full platform's deployed CloudFront/S3 administration console |
| `https://4vw29ltb6i.execute-api.us-east-1.amazonaws.com/prod` | Full platform API Gateway endpoint; authenticated calls required |

![Published full-platform entry point](demo-full-entry.png)

## Infrastructure and capacity

CodeBuild deployment **`sgsupport-full-platform:66a1d0ef-4569-47de-b2cb-65f6fb6c43c5`** returned **`SUCCEEDED`**, ending at **`2026-10-08T08:06:25.287Z`**. Install, build, post-build and artifact-upload phases succeeded. CloudFormation inspection confirmed all 16 expected stacks complete; the storage stack subsequently completed the Neptune resize:

| Stack | Confirmed complete state |
| --- | --- |
| `sgsupport-demo-network` | `CREATE_COMPLETE` |
| `sgsupport-demo-auth` | `CREATE_COMPLETE` |
| `sgsupport-demo-guardrail` | `CREATE_COMPLETE` |
| `sgsupport-demo-storage` | `UPDATE_COMPLETE` |
| `sgsupport-demo-authnz` | `CREATE_COMPLETE` |
| `sgsupport-demo-vkg` | `CREATE_COMPLETE` |
| `sgsupport-demo-namespace` | `CREATE_COMPLETE` |
| `sgsupport-demo-metric-service` | `CREATE_COMPLETE` |
| `sgsupport-demo-api` | `CREATE_COMPLETE` |
| `sgsupport-demo-serve` | `CREATE_COMPLETE` |
| `sgsupport-demo-sources` | `CREATE_COMPLETE` |
| `sgsupport-demo-data-layer` | `CREATE_COMPLETE` |
| `sgsupport-demo-edge-waf` | `CREATE_COMPLETE` |
| `sgsupport-demo-web` | `UPDATE_COMPLETE` |
| `sgsupport-demo-ontology` | `CREATE_COMPLETE` |
| `sgsupport-demo-mcp` | `CREATE_COMPLETE` |

The deployed accelerator is pinned to **v0.3.4**, commit `c84a3043a989c30fe33658c763f5f279c6981aba`. Neptune now uses **`db.r8g.large` (16 GiB)**. The resize change set modified only `NeptunePrimaryInstance`, with **`Replacement: False`**; cluster endpoints and other resources were retained. Successful document retries and live graph/query checks establish the result of that capacity change.

Two resolved failures remain recorded: the original asset build's reporter-only `KeyError: stackName` and the first document graph builds' Neptune `MemoryLimitExceededException` on `db.t4g.medium`. Diagnostic receipts preserve the original failed status, assembly provenance and narrowly repaired AOSS names; the original document executions also retain their failed states. The successful deployment and fresh post-resize executions are separate proofs, not rewritten failure history. [Operations](full-platform-operations.md) document recovery, current sizing, costs and teardown.

## Authentication and publication

The full deployment uses Cognito pool **`us-east-1_vnrazEagY`**, client **`g840baav6gnb704v1mheiltbj`**, and the prefix domain `sgsupport-demo-auth-879594333699.auth.us-east-1.amazoncognito.com`.

Administrator **`vincenoh@amazon.com`** is enabled, `CONFIRMED`, email-verified and belongs to **`Admin`**. Invitation emails were suppressed; the password remains in an ignored local file with mode **`0600`**. Real Cognito SRP authentication returned an ID token for this client and administrator group. No password or token appears in this record.

Client configuration permits SRP, refresh tokens and OAuth authorization-code flow, with callbacks for the accelerator console and branded navigator. The live browser has completed the actual Cognito hosted sign-in and frontend PKCE callback. The published navigator configuration selects **`platform.mode: "full"`**, the real namespace, accepted ontology identifier and full Cognito client, with **`localPreview: false`**. The recorded publication time is **`2026-10-08T08:35:16.837Z`**. The entry screenshot above comes from that authenticated deployed page and contains no credentials.

## Scan: approved tables and all documents processed

The active namespace is **`sg-support`**, ID **`c61cf292-1ad6-4ac0-ab85-f02b86a8c04b`**, with a DataZone project and Athena workgroup. Source data uses the private, versioned bucket `sgsupport-demo-official-879594333699-us-east-1` and Glue database `sgsupport_official`.

All **three structured tables** are scanned and approved: **20 programme rows**, **10 agency rows** and **41 evidence rows**. All **20 policy documents** completed processing in four batches of **6 / 6 / 6 / 2**, producing **122 graph chunks and 122 embedded/vector chunks**. The source check confirmed all four document sources `COMPLETED`, the database source `APPROVED` and the namespace VKG `HEALTHY`.

Fresh post-resize execution verification passed at **08:30:04 UTC**:

| Proof | Observed result |
| --- | --- |
| Fresh Step Functions executions | Four `SUCCEEDED` |
| ECS graph-build containers | Four stopped with exit code `0` |
| Complete log-stream inspection | 857 events scanned across the four successful executions |
| Runtime errors in those inspected logs | Zero |
| Expected/completed documents | Exactly 20 / 20 |

The post-repair report retains initial failed executions alongside these fresh successful executions. Completion counts were checked against execution state, container exits and logs, rather than relying on source labels alone. Programme evidence remains dated public information; applicant profiles are hypothetical. [The source inventory](singapore-sources.md) describes attribution, capture dates and coverage limits.

## Model: validated and accepted ontology

The Singapore reference ontology imported successfully with **eight authored classes**. Real induction job/proposal **`f5d939b6-7fe2-41a7-b303-2a359fef1370`** processed all three tables and 27 columns, with no dropped tables. Its reviewed R2RML has **three triples maps** for the actual schemes, agencies and evidence tables, including verified primary/foreign-key relationships and source identifiers.

Blocking validation job **`c91c7285-6cf3-4350-b93a-44e4b2d91720`** passed logical consistency, taxonomy-cycle and connectivity checks. The proposal is **`accepted`**, with ontology publication and vector synchronisation completed. The accepted ontology identifier is `https://vincentv89.github.io/singapore-ps-context/ontology/induced/`. Technical model validation is not an agency policy adjudication or statutory eligibility approval.

## Serve: actual graph, structured and retrieval results

The redacted native validation report `full-platform-checks-attempt01.local.json` records **all seven checks passing**:

| Check | Actual evidence | Observed check duration |
| --- | --- | ---: |
| Sources | Approved database; four completed document sources; private source bucket | 4.8 s |
| Schema | Accepted proposal, verified mappings and successful blocking validators | 3.0 s |
| Graph | Neptune traversal returned 21 entities and 29 relationships | 12.3 s |
| Athena | Exact 20 expected programme/agency pairs from the real table | 4.2 s |
| Natural-language SQL | Query executed and returned all 20 expected programme IDs | 14.7 s |
| Ontop | Actual SPARQL-to-SQL compilation and execution returned all 20 programme IDs | 16.4 s |
| Documents | Ten retrieval citation matches and seven answer citation matches linked to inspected official evidence | 35.3 s |

These timings are individual observed checks, not service latency guarantees. The document check includes knowledge-base search and an authenticated answer request. Structured checks require actual execution traces and matching source rows; a fallback does not satisfy the Ontop check.

The separate `full-platform-deep-checks-attempt01.local.json` report also **passed** against the real AgentCore streaming endpoint:

- Request duration: **145.3 seconds**.
- Returned execution trace: **45 actual steps**.
- Returned graph context: **104 entities**.
- Evidence verification: **19 retrieved chunk matches covering 12 programmes**, matched through document provenance to official source URLs and captured source hashes.
- Result flags: **`partial: false`**, **`guardrailBlocked: false`**.

This request used Sonnet 5 in deep-reasoning mode. Only the tools and steps actually returned by the platform are represented in its trace. These observed results do not guarantee that every subsequent question invokes every retrieval/query path.

## Browser verification still in progress

Cognito hosted-login/PKCE, the authenticated entry page and published full configuration have passed. The four live audience workspaces, their returned graph/evidence interactions and the mobile layout are still being verified. No completed four-persona browser suite or mobile result is claimed yet. Earlier [compact screenshots and tests](validation.md) remain evidence for the separate synthetic edition.

Operator reports are kept privately with credentials and signed URLs redacted. To reproduce source/model/query checks and the separate deep stream, use `scripts/full_platform_checks.py` as documented in [operations](full-platform-operations.md). Each programme card requires **agency assessment**; this demonstration does not submit applications or issue eligibility decisions.
