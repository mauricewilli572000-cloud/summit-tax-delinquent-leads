#!/usr/bin/env python3
"""Summit County, OH tax delinquent leads.

1. Download the Fiscal Office delinquent file (SC720_DELQ) and parcel file (SC705_PARDAT).
2. Keep delinquent parcels owing MIN_DELINQUENT+, excluding government/exempt/utility.
3. Fill missing property addresses from the parcel file, score, merge with earlier runs
   (parcels no longer listed are marked removed), export JSON + GHL CSV.

Usage:
    python run_pipeline.py            # normal (skips if the delinquent file hasn't changed)
    python run_pipeline.py --force
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import shutil
import sys

import config
from src import source, store
from src.schema import LeadRecord
from src.scoring import score

log = logging.getLogger("summit_tax_delinquent")
EXCLUDE_RE = re.compile("|".join(config.EXCLUDE_OWNER_PATTERNS))


def excluded(rec: dict) -> bool:
    luc = re.sub(r"\D", "", rec.get("land_use", ""))[:3]
    if luc and any(lo <= int(luc) <= hi for lo, hi in config.EXCLUDE_LUC_RANGES):
        return True
    return bool(EXCLUDE_RE.search(rec.get("owner_name", "")))


def tape_to_iso(tape: str) -> str:
    try:
        return dt.datetime.strptime(tape.title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return dt.date.today().isoformat()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    today = dt.date.today().isoformat()
    state = json.loads(config.STATE_JSON.read_text()) if config.STATE_JSON.exists() else {}

    links = source.discover_links()
    log.info("Files: %s", links)
    delq_path, delq_modified = source.fetch(config.DELQ_PREFIX, links[config.DELQ_PREFIX], config.RAW_DIR)
    delq, tape = source.read_delinquent(delq_path)
    snapshot = tape_to_iso(tape)
    if snapshot == state.get("snapshot") and not args.force:
        log.info("Delinquent file (%s) already processed - nothing to do (use --force).", snapshot)
        return 0
    current = {p: r for p, r in delq.items()
               if r["delinquent_amount"] >= config.MIN_DELINQUENT and not excluded(r)}
    log.info("Delinquent file %s: %d parcels, %d kept", snapshot, len(delq), len(current))

    par_path, _ = source.fetch(config.PARDAT_PREFIX, links[config.PARDAT_PREFIX], config.RAW_DIR)
    parcels = source.read_parcels(par_path, set(current))
    log.info("Parcel file matched %d of %d", len(parcels), len(current))

    leads = store.load(config.RECORDS_JSON)
    leads.update(store.load(config.PENDING_JSON))
    prev_active = sum(1 for l in leads.values() if l.status == "active")
    if prev_active > 500 and len(current) < 0.3 * prev_active:
        log.error("Only %d delinquent parcels vs %d active before - layout probably changed. Aborting.",
                  len(current), prev_active)
        return 2

    added = 0
    for pid, r in current.items():
        p = parcels.get(pid, {})
        lead = leads.get(pid)
        if lead is None:
            lead = LeadRecord(doc_num=pid, date_added=today)
            leads[pid] = lead
            added += 1
        elif lead.delinquent_amount != r["delinquent_amount"]:
            lead.amount_history.append({"date": snapshot, "amount": r["delinquent_amount"]})
        lead.parcel_id = pid
        lead.owner_name = r["owner_name"]
        lead.mailing_address, lead.mailing_city = r["mailing_address"], r["mailing_city"]
        lead.mailing_state, lead.mailing_zip = r["mailing_state"], r["mailing_zip"]
        lead.property_address = r["property_address"] or p.get("property_address", "")
        lead.property_city = p.get("property_city") or r["district_city"]
        lead.property_zip = p.get("property_zip", "")
        lead.land_use = r["land_use"] or p.get("luc", "")
        lead.tax_year = r["tax_year"]
        lead.delinquent_amount = r["delinquent_amount"]
        lead.amount_owed = r["delinquent_amount"]
        lead.market_value = round(r["taxable_value"] / config.ASSESSMENT_RATIO) if r["taxable_value"] else None
        lead.has_mortgage = r["has_mortgage"]
        lead.lead_type = config.LEAD_TYPE
        lead.county = config.COUNTY
        lead.source_url = links[config.DELQ_PREFIX]
        lead.auditor_url = config.PARCEL_SEARCH_URL
        if not lead.amount_history:
            lead.amount_history.append({"date": snapshot, "amount": r["delinquent_amount"]})
        lead.last_seen = snapshot
        lead.status, lead.removed_date = "active", ""

    removed = 0
    for pid, lead in leads.items():
        if pid not in current and lead.status == "active":
            lead.status, lead.removed_date = "removed", snapshot
            removed += 1
    log.info("Merge: new=%d removed=%d", added, removed)

    for lead in leads.values():
        score(lead)
    with_addr = {k: l for k, l in leads.items() if l.has_address()}
    pending = {k: l for k, l in leads.items() if not l.has_address() and l.status == "active"}
    active = [l for l in with_addr.values() if l.status == "active"]
    meta = {
        "county": config.COUNTY, "lead_type": config.LEAD_TYPE, "source": config.DOWNLOADS_PAGE,
        "snapshot": snapshot, "file_modified": delq_modified,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "active": len(active), "hot": sum(1 for l in active if l.tier == "Hot"),
        "warm": sum(1 for l in active if l.tier == "Warm"),
        "removed": sum(1 for l in with_addr.values() if l.status == "removed"),
        "pending_no_address": len(pending), "added_this_run": added,
        "property_address_found": sum(1 for l in active if l.property_address),
    }
    store.save(config.RECORDS_JSON, with_addr, meta)
    store.save(config.PENDING_JSON, pending, {"note": "active parcels with no address - retried each run"})
    n_csv = store.export_ghl(config.GHL_CSV, with_addr, config.COUNTY)
    shutil.copyfile(config.GHL_CSV, config.DASHBOARD_CSV)
    store.export_dashboard(config.DASHBOARD_JSON, with_addr, meta)
    state.update({"snapshot": snapshot, "file_modified": delq_modified, "last_processed": today})
    config.STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.info("Saved: active=%d (hot %d / warm %d), property address %d, removed=%d, pending=%d, GHL rows=%d",
             meta["active"], meta["hot"], meta["warm"], meta["property_address_found"], meta["removed"],
             len(pending), n_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
