# utahai-chatbot-api

A minimal Flask backend to power a chatbot on Google Cloud Run using Vertex AI Search (Discovery Engine).

Endpoints:
- GET /health — simple health check
- POST /chat — JSON body: { "query": string, "session_id"?: string }

Configuration (environment variables):
- PROJECT_ID (default: utahai)
- LOCATION (default: global) — must be "global" for Vertex AI Search
- DATA_STORE_ID (default: utahai-knowledge-base_1759607726769)
- MODEL_ID (default: gemini-1.5-pro-preview-0409)

Note on DATA_STORE_ID: You can pass either the full data store ID (which often includes a numeric suffix like `_1759607726769`) or a shorter prefix/display name (e.g., `utahai-knowledge-base`). The API will automatically resolve the correct ID at runtime. To disable this behavior, set `AUTO_RESOLVE_DATASTORE=false`. You can verify both the configured and effective IDs by calling GET / or GET /setup/check.

## How to chat with the documents in your storage bucket (TL;DR)

1) Connect your GCS bucket to a Vertex AI Search (Discovery Engine) data store in the global location:
   - Console → Vertex AI Search (Discovery Engine)
   - Create or open a Data store (Type: Unstructured)
   - Add Data source → Cloud Storage → point to gs://YOUR_BUCKET/PREFIX
   - Run the initial sync and wait for indexing to complete

2) Deploy this API to Cloud Run with the correct environment variables so it points at your data store:

   gcloud run deploy utahai-chatbot-api \
     --source . \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars "PROJECT_ID=utahai,LOCATION=global,DATA_STORE_ID=<YOUR_DATASTORE_ID_OR_NAME>"

   Or use the helper script on Windows PowerShell:

   ./scripts/deploy.ps1 -ProjectId utahai -Region us-central1 -Service utahai-chatbot-api -Location global -DataStoreId <YOUR_DATASTORE_ID_OR_NAME>

3) Ask questions via POST /chat:

   - curl:

     curl -X POST "https://YOUR_SERVICE_URL/chat" \
       -H "Content-Type: application/json" \
       -d '{"query": "What does the policy say about refunds?", "session_id": "user1"}'

   - PowerShell:

     ./scripts/test-chat.ps1 -Url https://YOUR_SERVICE_URL -Query "What does the policy say about refunds?" -SessionId user1

Notes:
- If you get a fallback answer, ensure the Discovery Engine API is enabled and that your Cloud Run service account has roles/discoveryengine.searchUser.
- The response includes an "answer" synthesized from snippets and a "results" array with titles and source URIs.
- For full details, see the "End-to-End: Deploy and chat with documents in your Cloud Storage bucket" section below.

## How to launch the chat UI locally

Option A — One command (starts API + Web UI in two terminals and opens your browser):

    ./scripts/launch.ps1 -ProjectId utahai -Location global -DataStoreId <YOUR_DATASTORE_ID_OR_NAME>

- What it does: starts the backend on http://localhost:8080 and the React Web UI on http://localhost:5173.
- The launcher sets VITE_API_URL automatically so the UI talks to the local API.
- Optional flags:
  - -BackendPort 8080 (default 8080)
  - -WebPort 5173 (default 5173)
  - -NoBrowser (don’t auto-open the browser)

Option B — Manual (run API and Web UI yourself in two terminals):

1) Backend (terminal 1, project root):

    $env:PROJECT_ID = "utahai"; $env:LOCATION = "global"; $env:DATA_STORE_ID = "<YOUR_DATASTORE_ID_OR_NAME>"; $env:PORT = "8080"; python .\main.py

2) Web UI (terminal 2, project root):

    cd .\web
    if (!(Test-Path node_modules)) { npm install }
    $env:VITE_API_URL = "http://localhost:8080"
    $env:PORT = "5173"
    npm run dev

Verify quickly:
- Visit: http://localhost:8080/setup/check
- Expected: { status: "ok", ... } when Vertex AI Search is reachable with the configured PROJECT_ID/LOCATION/DATA_STORE_ID.
- Then open the chat UI at: http://localhost:5173
- If you see an error, ensure the Discovery Engine API is enabled and your credentials/roles are correct (see troubleshooting below).

