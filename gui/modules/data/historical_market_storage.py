"""Authoritative PostgreSQL storage with file-fallback for historical market inputs."""
from __future__ import annotations
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID
import psycopg2
from psycopg2.extras import RealDictCursor
from core.config import DB_CONFIG
from modules.analysis.historical_market_inputs import (
    HistoricalMarketInput, InputScope, MarketConcept, ProvenanceQuality
)

STORAGE_PATH = Path(__file__).resolve().parents[2] / "results_history" / "_market_inputs_store.json"
_MEM_STORE: dict[str, HistoricalMarketInput] = {}
_USE_PG: bool = True

def _get_pg_conn():
    if not _USE_PG: return None
    try: return psycopg2.connect(**DB_CONFIG, connect_timeout=3)
    except Exception: return None

def _model_to_db_params(item: HistoricalMarketInput) -> tuple:
    return (
        str(item.input_id), item.scope.value, item.ticker, item.market_scope,
        item.concept.value, float(item.value), item.unit, item.observation_date,
        item.available_date, item.provider, item.source_url, item.source_methodology,
        item.notes, item.retrieval_timestamp, item.batch_id, item.lookback_period,
        item.frequency, item.levered, item.debt_method, item.provenance_quality.value,
        item.source_document_id, item.evidence_uri, item.evidence_hash,
        item.revision, str(item.supersedes_input_id) if item.supersedes_input_id else None,
        item.is_active, json.dumps(item.metadata), item.input_hash
    )

def _row_to_model(row: dict[str, Any]) -> HistoricalMarketInput:
    meta = row.get("metadata")
    if isinstance(meta, str): meta = json.loads(meta)
    return HistoricalMarketInput(
        input_id=UUID(str(row["input_id"])), scope=InputScope(row["scope"]),
        ticker=row.get("ticker"), market_scope=row.get("market_scope", "ZA"),
        concept=MarketConcept(row["concept"]), value=Decimal(str(row["value"])),
        unit=row.get("unit", "percentage"), observation_date=row["observation_date"],
        available_date=row["available_date"], provider=row["provider"],
        source_url=row.get("source_url"), retrieval_timestamp=row["retrieval_timestamp"],
        source_methodology=row.get("source_methodology"), notes=row.get("notes"),
        batch_id=row.get("batch_id"), lookback_period=row.get("lookback_period"),
        frequency=row.get("frequency"), levered=row.get("levered"), debt_method=row.get("debt_method"),
        provenance_quality=ProvenanceQuality(row.get("provenance_quality", "analyst_entered")),
        source_document_id=row.get("source_document_id"),
        evidence_uri=row.get("evidence_uri"), evidence_hash=row.get("evidence_hash"),
        revision=row.get("revision", 1),
        supersedes_input_id=UUID(str(row["supersedes_input_id"])) if row.get("supersedes_input_id") else None,
        is_active=row.get("is_active", True), metadata=meta or {}, input_hash=row["input_hash"]
    )

_INSERT_SQL = (
    "INSERT INTO historical_market_inputs (input_id, scope, ticker, market_scope, concept, value, unit, "
    "observation_date, available_date, provider, source_url, source_methodology, notes, retrieval_timestamp, "
    "batch_id, lookback_period, frequency, levered, debt_method, provenance_quality, source_document_id, "
    "evidence_uri, evidence_hash, revision, supersedes_input_id, is_active, metadata, input_hash) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (input_id) DO UPDATE SET is_active = EXCLUDED.is_active;"
)

def save_historical_market_input(item: HistoricalMarketInput) -> HistoricalMarketInput:
    _MEM_STORE[item.input_hash] = item
    conn = _get_pg_conn()
    if conn:
        with conn:
            with conn.cursor() as cur: cur.execute(_INSERT_SQL, _model_to_db_params(item))
        conn.close()
    _sync_to_file(); return item

