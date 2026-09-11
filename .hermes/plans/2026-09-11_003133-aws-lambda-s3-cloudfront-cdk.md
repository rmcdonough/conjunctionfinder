# Astrology Conjunction Finder — AWS Deployment Plan (Lambda + S3 + CloudFront, via CDK)

> **For Hermes:** This is a plan-only artifact. No AWS resources have been
> created and no files outside this plan have been touched while writing it.
> Execute task-by-task on explicit go-ahead; the last task (`cdk deploy`
> against the real account) needs a separate, explicit confirmation even
> after the rest is approved, since it spends real money on a live AWS
> account (867709893868, region to be chosen at deploy time — recommend
> `us-east-1` for lowest CloudFront/Lambda latency to most viewers, but any
> region works since nothing here is region-locked).

**Goal:** Stand up a serverless, HTTPS-only deployment of the existing app —
FastAPI backend on Lambda, React build on S3, one CloudFront distribution in
front of both — provisioned entirely by a CDK (TypeScript) app, driven by a
bash script that also builds the two npm projects involved (the frontend and
the CDK app itself).

**Architecture:**

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

One CloudFront distribution, two origins, one HTTPS URL. The frontend and API
become same-origin from the browser's point of view, so CORS stops being load-
bearing in production (it stays in place for local dev, where the Vite dev
server on :5173 still talks cross-origin to uvicorn on :8000, unchanged).

**Tech stack:** AWS CDK v2 (TypeScript, `aws-cdk-lib` 2.269.0 — already
resolvable via npm; installed CLI is 2.1141.0), Docker (for the Lambda
container image build — confirmed present: Docker 29.8.0), existing FastAPI/
Mangum backend and Vite/React frontend unchanged in logic.

---

## Key decisions and why

### 1. Lambda as a container image, not a zip

The backend's dependency set is native-code-heavy and large:

| Package | Why it's a problem for a zip deployment |
| --- | --- |
| `pyswisseph` | C extension; needs a manylinux wheel built for Lambda's exact runtime, not whatever the dev machine has |
| `numpy` | Pulled in by `timezonefinder`; also native, also needs manylinux |
| `h3` | Pulled in by `timezonefinder`; native |
| `timezonefinder` package data | The tz boundary dataset alone is ~49.5 MB compressed |
| `backend/ephe/*.se1` | ~2 MB, already committed, static data the app needs at runtime |

Zip-based Lambda deployments cap at **250 MB unzipped**. Between the compiled
extensions and the timezonefinder dataset, that's tight enough to be a real
risk, and getting the *correct* manylinux wheels without a build container
is its own fight. A **container image** Lambda (10 GB image size limit,
built via Docker against the official `public.ecr.aws/lambda/python:3.11`
base image) sidesteps both problems: `pip install` runs inside the exact
target environment, and the size ceiling is 40x higher than we need.

CDK supports this natively: `lambda.DockerImageFunction` +
`lambda.DockerImageCode.fromImageAsset(path)` runs `docker build` during
`cdk deploy` and pushes the result to an auto-created ECR repository. This
needs Docker running on whatever machine runs `cdk deploy` (present here).

### 2. One CloudFront distribution, two origins, no custom domain

CloudFront's default behavior (`/*`) origins on the S3 bucket (static
frontend); a second behavior (`/api/*`) origins on the API Gateway HTTP API
endpoint. Benefits:

- **One HTTPS URL for the whole site.** No custom domain needed — CloudFront
  issues every distribution a `*.cloudfront.net` name with a **free, default
  TLS certificate already attached**, satisfying "TLS protection, no
  personalized domain needed" with zero extra resources (no ACM certificate,
  no Route 53 hosted zone).
- **CORS becomes a non-issue in production.** Frontend and API are the same
  origin from the browser's perspective, so the existing `CORSMiddleware` in
  `backend/app/main.py` simply never gets exercised by the deployed app. It
  stays in the code unchanged — it's still what makes local dev work
  (`localhost:5173` → `localhost:8000` is genuinely cross-origin).
- The `.ics` **subscription feed is fetched directly by calendar clients**
  (Google Calendar's servers, Outlook's servers, etc.), not by a browser, so
  browser CORS never applies to it regardless of same-origin status — no
  special-casing needed there.