## Local development

1. Python 3.11 recommended.
2. Create a virtual env and install deps:

   pip install -r requirements.txt

3. Run the app:

   python main.py

The service listens on http://localhost:8080 by default.

## Deploy to Cloud Run

Prereqs:
- gcloud CLI installed and authenticated (gcloud auth login)
- Set the target project: gcloud config set project utahai

Why we can’t run gcloud for you here:
- This repo and its automation do not have access to your Google Cloud credentials or project.
- Please run the deploy from your own terminal (Cloud Shell/macOS/Linux) or use the Windows PowerShell helper script below.

Deploy using Cloud Build from source (uses the provided Dockerfile). Bash/Cloud Shell example:

  gcloud run deploy utahai-chatbot-api \
    --source . \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars "PROJECT_ID=utahai,LOCATION=global,DATA_STORE_ID=<YOUR_DATASTORE_ID_OR_NAME>"

On Windows PowerShell, use the helper script:

  ./scripts/deploy.ps1 -ProjectId utahai -Region us-central1 -Service utahai-chatbot-api -Location global -DataStoreId <YOUR_DATASTORE_ID_OR_NAME>

Upon success, the command prints the service URL.

If you prefer building locally and deploying the image, ensure the container listens on $PORT (already configured) and use:

  gcloud builds submit --tag gcr.io/utahai/utahai-chatbot-api
  gcloud run deploy utahai-chatbot-api --image gcr.io/utahai/utahai-chatbot-api --region us-central1 --allow-unauthenticated

## Notes
- The /chat endpoint attempts to use Vertex AI Search via google-cloud-discoveryengine v1alpha. If the SDK or credentials are missing, it returns a graceful fallback message instead of failing.
- Ensure your Discovery Engine data store exists and is in the global location. The full path will look like:
  projects/utahai/locations/global/collections/default_collection/dataStores/<YOUR_DATASTORE_ID> (e.g., utahai-knowledge-base_1234567890123)
- Assign appropriate IAM roles (Discovery Engine User) to the runtime service account if you disable --allow-unauthenticated and secure the endpoint.


---   

# End-to-End: Deploy and chat with documents in your Cloud Storage bucket

This section shows, step by step, how to deploy the API and hook it up to your documents in a Google Cloud Storage (GCS) bucket using Vertex AI Search (Discovery Engine).

Important: Vertex AI Search requires LOCATION=global. The code and examples below assume that.

## 0) Prerequisites
- Billing enabled on your project (utahai).
- You have Owner/Editor rights or the ability to grant roles.
- gcloud CLI installed and authenticated:
  - gcloud auth login
  - gcloud config set project utahai
- Enable required services:

  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    discoveryengine.googleapis.com

## 1) Prepare your data store and connect your GCS bucket
You only need to do this once per data store. Use the Google Cloud Console (recommended):

1. Go to Google Cloud Console → Vertex AI Search (Discovery Engine).
2. Make sure the location selector is set to global.
3. Create a Data store:
   - Type: Unstructured data (recommended for most docs like PDF, HTML, text).
   - Name: utahai-knowledge-base (or choose your own).
4. Add a Data source:
   - Choose Cloud Storage connector.
   - Point it to your bucket or a folder prefix, for example: gs://YOUR_BUCKET_NAME/docs/
   - Optionally schedule periodic syncs; run the initial sync now.
5. Wait for the sync and indexing to complete (initially may take minutes). You can monitor progress in the same UI under Data sources.
6. Test in the built-in Search testing UI for this data store to ensure documents are searchable.

Note the data store ID you created. In the console it often appears with a numeric suffix, e.g., `utahai-knowledge-base_1759607726769`. This API accepts either the full ID, the shorter prefix (e.g., `utahai-knowledge-base`), or the display name and will resolve it automatically. You pass this via the DATA_STORE_ID environment variable.