def batch_import_historical_market_inputs(items: list[HistoricalMarketInput], batch_id: str | None = None) -> list[HistoricalMarketInput]:
    saved = [raw.model_copy(update={"batch_id": batch_id or raw.batch_id}) for raw in items]
    for item in saved: _MEM_STORE[item.input_hash] = item
    conn = _get_pg_conn()
    if conn:
        with conn:
            with conn.cursor() as cur:
                for item in saved: cur.execute(_INSERT_SQL, _model_to_db_params(item))
        conn.close()
    _sync_to_file(); return saved

def supersede_historical_market_input(old_input_id: UUID | str, new_item: HistoricalMarketInput) -> HistoricalMarketInput:
    old_uuid = UUID(str(old_input_id))
    for k, v in list(_MEM_STORE.items()):
        if v.input_id == old_uuid: _MEM_STORE[k] = v.model_copy(update={"is_active": False})
    revised = new_item.model_copy(update={
        "supersedes_input_id": old_uuid, "revision": new_item.revision if new_item.revision > 1 else 2, "is_active": True
    })
    revised = revised.model_copy(update={"input_hash": revised.compute_hash()})
    _MEM_STORE[revised.input_hash] = revised
    conn = _get_pg_conn()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE historical_market_inputs SET is_active = false WHERE input_id = %s", (str(old_uuid),))
                cur.execute(_INSERT_SQL, _model_to_db_params(revised))
        conn.close()
    _sync_to_file(); return revised

def list_historical_market_inputs(
    scope: InputScope | None = None, ticker: str | None = None, market_scope: str | None = None,
    concept: MarketConcept | None = None, max_available_date: date | None = None, active_only: bool = True
) -> list[HistoricalMarketInput]:
    conn = _get_pg_conn()
    if conn:
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    q = "SELECT * FROM historical_market_inputs WHERE 1=1"
                    params: list[Any] = []
                    if active_only: q += " AND is_active = true"
                    if scope: q += " AND scope = %s"; params.append(scope.value)
                    if ticker: q += " AND (ticker = %s OR ticker IS NULL)"; params.append(ticker.upper())
                    if market_scope: q += " AND market_scope = %s"; params.append(market_scope.upper())
                    if concept: q += " AND concept = %s"; params.append(concept.value)
                    if max_available_date: q += " AND available_date <= %s"; params.append(max_available_date)
                    q += " ORDER BY available_date DESC, revision DESC"
                    cur.execute(q, params); rows = cur.fetchall()
                    return [_row_to_model(r) for r in rows]
        finally: conn.close()
    _load_persisted_file()
    results: list[HistoricalMarketInput] = []
    for item in _MEM_STORE.values():
        if active_only and not item.is_active: continue
        if scope and item.scope != scope: continue
        if ticker and item.scope == InputScope.COMPANY and item.ticker and item.ticker.upper() != ticker.upper(): continue
        if market_scope and item.market_scope.upper() != market_scope.upper(): continue
        if concept and item.concept != concept: continue
        if max_available_date and item.available_date > max_available_date: continue
        results.append(item)
    return sorted(results, key=lambda x: (x.available_date, x.revision), reverse=True)

def _load_persisted_file() -> None:
    if not STORAGE_PATH.is_file(): return
    try:
        for d in json.loads(STORAGE_PATH.read_text(encoding="utf-8")):
            item = HistoricalMarketInput.model_validate(d); _MEM_STORE[item.input_hash] = item
    except Exception: pass

def _sync_to_file() -> None:
    try:
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        items_json = [item.model_dump(mode="json") for item in _MEM_STORE.values()]
        STORAGE_PATH.write_text(json.dumps(items_json, indent=2, default=str), encoding="utf-8")
    except Exception: pass

def clear_historical_market_store_for_tests(clear_db: bool = False) -> None:
    _MEM_STORE.clear()
    if STORAGE_PATH.is_file(): STORAGE_PATH.unlink()
    if clear_db:
        conn = _get_pg_conn()
        if conn:
            with conn:
                with conn.cursor() as cur: cur.execute("DELETE FROM historical_market_inputs;")
            conn.close()
