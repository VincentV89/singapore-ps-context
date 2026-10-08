This compact demo deploys a private S3 frontend through CloudFront, a username-only Cognito user pool, and a scoped HTTP API backed by Python Lambda in `us-east-1`. CloudFront uses all edge locations, including Singapore. It does not provision Neptune, OpenSearch, an AgentCore runtime, a VPC or a NAT gateway.

Requirements are Python 3 with `boto3`, a recent Node/npm installation, AWS credentials for the intended account, and permissions to create the resources in the templates. The scripts use the normal AWS SDK credential chain and preserve proxy settings. The managed environment for this build supplied access keys in environment variables; its missing injected profile was explicitly cleared in the subprocess:

```bash
env -u AWS_PROFILE PYTHONPATH=/tmp/s3-list-sdk python scripts/deploy.py --enable-bedrock
```

For a regular workstation, use `python scripts/deploy.py --enable-bedrock` with your selected AWS profile. Omit `--enable-bedrock` to use the deterministic graph explanation only. `--skip-build` reuses an existing `backend/package.zip` and `frontend/dist`. Names default to `singapore-ps-context`; a new project name produces independent stacks and Cognito domain.

Deployment builds platform-compatible Python 3.12 x86_64 wheels and the frontend, creates a retained private artifact bucket, uploads the content-hashed Lambda package, and creates the main stack. A second stack update fills in the exact CloudFront CORS origin. This avoids a dependency cycle between API CORS and the CloudFront content security policy. Until that update completes, browser CORS denies the real website origin. Both Cognito callbacks and logout URLs use only the deployed HTTPS site.

The deployed `config.json` contains public endpoints and client identifiers, sets `localPreview` to `false`, and is never cached. Fingerprinted assets are served with immutable cache headers. CloudFront rewrites extensionless routes such as `/auth/callback` to the SPA; missing asset filenames retain their error responses. The frontend S3 bucket allows reads only from its own CloudFront distribution through Origin Access Control.

The output `deployment.json` is ignored by Git and contains no secrets. To create a user interactively:

```bash
python scripts/create_user.py demo.architect
```

Or generate credentials to an ignored, owner-readable file:

```bash
python scripts/create_user.py demo.architect --credentials-file artifacts/demo-login.local.json
```

The script never prints the password and refuses to overwrite a credential file or change an existing user's password unless `--reset-existing` is supplied. Cognito suppresses invitation messages. Self sign-up and email recovery are disabled; this isolated demo uses administrator-managed usernames. The browser uses OAuth authorization code with PKCE and sends access tokens with the `life-events/access` scope. API Gateway rejects an ID token because it lacks that scope. No client secret is generated.

Costs accrue while AWS resources remain deployed. This serverless baseline has no dedicated database/cluster hourly cost; S3 storage/requests, CloudFront transfer/requests, API Gateway requests, Lambda execution, Cognito usage and CloudWatch logs follow their service pricing. Optional Nova Lite narration incurs Bedrock token charges. The configuration caps Lambda concurrency at five and API throughput at five requests/second, retains Lambda logs for fourteen days and API logs for seven days. These controls limit concurrent work; they are not a spending cap. The retained artifact bucket keeps all uploaded package versions until explicitly cleaned up.

Preview cleanup first, then execute it explicitly:

```bash
python scripts/cleanup.py
python scripts/cleanup.py --confirm singapore-ps-context
```

Cleanup verifies both project and demo ownership tags, empties all versions and deletion markers in only the two owned buckets, deletes the main and artifact stacks, then deletes the retained artifact bucket. Existing account resources are refused. CloudFront deletion can take several minutes. Generated local files remain on disk.

Local infrastructure validation:

```bash
python -m unittest discover -s infra/tests -v
```

The tests validate dependency cycles, bucket isolation, scope enforcement, callbacks, cache behavior and actual execution of the SPA rewrite function. `scripts/check_deployment.py` checks the live public site/config and verifies that unauthenticated requests and fabricated tokens are rejected without printing any token.