## 2) Deploy the API to Cloud Run
From this repository folder:

- Quick one-command deploy (Windows PowerShell):

  ./scripts/deploy.ps1 -ProjectId utahai -Region us-central1 -Service utahai-chatbot-api -Location global -DataStoreId <YOUR_DATASTORE_ID_OR_NAME>

- Or run the gcloud command directly:

  gcloud run deploy utahai-chatbot-api \
    --source . \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars "PROJECT_ID=utahai,LOCATION=global,DATA_STORE_ID=<YOUR_DATASTORE_ID_OR_NAME>"

When the deploy finishes, copy the service URL it prints, e.g. https://utahai-chatbot-api-xxxxxx-uc.a.run.app

## 3) Chat with your documents
Use the /chat endpoint. Provide your question in the query field and optionally a session_id.

- PowerShell:

  ./scripts/test-chat.ps1 -Url https://YOUR_SERVICE_URL -Query "What does the policy say about refunds?" -SessionId user1

- curl:

  curl -X POST "https://YOUR_SERVICE_URL/chat" \
    -H "Content-Type: application/json" \
    -d '{"query": "What does the policy say about refunds?", "session_id": "user1"}'

The response includes an answer synthesized from the top snippets and a results array with titles/URIs.

## 4) Securing access (optional)
The examples above expose the service publicly using --allow-unauthenticated. To restrict access:
- Omit --allow-unauthenticated when deploying.
- Grant the Cloud Run Invoker role (roles/run.invoker) to the identities that should call the API.
- From clients, use an Identity Token (ID token) when calling the service.

## 5) IAM for Discovery Engine
Make sure the Cloud Run runtime service account (often PROJECT_NUMBER-compute@developer.gserviceaccount.com or the one you choose) has permission to call Vertex AI Search:
- roles/discoveryengine.searchUser — minimum for search.
- If you plan to manage ingestion programmatically from this service, additional roles may be needed, but for searching only, searchUser suffices.

## 6) Troubleshooting
- 404/empty results: Confirm your data store is in the global location and that indexing has finished. The API auto-resolves DATA_STORE_ID from prefixes/display names; call GET / to see the effective ID it resolved to. If it still fails, verify IAM and that the service account can access that data store.
- 403 permission denied from Vertex AI Search: Ensure the Cloud Run service account has roles/discoveryengine.searchUser and that the Discovery Engine API is enabled.
- Fallback answer in the response: This means the server couldn’t reach Vertex AI Search (missing credentials locally or API misconfiguration). In Cloud Run with correct IAM and API enablement, this should return real results.
- CORS errors in a browser: CORS is enabled by default in this API. If you need to restrict origins, swap the wildcard in CORS(app, ...) for specific allowed domains.

## 7) Environment variables reference
- PROJECT_ID: Your GCP project ID (e.g., utahai)
- LOCATION: Must be global for Vertex AI Search
- DATA_STORE_ID: Prefer the full data store ID (e.g., utahai-knowledge-base_1234567890123), but you may also pass the prefix or display name; the API will auto-resolve to the exact ID.
- AUTO_RESOLVE_DATASTORE: true/false (default: true). If enabled, resolves DATA_STORE_ID from a prefix or display name to the full ID. Disable if you want to use the ID exactly as provided.
- MODEL_ID: Reserved for future use (Gemini-based answer generation); the current implementation uses SearchService with snippets

That’s it — deploy, connect the bucket via Vertex AI Search, and start chatting with your documents!


---

## No curl required: React Chat UI (local and Cloud Run)

If you prefer a UI over curl/PowerShell, use the included React app.

Quick start (local):
- Prereqs: Node.js 18+ and Python 3.11+.
- Start the backend in one terminal:

      python main.py

- Start the web UI in another terminal (PowerShell):

      ./scripts/start-web.ps1

- Open http://localhost:5173 and chat. The UI calls the backend at http://localhost:8080 by default.

