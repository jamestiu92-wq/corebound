"""
COREBOUND reusable Flask error handlers
======================================

Purpose:
    Provides consistent, user-friendly error handling for the COREBOUND Flask app.

Integration:
    1. Copy this file into the same folder as app.py (as error_handlers.py).
    2. In app.py, import:
           from error_handlers import register_error_handlers
    3. After creating your Flask app instance, call:
           register_error_handlers(app)

Notes:
    - These handlers do not replace route-level input validation.
    - They do not expose stack traces or exception details to users.
    - If matching templates exist in templates/errors/, they will be rendered;
      otherwise, a safe plain HTML response is returned.
    - Review existing error handlers before registering to avoid conflicts.
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, BadRequest, Forbidden, NotFound, TooManyRequests

logger = logging.getLogger("corebound.errors")


def _wants_json() -> bool:
    """Return True when the request clearly expects a JSON response."""
    if request.is_json:
        return True
    best = request.accept_mimetypes.best
    return best == "application/json"


def _safe_error_response(status_code: int, title: str, message: str):
    """Return JSON for API requests or a safe HTML response for browser requests."""
    payload = {
        "success": False,
        "error": {
            "status": status_code,
            "title": title,
            "message": message,
        },
    }

    if _wants_json():
        return jsonify(payload), status_code

    # Use an error template only if the project has one; otherwise render a
    # small self-contained page so this module does not require new templates.
    template_name = f"errors/{status_code}.html"
    try:
        return render_template(
            template_name,
            status_code=status_code,
            title=title,
            message=message,
        ), status_code
    except Exception:
        # A missing template is expected in projects that use this module
        # without adding custom error pages. Do not expose template exceptions.
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{status_code} - {title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 720px; margin: 12vh auto;
           padding: 24px; color: #183044; background: #f4f7fa; }}
    main {{ background: white; padding: 32px; border-radius: 14px;
            box-shadow: 0 8px 28px rgba(0,0,0,.08); }}
    h1 {{ margin-top: 0; }} p {{ line-height: 1.6; }}
    a {{ color: #0866a6; }}
  </style>
</head>
<body><main>
  <h1>{status_code}: {title}</h1>
  <p>{message}</p>
  <p><a href="/">Return to the home page</a></p>
</main></body></html>"""
        return html, status_code, {"Content-Type": "text/html; charset=utf-8"}


def register_error_handlers(app: Flask) -> None:
    """Register COREBOUND error handlers on an existing Flask app."""

    @app.errorhandler(400)
    def handle_bad_request(error):
        logger.info("Bad request: path=%s", request.path)
        return _safe_error_response(400, "Bad Request", "The request could not be processed. Check the submitted information and try again.")

    @app.errorhandler(403)
    def handle_forbidden(error):
        logger.warning("Forbidden request: path=%s", request.path)
        return _safe_error_response(403, "Access Denied", "You do not have permission to access this page or perform this action.")

    @app.errorhandler(404)
    def handle_not_found(error):
        logger.info("Page not found: path=%s", request.path)
        return _safe_error_response(404, "Page Not Found", "The page or resource you requested could not be found.")

    @app.errorhandler(413)
    def handle_too_large(error):
        logger.warning("Request too large: path=%s", request.path)
        return _safe_error_response(413, "Upload Too Large", "The submitted request or file is too large. Reduce the file size and try again.")

    @app.errorhandler(429)
    def handle_rate_limited(error):
        logger.warning("Rate limit reached: path=%s", request.path)
        return _safe_error_response(429, "Too Many Requests", "Too many requests were received. Please wait a moment and try again.")

    @app.errorhandler(500)
    def handle_internal_error(error):
        # Flask may pass an InternalServerError wrapper; do not send exception
        # details, SQL statements, paths, or stack traces to the client.
        original = getattr(error, "original_exception", None)
        if original:
            logger.error(
                "Unhandled application exception on %s (%s)",
                request.path,
                type(original).__name__,
                exc_info=(type(original), original, original.__traceback__),
            )
        else:
            logger.error("Internal server error on %s", request.path)
        return _safe_error_response(500, "Server Error", "Something went wrong on the server. Please try again later.")

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        status = error.code or 500
        # Preserve standard HTTP status codes while using safe messages.
        known = {
            401: ("Authentication Required", "Please sign in and try again."),
            405: ("Method Not Allowed", "This action is not supported for this URL."),
            408: ("Request Timeout", "The request took too long. Please try again."),
            410: ("Resource Unavailable", "This resource is no longer available."),
            415: ("Unsupported Media Type", "The submitted content type is not supported."),
            422: ("Unprocessable Request", "The submitted information could not be processed."),
        }
        title, message = known.get(
            status,
            ("Request Error", "The request could not be completed. Please check it and try again."),
        )
        logger.info("HTTP error %s on %s", status, request.path)
        return _safe_error_response(status, title, message)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        # HTTPException instances are handled by the dedicated handler above.
        if isinstance(error, HTTPException):
            return error
        logger.error(
            "Unhandled exception on %s (%s)",
            request.path,
            type(error).__name__,
            exc_info=(type(error), error, error.__traceback__),
        )
        return _safe_error_response(500, "Server Error", "Something went wrong on the server. Please try again later.")
