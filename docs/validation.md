# Verified deployment

Validated on 8 October 2026 (Singapore time) in AWS account `879594333699`, region `us-east-1`.

[Live demo](https://d1pbdc1b2fpdk2.cloudfront.net) · [Repository](https://github.com/VincentV89/singapore-ps-context/tree/demo/life-events-navigator)

## Automated checks

- 20 backend tests passed: explicit rule results, changed context, exact income boundaries, unknown facts, changed RDF policy, current-profile provenance, authoritative edge direction, scoped citations, optional synthesis fallback, API input limits, and empty preflight responses.
- 6 infrastructure tests passed: dependency cycles, private encrypted buckets, OAuth and JWT scopes, CORS/CSP/cache settings, executed SPA routing, and Lambda permissions.
- 2 browser tests passed against the real local API: profile changes and evidence/checklist flow; Cognito cover before data access. Mobile width 390 pixels had no document overflow.
- TypeScript/Vite production build passed. GitHub Actions runs backend/infrastructure checks and builds the frontend without AWS credentials.

## Live AWS results

The deployed CloudFront site loads the production build and sets `localPreview: false`. The callback route serves the SPA, runtime configuration is uncached, and missing JavaScript files return an error. HTTPS security headers permit the exact API and Cognito endpoints.

The live HTTPS smoke checks verified:

| Check | Result |
| --- | --- |
| Cognito hosted form sign-in | Passed with the administrator-created demo user |
| Frontend authorization code / PKCE callback | Passed; authenticated workspace loaded |
| Unauthenticated API / fabricated bearer token | HTTP 401 |
| Valid Cognito ID token on the scoped data API | HTTP 403; access-token scope is required |
| CORS preflight from deployed CloudFront origin | Accepted |
| CORS from a different origin | No allow-origin header |
| Starting household | Two likely eligible fictional schemes |
| Income S$5,400 plus caregiving | Bridge grant excluded; caregiver relief likely eligible |
| Unknown income | Income-dependent pathways require review |
| Context changes | Highlighted graph edges and comparison states changed |
| Amazon Bedrock synthesis | Live `amazon.nova-lite-v1:0` response with supported evidence citations |
| Accelerator context in synthesis | 16 entities from the actual upstream traversal, with direction verified against RDF |
| Browser application errors | Zero |

The managed executor's proxy certificate is trusted by its HTTPS client but not Chromium. Live browser verification relayed actual remote responses through that existing TLS-validating client and followed Cognito's redirect targets in the driver. No certificate verification was disabled, no browser trust store was changed, and no authentication or application response was fabricated. Normal customer browsers access the public CloudFront/Cognito certificates directly.

## Reproduce

With dependencies installed:

```bash
make test
make dev-api
```

In another terminal:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The browser configuration starts Vite if needed and expects the local API on port 8000. For the deployed read-only checks:

```bash
source .venv/bin/activate
python scripts/check_deployment.py
```

Generated login credentials remain in an ignored file with mode `0600`. They are not present in the repository, screenshot, CI configuration, or deployment metadata.
