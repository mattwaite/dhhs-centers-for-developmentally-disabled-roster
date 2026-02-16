import pdfplumber
import csv
import re
import os
import shutil
import urllib.request
from datetime import date

PDF_URL = "https://dhhs.ne.gov/licensure/Documents/CDD%20Facility%20Roster.pdf"
PDF_DIR = "pdfs"
CSV_DIR = "csvs"

# Column boundaries based on word x-positions in the PDF:
#   Left block (x < ~310): town/name/address/phone/licensee/admin
#   Middle block (~310-400): fac type / license no
#   Right block (x > ~400): beds info
LEFT_BOUNDARY = 310
RIGHT_BOUNDARY = 400


def download_pdf(url, pdf_dir, date_str):
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"CDD_Facility_Roster_{date_str}.pdf")
    urllib.request.urlretrieve(url, pdf_path)
    print(f"Downloaded PDF to {pdf_path}")
    return pdf_path


def extract_facilities(pdf_path, date_str):
    facilities = []
    pdf = pdfplumber.open(pdf_path)

    # Data pages start at page index 2 (PDF page 3) through the end
    for page in pdf.pages[2:]:
        words = page.extract_words(x_tolerance=3, y_tolerance=3)
        if not words:
            continue

        # Group words into lines by y-position using clustering
        # Words on the same visual line can differ by ~2pt in top position
        sorted_words = sorted(words, key=lambda w: w["top"])
        lines_dict = {}
        y_keys = []
        for w in sorted_words:
            matched = False
            for yk in y_keys:
                if abs(w["top"] - yk) <= 4:
                    lines_dict[yk].append(w)
                    matched = True
                    break
            if not matched:
                y_keys.append(w["top"])
                lines_dict[w["top"]] = [w]

        sorted_y_keys = sorted(y_keys)

        # Build lines with left/middle/right columns
        lines = []
        for y_key in sorted_y_keys:
            line_words = sorted(lines_dict[y_key], key=lambda w: w["x0"])
            left = " ".join(
                w["text"] for w in line_words if w["x0"] < LEFT_BOUNDARY
            )
            mid = " ".join(
                w["text"]
                for w in line_words
                if LEFT_BOUNDARY <= w["x0"] < RIGHT_BOUNDARY
            )
            right = " ".join(
                w["text"] for w in line_words if w["x0"] >= RIGHT_BOUNDARY
            )
            lines.append((left.strip(), mid.strip(), right.strip()))

        # Skip header lines - find where data starts
        # Data lines start with TOWN pattern: ALLCAPS (ALLCAPS) - ZIPCODE
        town_pattern = re.compile(
            r"^([A-Z][A-Z .]+?)\s+\(([A-Z ]+)\)\s*-\s*(\d{5})"
        )

        i = 0
        # Skip header lines until we hit first town
        while i < len(lines):
            if town_pattern.match(lines[i][0]):
                break
            i += 1

        # Parse facility blocks - each is 6 lines:
        #   0: TOWN (COUNTY) - ZIP    | CDD        | Total Licensed - N
        #   1: Facility Name          | License No  |
        #   2: Address                |             |
        #   3: Phone FAX:Fax          |             |
        #   4: Licensee               |             |
        #   5: Administration         |             |
        while i < len(lines):
            left, mid, right = lines[i]

            # Check for "Total Facilities:" footer line
            if "Total Facilities" in left:
                break

            town_match = town_pattern.match(left)
            if not town_match:
                i += 1
                continue

            town = town_match.group(1).strip()
            county = town_match.group(2).strip()
            zip_code = town_match.group(3).strip()
            fac_type = mid.strip()

            # Parse beds from right column: "Total Licensed - N"
            beds_match = re.search(r"Total Licensed\s*-\s*(\d+)", right)
            beds = beds_match.group(1) if beds_match else ""

            # Next lines
            if i + 5 >= len(lines):
                # Not enough lines for a full record, gather what we can
                facility_name = lines[i + 1][0] if i + 1 < len(lines) else ""
                license_no = lines[i + 1][1] if i + 1 < len(lines) else ""
                address = lines[i + 2][0] if i + 2 < len(lines) else ""
                phone_line = lines[i + 3][0] if i + 3 < len(lines) else ""
                licensee = lines[i + 4][0] if i + 4 < len(lines) else ""
                admin = ""
                i += 6
            else:
                facility_name = lines[i + 1][0]
                license_no = lines[i + 1][1]
                address = lines[i + 2][0]
                phone_line = lines[i + 3][0]
                licensee = lines[i + 4][0]
                admin = lines[i + 5][0]
                i += 6

            # Parse phone and fax
            phone_match = re.match(
                r"([\(\d\)\- ]+?)\s*FAX:\s*(.*)", phone_line
            )
            if phone_match:
                phone = phone_match.group(1).strip()
                fax = phone_match.group(2).strip()
            else:
                phone = phone_line.strip()
                fax = ""

            facilities.append(
                {
                    "Date Parsed": date_str,
                    "Town": town,
                    "County": county,
                    "Zip Code": zip_code,
                    "Facility Name": facility_name,
                    "Address": address,
                    "Phone": phone,
                    "FAX": fax,
                    "Licensee": licensee,
                    "Administration": admin,
                    "Facility Type": fac_type,
                    "License No": license_no,
                    "Licensed Beds": beds,
                }
            )

    pdf.close()
    return facilities


