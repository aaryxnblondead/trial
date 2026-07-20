from __future__ import annotations

from urllib.parse import urlparse

import requests

from etl.models import ALLOWED_ACCESS_METHODS, ALLOWED_SOURCE_SYSTEMS, SourceDefinition


class SourceFetchError(RuntimeError):
    pass


class SourceValidationError(RuntimeError):
    pass


def _validate_source_url(source: SourceDefinition) -> None:
    parsed = urlparse(source.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SourceFetchError(f"Invalid source URL for {source.source_id}: {source.url}")


def validate_source_definition(source: SourceDefinition) -> None:
    if source.source_system not in ALLOWED_SOURCE_SYSTEMS:
        raise SourceValidationError(f"Unsupported source system for {source.source_id}: {source.source_system}")
    if source.access_method not in ALLOWED_ACCESS_METHODS:
        raise SourceValidationError(f"Unsupported access method for {source.source_id}: {source.access_method}")
    _validate_source_url(source)


def fetch_source_payload(source: SourceDefinition, timeout_seconds: int = 60) -> tuple[bytes, str]:
    validate_source_definition(source)
    try:
        response = requests.get(source.url, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SourceFetchError(f"Failed to fetch {source.source_id} from {source.url}") from exc

    content_type = response.headers.get("Content-Type", "")
    return response.content, content_type