Pointing the UI at your Cloud Run backend:
- Copy web/.env.example to web/.env and set VITE_API_URL to your Cloud Run service URL, e.g.:

      VITE_API_URL=https://utahai-chatbot-api-xxxxxx-uc.a.run.app

- Then start the UI again with ./scripts/start-web.ps1 (or build with npm run build).

Build for production (optional):
- From the web folder:

      npm install
      npm run build

- This produces web/dist which you can host on your preferred static site host (Cloud Storage website hosting, Firebase Hosting, Vercel, Netlify, etc.). Set VITE_API_URL to point at your backend.

Notes:
- CORS is already enabled on the backend, so the web app can call it directly from localhost or a hosted domain. For stricter origins, adjust CORS(app, ...) in main.py.
- This UI works with your Vertex AI Search data store that is connected to your GCS bucket (see the earlier section for how to connect/sync documents). We cannot enumerate your project buckets from here; as long as your data store is correctly connected and indexed, the chatbot will retrieve and cite those documents.


---

## Deploy the Web UI to a public URL (Google Cloud Storage)

You can host the React chat UI as a static site on Google Cloud Storage and point it at your Cloud Run API.

Prereqs:
- gcloud CLI installed and authenticated: gcloud auth login
- A globally-unique bucket name you control, e.g., my-utahai-chat

Steps:
1) Deploy the API and get its URL (if you haven’t already):

   ./scripts/deploy.ps1 -ProjectId utahai -Region us-central1 -Service utahai-chatbot-api -Location global -DataStoreId <YOUR_DATASTORE_ID_OR_NAME>

   Note the printed Service URL, e.g., https://utahai-chatbot-api-xxxxxx-uc.a.run.app

2) Build and deploy the Web UI to Cloud Storage, pointing it to your API URL:

   ./scripts/deploy-web.ps1 -Bucket <YOUR_STATIC_BUCKET> -ApiUrl https://YOUR_SERVICE_URL

This script will:
- Build the production bundle with VITE_API_URL set to your Cloud Run API
- Create the bucket if it doesn’t exist, enable public read (unless -NoPublic is used),
  configure the website main page, and upload the files
- Print the final website URL (for example: https://storage.googleapis.com/YOUR_STATIC_BUCKET/index.html)

Notes:
- If you prefer to keep the bucket private, pass -NoPublic and serve it behind a CDN or use signed URLs.
- Any static host will work (Firebase Hosting, Cloud Run static, Vercel, Netlify). Just ensure VITE_API_URL points at your API.
- CORS is already enabled on the backend. If you need to restrict origins, edit CORS(app, ...) in main.py.


---

## Optional: Direct RAG over your GCS bucket using Pinecone (no Discovery Engine required)

This repository now includes an optional Retrieval-Augmented Generation (RAG) path that lets the chatbot read files directly from a Google Cloud Storage (GCS) bucket, index them into a Pinecone vector database, and answer questions grounded in those files.

Key endpoints:
- POST /ingest/gcs — Index text-like files from your GCS bucket into Pinecone
- POST /chat/rag — Ask questions that retrieve from Pinecone and synthesize an answer with Gemini

When to use this:
- You want fast, incremental control of indexing specific objects from a bucket
- You prefer Pinecone for vector search
- You may not want to set up Vertex AI Search (Discovery Engine) yet, or you want both options side-by-side

Environment variables (in addition to the ones above):
- GOOGLE_API_KEY: API key for Google Generative AI (Gemini + Embeddings)
- PINECONE_API_KEY: Pinecone API key
- PINECONE_INDEX_NAME (default: utahai-files)
- PINECONE_CLOUD (default: aws) and PINECONE_REGION (default: us-east-1) used for creating a serverless index if missing
- EMBED_MODEL (default: text-embedding-004) and EMBED_DIM (default: 768)
- RAG_MODEL (default: gemini-1.5-flash)
- GCS_BUCKET_NAME: exact bucket name (preferred)
- GCS_BUCKET_HINT (default: "gchat utahai bucket 1"): fuzzy hint to auto-resolve a bucket name if GCS_BUCKET_NAME is unset
- GCS_PATH_PREFIX: optional folder/prefix inside the bucket
- GCS_ALLOWED_EXTS (default: txt,md,log,csv,json,html)
- GCS_MAX_FILE_SIZE_MB (default: 5)

Google Cloud credentials for GCS:
- Locally, set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON file with storage.objects.get/list on the target bucket.
- In Cloud Run/GKE/Compute Engine, rely on Application Default Credentials (ADC) via the runtime service account.

Install dependencies (local dev):

  pip install -r requirements.txt

Ingest from your bucket (dry-run first):

  curl -X POST "http://localhost:8080/ingest/gcs" \
    -H "Content-Type: application/json" \
    -d '{
      "hint": "gchat utahai bucket 1",
      "prefix": "",
      "dry_run": true,
      "max_files": 10
    }'

