# Smart Pantry Recipe Concierge

A conversational AI agent built with Google Agent Development Kit (ADK) that acts as a personalized culinary assistant, helping home cooks manage pantry inventory, find recipes, analyze nutritional macros, generate dish photos/videos, and locate nearby grocery stores.

![Smart Pantry Agent Demo](./demo.gif)

---

## Implemented Features & Architecture

This repository contains the complete implementation for the **Smart Pantry Recipe Concierge**. All listed features are implemented and wired in [`app/agent.py`](file:///config/.gemini/antigravity/scratch/build-with-gemini/smart-pantry/app/agent.py) and [`agents-cli-manifest.yaml`](file:///config/.gemini/antigravity/scratch/build-with-gemini/smart-pantry/agents-cli-manifest.yaml):

* **Long-Term Memory Bank (`VertexAiMemoryBankService`)**: Persists user food preferences, dietary restrictions, and allergies across sessions using Vertex AI Memory Bank.
* **Firestore Recipe Database (`firestore.Client`)**: Stores and retrieves custom user recipes from Google Cloud Firestore.
* **External Recipe Discovery**: Searches public recipe collections using TheMealDB API (`fetch_external_recipes`).
* **Vertex AI Image Generation (`gemini-3.1-flash-lite-image`)**: Generates dish presentation photography in the `global` region, saving artifacts to the ADK Playground and uploading to Google Cloud Storage.
* **Vertex AI Video Generation (`gemini-omni-flash-preview`)**: Generates short cooking demonstration videos using Google's Omni model in the `global` region via the Interactions API (`generate_dish_video`), uploading directly to Cloud Storage.
* **Google Cloud Storage (GCS)**: Stores generated media assets in a public GCS bucket (`smart-pantry-images-qwiklabs-gcp-02-075769363a76`).
* **Agent Engine Code Execution Sandbox (`AgentEngineSandboxCodeExecutor`)**: Safely executes Python code in a sandboxed environment to calculate nutritional macro distributions and scale recipe portions.
* **Google Maps Geocoding & Places APIs**: Converts addresses into geographic coordinates (`geocode_address`) and locates nearby specialty grocery stores (`find_nearby_places`).
* **A2UI Rich UI Components (`a2ui-agent-sdk`)**: Formats agent responses into structured A2UI v0.8 cards rendered inline by compatible web UI clients.
* **A2A Protocol & Fast API Proxy**: Exposes the agent over the A2A protocol and serves a web chat interface through a FastAPI proxy (`frontend/main.py`).

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── agent.py          # Root agent configuration, tools, memory, and callbacks
│   └── a2ui_utils.py     # A2UI response formatting callback
├── frontend/
│   ├── main.py           # FastAPI proxy forwarding A2A chat traffic
│   ├── Dockerfile        # Container build definition for Cloud Run
│   ├── requirements.txt  # Dependencies for frontend proxy
│   └── static/
│       └── index.html    # Chat UI frontend with A2UI card renderer
├── agents-cli-manifest.yaml # ADK project manifest
├── pyproject.toml        # Agent Python dependencies
├── demo.gif              # Inline demonstration recording
└── README.md
```

---

## Local Development & Setup

### Prerequisites

- Python 3.11+
- `uv` package manager (`pip install uv`)
- Google Cloud SDK (`gcloud`) with credentials configured via `gcloud auth application-default login`

### Installation

Install dependencies into the virtual environment:

```bash
uv pip install -e .
```

### Running the Local Playground

To run the ADK web playground with Vertex AI Memory Bank attached:

```bash
uv run adk web . --port 8080 --reload_agents --memory_service_uri=agentengine://<MEMORY_BANK_ID>
```

### Running the Frontend Chat UI Locally

Start the local FastAPI proxy server to interact with the deployed agent:

```bash
export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"
export PORT=8080

uv run python frontend/main.py
```

---

## Deployment Instructions

### Deploying the Agent to Vertex AI Agent Runtime

Redeploy the agent to Agent Platform using `agents-cli`:

```bash
uv run agents-cli deploy --update-env-vars GOOGLE_MAPS_API_KEY=<YOUR_API_KEY> --no-confirm-project
```

### Deploying the Frontend Proxy to Cloud Run

Build and deploy the frontend proxy container to Google Cloud Run:

```bash
cd frontend

gcloud run deploy smart-pantry-frontend \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>",AGENT_DIRECTORY="app" \
  --quiet
```

Grant the Cloud Run default service account permission to call the agent:

```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```