### 3. FastAPI's existing route prefix (`/api/...`) maps directly

Every route is already `/api/health`, `/api/natal-chart`, `/api/conjunctions`,
`/api/conjunctions.ics` (see `backend/app/main.py`). CloudFront's `/api/*`
behavior forwards to the HTTP API's default-stage endpoint with **no path
rewriting** — the Lambda sees exactly the same paths it already handles
locally. Nothing in `backend/app/` needs to change.

### 4. No VPC, no NAT Gateway

Lambda functions with no VPC configuration already have default internet
egress through AWS-managed networking — no VPC attachment, no NAT Gateway
needed for the outbound Nominatim geocoding calls in
`backend/app/location.py`. Attaching this Lambda to a VPC would be a pure
cost regression (NAT Gateway is ~$32/month alone) for zero benefit, since
there's no private resource (RDS, etc.) to reach. **Decision: leave the
Lambda un-VPC'd.**

### 5. Two-pass deploy, because the frontend needs to know its own API URL

The frontend calls the backend via `API_BASE_URL` (from `VITE_API_BASE_URL`,
baked in at `vite build` time — see `frontend/src/api.ts`). But the CloudFront
domain name doesn't exist until CloudFront is created, and the frontend
bundle needs the *domain* baked in before `cdk deploy` even starts (CDK
uploads whatever is already in `frontend/dist/` as an S3 asset at synth
time). This is a one-time chicken-and-egg, solved with two passes:

1. **Pass 1** (`cdk deploy`): stands up everything — S3, Lambda, API Gateway,
   CloudFront — using whatever's currently in `frontend/dist/` (even a stale
   or placeholder build; it'll be overwritten in pass 2). Capture the
   CloudFront domain from the stack outputs.
2. **Rebuild the frontend** with `VITE_API_BASE_URL=https://<that domain>`.
3. **Pass 2** (`cdk deploy` again): `BucketDeployment` re-uploads the new
   `frontend/dist/` and automatically invalidates the CloudFront cache for
   the changed files (it's handed the distribution and does this itself —
   see Task 5 below).

