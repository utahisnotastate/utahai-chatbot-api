import os
import logging
from typing import Any, Dict, List, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

# Configure logging early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("utahai-chatbot-api")

# Try to import the Discovery Engine SDK; keep app runnable even if not installed locally.
try:
    from google.cloud import discoveryengine  # type: ignore
except Exception as e:  # pragma: no cover - optional dependency locally
    # Log the full error to help debug import issues in production.
    logger.exception(
        "Failed to import discoveryengine SDK. Fallback mode will be used. Error: %s", e
    )
    discoveryengine = None  # type: ignore

# --- CONFIGURATION ---
# Environment variable overrides are supported so you don't have to edit code when deploying.
PROJECT_ID = os.getenv("PROJECT_ID", "utahai")
LOCATION = os.getenv("LOCATION", "global")  # Must be "global" for Vertex AI Search
DATA_STORE_ID = os.getenv("DATA_STORE_ID", "utahai-knowledge-base_1759607726769")
MODEL_ID = os.getenv("MODEL_ID", "gemini-1.5-pro-preview-0409")
AUTO_RESOLVE_DATASTORE = os.getenv("AUTO_RESOLVE_DATASTORE", "true").lower() not in {"0","false","no"}

# Cache for the effective/resolved data store id
_RESOLVED_DATA_STORE_ID: Optional[str] = None

# Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Utilities: resolve data store and build serving config ---

def _looks_full_datastore_id(ds_id: str) -> bool:
    try:
        suffix = ds_id.rsplit("_", 1)[1]
        return suffix.isdigit()
    except Exception:
        return False


def get_effective_data_store_id() -> str:
    """Return a data store ID that exists in Discovery Engine.
    If AUTO_RESOLVE_DATASTORE=true and DATA_STORE_ID appears to be a short
    name/prefix or a display name, we will list data stores and select the
    best match. The result is cached for subsequent calls.
    """
    global _RESOLVED_DATA_STORE_ID

    if _RESOLVED_DATA_STORE_ID:
        return _RESOLVED_DATA_STORE_ID

    ds = (DATA_STORE_ID or "").strip()
    if not ds:
        # Keep non-empty to avoid malformed path; will cause readable error later
        _RESOLVED_DATA_STORE_ID = ds
        return ds

    if discoveryengine is None or not AUTO_RESOLVE_DATASTORE or _looks_full_datastore_id(ds):
        _RESOLVED_DATA_STORE_ID = ds
        return ds

    try:
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection"
        client = discoveryengine.DataStoreServiceClient()
        matches: list[tuple[int, str]] = []  # (priority, ds_id)
        ds_lc = ds.lower()
        for item in client.list_data_stores(parent=parent):
            name = getattr(item, "name", "") or ""
            display_name = getattr(item, "display_name", "") or ""
            item_id = name.split("/")[-1] if name else ""
            # Priority: exact id (without suffix), then id prefix, then exact display name, then display name prefix
            if item_id == ds:
                matches.append((0, item_id))
            elif item_id.startswith(ds + "_"):
                matches.append((1, item_id))
            elif display_name.lower() == ds_lc:
                matches.append((2, item_id))
            elif display_name.lower().startswith(ds_lc):
                matches.append((3, item_id))
        if matches:
            matches.sort(key=lambda x: x[0])
            chosen = matches[0][1]
            logger.info("Resolved DATA_STORE_ID '%s' to '%s' via Discovery Engine", ds, chosen)
            _RESOLVED_DATA_STORE_ID = chosen
            return chosen
    except Exception as e:  # pragma: no cover - resolution is best-effort
        logger.warning("Auto-resolve of DATA_STORE_ID failed: %s", e)

    # Fallback: return what we were given
    _RESOLVED_DATA_STORE_ID = ds
    return ds


def build_serving_config_path() -> str:
    dsid = get_effective_data_store_id()
    return (
        f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
        f"dataStores/{dsid}/servingConfigs/default_serving_config"
    )


@app.get("/")
def root() -> Any:
    return jsonify({
        "service": "utahai-chatbot-api",
        "status": "ok",
        "project_id": PROJECT_ID,
        "location": LOCATION,
        "data_store_id_configured": DATA_STORE_ID,
        "data_store_id_effective": get_effective_data_store_id(),
        "library_available": bool(discoveryengine is not None),
        "docs": "/health, POST /chat { query: string, session_id?: string }",
    })


