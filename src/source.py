"""Download and parse the Summit County Fiscal Office delinquent + parcel files."""
from __future__ import annotations

import csv
import io
import logging
import re
import time
import urllib.parse
import zipfile
from pathlib import Path

import config

log = logging.getLogger(__name__)
csv.field_size_limit(10_000_000)

try:
    from curl_cffi import requests as _http
    _SESSION = _http.Session(impersonate="chrome")
except Exception:  # pragma: no cover
    import requests as _http
    _SESSION = _http.Session()
    _SESSION.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"


def get(url: str):
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            r = _SESSION.get(url, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def discover_links() -> dict[str, str]:
    """{prefix: url} for the delinquent and parcel files (newest suffix wins)."""
    found = {p: config.FILES_BASE + f for p, f in config.FALLBACK_FILES.items()}
    try:
        html = get(config.DOWNLOADS_PAGE).text
        for prefix in (config.DELQ_PREFIX, config.PARDAT_PREFIX):
            links = sorted(set(re.findall(rf'href="([^"]*{prefix}_\d+\.zip)"', html, re.I)))
            if links:
                found[prefix] = urllib.parse.urljoin(config.DOWNLOADS_PAGE, links[-1])
    except Exception as e:  # noqa: BLE001
        log.warning("Downloads page unavailable, using fallback file names: %s", e)
    return found


def fetch(prefix: str, url: str, raw_dir: Path) -> tuple[Path, str]:
    """Download a zip, extract its single CSV. Returns (csv path, last-modified)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = get(url)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        member = next(i for i in z.infolist() if i.filename.lower().endswith(".csv"))
        out = raw_dir / f"{prefix}.csv"
        with z.open(member) as src, out.open("wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
    return out, r.headers.get("last-modified", "")


def clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def num(v) -> float:
    try:
        return float(clean(v).replace(",", "") or 0)
    except ValueError:
        return 0.0


def rows(path: Path):
    with path.open(encoding="latin-1", newline="") as f:
        yield from csv.DictReader(f)


def norm_parcel(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return d.zfill(7) if d else ""


def district_city(district: str) -> str:
    """'AKRON CITY-AKRON CSD' / 'AKRON CITY AKRON CSD' -> 'Akron'; 'COPLEY TWP-REVERE LSD' -> 'Copley Twp'."""
    d = re.split(r"\s*-\s*", clean(district).upper())[0]
    d = re.sub(r"\s+\S+\s+(CSD|LSD|EVSD|SD)$", "", d)
    d = re.sub(r"\s+(CITY|VIL|VILLAGE)$", "", d)
    return d.strip().title()


def read_delinquent(path: Path) -> tuple[dict[str, dict], str]:
    """SC720_DELQ.csv -> ({parcel: record}, tape date)."""
    out, tape = {}, ""
    for r in rows(path):
        pid = norm_parcel(r.get("PARCEL"))
        if not pid:
            continue
        tape = tape or clean(r.get("TAPE_CREATE_DATE"))
        amt = num(r.get("DLQ_AMOUNT"))
        bill = clean(r.get("TAXBILL_ADDRESS"))
        if bill:      # the tax bill address is where mail actually goes
            mail = (bill, clean(r.get("TAXBILL_CITY")), clean(r.get("TAXBILL_STATE")), clean(r.get("TAXBILL_ZIPCD1")))
        else:
            mail = (clean(r.get("OWNER_ADDRESS")), clean(r.get("OWNER_CITY")), clean(r.get("OWNER_STATE")),
                    clean(r.get("OWNER_ZIPCD1")))
        district = clean(r.get("DISTRICT_NAME"))
        rec = out.get(pid)
        if rec:       # a parcel can appear once per certified year - sum the amounts
            rec["delinquent_amount"] = round(rec["delinquent_amount"] + amt, 2)
            yr = clean(r.get("CERTIFIED_YR"))
            if yr and (not rec["tax_year"] or yr < rec["tax_year"]):
                rec["tax_year"] = yr
            continue
        out[pid] = {
            "owner_name": clean(r.get("OWNER")),
            "mailing_address": mail[0].strip(" ,"), "mailing_city": mail[1], "mailing_state": mail[2],
            "mailing_zip": mail[3][:5],
            "property_address": clean(r.get("PROPERTY_ADDRESS")),
            "district_city": district_city(district),
            "land_use": clean(r.get("LUC")),
            "tax_year": clean(r.get("CERTIFIED_YR")),
            "delinquent_amount": round(amt, 2),
            "taxable_value": num(r.get("TAX_VAL")),
            "has_mortgage": bool(clean(r.get("MORTCO"))),
            "legal": " ".join(x for x in (clean(r.get("LEGAL_DESC1")), clean(r.get("LEGAL_DESC2"))) if x),
        }
    return out, tape


def read_parcels(path: Path, wanted: set[str]) -> dict[str, dict]:
    """SC705_PARDAT.csv -> {parcel: situs address, zip, city, rental} for wanted parcels (latest tax year)."""
    out: dict[str, tuple[str, dict]] = {}
    for r in rows(path):
        pid = norm_parcel(r.get("PARCEL"))
        if pid not in wanted:
            continue
        yr = clean(r.get("TAXYR"))
        if pid in out and out[pid][0] >= yr:
            continue
        parts = [clean(r.get(k)) for k in ("ADRNO", "ADRADD", "ADRDIR", "ADRSTR", "ADRSUF")]
        addr = " ".join(p for p in parts if p)
        if not re.match(r"^\d", addr):
            addr = ""
        # The file's header is misaligned after column 40: the ZIP is under "USER2" and
        # the city under "UDATE1" (checked against the 30-OCT-2026 file). Fall back to the
        # labelled columns if a later file fixes the header.
        zipc = next((z for z in (clean(r.get("USER2")), clean(r.get("ZIPCD")))
                     if re.fullmatch(r"\d{5}(-\d{4})?", z)), "")
        city = next((c for c in (clean(r.get("UDATE1")), clean(r.get("CITY")))
                     if c and not re.search(r"\d", c)), "")
        out[pid] = (yr, {
            "property_address": addr,
            "property_zip": zipc[:5],
            "property_city": city.title(),
            "luc": clean(r.get("LUC")),
        })
    return {k: v for k, (_, v) in out.items()}
