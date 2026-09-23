"""Durable request archives and append-only report versions.

The local archive is written before inference. PostgreSQL indexes each attempt;
the existing stock_analysis columns remain the current-report projection.
"""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

ARCHIVE_ROOT = Path(__file__).resolve().parents[2] / "report_evidence"


def json_text(value):
    def encode(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        return str(obj)
    return json.dumps(value, ensure_ascii=False, indent=2, default=encode)


def raw_response(response):
    if isinstance(response, str):
        return {"text": response}
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    return {"text": getattr(response, "text", ""), "representation": repr(response)}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json_text(value), encoding="utf-8")
    temporary.replace(path)


def source_date_from_name(name):
    match = re.search(r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)(?:\d{6})?(?!\d)", name)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def source_date_from_text(text):
    """Use an explicit SENS publication stamp before a file-save timestamp."""
    match = re.search(r"(?im)^\s*Date:\s*(\d{1,2})[-/](\d{1,2})[-/](20\d{2})(?:\s|$)", text)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat()
        except ValueError:
            pass
    return None


class EvidenceArchive:
    def __init__(self, ticker, *, root=None, report_id=None, generated_at=None):
        self.report_id = str(report_id or uuid4())
        safe_ticker = re.sub(r"[^A-Za-z0-9_.-]", "_", ticker).strip(".") or "unknown"
        self.path = Path(root or ARCHIVE_ROOT) / safe_ticker / self.report_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.generated_at = generated_at or datetime.now(timezone.utc)
        self.ticker = ticker

    def snapshot_sources(self, paths):
        sources = []
        folder = self.path / "sources"
        folder.mkdir(exist_ok=False)
        for index, original in enumerate(paths):
            original = Path(original)
            data = original.read_bytes()
            archived = folder / f"{index:03d}_{original.name}"
            archived.write_bytes(data)
            text = ""
            extraction_error = None
            if original.suffix.lower() == ".txt":
                text = data.decode("utf-8", errors="ignore")
            elif original.suffix.lower() == ".pdf":
                try:
                    from PyPDF2 import PdfReader
                    text = "\n".join(p.extract_text() or "" for p in PdfReader(archived).pages)
                except Exception as exc:
                    extraction_error = str(exc)
            embedded_date = source_date_from_text(text)
            source_date = embedded_date or source_date_from_name(original.name)
            sources.append({"source_id": f"file:{index}", "name": original.name,
                            "original_path": str(original.resolve()), "archive_path": str(archived.resolve()),
                            "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
                            "source_date": source_date, "date_basis": "embedded publication stamp" if embedded_date else "filename" if source_date else None,
                            "supplied_to_model": True, "text": text, "extraction_error": extraction_error,
                            "observed_at": self.generated_at.isoformat(), "fetched_at": self.generated_at.isoformat()})
        return sources

    def snapshot_text_records(self, records):
        """Archive in-memory/database text evidence without a staging source file."""
        sources = []
        folder = self.path / "sources"
        folder.mkdir(exist_ok=False)
        for index, record in enumerate(records):
            text = str(record.get("text") or "")
            data = text.encode("utf-8")
            raw_name = str(record.get("name") or f"source_{index}.txt")
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(raw_name).name) or f"source_{index}.txt"
            archived = folder / f"{index:03d}_{safe_name}"
            archived.write_bytes(data)
            embedded_date = source_date_from_text(text)
            source_date = record.get("source_date") or embedded_date
            item = {k: v for k, v in record.items() if k != "text"}
            item.update({"source_id": record.get("source_id") or f"inline:{index}",
                         "name": raw_name, "original_path": None,
                         "archive_path": str(archived.resolve()),
                         "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
                         "source_date": str(source_date)[:10] if source_date else None,
                         "date_basis": record.get("date_basis") or ("embedded publication stamp" if embedded_date else None),
                         "supplied_to_model": True, "text": text, "extraction_error": None,
                         "observed_at": self.generated_at.isoformat(), "fetched_at": self.generated_at.isoformat()})
            sources.append(item)
        return sources

    def save_inputs(self, inputs):
        if (self.path / "inputs.json").exists():
            raise ValueError("Generation inputs cannot be overwritten")
        inputs.update(report_id=self.report_id, ticker=self.ticker,
                      generated_at=self.generated_at.isoformat(), archive_path=str(self.path.resolve()))
        write_json(self.path / "inputs.json", inputs)
        (self.path / "prompt.txt").write_text(inputs.get("prompt") or "", encoding="utf-8")
        return inputs

    def save_result(self, result):
        path = self.path / "result.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("status") in {"published", "manual", "rejected", "failed"}:
                if existing == json.loads(json_text(result)):
                    return
                raise ValueError("A completed report archive cannot be overwritten")
        write_json(path, result)


async def get_previous_report(ticker):
    from core.db.engine import DBEngine
    rows = await DBEngine.fetch("""
        SELECT deepresearch, deepresearch_date, current_report_id
        FROM stock_analysis WHERE ticker=$1
    """, ticker)
    return dict(rows[0]) if rows else {}


