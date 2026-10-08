# Singapore public agency source corpus

The full-platform demonstration uses public programme and policy information captured from official Singapore agency websites. Applicant profiles remain hypothetical. This corpus does not contain citizen records, business applications, internal government data, or personal information.

The current capture contains **20 programmes, 10 agencies and all four audience journeys**, captured on **2026-10-08T06:20:56Z**. Seven programmes serve individuals and families, four businesses, five nonprofits/community organisations, and four researchers. `published` means that a programme page was published and captured; it does not mean a funding call is currently open or an applicant is eligible.

Every catalogue entry contains the official URL, source title, UTC capture time, SHA-256 of its exact HTML snapshot, administering agency, reviewed summary, verbatim policy excerpts, and application-information URL. `verified: true` means the public source was fetched successfully and the stored excerpts match its content. It does not mean eligibility, approval or agency endorsement.

## Programmes

| Programme | Agency | Journey | Source |
|---|---|---|---|
| ComCare Short-to-Medium-Term Assistance | MSF | individuals | [Official source](https://www.msf.gov.sg/what-we-do/comcare) |
| ComCare Long-Term Assistance | MSF | individuals | [Official source](https://www.msf.gov.sg/what-we-do/comcare) |
| Community Health Assist Scheme (CHAS) | MOH | individuals | [Official source](https://www.chas.sg/Applying-for-CHAS/Eligibility) |
| SkillsFuture Credit | SWDA | individuals | [Official source](https://www.myskillsfuture.gov.sg/content/portal/en/career-resources/career-resources/education-career-personal-development/SkillsFuture_Credit.html) |
| Kindergarten Fee Assistance Scheme (KiFAS) | ECDA | individuals | [Official source](https://www.ecda.gov.sg/parents/preschool-subsidies/kindergarten-fee-assistance-scheme-(kifas)/overview) |
| Infant and Childcare Subsidy Scheme | ECDA | individuals | [Official source](https://www.ecda.gov.sg/parents/preschool-subsidies/infant-and-childcare-subsidy-scheme/overview) |
| MOE Financial Assistance | MOE | individuals | [Official source](https://www.moe.gov.sg/financial-matters/financial-assistance) |
| EDGE Grant | EnterpriseSG | businesses | [Official source](https://www.enterprisesg.gov.sg/financial-support/edge-grant) |
| Energy Efficiency Grant (EEG) | EnterpriseSG | businesses | [Official source](https://www.enterprisesg.gov.sg/financial-support/energy-efficiency-grant) |
| Enterprise Financing Scheme – SME Working Capital Loan | EnterpriseSG | businesses | [Official source](https://www.enterprisesg.gov.sg/financial-support/enterprise-financing-scheme---sme-working-capital) |
| Enterprise Financing Scheme – Green | EnterpriseSG | businesses | [Official source](https://www.enterprisesg.gov.sg/financial-support/enterprise-financing-scheme---green) |
| Transformation Sustainability Scheme | NCSS | community | [Official source](https://www.ncss.gov.sg/grants/organisation-development/transformation-sustainability-scheme/) |
| Organisation Health Diagnostic Scheme | NCSS | community | [Official source](https://www.ncss.gov.sg/grants/organisation-development/organisation-health-diagnostic-scheme/) |
| Professional Capability Grant | NCSS | community | [Official source](https://www.ncss.gov.sg/grants/people-development/professional-capability-grant/) |
| Presentation and Participation Grant | NAC | community | [Official source](https://www.nac.gov.sg/support/funding-and-schemes/presentation-and-participation-grant/overview) |
| Capability Development Grant | NAC | community | [Official source](https://www.nac.gov.sg/support/funding-and-schemes/capability-development-grant/overview) |
| Competitive Research Programme | NRF | research | [Official source](https://www.nrf.gov.sg/grants/crp/) |
| NRF Fellowship | NRF | research | [Official source](https://www.nrf.gov.sg/grants/nrff/) |
| NRF Investigatorship | NRF | research | [Official source](https://www.nrf.gov.sg/grants/nrfi/) |
| Industry Alignment Fund – Industry Collaboration Projects | A*STAR | research | [Official source](https://www.a-star.edu.sg/research/funding-opportunities/iaf-icp) |

## Ingestion assets

- `data/official/catalogue.json`: the UI catalogue and its source-backed excerpts.
- `data/official/sources.json`: HTTP capture metadata, source hashes, and unavailable source notes.
- `data/official/raw/{scheme_id}.html`: exact policy snapshots for audit and reproducibility.
- `data/official/documents/{scheme_id}.md`: readable policy corpus with source metadata, verbatim excerpts and extracted main content. Upload this directory to the accelerator's private S3 document source.
- `data/official/structured/schemes.csv`: 20 programme records for a Glue/Athena data source.
- `data/official/structured/agencies.csv`: 10 agency records.
- `data/official/structured/evidence.csv`: 41 verbatim evidence records linked to programmes and agencies.
- `data/official/seeds.json`: reviewed public URLs, programme metadata and exact excerpt selectors.

The CSV join keys are `schemes.agency_id = agencies.agency_id`, `evidence.scheme_id = schemes.scheme_id`, and `evidence.agency_id = agencies.agency_id`. Every column is a string. Categories are separated by `|`. CSV values are single-line and quoted where necessary; configure Glue with `org.apache.hadoop.hive.serde2.OpenCSVSerde`, comma separator, quote character `"`, and `skip.header.line.count=1`. An ontology upload alone does not install source mappings. Scan the tables, review relationships, and accept source mappings before relying on structured semantic queries.

`schemes.csv` columns: `scheme_id,scheme_name,persona,categories,agency_id,status,summary,eligibility_text,benefit_text,application_url,source_url,source_title,fetched_at,source_hash`.

`agencies.csv` columns: `agency_id,agency_name,abbreviation,agency_url`.

`evidence.csv` columns: `evidence_id,scheme_id,agency_id,evidence_type,excerpt,source_url,source_title,fetched_at,source_hash`.

## Refresh and verification

Run from the repository root with Python 3.12:

```sh
python scripts/official_sources.py verify
python scripts/official_sources.py refresh
```

The script uses only the Python standard library, keeps the configured HTTPS proxy and CA trust, and checks official HTTPS hosts. It extracts visible policy content from the HTML main element and excludes scripts, navigation and styling. It does not execute page code or bypass challenge pages.

Refresh fetches all sources and verifies every reviewed excerpt before replacing the last complete snapshot. If an official page changes or becomes unavailable, refresh exits with the affected URL and preserves existing assets. Review the new public policy wording and update excerpt selectors in `seeds.json` before rerunning. A successful refresh produces a new dated capture; upload and rescan that version explicitly. This is a snapshot workflow, not continuous live synchronisation.

`export` regenerates JSON, Markdown and CSV from the current local raw snapshots after verifying their hashes:

```sh
python scripts/official_sources.py export
```

## Policy changes and scope

The live Enterprise Singapore pages state that **EDG, MRA and PSG ceased on 29 September 2026** and that new applications from 30 September use the **EDGE Grant**. This corpus uses EDGE rather than presenting the former schemes as open for new applications. Existing submissions and claims have distinct treatment described in the source. The NAC Presentation and Participation source also records changes affecting Production and Extended Play grants from April 2026. These lifecycle statements are preserved as separate evidence.

Overview pages are sometimes incomplete. For example, the NRF Competitive Research Programme overview directs readers to the Research Grants Portal and does not state complete applicant criteria; its `eligibilityText` is empty. The policy documents retain the source text and official portal link. Conditional subsidy tables, exceptions, funding rates, bank credit approval and open-call requirements are descriptive evidence. They are not converted into automatic eligibility rules.

HDB's Enhanced CPF Housing Grant page returned HTTP 403 from this environment. SupportGoWhere and IMDA pages returned application/loading shells without extractable policy content; ComCare information therefore comes from the administering MSF page. Our Singapore Fund returned HTTP 503. No criteria from those unavailable pages are included. See `sources.json` for exact attempted URLs and status notes. Housing grant coverage is therefore not claimed in this capture.

The UI should describe this as an independent Singapore support navigation demonstration, display official source links and capture dates, and direct applicants to agency assessment. Government crests and agency endorsement are not implied by the use of public source information.