def write_csv(facilities, csv_dir, date_str):
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, f"CDD_Facility_Roster_{date_str}.csv")
    fieldnames = [
        "Date Parsed",
        "Town",
        "County",
        "Zip Code",
        "Facility Name",
        "Address",
        "Phone",
        "FAX",
        "Licensee",
        "Administration",
        "Facility Type",
        "License No",
        "Licensed Beds",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(facilities)
    return csv_path


def validate_counts(facilities, pdf_path):
    pdf = pdfplumber.open(pdf_path)

    # Extract expected counts from summary page (page 2)
    summary_text = pdf.pages[1].extract_text()
    match = re.search(
        r"Centers for Persons with Developmental Disabilities\s+(\d+)\s+(\d+)",
        summary_text,
    )
    if not match:
        print("WARNING: Could not parse summary counts from page 2")
        return

    expected_facilities = int(match.group(1))
    expected_beds = int(match.group(2))

    # Extract "Total Facilities" from last page footer
    last_page_text = pdf.pages[-1].extract_text()
    footer_match = re.search(r"Total Facilities:\s*(\d+)", last_page_text)
    footer_facilities = int(footer_match.group(1)) if footer_match else None

    # Count beds directly from PDF text for cross-check
    pdf_beds = 0
    for page in pdf.pages[2:]:
        for m in re.finditer(r"Total Licensed\s*-\s*(\d+)", page.extract_text()):
            pdf_beds += int(m.group(1))

    pdf.close()

    actual_facilities = len(facilities)
    actual_beds = sum(int(f["Licensed Beds"]) for f in facilities if f["Licensed Beds"])

    print("=== Validation ===")
    print(f"Summary page (p2):    {expected_facilities} facilities, {expected_beds} beds")
    if footer_facilities is not None:
        print(f"Last page footer:     {footer_facilities} facilities")
    print(f"Raw PDF bed totals:   {pdf_beds} beds")
    print(f"Parsed CSV:           {actual_facilities} facilities, {actual_beds} beds")
    print()

    if footer_facilities is not None and actual_facilities == footer_facilities:
        print(f"Facility count matches last-page footer ({footer_facilities}).")
    if actual_facilities == expected_facilities:
        print("Facility count matches summary page.")
    else:
        print(
            f"Facility count ({actual_facilities}) differs from summary page "
            f"({expected_facilities}). The summary page may be outdated — the "
            f"PDF's own footer says {footer_facilities}."
        )

    if actual_beds == expected_beds:
        print("Bed count matches summary page.")
    elif actual_beds == pdf_beds:
        print(
            f"Bed count ({actual_beds}) matches raw PDF data but differs from "
            f"summary page ({expected_beds}). The summary page may be outdated."
        )
    else:
        print(f"Bed count: MISMATCH — parsed {actual_beds}, PDF text {pdf_beds}, summary {expected_beds}")


if __name__ == "__main__":
    date_str = date.today().strftime("%Y-%m-%d")

    pdf_path = download_pdf(PDF_URL, PDF_DIR, date_str)
    facilities = extract_facilities(pdf_path, date_str)
    csv_path = write_csv(facilities, CSV_DIR, date_str)
    print(f"Wrote {len(facilities)} facilities to {csv_path}")
    print()
    validate_counts(facilities, pdf_path)