Every deploy *after* the first only needs pass 2 in practice (the CloudFront
domain doesn't change once created), but the bash wrapper always runs both
passes so it's correct unconditionally, including on a from-scratch deploy
to a fresh AWS account.

### 6. `ALLOWED_ORIGINS` wired to the CloudFront domain anyway

Even though production CORS isn't load-bearing (same-origin), the Lambda's
`ALLOWED_ORIGINS` env var gets set to `https://<cloudfront-domain>` rather
than left as the `localhost:5173` dev default, as defense-in-depth and so
direct API testing against the real endpoint behaves predictably. This is a
same-stack `addEnvironment()` call after the distribution is defined — not
a real circular dependency, since the distribution's domain doesn't depend
on anything the Lambda's environment variables affect.

---

## Repo layout after this work

```
astrology/
  backend/
    Dockerfile              NEW — builds the Lambda container image
    .dockerignore            NEW — keep .venv/__pycache__/tests out of the image
    app/                     unchanged
    ephe/                    unchanged (copied into the image)
    requirements.txt         unchanged
  frontend/
    (unchanged — VITE_API_BASE_URL is supplied at build time by deploy.sh,
     no source changes needed)
  infra/                     NEW — the CDK app
    package.json
    tsconfig.json
    cdk.json
    .gitignore               cdk.out/, node_modules/
    bin/
      astrology-infra.ts     CDK app entrypoint
    lib/
      astrology-stack.ts     the one stack: S3 + Lambda + HTTP API + CloudFront
    README.md                 what this deploys, how to tear it down, rough cost
  deploy.sh                  NEW — root-level bash wrapper (see Task 8)
  destroy.sh                 NEW — root-level teardown wrapper
```

Single stack, not split per-concern: there's no multi-account/multi-region
need here, and splitting S3/Lambda/CloudFront into separate stacks would only
add cross-stack reference ceremony for zero real benefit at this size.

---

## Step-by-step plan

### Task 1: Add the Lambda container image Dockerfile

**Objective:** A Dockerfile that builds a working Lambda container image for
the existing FastAPI app, using the official Lambda Python base image so
native wheels (`pyswisseph`, `numpy`, `h3`) build correctly.

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Dockerfile:**

```dockerfile
FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app ${LAMBDA_TASK_ROOT}/app
COPY ephe ${LAMBDA_TASK_ROOT}/ephe

# Matches backend/app/ephemeris.py's EPHE_PATH default resolution — set
# explicitly here since /var/task is where the base image lands our files.
ENV EPHE_PATH=${LAMBDA_TASK_ROOT}/ephe

CMD ["app.main.handler"]
```

**.dockerignore:**

```
.venv/
__pycache__/
*.pyc
tests/
.pytest_cache/
template.yaml
README.md
```

**Verification:**

```bash
cd backend
docker build -t astrology-backend-test .
```

Expected: build completes without error. Then a smoke test using the Lambda
Runtime Interface Emulator that ships in the base image:

```bash
docker run -d -p 9000:8080 --name astrology-smoke astrology-backend-test
sleep 2
curl -s -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"version":"2.0","routeKey":"GET /api/health","rawPath":"/api/health","requestContext":{"http":{"method":"GET","path":"/api/health"}}}'
docker rm -f astrology-smoke
```

Expected: a JSON body containing `"status":"ok"` (Mangum's HTTP-API-v2 event
shape wrapping the FastAPI response). This proves the image runs the app
correctly *before* any CDK/AWS involvement — cheapest possible place to catch
a packaging mistake.

**Commit:**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "infra: add Lambda container image Dockerfile for the backend"
```

---

### Task 2: Scaffold the CDK app

**Objective:** A minimal, empty CDK TypeScript app that synthesizes
successfully, before adding any real resources.

**Files:**
- Create: `infra/package.json`
- Create: `infra/tsconfig.json`
- Create: `infra/cdk.json`
- Create: `infra/.gitignore`
- Create: `infra/bin/astrology-infra.ts`
- Create: `infra/lib/astrology-stack.ts` (empty stack for now)

**infra/package.json:**

```json
{
  "name": "astrology-infra",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "build": "tsc",
    "synth": "cdk synth",
    "diff": "cdk diff",
    "deploy": "cdk deploy",
    "destroy": "cdk destroy"
  },
  "devDependencies": {
    "@types/node": "^24.0.0",
    "aws-cdk": "^2.1141.0",
    "typescript": "~5.6.0"
  },
  "dependencies": {
    "aws-cdk-lib": "^2.269.0",
    "constructs": "^10.4.0"
  }
}
```

**infra/tsconfig.json:**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "declaration": false,
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitThis": true,
    "alwaysStrict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": false,
    "inlineSourceMap": true,
    "inlineSources": true,
    "experimentalDecorators": true,
    "strictPropertyInitialization": false,
    "typeRoots": ["./node_modules/@types"]
  },
  "exclude": ["node_modules", "cdk.out"]
}
```

**infra/cdk.json:**

```json
{
  "app": "npx ts-node --prefer-ts-exts bin/astrology-infra.ts",
  "watch": {
    "include": ["**"],
    "exclude": ["README.md", "cdk*.json", "**/*.d.ts", "**/*.js", "node_modules"]
  },
  "context": {
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
    "@aws-cdk/core:checkSecretUsage": true,
    "@aws-cdk/core:target-partitions": ["aws"]
  }
}
```

(`ts-node` needs adding to devDependencies too — add
`"ts-node": "^10.9.0"`.)

**infra/.gitignore:**

```
node_modules/
cdk.out/
*.d.ts
*.js
!jest.config.js
```

**infra/bin/astrology-infra.ts:**

```typescript
#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AstrologyStack } from '../lib/astrology-stack';

const app = new cdk.App();
new AstrologyStack(app, 'AstrologyConjunctionFinder', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
```

**infra/lib/astrology-stack.ts** (placeholder, filled in over the next tasks):

```typescript
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

export class AstrologyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    // Resources added in subsequent tasks.
  }
}
```

**Verification:**

```bash
cd infra
npm install
npx cdk synth
```

