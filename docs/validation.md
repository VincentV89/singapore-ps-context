# Verified deployment

Validated on 8 October 2026 (Singapore time) in AWS account `879594333699`, region `us-east-1`.

[Live demo](https://d1pbdc1b2fpdk2.cloudfront.net) · [Repository](https://github.com/VincentV89/singapore-ps-context/tree/demo/life-events-navigator)

## Automated checks

- 37 backend tests passed: four-audience isolation, audience-specific presets, explicit rule results, changed context, inclusive numeric boundaries, unknown facts, changed RDF policy/category, current-profile provenance, authoritative edge direction, scoped citations, optional synthesis fallback, API input limits, and empty preflight responses.
- 6 infrastructure tests passed: dependency cycles, private encrypted buckets, OAuth and JWT scopes, CORS/CSP/cache settings, executed SPA routing, and Lambda permissions.
- 5 browser tests passed against the real local API: household changes and evidence/checklist flow; Cognito cover before data access; all four audience journeys and scoped graph/evidence; support filters and missing organisation facts; delayed responses during audience switching. Mobile width 390 pixels had no document overflow.
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

## Four-audience expansion

The updated deployment was verified through the actual Cognito hosted login and frontend PKCE callback. All four entry cards opened their own context, schemes, graph and evidence against the live API. Both scenario retrieval and analysis returned HTTP 200 for every audience.

| Audience | Fictional schemes | Starting likely eligible | Missing-fact review | Traversed context entities |
| --- | ---: | ---: | ---: | ---: |
| Individuals & Families | 6 | 2 | 2 | 16 |
| Businesses & Entrepreneurs | 3 | 1 | 1 | 13 |
| Nonprofits & Community Organisations | 3 | 1 | 1 | 10 |
| Researchers & Educational Institutions | 3 | 1 | 1 | 12 |

The live checks confirmed that returned schemes and traversal entities belong to the selected audience. Changing the business project focus from digitalisation to sustainability excluded Digital Spark Grant and matched Green Launch Support. Selecting the Sustainability discovery filter displayed one scheme and its graph. A live business Bedrock explanation returned supported evidence citations. ID tokens remained rejected with HTTP 403; scoped access tokens were required.

The live browser reported zero application errors. The mobile entry and business workspace had no document overflow at 390 pixels. [Entry screenshot](demo-preview.png) and [filtered business workspace](demo-business.png) were captured from the deployed site. No credentials appear in these artifacts.

The expanded shared ontology contains 106 triples; the combined synthetic instance export contains 2,764 triples. This remains a bundled, in-memory RDFLib demo with 15 fictional schemes, without live source discovery or deployment of the complete accelerator.

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
