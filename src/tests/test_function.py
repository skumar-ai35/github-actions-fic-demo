# src/tests/test_function.py
#
# Unit tests for the HelloFIC Azure Function.
#
# We use azure.functions.HttpRequest / HttpResponse directly — no need for a
# running Azure host.  The v2 function is just a plain Python function that
# accepts an HttpRequest and returns an HttpResponse, so we can call it like
# any other function.
#
# Run locally:
#   pip install pytest azure-functions
#   pytest src/tests --tb=short -v
# Test
import json
import sys
import os

import pytest

# ---------------------------------------------------------------------------
# Make sure the src/ directory is on sys.path so we can import function_app
# when running pytest from the project root.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import azure.functions as func  # noqa: E402  (import after sys.path manipulation)
from function_app import hello_fic  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_get_request(params: dict | None = None) -> func.HttpRequest:
    """Build a minimal GET HttpRequest with optional query parameters."""
    return func.HttpRequest(
        method="GET",
        url="http://localhost/api/HelloFIC",
        params=params or {},
        headers={},
        body=b"",
    )


def _make_post_request(body: dict | None = None) -> func.HttpRequest:
    """Build a POST HttpRequest with a JSON body."""
    raw_body = json.dumps(body).encode("utf-8") if body else b""
    return func.HttpRequest(
        method="POST",
        url="http://localhost/api/HelloFIC",
        params={},
        headers={"Content-Type": "application/json"},
        body=raw_body,
    )


def _parse_response(response: func.HttpResponse) -> dict:
    """Decode the HttpResponse body as JSON."""
    return json.loads(response.get_body().decode("utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHelloFIC:

    def test_default_greeting_no_name(self):
        """GET with no name param should greet 'World'."""
        req = _make_get_request()
        resp = hello_fic(req)

        assert resp.status_code == 200
        body = _parse_response(resp)
        assert "Hello, World!" in body["message"]

    def test_query_param_name(self):
        """GET ?name=Alice should personalise the greeting."""
        req = _make_get_request(params={"name": "Alice"})
        resp = hello_fic(req)

        assert resp.status_code == 200
        body = _parse_response(resp)
        assert "Hello, Alice!" in body["message"]

    def test_json_body_name(self):
        """POST with JSON body {"name": "Bob"} should personalise the greeting."""
        req = _make_post_request(body={"name": "Bob"})
        resp = hello_fic(req)

        assert resp.status_code == 200
        body = _parse_response(resp)
        assert "Hello, Bob!" in body["message"]

    def test_post_empty_body_falls_back_to_world(self):
        """POST with no body and no query param should default to 'World'."""
        req = func.HttpRequest(
            method="POST",
            url="http://localhost/api/HelloFIC",
            params={},
            headers={},
            body=b"",
        )
        resp = hello_fic(req)

        assert resp.status_code == 200
        body = _parse_response(resp)
        assert "Hello, World!" in body["message"]

    def test_metadata_fields_present(self):
        """Response must include all required metadata keys."""
        req = _make_get_request()
        resp = hello_fic(req)
        body = _parse_response(resp)

        required_keys = {
            "message",
            "deployed_via",
            "runtime",
            "timestamp",
            "auth_method",
            "secrets_used",
        }
        assert required_keys.issubset(body.keys()), (
            f"Missing keys: {required_keys - body.keys()}"
        )

    def test_secrets_used_is_zero(self):
        """The secrets_used field must always be 0 — the whole point of FIC."""
        req = _make_get_request()
        resp = hello_fic(req)
        body = _parse_response(resp)

        assert body["secrets_used"] == 0, (
            "secrets_used must be 0 — this function is deployed without any secrets!"
        )

    def test_auth_method_mentions_oidc(self):
        """auth_method field should reference OIDC to document the auth flow."""
        req = _make_get_request()
        resp = hello_fic(req)
        body = _parse_response(resp)

        assert "OIDC" in body["auth_method"] or "OpenID" in body["auth_method"]

    def test_response_content_type_is_json(self):
        """Response mimetype must be application/json."""
        req = _make_get_request()
        resp = hello_fic(req)

        # azure.functions.HttpResponse stores mimetype separately from headers
        assert resp.mimetype == "application/json"

    def test_timestamp_is_iso_format(self):
        """timestamp field must be parseable as an ISO-8601 datetime."""
        from datetime import datetime
        req = _make_get_request()
        resp = hello_fic(req)
        body = _parse_response(resp)

        # fromisoformat handles the UTC '+00:00' suffix in Python 3.11
        dt = datetime.fromisoformat(body["timestamp"])
        assert dt is not None

    def test_runtime_contains_python(self):
        """runtime field should mention Python and a version number."""
        import re
        req = _make_get_request()
        resp = hello_fic(req)
        body = _parse_response(resp)

        assert re.search(r"Python \d+\.\d+", body["runtime"]), (
            f"Unexpected runtime value: {body['runtime']}"
        )
