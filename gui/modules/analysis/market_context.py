"""Price context with explicit units; no valuation calculations."""
from datetime import datetime, timezone


async def fetch_market_averages(since_date, *, until=None):
    from core.db.engine import DBEngine

    until = until or datetime.now(timezone.utc)
    # Retain the existing averaging window and observation weighting. Group by
    # units/currency too: averaging unlike units would be meaningless.
    commodities = await DBEngine.fetch("""
        SELECT commodity, currency, unit, AVG(price) AS value, COUNT(*) AS samples,
               array_agg(id ORDER BY id) AS observation_ids,
               array_agg(DISTINCT source) AS sources,
               MIN(as_of_ts) AS observation_start, MAX(as_of_ts) AS observation_end
        FROM commodity_prices WHERE collected_ts >= $1 AND collected_ts <= $2
        GROUP BY commodity, currency, unit ORDER BY samples DESC, commodity, currency, unit
    """, since_date, until)
    fx = await DBEngine.fetch("""
        SELECT pair, AVG(rate) AS value, COUNT(*) AS samples,
               array_agg(id ORDER BY id) AS observation_ids,
               array_agg(DISTINCT source) AS sources,
               MIN(as_of_ts) AS observation_start, MAX(as_of_ts) AS observation_end
        FROM fx_rates WHERE collected_ts >= $1 AND collected_ts <= $2
        GROUP BY pair ORDER BY samples DESC, pair
    """, since_date, until)
    result = []
    for kind, rows in (("commodity", commodities), ("fx", fx)):
        items = []
        for row in rows:
            item = dict(row)
            item["name"] = item.pop("commodity" if kind == "commodity" else "pair")
            item["value"] = float(item["value"])
            item["supplied_value"] = f"{item['value']:.{2 if kind == 'commodity' else 4}f}"
            if kind == "commodity":
                # DB stores e.g. USD/lb. Keep the original string as well.
                item["stored_unit"] = item.get("unit")
                prefix = f"{item.get('currency')}/"
                if (item.get("unit") or "").startswith(prefix):
                    item["unit"] = item["unit"][len(prefix):]
            else:
                pair = item["name"].replace("/", "").upper()
                item["currency"] = pair[3:] if len(pair) == 6 else None
                item["unit"] = f"{pair[3:]} per {pair[:3]}" if len(pair) == 6 else None
            item.update(price_type="historical average", period_start=str(since_date),
                        period_end=until.isoformat(), averaging_basis="collected_ts",
                        source_id=f"market:{kind}:{len(items)}", kind=kind)
            items.append(item)
        result.append(items)
    return tuple(result)


def format_market_context(commodities, fx, *, limit=10):
    blocks = []
    for item in list(commodities or [])[:limit] + list(fx or [])[:limit]:
        blocks.append(
            f"{item['name']}:\n"
            f"Source ID: {item['source_id']}\n"
            f"Value: {item['supplied_value']}\n"
            f"Currency: {item.get('currency') or 'unresolved'}\n"
            f"Unit: {item.get('unit') or 'unresolved'}\n"
            f"Price type: {item['price_type']}\n"
            f"Period: {item['period_start']} to {item['period_end']}\n"
            f"Samples: {item['samples']}"
        )
    return "\n\n".join(blocks)


def market_audit_sources(commodities, fx):
    """Register only arithmetic actually performed by SQL/Python, never a target."""
    sources = []
    for item in list(commodities or [])[:10] + list(fx or [])[:10]:
        currency, unit = item.get("currency"), item.get("unit")
        sources.append({
            "source_id": item["source_id"], "name": item["name"],
            "source_date": item["period_end"][:10], "supplied_to_model": True,
            "text": format_market_context([item], []),
            "python_calculation": {"operation": "SQL AVG and Python prompt rounding",
                                   "value": item["supplied_value"],
                                   "allowed_units": [unit, f"{currency}/{unit}"]},
        })
    return sources
