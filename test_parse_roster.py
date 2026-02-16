import csv
import os
import re
import tempfile

import pdfplumber
import pytest

from parse_roster import extract_facilities, write_csv, download_pdf, PDF_URL

# Use the most recent PDF in the pdfs/ directory for tests
PDF_DIR = "pdfs"
CSV_DIR = "csvs"


@pytest.fixture(scope="session")
def pdf_path():
    """Find the most recent downloaded PDF."""
    pdfs = sorted(
        f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")
    )
    assert pdfs, "No PDF files found in pdfs/ — run parse_roster.py first"
    return os.path.join(PDF_DIR, pdfs[-1])


@pytest.fixture(scope="session")
def date_str(pdf_path):
    """Extract the date string from the PDF filename."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(pdf_path))
    assert m, f"Could not extract date from {pdf_path}"
    return m.group(1)


@pytest.fixture(scope="session")
def facilities(pdf_path, date_str):
    """Parse facilities from the PDF once for all tests."""
    return extract_facilities(pdf_path, date_str)


@pytest.fixture(scope="session")
def pdf_footer_count(pdf_path):
    """Extract the Total Facilities count from the last page footer."""
    pdf = pdfplumber.open(pdf_path)
    text = pdf.pages[-1].extract_text()
    pdf.close()
    m = re.search(r"Total Facilities:\s*(\d+)", text)
    return int(m.group(1)) if m else None


@pytest.fixture(scope="session")
def pdf_bed_total(pdf_path):
    """Sum all bed counts directly from PDF text."""
    pdf = pdfplumber.open(pdf_path)
    total = 0
    for page in pdf.pages[2:]:
        for m in re.finditer(r"Total Licensed\s*-\s*(\d+)", page.extract_text()):
            total += int(m.group(1))
    pdf.close()
    return total


# ---------------------------------------------------------------------------
# PDF structure tests
# ---------------------------------------------------------------------------

class TestPDFStructure:
    def test_pdf_has_minimum_pages(self, pdf_path):
        pdf = pdfplumber.open(pdf_path)
        assert len(pdf.pages) >= 4, "PDF should have at least 4 pages (cover, summary, 2+ data)"
        pdf.close()

    def test_summary_page_has_counts(self, pdf_path):
        pdf = pdfplumber.open(pdf_path)
        text = pdf.pages[1].extract_text()
        pdf.close()
        assert re.search(
            r"Centers for Persons with Developmental Disabilities\s+\d+\s+\d+", text
        ), "Summary page should contain facility and bed counts"

    def test_data_pages_have_header(self, pdf_path):
        pdf = pdfplumber.open(pdf_path)
        for page in pdf.pages[2:]:
            text = page.extract_text()
            assert "FACILITY ROSTER" in text, f"Data page missing header"
        pdf.close()

    def test_last_page_has_total_footer(self, pdf_footer_count):
        assert pdf_footer_count is not None, "Last page should have 'Total Facilities: N' footer"
        assert pdf_footer_count > 0


# ---------------------------------------------------------------------------
# Parsing tests — facility count and completeness
# ---------------------------------------------------------------------------

class TestFacilityCount:
    def test_facilities_not_empty(self, facilities):
        assert len(facilities) > 0

    def test_facility_count_matches_pdf_footer(self, facilities, pdf_footer_count):
        assert len(facilities) == pdf_footer_count, (
            f"Parsed {len(facilities)} facilities but PDF footer says {pdf_footer_count}"
        )

    def test_bed_total_matches_pdf(self, facilities, pdf_bed_total):
        actual = sum(int(f["Licensed Beds"]) for f in facilities if f["Licensed Beds"])
        assert actual == pdf_bed_total, (
            f"Parsed bed total {actual} doesn't match PDF text total {pdf_bed_total}"
        )

    def test_no_duplicate_license_numbers(self, facilities):
        license_nos = [f["License No"] for f in facilities]
        duplicates = [ln for ln in license_nos if license_nos.count(ln) > 1]
        assert not duplicates, f"Duplicate license numbers: {set(duplicates)}"


# ---------------------------------------------------------------------------
# Data quality tests — every row should have valid values
# ---------------------------------------------------------------------------

class TestDataQuality:
    REQUIRED_FIELDS = [
        "Date Parsed",
        "Town",
        "County",
        "Zip Code",
        "Facility Name",
        "Address",
        "Phone",
        "Licensee",
        "Administration",
        "Facility Type",
        "License No",
        "Licensed Beds",
    ]

    def test_all_required_fields_present(self, facilities):
        for f in facilities:
            for field in self.REQUIRED_FIELDS:
                assert field in f, f"Missing field '{field}' in facility {f.get('License No', '?')}"

    def test_no_empty_required_fields(self, facilities):
        for f in facilities:
            for field in self.REQUIRED_FIELDS:
                assert f[field], (
                    f"Empty '{field}' for facility {f['License No']}"
                )

    def test_date_parsed_format(self, facilities):
        for f in facilities:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", f["Date Parsed"]), (
                f"Bad date format: {f['Date Parsed']}"
            )

    def test_zip_code_format(self, facilities):
        for f in facilities:
            assert re.match(r"^\d{5}$", f["Zip Code"]), (
                f"Bad zip code '{f['Zip Code']}' for {f['License No']}"
            )

    def test_license_no_format(self, facilities):
        for f in facilities:
            assert re.match(r"^CDD\d+$", f["License No"]), (
                f"Bad license number '{f['License No']}'"
            )

    def test_phone_format(self, facilities):
        for f in facilities:
            assert re.match(r"^\(\d{3}\) \d{3}-\d{4}$", f["Phone"]), (
                f"Bad phone '{f['Phone']}' for {f['License No']}"
            )

    def test_facility_type_is_cdd(self, facilities):
        for f in facilities:
            assert f["Facility Type"] == "CDD", (
                f"Unexpected facility type '{f['Facility Type']}' for {f['License No']}"
            )

    def test_licensed_beds_is_nonnegative_integer(self, facilities):
        for f in facilities:
            assert f["Licensed Beds"].isdigit(), (
                f"Beds '{f['Licensed Beds']}' not a number for {f['License No']}"
            )
            assert int(f["Licensed Beds"]) >= 0

    def test_town_is_uppercase(self, facilities):
        for f in facilities:
            assert f["Town"] == f["Town"].upper(), (
                f"Town '{f['Town']}' should be uppercase for {f['License No']}"
            )

    def test_county_is_uppercase(self, facilities):
        for f in facilities:
            assert f["County"] == f["County"].upper(), (
                f"County '{f['County']}' should be uppercase for {f['License No']}"
            )


# ---------------------------------------------------------------------------
# CSV round-trip test — write and read back
# ---------------------------------------------------------------------------

class TestCSVOutput:
    def test_csv_round_trip(self, facilities, date_str):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = write_csv(facilities, tmpdir, date_str)
            assert os.path.exists(csv_path)
            assert date_str in os.path.basename(csv_path)

            with open(csv_path) as f:
                reader = list(csv.DictReader(f))

            assert len(reader) == len(facilities)

            # Verify every field survives the round trip
            for orig, loaded in zip(facilities, reader):
                for key in orig:
                    assert orig[key] == loaded[key], (
                        f"Mismatch in '{key}' for {orig['License No']}: "
                        f"'{orig[key]}' vs '{loaded[key]}'"
                    )

    def test_csv_filename_contains_date(self, date_str):
        csvs = [f for f in os.listdir(CSV_DIR) if f.endswith(".csv")]
        assert any(date_str in f for f in csvs), (
            f"No CSV file found with date {date_str} in {CSV_DIR}"
        )


# ---------------------------------------------------------------------------
# Download test
# ---------------------------------------------------------------------------

class TestDownload:
    def test_download_produces_valid_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = download_pdf(PDF_URL, tmpdir, "test")
            assert os.path.exists(path)
            assert os.path.getsize(path) > 10000, "PDF file too small — download may have failed"
            pdf = pdfplumber.open(path)
            assert len(pdf.pages) >= 4
            pdf.close()