Expected: prints an (almost empty) CloudFormation template with no errors.
This is the point to also run `cdk bootstrap` for the target
account/region if it hasn't been bootstrapped before:

```bash
npx cdk bootstrap aws://867709893868/us-east-1
```

(Safe to run even if already bootstrapped — it's idempotent.)

**Commit:**

```bash
git add infra/
git commit -m "infra: scaffold empty CDK TypeScript app"
```

---

### Task 3: S3 bucket + frontend deployment

**Objective:** A private S3 bucket holding the built frontend, with the
`BucketDeployment` construct wired up (upload happens on every `cdk deploy`).

**Files:** Modify `infra/lib/astrology-stack.ts`

```typescript
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as path from 'path';

// Inside the stack constructor:

const siteBucket = new s3.Bucket(this, 'FrontendBucket', {
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  removalPolicy: cdk.RemovalPolicy.DESTROY, // demo project — no retention need
  autoDeleteObjects: true,
  enforceSSL: true,
});
```

(The `BucketDeployment` itself is added in Task 5, once the CloudFront
`distribution` reference it needs for auto-invalidation exists — adding it
here first would need a forward reference to a resource defined later, which
CDK allows but is more confusing to read in one pass. Order in the plan
follows the cleanest reading order, not strict resource-creation order — CDK
resolves everything at synth time regardless of declaration order.)

**Verification:** `npx cdk synth` — expect an `AWS::S3::Bucket` resource in
the output template, no errors.

**Commit:**

```bash
git add infra/lib/astrology-stack.ts
git commit -m "infra: add private frontend S3 bucket"
```

---

### Task 4: Lambda (container image) + HTTP API

**Objective:** The backend running behind an API Gateway HTTP API.

**Files:** Modify `infra/lib/astrology-stack.ts`

```typescript
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as logs from 'aws-cdk-lib/aws-logs';

// Inside the stack constructor, after siteBucket:

const backendFn = new lambda.DockerImageFunction(this, 'BackendFunction', {
  code: lambda.DockerImageCode.fromImageAsset(
    path.join(__dirname, '..', '..', 'backend'),
  ),
  memorySize: 1024,
  timeout: cdk.Duration.seconds(30),
  architecture: lambda.Architecture.X86_64,
  environment: {
    // Placeholder; replaced with the real CloudFront domain once the
    // distribution exists (Task 6). Keeps local synth/diff runnable before
    // that resource is defined.
    ALLOWED_ORIGINS: 'http://localhost:5173,http://127.0.0.1:5173',
    GEOCODER_USER_AGENT: 'astrology-conjunction-finder/1.0',
  },
  logRetention: logs.RetentionDays.TWO_WEEKS,
});

const httpApi = new apigwv2.HttpApi(this, 'BackendApi', {
  defaultIntegration: new apigwv2Integrations.HttpLambdaIntegration(
    'BackendIntegration',
    backendFn,
  ),
});
```

`docker build` runs automatically here — the first `cdk synth`/`cdk diff`/
`cdk deploy` that touches this construct will build the image from
`backend/Dockerfile` (Task 1) and, for `deploy`, push it to an
auto-created ECR repository.

**Verification:**

```bash
cd infra
npx cdk synth
```

Expected: template now includes `AWS::Lambda::Function` (as
`AWS::Lambda::Function` with `PackageType: Image`), an ECR-asset reference,
and `AWS::ApiGatewayV2::Api` + `AWS::ApiGatewayV2::Integration` +
`AWS::ApiGatewayV2::Route` + `AWS::ApiGatewayV2::Stage` resources. This step
does invoke Docker locally (to compute the image's content hash for the
asset), so it'll take as long as `docker build` does — expect it to reuse
Task 1's build cache if that image is still around.

**Commit:**

```bash
git add infra/lib/astrology-stack.ts
git commit -m "infra: add backend Lambda (container image) + HTTP API"
```

---

### Task 5: CloudFront distribution (two origins) + finish S3 wiring

**Objective:** One distribution: `/api/*` → the HTTP API, everything else →
the S3 bucket (via Origin Access Control, no public bucket access). Then
attach `BucketDeployment` so every deploy actually uploads the frontend and
invalidates the right cache paths.

**Files:** Modify `infra/lib/astrology-stack.ts`

```typescript
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';

// Inside the stack constructor, after httpApi:

// HttpApi's generated domain, without the scheme — HttpOrigin wants a
// bare hostname. apiEndpoint looks like "https://abc123.execute-api.
// us-east-1.amazonaws.com"; defaultStage exists automatically (HttpApi
// creates one unless createDefaultStage: false is passed, which it wasn't).
const apiDomain = cdk.Fn.select(2, cdk.Fn.split('/', httpApi.apiEndpoint));

const distribution = new cloudfront.Distribution(this, 'SiteDistribution', {
  defaultRootObject: 'index.html',
  defaultBehavior: {
    origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
  },
  additionalBehaviors: {
    '/api/*': {
      origin: new origins.HttpOrigin(apiDomain, {
        protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
      }),
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
    },
  },
  // No `domainNames`/`certificate` props — this is exactly what makes
  // CloudFront issue its own *.cloudfront.net name with a free default
  // certificate. That satisfies "TLS, no custom domain" with zero extra
  // resources.
});

new s3deploy.BucketDeployment(this, 'FrontendDeployment', {
  sources: [s3deploy.Source.asset(path.join(__dirname, '..', '..', 'frontend', 'dist'))],
  destinationBucket: siteBucket,
  distribution,
  distributionPaths: ['/*'],
});
```

**Verification:**

```bash
cd infra
npx cdk synth
```

Expected: template now includes `AWS::CloudFront::Distribution` with two
cache behaviors, an `AWS::CloudFront::OriginAccessControl`, and the
`BucketDeployment`'s backing Lambda (a CDK-managed custom resource — this is
normal and expected, not something to hand-write).