@app.get("/health")
def health() -> Any:
    return ("ok", 200)


@app.get("/setup/check")
def setup_check() -> Any:
    """Lightweight diagnostics to help verify configuration and connectivity.
    Does a tiny search (page_size=1) and returns status info and any error.
    """
    effective_ds = get_effective_data_store_id()
    info: Dict[str, Any] = {
        "project_id": PROJECT_ID,
        "location": LOCATION,
        "data_store_id_configured": DATA_STORE_ID,
        "data_store_id_effective": effective_ds,
        "serving_config": build_serving_config_path(),
        "library_available": bool(discoveryengine is not None),
    }

    if discoveryengine is None:
        info["status"] = "missing_client_lib"
        return jsonify(info), 200

    try:
        client = discoveryengine.SearchServiceClient()
        request = discoveryengine.SearchRequest(
            serving_config=info["serving_config"],
            query="setup check",
            page_size=1,
            safe_search=True,
            user_pseudo_id="setup-check",
        )
        _ = client.search(request=request)
        info["status"] = "ok"
        return jsonify(info), 200
    except Exception as e:
        logger.exception("Setup check failed")
        info["status"] = "error"
        info["error"] = str(e)
        return jsonify(info), 200


@app.post("/chat")
def chat() -> Any:
    body = request.get_json(silent=True) or {}
    query: str = (body.get("query") or "").strip()
    session_id: str = (body.get("session_id") or "").strip()

    if not query:
        return jsonify({"error": "Missing 'query' in JSON body"}), 400

    # Attempt to answer using Vertex AI Search (Discovery Engine)
    try:
        answer, results = vertex_ai_search_answer(query, session_id=session_id or None)
        return jsonify({
            "answer": answer,
            "results": results,
            "model": MODEL_ID,
        })
    except Exception as e:
        logger.exception("Vertex AI Search call failed")
        # Fallback: echo response so the service still functions without GCP setup
        return jsonify({
            "answer": f"(Fallback) I could not reach Vertex AI Search. Here is your query back: '{query}'.",
            "results": [],
            "error": str(e),
        }), 200


# --- Helper that uses Discovery Engine (Vertex AI Search) ---

def vertex_ai_search_answer(query: str, session_id: str | None = None) -> tuple[str, List[Dict[str, Any]]]:
    """Queries Vertex AI Search and returns a simple synthesized answer and result list.
    This uses the SearchService for broad compatibility.
    If the Discovery Engine client library is not available, returns a graceful
    fallback without raising so that local development can proceed.
    """
    if discoveryengine is None:
        # Graceful local fallback: no exception, just echo-style reply
        fallback_answer = "(Fallback) Discovery Engine client library not installed; returning echo answer."
        return fallback_answer, []

    # Build the serving config path (auto-resolving data store id if needed)
    serving_config = build_serving_config_path()

    client = discoveryengine.SearchServiceClient()

    # Optional user pseudo id to help session personalization
    user_pseudo_id = session_id or os.getenv("USER_PSEUDO_ID") or "anon"

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=5,
        safe_search=True,
        user_pseudo_id=user_pseudo_id,
        query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
            condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO
        ),
        spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
            mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
        ),
    )

    response = client.search(request=request)

    # Collect simple results
    results: List[Dict[str, Any]] = []
    snippets: List[str] = []

    for res in response.results:
        try:
            doc = res.document
            meta = doc.derived_struct_data or {}
            uri = meta.get("link") or meta.get("uri") or doc.uri or ""
            title = meta.get("title") or (doc.struct_data.get("title") if doc.struct_data else None) or ""
            snippet_text = ""
            if meta.get("snippets"):
                snippet_text = " ".join([s.get("snippet", "") for s in meta.get("snippets", [])])

            if snippet_text:
                snippets.append(snippet_text)

            results.append({
                "id": getattr(doc, "name", ""),
                "title": title,
                "uri": uri,
                "snippet": snippet_text,
            })
        except Exception:
            # Keep robust to schema diffs between versions
            continue

    # Naive synthesis: first snippet or fallback message
    answer = snippets[0] if snippets else "I found some relevant results."

    return answer, results


if __name__ == "__main__":
    # Local dev server (not used in Cloud Run image, where gunicorn is preferred)
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