If the response shows the right files, run actual ingestion (removes dry_run):

  curl -X POST "http://localhost:8080/ingest/gcs" \
    -H "Content-Type: application/json" \
    -d '{
      "hint": "gchat utahai bucket 1",
      "prefix": "",
      "dry_run": false
    }'

Ask questions over your indexed files:

  curl -X POST "http://localhost:8080/chat/rag" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Summarize the main points in the project notes",
      "top_k": 5
    }'

Notes and limitations:
- The GCS ingestion path indexes text-like files by extension filter. PDFs/Docs aren’t parsed here; to index those, convert to text first or continue using Vertex AI Search which supports rich doc parsing.
- Each Pinecone record stores a text chunk (truncated to ~1800 chars) and metadata including the GCS source URI. Metadata size limits apply.
- Error handling is best-effort; the API returns a list of errors in the ingestion result if any items failed.
- You can safely use both /chat and /chat/rag in the same deployment. /chat uses Vertex AI Search; /chat/rag uses Pinecone.


---

## Agentic RAG and multimodal messaging (new)

This API now supports an agentic RAG flow and multimodal inputs (images/audio/video) when using Gemini.

New endpoints:
- POST /chat/rag — now accepts optional attachments to include media in the prompt
- POST /chat/agentic — planner–executor loop with simple tools and citations

Multimodal attachments
- Request body field: attachments (array)
- Each attachment may be either a GCS URI or an HTTP URL:
  - { "gcs_uri": "gs://YOUR_BUCKET/path/to/image.png", "mime"?: "image/png" }
  - { "url": "https://example.com/image.jpg" }
- Only image/*, audio/*, and video/* are passed to the model; others are ignored.
- Size limits (configurable via env):
  - GCS_MEDIA_MAX_FILE_SIZE_MB (default: 15)
  - HTTP_MEDIA_MAX_FILE_SIZE_MB (default: 15)

Example — RAG with image context:

  curl -X POST "http://localhost:8080/chat/rag" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Summarize the notes and interpret the chart",
      "top_k": 5,
      "attachments": [
        {"gcs_uri": "gs://utahai_bucket-1/plots/weekly.png"}
      ]
    }'

Agentic RAG (/chat/agentic)
- The agent plans up to max_steps (default 3) with a limited set of tools:
  - vector_retrieve: query Pinecone over your GCS-ingested chunks
  - vertex_search: query Vertex AI Search (Discovery Engine)
  - read_gcs_object: fetch and read a text object from GCS
  - rng: generate a random integer (demonstrates tool use; can be handy for sampling)
- The agent returns a final answer with citations and a trace of steps.

Example — Agentic query with media:

  curl -X POST "http://localhost:8080/chat/agentic" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "What are the key takeaways from the roadmap? If not enough context, look up more.",
      "top_k": 5,
      "max_steps": 3,
      "attachments": [
        {"url": "https://example.com/diagram.png"}
      ]
    }'

Notes
- All multimodal and agentic features are optional. If GOOGLE_API_KEY is not set or libraries are missing, the API falls back gracefully.
- Ensure your service account has read access to the GCS objects you attach (for private buckets). For public files, HTTP URLs work without credentials.
- Attachments are not stored; they are fetched at request time and streamed to the model.
