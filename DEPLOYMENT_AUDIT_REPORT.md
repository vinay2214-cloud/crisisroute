# CrisisRoute Deployment Audit Report

This report documents the deployment audit findings, implemented fixes, remaining risk assessment, and the recommended production deployment sequence for the CrisisRoute emergency routing dashboard on Google Cloud Platform.

---

## 1. Summary of Changes

### Every File Changed:
1. **`deploy.sh`**:
   - Replaced outdated project ID `"crisisroute-2026"` with `"crisisroute-2026-498212"`.
2. **`frontend/deploy.sh`**:
   - Replaced outdated project ID `"crisisroute-2026"` with `"crisisroute-2026-498212"`.
   - Updated template `BACKEND_URL` comment to reference `498212` hash pattern.
3. **`.env`**:
   - Updated local `GOOGLE_CLOUD_PROJECT` configuration parameter to `"crisisroute-2026-498212"`.
4. **`agents/triage_agent.py`**:
   - Implemented a backwards-compatible Google Vertex AI / Application Default Credentials (ADC) fallback. If no `GEMINI_API_KEY` or `GOOGLE_API_KEY` is present in the environment, the client initializes using standard Google Cloud Service Account credentials targeting project `crisisroute-2026-498212` in region `us-central1`.
5. **`api/main.py`**:
   - Synced the `/health` endpoint Gemini verification logic with the triage agent client authentication logic to prevent false degradation warnings on startup in GCP.

---

## 2. Audit Findings & Issues Resolved

### Issue 1: Hardcoded Outdated Project ID
- **Discovery**: The project ID `crisisroute-2026` was hardcoded in `deploy.sh` (line 3), `frontend/deploy.sh` (line 4), and `.env` (line 8). The verified active Google Cloud Project ID is `crisisroute-2026-498212`.
- **Fix**: Updated all instances to `crisisroute-2026-498212`. Any builds and deployments triggered from these files will now target the correct GCP project.

### Issue 2: Developer-Specific API Key Dependencies
- **Discovery**: In the `google-genai` SDK, initializing `Client(api_key=api_key)` throws a `ValueError` if the keys are missing or evaluate to `None`. In production Cloud Run environments, it is insecure to store API keys in plain-text env variables. Instead, IAM-based Service Accounts should authenticate using Application Default Credentials (ADC) to call Vertex AI.
- **Fix**: Added dynamic authentication switching. The code checks for environment API keys; if they are not provided, it initializes using:
  ```python
  client = genai.Client(vertexai=True, project=project, location=location)
  ```
  This is backwards-compatible, allowing developers to continue using standard Gemini API keys locally while enabling secure passwordless IAM authentication in Google Cloud.

---

## 3. Remaining Deployment & Infrastructure Risks

### Risk 1: Secret Management
- **Description**: The Elasticsearch endpoints and keys are currently passed as raw environment variables.
- **Mitigation**: Before pushing to production, load `ELASTIC_API_KEY` and `ELASTIC_ENDPOINT` using GCP **Secret Manager**, mapping them to container environment variables at deploy time.

### Risk 2: GCP Service Account Permissions
- **Description**: In production, the Cloud Run instance runs under a service account. If this account lacks sufficient roles, Vertex AI requests will fail with `PermissionDenied`.
- **Mitigation**: Assign the **Vertex AI User** (`roles/aiplatform.user`) role to the Cloud Run runtime service account (usually the Compute Engine default service account `PROJECT_NUMBER-compute@developer.gserviceaccount.com` or a custom user-managed service account).

### Risk 3: Network Interdependency (Frontend & Backend URL)
- **Description**: The frontend static bundle is built with `VITE_API_URL` injected at build-time.
- **Mitigation**: You must deploy the backend service first, obtain its public URL, and then populate `BACKEND_URL` in `frontend/deploy.sh` before running the frontend deployment.

---

## 4. Exact Cloud Run Deployment Sequence

Follow this exact step-by-step sequence to deploy the entire CrisisRoute application to Google Cloud Run.

### Step 1: Set Up Authentication & Project
Ensure you are logged into your GCP account and have set the correct project target in your terminal:
```bash
# Authenticate with Google Cloud SDK
gcloud auth login

# Set the active project ID
gcloud config set project crisisroute-2026-498212
```

### Step 2: Enable Required GCP APIs
Enable APIs for Cloud Build, Cloud Run, Vertex AI, and Container Registry:
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  containerregistry.googleapis.com
```

### Step 3: Deploy the Backend Service
Run the backend deployment script. This builds the container image using `Dockerfile`, pushes it to Container Registry, and deploys it to Cloud Run.
```bash
# Ensure required production variables are set, or loaded from secret manager
export ELASTIC_ENDPOINT="https://your-elasticsearch-endpoint"
export ELASTIC_API_KEY="your-elasticsearch-api-key"

# Make the deploy script executable and run it
chmod +x deploy.sh
./deploy.sh
```
Observe the terminal output and note down the **Service URL** generated (e.g., `https://crisisroute-backend-498212-as.a.run.app`).

### Step 4: Configure Backend Service IAM Role
Authorize the Cloud Run default service account to call Vertex AI:
```bash
# Get the active project number
PROJECT_NUMBER=$(gcloud projects describe crisisroute-2026-498212 --format="value(projectNumber)")

# Grant Vertex AI User access to the default compute service account
gcloud projects add-iam-policy-binding crisisroute-2026-498212 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### Step 5: Test Backend Health Check
Verify the backend service is running and correctly connecting to Vertex AI and Elasticsearch:
```bash
# Replace with the actual URL from Step 3
curl https://crisisroute-backend-498212-as.a.run.app/health
```
You should receive a `200 OK` response with:
`{"status":"healthy","services":{"api":"ok","elasticsearch":"ok","gemini":"ok"}}`

### Step 6: Deploy the Frontend Service
Open `frontend/deploy.sh` and update `BACKEND_URL` with your actual backend service URL. Then deploy:
```bash
# Make the frontend deploy script executable and run it
cd frontend
chmod +x deploy.sh
./deploy.sh
```
Once complete, the script will output the public URL of the **CrisisRoute React Dashboard**.
