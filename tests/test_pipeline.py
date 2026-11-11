from pathlib import Path

import run_pipeline
from src import source

FX = Path(__file__).parent / "fixtures"


def test_delinquent_file():
    delq, tape = source.read_delinquent(FX / "SC720_DELQ.csv")
    assert tape == "30-OCT-2026" and run_pipeline.tape_to_iso(tape) == "2026-10-30"
    r = delq["0102701"]
    assert (r["mailing_address"], r["mailing_state"]) == ("4312 SAVANNAH TRAIL", "GA")   # tax-bill address wins
    assert r["delinquent_amount"] == 12966.51 and r["tax_year"] == "2012"
    assert delq["0101379"]["district_city"] == "Barberton"
    assert run_pipeline.excluded(delq["6800001"])


def test_parcel_file_fills_property_address():
    p = source.read_parcels(FX / "SC705_PARDAT.CSV", {"0101379", "0102701"})
    assert p["0101379"]["property_address"] == "122 JOSEPH AVE"          # latest tax year wins
    assert (p["0102701"]["property_zip"], p["0102701"]["property_city"]) == ("44203", "Barberton")


def test_district_city():
    assert source.district_city("AKRON CITY-AKRON CSD") == "Akron"
    assert source.district_city("AKRON CITY AKRON CSD") == "Akron"
    assert source.district_city("COPLEY TWP-REVERE LSD") == "Copley Twp"
