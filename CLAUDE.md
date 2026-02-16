# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Monthly data pipeline that downloads the Nebraska DHHS "Centers for Developmentally Disabled" facility roster PDF, parses it into a date-stamped CSV, and archives both files. Runs automatically on the 16th of each month via GitHub Actions.

## Commands

```bash
# Run the full pipeline (download PDF, parse, validate)
python parse_roster.py

# Run all tests
pytest test_parse_roster.py -v

# Run a single test class
pytest test_parse_roster.py::TestDataQuality -v

# Run a single test
pytest test_parse_roster.py::TestDataQuality::test_phone_format -v
```

## Architecture

`parse_roster.py` is the sole application module. It downloads the PDF, parses it with `pdfplumber`, writes a CSV, and prints validation results. Tests in `test_parse_roster.py` import its functions directly.

**PDF parsing approach:** The roster PDF has no extractable tables. Instead, `pdfplumber` extracts individual words with x/y coordinates. Words are clustered into lines by y-position (within 4pt tolerance), then split into three columns by x-position boundaries (`LEFT_BOUNDARY=310`, `RIGHT_BOUNDARY=400`). Each facility is a fixed 6-line block. If DHHS changes the PDF layout, these boundaries will need recalibration.

**Date-stamped archiving:** Every run produces `pdfs/CDD_Facility_Roster_YYYY-MM-DD.pdf` and `csvs/CDD_Facility_Roster_YYYY-MM-DD.csv`. The GitHub Actions workflow commits and pushes these to build a historical archive.

**Validation:** The PDF contains two independent counts — a summary on page 2 and a "Total Facilities" footer on the last page. The summary page is often stale. Tests validate against the footer and raw PDF bed totals, not the summary page.
