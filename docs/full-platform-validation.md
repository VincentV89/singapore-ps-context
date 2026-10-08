# Full-platform deployment and validation

Initial infrastructure/authentication record checked on **8 October 2026 at 08:09:31 UTC** in AWS account `879594333699`, region **`us-east-1`**. Source processing and application validation remain in progress. This record does not establish completed Scan → Model → Serve journeys.

| Endpoint | Purpose and current state |
| --- | --- |
| [Accelerator console](https://d1nupu5vkgc6el.cloudfront.net) | Full platform's deployed CloudFront/S3 console; Cognito sign-in required |
| `https://4vw29ltb6i.execute-api.us-east-1.amazonaws.com/prod` | Full platform API Gateway endpoint; authenticated calls required |
| [SG Support Navigator entry point](https://d1pbdc1b2fpdk2.cloudfront.net) | Still serving compact runtime configuration; full-platform publication pending |

## Infrastructure proof

CodeBuild deployment **`sgsupport-full-platform:66a1d0ef-4569-47de-b2cb-65f6fb6c43c5`** returned **`SUCCEEDED`**, ending at **`2026-10-08T08:06:25.287Z`**. Install, build, post-build and artifact-upload phases succeeded. Read-only CloudFormation inspection subsequently confirmed all 16 expected platform stacks in complete states:

| Stack | Observed state |
| --- | --- |
| `sgsupport-demo-network` | `CREATE_COMPLETE` |
| `sgsupport-demo-auth` | `CREATE_COMPLETE` |
| `sgsupport-demo-guardrail` | `CREATE_COMPLETE` |
| `sgsupport-demo-storage` | `CREATE_COMPLETE` |
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

The deployed assembly derives from the pinned accelerator **v0.3.4**, commit `c84a3043a989c30fe33658c763f5f279c6981aba`. The original published asset build `d02373af-0f9e-4280-8aee-8b1e7309ef30` retains its actual **`FAILED`** status because its final stack-summary reporter raised `KeyError: stackName`; the completed asset publication was recovered with recorded diagnostic proof. A subsequent narrow AOSS name repair changed three templates and their content-addressed references, with application/Docker assets unchanged.

The retained repair receipt records:

- Original assembly SHA-256: `71fd1600321f61ef64d2a07cb5bd1feb403933863257da10639a75f851055158`.
- Derived deployed assembly SHA-256: `96f483d3ce3c3c6e09cf3b91f9de609db80941f126093796505fdeb19f802566`.
- All 16 expected stack names, the changed AOSS properties and unchanged-application-asset verification.

The later successful deployment is separate evidence from that preserved asset-build failure. [Operations](full-platform-operations.md) describe the constrained recovery and teardown procedures.

## Authentication proof

The full deployment uses Cognito pool **`us-east-1_vnrazEagY`**, client **`g840baav6gnb704v1mheiltbj`**, and the prefix domain `sgsupport-demo-auth-879594333699.auth.us-east-1.amazoncognito.com`.

The configured administrator **`vincenoh@amazon.com`** is enabled, `CONFIRMED`, email-verified and belongs to the **`Admin`** group. Administrator setup used suppressed invitations, and the generated password is stored only in an ignored local file with mode **`0600`**. Real Cognito SRP authentication was verified with an ID token for the full client and the administrator group. No password or token is included in this record.

Read-only client inspection confirmed `ALLOW_USER_SRP_AUTH`, refresh-token authentication and OAuth authorization-code flow. Callback URLs include the accelerator console's `/authenticate/` and the branded navigator's `/auth/callback`. This establishes the configured authentication contract; full-platform hosted-login/PKCE browser verification remains pending.

## Official-source staging and work in progress

An authenticated platform call created the active **`sg-support`** namespace, ID **`c61cf292-1ad6-4ac0-ab85-f02b86a8c04b`**, with its DataZone project and Athena workgroup. The ingestion checkpoint records a private, versioned source bucket `sgsupport-demo-official-879594333699-us-east-1`, Glue database `sgsupport_official`, and staging completed at **`2026-10-08T08:06:49.827Z`**.

The public-source corpus contains **20 programme rows, 10 agency rows and 41 evidence rows** across three structured tables, plus **20 policy documents** staged in four batches of **6 / 6 / 6 / 2**. These are dated public agency snapshots; applicant profiles remain hypothetical. [The source inventory](singapore-sources.md) describes provenance and coverage.

At the observed checkpoint, the structured source was registered and had discovered all **three tables**, with **zero approved tables** and status **`PENDING_REVIEW`**. All four registered document sources were **`SCANNING`**. Reference ontology ingest had started and was **`running`**; no induced model or completed scan-review receipt had been recorded. Registration and staging therefore do not prove successful indexing, approved source metadata or accepted mappings.

| Remaining check | State at this record |
| --- | --- |
| Structured source review and approval | Pending |
| All 20 policy documents indexed/extracted | Pending |
| Reference ontology ingest complete | Pending |
| Real induction, blocking validation and accepted OWL/R2RML | Pending |
| Neptune schema/relationship traversal | Pending |
| Actual Athena rows and Ontop SPARQL-to-SQL execution | Pending |
| Retrieved official citations and AgentCore deep stream | Pending |
| Branded frontend full-platform publication | Pending |
| Cognito browser PKCE and all four live audience journeys | Pending |

A read of the public navigator's `/config.json` confirmed `localPreview: false`, the earlier compact API and compact Cognito client, and no full-platform mode. The published entry point consequently remains the compact edition until the full-source/model/query checks permit publication. Its previous screenshots and [compact validation record](validation.md) are not full-platform browser evidence.

Resume the checkpointed ingestion and run `scripts/full_platform_checks.py` as documented in [operations](full-platform-operations.md). Record actual source states, accepted proposals, query outputs, citations, traces and browser results when those checks complete. No full-platform screenshots or completed applicant journeys are claimed by this initial record.

## Ingestion capacity correction

Subsequent real processing approved all three structured tables, imported the reference ontology (8 classes), and completed induction job `f5d939b6-7fe2-41a7-b303-2a359fef1370`. Its pending proposal contains mappings to the three actual tables and the verified key relationships. Validation and acceptance are paused while Neptune is resized.

The initial `db.t4g.medium` instance encountered `MemoryLimitExceededException` in `ExecuteOpenCypherQuery` during the four concurrent document graph builds. The ECS task memory was approximately 375 MB; the failure occurred in Neptune source-node versioning and insertion. Extraction succeeded for the first six-document batch, while graph ingestion did not complete. Failure evidence is preserved privately, and no completed source corpus or live answer is claimed.

[The constrained resize helper](../scripts/resize_full_platform_neptune.py) verified a CloudFormation change set containing exactly one `Modify` action, with `Replacement: False`, for `NeptunePrimaryInstance`. The resize to `db.r8g.large` (16 GiB) is in progress. The cluster, instance identifier, endpoints, exports and other resources remain unchanged. The build specification now uses that class for subsequent builds. Database availability, successful document retries and actual graph/query checks are required before publication.
