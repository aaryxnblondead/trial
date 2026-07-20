from dataclasses import dataclass
from typing import Any, Dict, Optional


ALLOWED_SOURCE_SYSTEMS = {
    "ADR_MyNeta",
    "AICTE",
    "ECI",
    "MCA21",
    "RTI_Archive",
    "Research_Crosscheck",
    "State_Registry",
    "UGC",
}

ALLOWED_ACCESS_METHODS = {
    "official_api",
    "official_bulk_download",
    "local_archive",
}


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    name: str
    source_system: str
    url: str
    jurisdiction: str
    document_type: str
    license_note: str
    access_method: str = "official_api"
    citation_locator: Optional[str] = None
    record_path: Optional[str] = None
    content_type_hint: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_system": self.source_system,
            "url": self.url,
            "jurisdiction": self.jurisdiction,
            "document_type": self.document_type,
            "license_note": self.license_note,
            "access_method": self.access_method,
            "citation_locator": self.citation_locator,
            "record_path": self.record_path,
            "content_type_hint": self.content_type_hint,
        }


@dataclass(frozen=True)
class RetrievedArtifact:
    source_id: str
    source_url: str
    retrieved_at_utc: str
    sha256: str
    bytes_size: int
    artifact_path: str