async def get_previous_report_metadata(ticker):
    """Return version lineage without loading prior report text into generation."""
    from core.db.engine import DBEngine
    rows = await DBEngine.fetch("""
        SELECT deepresearch_date, current_report_id,
               (deepresearch IS NOT NULL AND BTRIM(deepresearch) <> '') AS has_previous_report
        FROM stock_analysis WHERE ticker=$1
    """, ticker)
    return dict(rows[0]) if rows else {}


async def fetch_audit_sources(ticker, *, until=None):
    """Disclosure evidence for warnings, never silently inserted into model inputs."""
    from core.db.engine import DBEngine
    rows = await DBEngine.fetch("""
        SELECT sens_id, publication_datetime, content FROM sens
        WHERE ticker=$1 AND publication_datetime <= $2 ORDER BY publication_datetime, sens_id
    """, ticker, until or datetime.now(timezone.utc))
    return [{"source_id": f"sens:{r['sens_id']}", "source_date": r["publication_datetime"].date().isoformat(),
             "text": r["content"], "supplied_to_model": False} for r in rows]


async def register_generation(archive, inputs):
    from core.db.engine import DBEngine
    await DBEngine.execute("""
        INSERT INTO deepresearch_versions
          (report_id,ticker,generated_at,previous_report_id,status,archive_path,inputs)
        VALUES ($1::uuid,$2,$3,$4::uuid,'pending',$5,$6::jsonb)
    """, archive.report_id, archive.ticker, archive.generated_at,
        inputs.get("previous_report_id"), str(archive.path.resolve()), json_text(inputs))


async def finish_generation(archive, result, *, report_content=None, publish=False, manual=False,
                            metrics=(), metric_warnings=(), valuation_result=None):
    """Publish report + current pointer in one transaction, retaining every version."""
    from core.db.engine import DBEngine
    pending_result = dict(result, status="pending")
    archive.save_result(pending_result)  # Retain response if DB publication fails.
    pool = await DBEngine.get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            if publish:
                # Ensure the row exists; serialise writers for this ticker.
                await connection.execute("INSERT INTO stock_analysis (ticker) VALUES ($1) ON CONFLICT DO NOTHING", archive.ticker)
                current = await connection.fetchrow("SELECT * FROM stock_analysis WHERE ticker=$1 FOR UPDATE", archive.ticker)
                old_text = current.get("deepresearch")
                old_id = current.get("current_report_id")
                # Also preserve text edited by an older client which did not update
                # the version pointer. Never claim those edits were model output.
                version_text = await connection.fetchval(
                    "SELECT report_content FROM deepresearch_versions WHERE report_id=$1", old_id) if old_id else None
                if old_text and old_text != version_text:
                    snapshot_id = uuid4()
                    await connection.execute("""
                        INSERT INTO deepresearch_versions
                          (report_id,ticker,generated_at,previous_report_id,status,inputs,report_content,completed_at)
                        VALUES ($1,$2,NOW(),$3,'legacy',$4::jsonb,$5,NOW())
                    """, snapshot_id, archive.ticker, old_id,
                        json_text({"provenance": "unversioned edit; original inputs unavailable",
                                   "original_report_date": current.get("deepresearch_date")}), old_text)
                    old_id = snapshot_id
                result["supersedes_report_id"] = str(old_id) if old_id else None
            status = ("manual" if manual else "published") if publish else result.get("status", "failed")
            result["status"] = status
            updated = await connection.execute("""
                UPDATE deepresearch_versions SET status=$2, response=$3::jsonb,
                    report_content=$4, audit=$5::jsonb, completed_at=NOW()
                WHERE report_id=$1::uuid AND status='pending'
            """, archive.report_id, status, json_text(result), report_content, json_text(result.get("audit")))
            if updated != "UPDATE 1":
                raise ValueError("Report does not exist or is already finalised")
            for metric in metrics:
                await connection.execute("""
                    INSERT INTO financial_metrics
                      (metric_id, ticker, report_id, metric, warnings)
                    VALUES ($1::uuid, $2, $3::uuid, $4::jsonb, $5::jsonb)
                """, metric.metric_id, archive.ticker, archive.report_id,
                    json_text(metric.model_dump(mode="json")),
                    json_text([w for w in metric_warnings if w.get("metric_id") == str(metric.metric_id)]))
            if valuation_result is not None:
                if str(valuation_result.report_version_id) != archive.report_id:
                    raise ValueError("Valuation result must reference this report version")
                from modules.data.valuation_results import insert_valuation_result
                await insert_valuation_result(connection, valuation_result)
            if publish:
                await connection.execute("""
                    UPDATE stock_analysis SET deepresearch=$2, deepresearch_date=CURRENT_DATE,
                        current_report_id=$3::uuid WHERE ticker=$1
                """, archive.ticker, report_content, archive.report_id)
    result["status"] = status
    archive.save_result(result)


async def save_manual_report(ticker, content):
    previous = await get_previous_report(ticker)
    archive = EvidenceArchive(ticker)
    inputs = archive.save_inputs({"kind": "manual", "prompt": None, "model": None, "temperature": None,
                                  "previous_report_supplied_to_model": False,
                                  "previous_report_id": str(previous["current_report_id"]) if previous.get("current_report_id") else None,
                                  "sources": [], "provenance": "manual edit; no Gemini generation"})
    await register_generation(archive, inputs)
    await finish_generation(archive, {"raw_response": None}, report_content=content, publish=True, manual=True)
    return archive.report_id
