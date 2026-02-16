# Nebraska Centers for Developmentally Disabled — Facility Roster

This repository tracks the Nebraska DHHS [Centers for Developmentally Disabled Facility Roster](https://dhhs.ne.gov/licensure/Documents/CDD%20Facility%20Roster.pdf) over time by downloading and parsing the PDF into CSV on a monthly basis.

## Data

Each monthly run produces two date-stamped files:

- `pdfs/CDD_Facility_Roster_YYYY-MM-DD.pdf` — archived copy of the source PDF
- `csvs/CDD_Facility_Roster_YYYY-MM-DD.csv` — parsed facility data

### CSV columns

| Column | Description |
|---|---|
| Date Parsed | Date the PDF was downloaded and parsed |
| Town | City where the facility is located |
| County | County name |
| Zip Code | 5-digit zip code |
| Facility Name | Name of the facility |
| Address | Street address |
| Phone | Phone number |
| FAX | Fax number (may be empty) |
| Licensee | Organization that holds the license |
| Administration | Administrator name |
| Facility Type | License type (always CDD) |
| License No | DHHS license number (e.g., CDD001) |
| Licensed Beds | Number of licensed beds |

## How it works

The roster PDF is published by the Nebraska DHHS Division of Public Health, Licensure Unit. It has no extractable tables, so the parser uses [pdfplumber](https://github.com/jsvine/pdfplumber) to extract word positions and reconstructs the tabular data from x/y coordinates.

A GitHub Actions workflow runs on the 16th of each month, downloads the latest PDF, parses it, runs the test suite, and commits the results.

## Running locally

```bash
pip install -r requirements.txt

# Download, parse, and validate
python parse_roster.py

# Run tests
pytest test_parse_roster.py -v
```

## Data source

Nebraska Department of Health and Human Services, Division of Public Health, Licensure Unit
https://dhhs.ne.gov/Pages/Public-Health-Licensure.aspx