**Note:** This step requires `frontend/dist/` to exist (even empty/stale) —
run `cd frontend && npm install && npm run build` at least once before this
`cdk synth`/`cdk deploy`, or the asset path will fail to resolve. The bash
wrapper (Task 8) handles this ordering automatically; doing it by hand while
iterating on the stack is just `npm run build` in `frontend/` first.

**Commit:**

```bash
git add infra/lib/astrology-stack.ts
git commit -m "infra: add CloudFront distribution with S3 + API origins"
```

---

### Task 6: Wire `ALLOWED_ORIGINS` to the real CloudFront domain, add outputs

**Objective:** Replace the Task 4 placeholder with the actual deployed
domain, and expose the values a human (or the bash script) needs after
deploy.

**Files:** Modify `infra/lib/astrology-stack.ts`

```typescript
// After `distribution` is defined:
backendFn.addEnvironment(
  'ALLOWED_ORIGINS',
  `https://${distribution.distributionDomainName}`,
);

new cdk.CfnOutput(this, 'SiteUrl', {
  value: `https://${distribution.distributionDomainName}`,
  description: 'Public HTTPS URL for the whole site (frontend + /api/*)',
});
new cdk.CfnOutput(this, 'ApiBaseUrl', {
  value: `https://${distribution.distributionDomainName}/api`,
  description: 'Value to bake into VITE_API_BASE_URL for the frontend build',
});
new cdk.CfnOutput(this, 'DistributionId', {
  value: distribution.distributionId,
  description: 'CloudFront distribution ID (for manual invalidations)',
});
new cdk.CfnOutput(this, 'BucketName', {
  value: siteBucket.bucketName,
  description: 'Frontend S3 bucket name',
});
```

**Verification:** `npx cdk synth` — outputs section of the template should
list all four; no errors from the `addEnvironment` call being "out of order"
relative to `distribution`'s declaration (confirmed fine per the reasoning in
"Key decisions #6" above — CDK resolves by reference, not by source order).

**Commit:**

```bash
git add infra/lib/astrology-stack.ts
git commit -m "infra: wire ALLOWED_ORIGINS to CloudFront domain, add outputs"
```

---

### Task 7: `infra/README.md`

**Objective:** Document what this deploys, rough cost, and how to tear it
down — so future-you (or the user) isn't guessing later.

**Files:** Create `infra/README.md`

Content to include:
- One-paragraph summary of the architecture (can lift from this plan's
  diagram).
- **Cost expectations**, stated honestly and approximately: at low/personal
  traffic, this is a few cents to a couple of dollars a month — S3 storage
  for a ~200KB frontend bundle + background image is negligible; Lambda and
  API Gateway HTTP API both bill per-request with a generous free tier;
  CloudFront's free tier covers 1TB/month egress and 10M requests for the
  first 12 months on a new account, modest cost after. The one thing that
  would meaningfully change this is heavy traffic driving Lambda invocation
  count up, which is the same cost shape as any serverless API.
- **How to deploy**: point at `deploy.sh` at the repo root (Task 8).
- **How to tear down**: point at `destroy.sh` (Task 9), and note that
  because `RemovalPolicy.DESTROY` + `autoDeleteObjects: true` were used on
  the S3 bucket, `cdk destroy` alone is sufficient — no manual bucket-empty
  step needed first (a common CDK footgun this plan deliberately avoids).
- **Known limitation**: the two-pass deploy (see "Key decisions #5") means a
  *first-ever* deploy to a fresh account takes two `cdk deploy` runs; every
  deploy after that only strictly needs the second pass, but the script
  always does both for correctness.

**Commit:**

```bash
git add infra/README.md
git commit -m "infra: document architecture, cost, and teardown"
```

---

### Task 8: `deploy.sh` — the bash wrapper

**Objective:** One command that takes a clean checkout to a fully deployed
site: installs both npm projects, builds the frontend twice (per the
two-pass plan), and runs `cdk deploy` twice.

**Files:** Create `deploy.sh` (repo root), `chmod +x deploy.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
FRONTEND_DIR="$REPO_ROOT/frontend"
OUTPUTS_FILE="$INFRA_DIR/cdk-outputs.json"

