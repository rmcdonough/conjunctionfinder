# Infra — AWS deployment (CDK)

CDK v2 (TypeScript) app that provisions the whole deployed stack: a private
S3 bucket for the built frontend, the backend as a Lambda container image
behind an API Gateway HTTP API, and one CloudFront distribution in front of
both.

## Architecture

```
                         ┌─────────────────────────────┐
 Browser / calendar  ───▶│  CloudFront (default cert,   │
 client (HTTPS)          │  *.cloudfront.net, TLS 1.2+) │
                         └───────────┬──────────────────┘
                    path: /*         │         path: /api/*
                    (static site)    │         (dynamic API)
                         ▼                          ▼
              ┌─────────────────────┐   ┌───────────────────────────┐
              │  S3 bucket          │   │  API Gateway HTTP API     │
              │  (private, OAC-only)│   │  └─▶ Lambda (container    │
              │  frontend/dist/*    │   │        image, Mangum +    │
              └─────────────────────┘   │        FastAPI, pyswisseph│
                                          │        + .se1 + tzfinder)│
                                          └───────────────────────────┘
```

One distribution, two origins, one HTTPS URL — frontend and API are
same-origin from the browser's point of view in production, so CORS is not
load-bearing there (it stays configured for local dev, where the Vite dev
server and uvicorn genuinely are cross-origin).

No custom domain: CloudFront's own `*.cloudfront.net` name comes with a
free, already-attached default TLS certificate, satisfying the "HTTPS, no
personalized domain" requirement with zero extra ACM/Route53 resources.

## Deploying

From the repo root:

```bash
./deploy.sh
```

This does a **two-pass deploy** (see below for why) and prints the site URL
at the end. Every deploy after the very first one only strictly needs the
second pass, but the script always runs both for correctness — it's cheap
if nothing changed.

### Why two passes

The frontend bakes its backend URL in at build time (`VITE_API_BASE_URL`),
but that URL is the CloudFront domain name, which doesn't exist until
CloudFront is created. Chicken-and-egg, solved by:

1. **Pass 1**: `cdk deploy` stands up everything (S3, Lambda, API Gateway,
   CloudFront) using whatever's currently built in `frontend/dist/` — even
   if that's stale or a placeholder. Capture the CloudFront domain from the
   stack outputs.
2. Rebuild the frontend with `VITE_API_BASE_URL=https://<that domain>`.
3. **Pass 2**: `cdk deploy` again. `BucketDeployment` re-uploads the
   correctly-built frontend and automatically invalidates CloudFront's
   cache for the changed paths — no manual invalidation needed.

## Manual CDK commands

```bash
cd infra
npm install
npx cdk synth     # local only — renders the CloudFormation template
npx cdk diff       # read-only AWS call — shows what WOULD change
npx cdk deploy     # creates/updates real resources
npx cdk destroy    # tears down the stack
```

`cdk bootstrap` is a one-time per-account/region setup step (already done
for this project against `867709893868`/`ca-central-1`):

```bash
npx cdk bootstrap aws://<account-id>/<region>
```

## Tearing down

```bash
./destroy.sh
```

This runs `cdk destroy --force`. Because the S3 bucket was created with
`RemovalPolicy.DESTROY` and `autoDeleteObjects: true`, `cdk destroy` alone
is enough — no manual "empty the bucket first" step, which is a common CDK
footgun this stack deliberately avoids.

**Not cleaned up by `cdk destroy`:** the CDK-managed ECR repository that
holds the Lambda's container image assets. This repo (name starts with
`cdk-hnb659fds-container-assets-`) is shared across every CDK app deployed
into that account/region — it isn't part of this stack, and CDK doesn't
delete it on stack teardown. Old image versions inside it cost a small
amount of storage; check `aws ecr describe-repositories` /
`aws ecr list-images` if you want to clean those up manually.

## Rough cost expectations

At low/personal traffic, this whole stack should run to **a few cents to a
couple of dollars a month**:

- **S3**: storage for a ~200KB frontend bundle plus the background image —
  negligible.
- **Lambda + API Gateway HTTP API**: both bill per-request/per-duration with
  a generous free tier (1M free Lambda requests/month, 1M free HTTP API
  calls/month). Cost scales with real usage, same shape as any serverless
  API.
- **CloudFront**: the AWS Free Tier covers 1TB/month data transfer out and
  10M HTTP/HTTPS requests for a new account's first 12 months; modest
  per-GB/per-request cost after that or once the free tier expires.

The one thing that would meaningfully move this number is a real spike in
traffic driving Lambda invocation count and CloudFront egress up — there's
no fixed always-on cost anywhere in this stack (no NAT Gateway, no
provisioned concurrency, no RDS).

## Known limitations

- **First deploy needs both passes for real** (see above); every deploy
  after that only strictly needs pass 2, since the CloudFront domain
  doesn't change once created.
- **Cold starts.** First request after Lambda idles pays the cost of
  loading pyswisseph, the `.se1` ephemeris files, and timezonefinder's
  dataset. 1024MB memory / 30s timeout (matched from the project's old SAM
  scaffolding) should keep this well within a few seconds; provisioned
  concurrency would eliminate it entirely at an ongoing extra cost, not
  configured here.
- **No VPC.** Deliberate — Lambda has default internet egress without one
  (needed for the Nominatim geocoding calls in `backend/app/location.py`),
  and there's no private resource to reach that would justify a NAT
  Gateway's ~$32/month.
