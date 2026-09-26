"""Stage 1: PDF Source Archive Management.

Preserves immutable raw document metadata and file evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader


@dataclass(frozen=True)
class ArchivedDocument:
    document_id: str
    ticker: str
    company: str
    financial_period: str
    publication_datetime: datetime
    document_type: str
    original_filename: str
    source_url: Optional[str]
    sha256_hash: str
    ingestion_timestamp: datetime
    page_count: int
    raw_pdf_path: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["publication_datetime"] = self.publication_datetime.isoformat()
        d["ingestion_timestamp"] = self.ingestion_timestamp.isoformat()
        return d


def compute_file_sha256(path: Path | str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def archive_afs_pdf(
    pdf_path: Path | str,
    ticker: str,
    company: str,
    financial_period: str,
    publication_datetime: datetime | str,
    source_url: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    db_conn: Optional[Any] = None,
) -> ArchivedDocument:
    """Archive an AFS PDF source and preserve cryptographic evidence."""
    path = Path(pdf_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"AFS PDF not found: {path}")

    file_hash = compute_file_sha256(path)
    reader = PdfReader(str(path))
    page_count = len(reader.pages)

    if isinstance(publication_datetime, str):
        # Support ISO string or simple date
        if "T" in publication_datetime or " " in publication_datetime:
            pub_dt = datetime.fromisoformat(publication_datetime.replace("Z", "+00:00"))
        else:
            d = date.fromisoformat(publication_datetime)
            pub_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    else:
        pub_dt = publication_datetime

    doc_id = str(uuid4())
    ingest_ts = datetime.now(timezone.utc)

    meta = {
        "file_size_bytes": path.stat().st_size,
        "page_count": page_count,
        "source_archive": "results_history",
        **(extra_metadata or {}),
    }

    archived = ArchivedDocument(
        document_id=doc_id,
        ticker=ticker,
        company=company,
        financial_period=financial_period,
        publication_datetime=pub_dt,
        document_type="annual_financial_statements",
        original_filename=path.name,
        source_url=source_url,
        sha256_hash=file_hash,
        ingestion_timestamp=ingest_ts,
        page_count=page_count,
        raw_pdf_path=str(path),
        metadata=meta,
    )

    # If DB connection provided, register in source_documents table
    if db_conn is not None:
        _register_in_db(db_conn, archived)

    return archived


def _register_in_db(conn: Any, doc: ArchivedDocument) -> None:
    """Insert into source_documents table if not already present."""
    cur = conn.cursor()
    entity_key = f"{doc.ticker}:{doc.financial_period}:{doc.original_filename}"
    meta_json = json.dumps(doc.to_dict(), sort_keys=True)
    cur.execute(
        """
        INSERT INTO source_documents
            (id, source, entity_key, document_type, source_url, fetched_at,
             source_date, effective_date, content_hash, content_type,
             raw_content, parser_version, metadata_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, entity_key, document_type, content_hash) DO NOTHING;
        """,
        (
            doc.document_id,
            "afs_archive",
            entity_key,
            doc.document_type,
            doc.source_url,
            doc.ingestion_timestamp,
            doc.publication_datetime.date(),
            doc.publication_datetime.date(),
            doc.sha256_hash,
            "application/pdf",
            f"FILE_REF:{doc.raw_pdf_path}",
            "afs_pipeline_v1",
            meta_json,
        ),
    )
    conn.commit()