echo "==> Installing infra (CDK) dependencies"
( cd "$INFRA_DIR" && npm install )

echo "==> Installing frontend dependencies"
( cd "$FRONTEND_DIR" && npm install )

echo "==> Building frontend (pass 1 — placeholder API URL, needed so the S3 asset exists)"
( cd "$FRONTEND_DIR" && npm run build )

echo "==> cdk deploy (pass 1 — provisions S3 / Lambda / API Gateway / CloudFront)"
( cd "$INFRA_DIR" && npx cdk deploy --require-approval never --outputs-file "$OUTPUTS_FILE" )

API_BASE_URL="$(python3 -c "
import json
with open('$OUTPUTS_FILE') as f:
    outputs = json.load(f)
stack = next(iter(outputs.values()))
print(stack['ApiBaseUrl'])
")"
SITE_URL="$(python3 -c "
import json
with open('$OUTPUTS_FILE') as f:
    outputs = json.load(f)
stack = next(iter(outputs.values()))
print(stack['SiteUrl'])
")"

echo "==> Rebuilding frontend with the real API URL: $API_BASE_URL"
( cd "$FRONTEND_DIR" && VITE_API_BASE_URL="$API_BASE_URL" npm run build )

echo "==> cdk deploy (pass 2 — uploads the correctly-built frontend, invalidates CloudFront)"
( cd "$INFRA_DIR" && npx cdk deploy --require-approval never --outputs-file "$OUTPUTS_FILE" )

echo ""
echo "Deployed. Site: $SITE_URL"
echo "API base: $API_BASE_URL"
```

**Verification:** This is the task that actually touches the real AWS
account — see the "Task 10: go/no-go" gate below. Do not run this until that
gate is explicitly passed. Before then, the closest safe checks are:

```bash
bash -n deploy.sh   # syntax check only, no execution
```

**Commit:**

```bash
git add deploy.sh
git commit -m "infra: add deploy.sh bash wrapper for the two-pass deploy"
```

---

### Task 9: `destroy.sh` — teardown wrapper

**Objective:** Symmetric one-command teardown.

**Files:** Create `destroy.sh` (repo root), `chmod +x destroy.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$REPO_ROOT/infra"

echo "==> cdk destroy"
( cd "$INFRA_DIR" && npx cdk destroy --force )

