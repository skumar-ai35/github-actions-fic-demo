# src/function_app.py
#
# Python Azure Functions v2 programming model.
# The v2 model uses decorators instead of a per-function function.json file,
# which means a single file can define multiple routes and bindings.
#
# This function demonstrates that it was deployed via GitHub Actions
# using Federated Identity Credentials — no secrets, no passwords.

import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func

# ---------------------------------------------------------------------------
# App initialisation
# FunctionApp() is the entry point for the v2 model.
# auth_level=func.AuthLevel.ANONYMOUS means callers do NOT need a function key.
# Change to FUNCTION or ADMIN for key-protected endpoints.
# ---------------------------------------------------------------------------
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)


@app.route(route="HelloFIC", methods=["GET", "POST"])
def hello_fic(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered function that demonstrates passwordless deployment.

    Accepted inputs (in priority order):
      1. JSON body:  {"name": "Alice"}
      2. Query string: ?name=Alice
      3. No name → defaults to "World"

    Returns a JSON payload that proves the function is live and shows
    deployment metadata useful for verifying the FIC workflow succeeded.
    """
    logger.info("HelloFIC function triggered. Method=%s", req.method)

    # ------------------------------------------------------------------
    # Resolve the caller's name from the request.
    # We try the JSON body first (POST use-case), then fall back to the
    # query string (GET use-case), then use "World" as the default.
    # ------------------------------------------------------------------
    name = None

    if req.method == "POST":
        try:
            body = req.get_json()
            # body may be a dict or None if Content-Type isn't application/json
            if isinstance(body, dict):
                name = body.get("name")
        except ValueError:
            # Body is not valid JSON — not an error, just fall through.
            logger.debug("Request body is not JSON; falling back to query param.")

    # Fall back to query string for both GET and POST
    if not name:
        name = req.params.get("name")

    # Final default
    if not name:
        name = "World"

    # ------------------------------------------------------------------
    # Build the response payload.
    # Every field here has a purpose:
    #   message       — the human-readable greeting
    #   deployed_via  — shows the CI/CD pipeline that published this code
    #   runtime       — the Python version running inside Azure Functions
    #   timestamp     — UTC ISO-8601 so callers can verify freshness
    #   auth_method   — emphasises that OIDC/FIC was used, not a secret
    #   secrets_used  — always 0; the point of this whole demo
    # ------------------------------------------------------------------
    payload = {
        "message": f"Hello, {name}! This function was deployed via GitHub Actions using Federated Identity Credentials.",
        "deployed_via": "GitHub Actions + azure/login@v2 (OIDC / Federated Identity Credential)",
        "runtime": f"Python {_python_version()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "auth_method": "OpenID Connect (OIDC) — no client secret stored anywhere",
        "secrets_used": 0,
    }

    logger.info("Returning response for name=%s", name)

    return func.HttpResponse(
        body=json.dumps(payload, indent=2),
        mimetype="application/json",
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _python_version() -> str:
    """Return a human-readable Python version string, e.g. '3.11.9'."""
    import sys
    return ".".join(str(v) for v in sys.version_info[:3])
