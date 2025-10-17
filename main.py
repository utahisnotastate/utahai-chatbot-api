import os
import logging
from typing import Any, Dict, List

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from flask import Flask, request, jsonify
from flask_cors import CORS

# Configure logging early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("utahai-chatbot-api")

# Try to import the Discovery Engine SDK; keep app runnable even if not installed locally.
try:
    from google.cloud import discoveryengine  # type: ignore
except Exception as e:  # pragma: no cover - optional dependency locally
    logger.exception(
        "Failed to import discoveryengine SDK. Fallback mode will be used. Error: %s", e
    )
    discoveryengine = None  # type: ignore

# --- CONFIGURATION ---
PROJECT_ID = os.getenv("PROJECT_ID", "utahai")
LOCATION = os.getenv("LOCATION", "global")
DATA_STORE_ID = os.getenv("DATA_STORE_ID", "utahai-knowledge-base")
MODEL_ID = os.getenv("MODEL_ID", "gemini-1.5-pro-preview-0409")

# --- VERTEX AI INITIALIZATION ---
try:
    vertexai.init(project=PROJECT_ID, location="us-central1")
    logger.info("Vertex AI initialized successfully.")
except Exception as e:
    logger.exception("Failed to initialize Vertex AI. Error: %s", e)

# Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


@app.get("/")
def root() -> Any:
    return jsonify({
        "service": "utahai-chatbot-api",
        "status": "ok",
        "project_id": PROJECT_ID,
        "location": LOCATION,
        "data_store_id": DATA_STORE_ID,
        "model_id": MODEL_ID,
        "docs": "/health, POST /chat { query: string, session_id?: string }",
    })


@app.get("/health")
def health() -> Any:
    return ("ok", 200)


@app.post("/chat")
def chat() -> Any:
    body = request.get_json(silent=True) or {}
    query: str = (body.get("query") or "").strip()
    session_id: str = (body.get("session_id") or "").strip()

    if not query:
        return jsonify({"error": "Missing 'query' in JSON body"}), 400

    try:
        answer, results = vertex_ai_search_and_generate(
            query, session_id=session_id or None
        )
        return jsonify({"answer": answer, "results": results, "model": MODEL_ID})
    except Exception as e:
        logger.exception("RAG call failed")
        return jsonify({
            "answer": f"(Fallback) An error occurred. Here is your query back: '{query}'.",
            "results": [],
            "error": str(e),
        }), 200


# --- RAG Helper using Vertex AI Search and Gemini ---
def vertex_ai_search_and_generate(
    query: str, session_id: str | None = None
) -> tuple[str, List[Dict[str, Any]]]:
    """Implements a RAG pattern: Retrieve from Vertex AI Search, then Generate with Gemini.
    """
    # 1. RETRIEVE relevant documents from Vertex AI Search
    if discoveryengine is None:
        return "(Fallback) Discovery Engine client library not installed.", []

    serving_config = (
        f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
        f"dataStores/{DATA_STORE_ID}/servingConfigs/default_serving_config"
    )
    client = discoveryengine.SearchServiceClient()
    user_pseudo_id = session_id or "anon"

    search_request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=5,
        safe_search=True,
        user_pseudo_id=user_pseudo_id,
        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True
            ),
            summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=5,
                include_citations=True,
                ignore_adversarial_query=True,
                use_semantic_chunks=True
            )
        )
    )
    search_response = client.search(request=search_request)

    # Collect search results for citation
    results: List[Dict[str, Any]] = []
    for res in search_response.results:
        try:
            doc = res.document
            meta = doc.derived_struct_data or {}
            results.append({
                "id": doc.name,
                "title": meta.get("title", ""),
                "uri": meta.get("link") or doc.uri,
                "snippet": meta.get("snippets", [{}])[0].get("snippet", ""),
            })
        except Exception: continue

    # 2. AUGMENT the prompt with the search results
    context = "\n".join([f"Source: {r['uri']}\nContent: {r['snippet']}" for r in results])
    prompt = f"""You are an expert assistant. Your task is to answer the user's query based *only* on the provided context.

    User Query: {query}

    Context:
    ---
    {context}
    ---

    Answer:
    """

    if not results:
        return "I could not find any relevant documents to answer your question.", []

    # 3. GENERATE a response using a Gemini model
    model = GenerativeModel(MODEL_ID)
    generation_config = GenerationConfig(temperature=0.1, max_output_tokens=2048)
    
    generation_response = model.generate_content(
        [prompt],
        generation_config=generation_config,
    )

    return generation_response.text, results


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