echo "Torn down. The auto-created ECR repository for the Lambda image asset"
echo "may still hold old image versions — check 'aws ecr describe-repositories'"
echo "if you want those gone too; CDK does not currently auto-delete it."
```

**Note:** flagging the ECR repository explicitly because CDK's
`DockerImageCode.fromImageAsset` provisions a small "CDK asset" ECR repo per
environment (account+region) that isn't part of this stack and isn't deleted
by `cdk destroy` — it's shared across all CDK apps in that account/region.
Leaving it is harmless (tiny storage cost for a few images) but worth the
user knowing about rather than being surprised by later.

**Commit:**

```bash
git add destroy.sh
git commit -m "infra: add destroy.sh teardown wrapper"
```

---

### Task 10: Go/no-go gate — first real deploy

**This is not a code task — it's a decision point.**

Everything above can be built, `cdk synth`'d, and `cdk diff`'d against the
real account (both read-only / local-only operations — `cdk diff` does call
AWS to compare against the currently-deployed stack, but changes nothing)
without spending a cent or touching production infrastructure. Recommend
running, in order, before ever calling `deploy.sh` for real:

```bash
cd infra && npx cdk synth   # local only, validates the template builds
cd infra && npx cdk diff    # read-only AWS call, shows what WOULD be created
```

Only after reviewing that diff and getting explicit confirmation should
`./deploy.sh` be run for real. This spends real money (small, but real) and
creates real, billable, publicly-reachable infrastructure on account
`867709893868`.

**Post-deploy verification** (once confirmed and run):

```bash
# Health check through CloudFront
curl -s "$SITE_URL/api/health"
# Expect: {"status":"ok","allowed_origins":["https://<cloudfront-domain>"]}

# Real conjunction search through the deployed stack
curl -s -X POST "$SITE_URL/api/conjunctions" \
  -H "Content-Type: application/json" \
  -d '{"birth_date":"1976-03-13","birth_time":"19:18","birth_place":"Edmonton, Alberta, Canada","start_year":2026,"start_month":9,"end_year":2026,"end_month":9,"bodies":["moon"]}'
# Expect: HTTP 200, a real natal chart + events payload — same shape as the
# local backend already returns.

# Frontend loads over HTTPS
curl -s -o /dev/null -w "%{http_code}\n" "$SITE_URL/"
# Expect: 200

# .ics feed is publicly fetchable (no auth, as designed)
curl -s "$SITE_URL/api/conjunctions.ics?birth_date=1976-03-13&birth_time=19:18&latitude=53.5461&longitude=-113.4938" \
  | head -5
# Expect: BEGIN:VCALENDAR ...
```

Then open `$SITE_URL` in an actual browser and run one real search end to
end, exactly as already done for the local dev version, to confirm the
deployed frontend and backend agree.

---

## Files touched, summary

| File | Change |
| --- | --- |
| `backend/Dockerfile` | new |
| `backend/.dockerignore` | new |
| `infra/**` | new (whole CDK app) |
| `deploy.sh` | new |
| `destroy.sh` | new |
| `backend/app/*.py` | **unchanged** |
| `frontend/src/*` | **unchanged** — only a build-time env var differs between local and deployed |

## Risks / open questions

1. **Region choice.** Plan defaults to `us-east-1` in `bin/astrology-infra.ts`
   for lowest CloudFront-edge/Lambda coupling latency, but this is a one-line
   change if a different region (e.g. closer to Edmonton — `ca-central-1`)
   is preferred. CloudFront itself is global regardless of where the origin
   resources live.
2. **Cold starts.** First request after idle will pay Lambda container
   cold-start cost (loading pyswisseph + the .se1 files + timezonefinder's
   dataset). Existing `backend/template.yaml` already budgeted a 30s
   timeout and 1024MB memory for this reason; carried forward unchanged.
   Not addressed here: provisioned concurrency (an extra, ongoing cost) —
   worth revisiting only if cold-start latency turns out to matter for real
   usage patterns.
3. **Nominatim rate limits under real traffic.** Already flagged in the
   existing security audit — becomes more relevant once this is a public
   URL instead of localhost. Out of scope for *this* plan (infra), but worth
   a follow-up if usage grows.
4. **ECR asset repo lifecycle**, noted in Task 9 — not cleaned up by
   `cdk destroy`, shared across CDK apps in the account.
