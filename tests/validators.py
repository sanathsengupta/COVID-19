"""Validation helpers for the CSSE daily report CSV files."""

import csv
import re
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DAILY_REPORTS_DIR = REPO_ROOT / "csse_covid_19_data" / "csse_covid_19_daily_reports"

REQUIRED_COLUMNS = (
    "Province/State",
    "Country/Region",
    "Last Update",
    "Confirmed",
    "Deaths",
    "Recovered",
)
COUNT_COLUMNS = ("Confirmed", "Deaths", "Recovered")

FILENAME_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})\.csv$")

# Formats observed in the daily reports; the README documents MM/DD/YYYY HH:mm,
# but earlier files use a 2-digit year and later files use ISO 8601.
LAST_UPDATE_FORMATS = (
    "%m/%d/%Y %H:%M",
    "%m/%d/%y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)


def parse_filename_date(name):
    """Return the date encoded in an MM-DD-YYYY.csv file name."""
    match = FILENAME_RE.match(name)
    if not match:
        raise ValueError(f"{name!r} does not match MM-DD-YYYY.csv")
    month, day, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{name!r} is not a valid calendar date: {exc}") from None


def read_report(path):
    """Parse a daily report CSV, returning (header, rows as dicts).

    Raises ValueError if the file is empty, has blank/duplicate header
    names, or contains rows whose field count differs from the header.
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            raise ValueError(f"{path}: file is empty") from None
        if any(not h for h in header):
            raise ValueError(f"{path}: header contains a blank column name")
        if len(set(header)) != len(header):
            raise ValueError(f"{path}: header contains duplicate column names")
        rows = []
        for line_no, fields in enumerate(reader, start=2):
            if not fields:
                continue
            if len(fields) != len(header):
                raise ValueError(
                    f"{path}:{line_no}: expected {len(header)} fields, got {len(fields)}"
                )
            rows.append(dict(zip(header, fields)))
    return header, rows


def missing_columns(header):
    """Return the required columns absent from header, in canonical order."""
    present = set(header)
    return [col for col in REQUIRED_COLUMNS if col not in present]


def parse_count(value):
    """Parse a case count. Blank means "not reported" and returns None.

    Raises ValueError for non-numeric, fractional or negative values.
    """
    text = value.strip()
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{value!r} is not numeric") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{value!r} is not a finite number")
    if not number.is_integer():
        raise ValueError(f"{value!r} is not a whole number")
    if number < 0:
        raise ValueError(f"{value!r} is negative")
    return int(number)


def parse_last_update(value):
    """Parse a Last Update timestamp in any of the known formats."""
    text = value.strip()
    for fmt in LAST_UPDATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"{value!r} does not match any known Last Update format")


def row_errors(row):
    """Return a list of human-readable problems found in a single row."""
    errors = []
    if not row.get("Country/Region", "").strip():
        errors.append("Country/Region is blank")
    for col in COUNT_COLUMNS:
        try:
            parse_count(row.get(col, ""))
        except ValueError as exc:
            errors.append(f"{col}: {exc}")
    try:
        parse_last_update(row.get("Last Update", ""))
    except ValueError as exc:
        errors.append(f"Last Update: {exc}")
    for col, limit in (("Latitude", 90), ("Longitude", 180)):
        if col not in row or not row[col].strip():
            continue
        try:
            coord = float(row[col])
        except ValueError:
            errors.append(f"{col}: {row[col]!r} is not numeric")
            continue
        if not -limit <= coord <= limit:
            errors.append(f"{col}: {coord} outside [-{limit}, {limit}]")
    return errors


def daily_report_files(directory=DAILY_REPORTS_DIR):
    """Return all CSV files in the daily reports directory, sorted by name."""
    return sorted(Path(directory).glob("*.csv"))
