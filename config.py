"""
Summit County, OH - Tax Delinquent lead scraper configuration.

Source: Summit County Fiscal Office "Data Downloads" (official CAMA exports, no login)
  https://fiscaloffice.summitoh.net/data-downloads
    SC720_DELQ_*.zip    delinquent parcels: owner, owner + tax-bill mailing address,
                        property address, land use, CERTIFIED_YR, DLQ_AMOUNT, taxable value
    SC705_PARDAT_*.zip  parcel data: situs address parts, ZIP, city, rental registration
"""
from pathlib import Path

COUNTY = "Summit"
STATE = "OH"
LEAD_TYPE = "Tax Delinquent"

DOWNLOADS_PAGE = "https://fiscaloffice.summitoh.net/data-downloads"
FILES_BASE = "https://fiscaloffice.summitoh.net/sites/default/files/assets/forms/"
# File name prefixes; the numeric suffix changes over time, so links are discovered
# on DOWNLOADS_PAGE and these are the fallbacks.
DELQ_PREFIX = "SC720_DELQ"
PARDAT_PREFIX = "SC705_PARDAT"
FALLBACK_FILES = {DELQ_PREFIX: "SC720_DELQ_5.zip", PARDAT_PREFIX: "SC705_PARDAT_4.zip"}

PARCEL_SEARCH_URL = "https://propertyaccess.summitoh.net/search/commonsearch.aspx?mode=realprop"

HTTP_TIMEOUT = 300
HTTP_RETRIES = 4

# Ohio taxable value is 35% of market value.
ASSESSMENT_RATIO = 0.35

MIN_DELINQUENT = 250.00
EXCLUDE_LUC_RANGES = [(600, 699), (800, 899)]
EXCLUDE_OWNER_PATTERNS = [
    r"\bCITY OF\b", r"\bVILLAGE OF\b", r"\bTOWNSHIP\b", r"\bBOARD OF\b", r"\bCOUNTY OF SUMMIT\b",
    r"\bSUMMIT COUNTY\b", r"\bSTATE OF OHIO\b", r"\bUNITED STATES\b", r"\bLAND REUTILIZATION\b",
    r"\bLAND BANK\b", r"\bPORT AUTHORITY\b", r"\bMETROPOLITAN HOUSING\b", r"\bSCHOOL DIST",
    r"\bRAILROAD\b", r"\bRAILWAY\b", r"\bBOARD OF EDUCATION\b", r"\bHOMEOWNERS\b", r"\bCONDOMINIUM ASSOC",
    r"\bCONDO ASSOC",
]

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
RECORDS_JSON = DATA_DIR / "records.json"
PENDING_JSON = DATA_DIR / "pending_records.json"
STATE_JSON = DATA_DIR / "state.json"
GHL_CSV = DATA_DIR / "ghl_summit_tax_delinquent.csv"
DASHBOARD_JSON = DOCS_DIR / "summit_tax_delinquent.json"
DASHBOARD_CSV = DOCS_DIR / "summit_tax_delinquent_ghl.csv"
