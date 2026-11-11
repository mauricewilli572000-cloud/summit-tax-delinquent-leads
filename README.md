# Summit County, OH — Tax Delinquent Leads

Motivated-seller leads from Summit County's certified delinquent tax parcels, built like
`hamilton-tax-delinquent-leads` and `franklin-tax-delinquent-leads`.

**Source (Summit County Fiscal Office, official, free):** Data Downloads
(`fiscaloffice.summitoh.net/data-downloads`)
- `SC720_DELQ` — delinquent parcels: owner, tax-bill mailing address, property address,
  certified year, delinquent amount
- `SC705_PARDAT` — parcel situs address/ZIP/city (fills blanks), rental registration

**Outputs:** `docs/index.html` dashboard · `docs/summit_tax_delinquent.json` (read by
ohio-lead-stacker) · `data/ghl_summit_tax_delinquent.csv` for GoHighLevel.

Leads: $250+ delinquent, excluding government, exempt, utility and HOA/condo-association
parcels. Parcels that drop off the file are kept but marked `removed`.

Runs daily (~6:47 AM ET) and only rebuilds when the Fiscal Office posts a new file.
