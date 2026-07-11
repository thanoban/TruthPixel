# Cloud Run + Supabase Deployment

This is the trusted deployment path for the backend API:

- Container host: GCP Cloud Run
- Production database: Supabase Postgres via the Supavisor transaction pooler
- Backend auth: tenant API keys with an admin token for tenant/key issuance
- Dashboard auth: `NEXT_PUBLIC_API_KEY`, sent as `X-API-Key`

The image never includes `.env`; all runtime configuration is injected through Cloud Run
environment variables or secrets.

## One-Time GCP Setup

Run these commands once from a machine authenticated with `gcloud` to the target project.

```bash
PROJECT_ID=<your-gcp-project-id>
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
REGION=us-central1
REPO=truthpixel
SA_NAME=truthpixel-deployer
GITHUB_REPO=thanoban/TruthPixel

gcloud services enable artifactregistry.googleapis.com run.googleapis.com iamcredentials.googleapis.com --project="$PROJECT_ID"
gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" --project="$PROJECT_ID"
gcloud iam service-accounts create "$SA_NAME" --project="$PROJECT_ID"

for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="$ROLE"
done

gcloud iam workload-identity-pools create github-pool --project="$PROJECT_ID" --location=global
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project="$PROJECT_ID" --location=global --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'"

gcloud iam service-accounts add-iam-policy-binding \
  "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GITHUB_REPO}"
```

Add these GitHub Actions repository secrets:

```text
GCP_PROJECT_ID=<your-gcp-project-id>
GCP_REGION=us-central1
GCP_ARTIFACT_REPO=truthpixel
CLOUD_RUN_SERVICE_NAME=truthpixel-backend
GCP_WORKLOAD_IDENTITY_PROVIDER=projects/<project-number>/locations/global/workloadIdentityPools/github-pool/providers/github-provider
GCP_SERVICE_ACCOUNT=truthpixel-deployer@<your-gcp-project-id>.iam.gserviceaccount.com
```

The workflow still builds and publishes to GitHub Container Registry when these secrets are
missing. The Cloud Run deploy steps run only when all six are configured.

## Supabase Setup

Create a Supabase project and use the transaction pooler connection string, not the direct
Postgres connection. The backend uses SQLAlchemy with psycopg3, so the URL must use this
driver prefix:

```text
postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

The important pieces are:

- `postgresql+psycopg://`, because `backend/requirements.txt` installs `psycopg[binary]`.
- Port `6543`, because Cloud Run can create many container instances and the pooler protects
  the database from connection spikes.
- `sslmode=require`, because Supabase requires TLS.

No manual schema SQL is required. `backend/app/storage/repository.py::init_db()` runs Alembic
`upgrade head` on startup against the configured `DATABASE_URL`.

## Cloud Run Runtime Variables

Minimum production variables:

```text
APP_ENV=production
DATABASE_URL=postgresql+psycopg://...
API_AUTH_ENABLED=true
ADMIN_API_TOKEN=<strong random token>
ARTIFACT_ACCESS_TOKEN_SECRET=<strong random token>
PUBLIC_SUBMISSION_ENABLED=false
CORS_ALLOW_ORIGINS=https://<dashboard-origin>,https://<webapp-origin>
CELERY_TASK_ALWAYS_EAGER=true
```

Storage variables:

```text
STORAGE_BACKEND=s3
S3_ENDPOINT=<s3-compatible-endpoint>
S3_ACCESS_KEY=<access-key>
S3_SECRET_KEY=<secret-key>
S3_BUCKET=<bucket-name>
S3_REGION=<region>
```

`STORAGE_BACKEND=local` is acceptable only for a throwaway smoke test. Cloud Run container
storage is ephemeral, so local artifacts disappear on restart or redeploy.

Optional model and API variables:

```text
L1_MODEL_PATH=./models/l1_clip_head.pt
HF_API_TOKEN=<hugging-face-token>
L2_TRUFOR_REPO_DIR=
L2_TRUFOR_MODEL_FILE=
GOOGLE_CLOUD_PROJECT=<gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
SIGHTENGINE_API_USER=
SIGHTENGINE_API_SECRET=
FUSION_MODEL_PATH=
```

Leave optional model/API variables unset until the corresponding artifacts or credentials
exist. The backend has fallback paths for unconfigured L1, L2, L3, and Vertex agents.

## Dashboard Runtime Variables

The dashboard is a thin client over the backend API.

```text
NEXT_PUBLIC_API_URL=https://<cloud-run-service-url>
NEXT_PUBLIC_API_KEY=<tenant-api-key-issued-by-backend>
```

Issue the tenant key after the backend is deployed:

```bash
API_URL=https://<cloud-run-service-url>
ADMIN_TOKEN=<ADMIN_API_TOKEN>

curl -sS -X POST "$API_URL/v1/admin/tenants" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"name":"Pilot Tenant","slug":"pilot-tenant"}'

curl -sS -X POST "$API_URL/v1/admin/tenants/pilot-tenant/api-keys" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"name":"dashboard"}'
```

Use the returned `api_key` as `NEXT_PUBLIC_API_KEY` for the dashboard deployment.

Artifact previews in the dashboard use short-lived signed URLs. The dashboard first calls the
protected API with `NEXT_PUBLIC_API_KEY`; the backend returns an expiring artifact URL that can
be used by browser `<img>` and download links without putting the tenant API key in the URL.

## Smoke-Test Checklist

Run this after a Cloud Run deploy. It proves auth-on behavior, tenant issuance, keyed claim
submission, reviewer flow, and artifact access.

```bash
API_URL=https://<cloud-run-service-url>
ADMIN_TOKEN=<ADMIN_API_TOKEN>

curl -i "$API_URL/health"

curl -i "$API_URL/v1/claims"
# Expect: 401 API key required

curl -sS -X POST "$API_URL/v1/admin/tenants" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"name":"Smoke Tenant","slug":"smoke-tenant"}'

KEY=$(curl -sS -X POST "$API_URL/v1/admin/tenants/smoke-tenant/api-keys" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"name":"smoke"}' | python -c "import json,sys; print(json.load(sys.stdin)['api_key'])")

curl -i "$API_URL/v1/claims" -H "X-API-Key: $KEY"
# Expect: 200 []

CLAIM_ID=$(curl -sS -X POST "$API_URL/v1/claims" \
  -H "X-API-Key: $KEY" \
  -F "image=@sample.jpg" \
  -F "order_id=SMOKE-1" \
  -F "product_sku=SKU-SMOKE" \
  -F "claim_reason=deployment smoke" | python -c "import json,sys; print(json.load(sys.stdin)['claim_id'])")

curl -i "$API_URL/v1/claims/$CLAIM_ID" -H "X-API-Key: $KEY"
curl -i "$API_URL/v1/claims/$CLAIM_ID/status" -H "X-API-Key: $KEY"
curl -i "$API_URL/v1/claims/$CLAIM_ID/audit" -H "X-API-Key: $KEY"

curl -i -X POST "$API_URL/v1/claims/$CLAIM_ID/decision" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"reviewer_id":"smoke-reviewer","decision":"reject","reason":"deployment smoke"}'
```

For the dashboard smoke, deploy/build it with:

```text
NEXT_PUBLIC_API_URL=$API_URL
NEXT_PUBLIC_API_KEY=$KEY
```

Then open the dashboard and verify the queue loads, the smoke claim detail opens, and the
decision/audit views still use the same tenant key.
