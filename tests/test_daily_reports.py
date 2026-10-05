"""Data-integrity checks run against the real CSSE daily report files."""

from collections import Counter
from datetime import date, timedelta

import pytest

from validators import (
    COUNT_COLUMNS,
    DAILY_REPORTS_DIR,
    daily_report_files,
    missing_columns,
    parse_count,
    parse_filename_date,
    parse_last_update,
    read_report,
    row_errors,
)

REPORT_FILES = daily_report_files()

# First report in the series, and the latest report known to exist; newer
# reports may be added, but the series must not start later or end earlier.
FIRST_REPORT_DATE = date(2020, 1, 22)
MIN_LATEST_REPORT_DATE = date(2020, 3, 16)


def _ids(paths):
    return [p.name for p in paths]


def test_daily_reports_directory_has_csv_files():
    assert DAILY_REPORTS_DIR.is_dir()
    assert REPORT_FILES, "no CSV files found in the daily reports directory"


def test_no_unexpected_files():
    allowed_names = {".gitignore", ".DS_Store"}
    unexpected = [
        p.name
        for p in DAILY_REPORTS_DIR.iterdir()
        if p.is_file() and p.suffix not in {".csv", ".md"} and p.name not in allowed_names
    ]
    assert not unexpected, f"unexpected files in daily reports: {unexpected}"


def test_report_series_endpoints():
    dates = sorted(parse_filename_date(p.name) for p in REPORT_FILES)
    assert dates[0] == FIRST_REPORT_DATE
    assert dates[-1] >= MIN_LATEST_REPORT_DATE


def test_report_dates_are_contiguous():
    dates = sorted(parse_filename_date(p.name) for p in REPORT_FILES)
    missing = []
    for prev, cur in zip(dates, dates[1:]):
        gap = prev + timedelta(days=1)
        while gap < cur:
            missing.append(gap.strftime("%m-%d-%Y"))
            gap += timedelta(days=1)
    assert not missing, f"missing daily reports for: {missing}"


@pytest.mark.parametrize("path", REPORT_FILES, ids=_ids(REPORT_FILES))
class TestDailyReport:
    def test_filename_follows_convention(self, path):
        parse_filename_date(path.name)

    def test_parses_and_has_rows(self, path):
        _, rows = read_report(path)
        assert rows, f"{path.name} has a header but no data rows"

    def test_required_columns_present(self, path):
        header, _ = read_report(path)
        assert missing_columns(header) == []

    def test_rows_are_valid(self, path):
        _, rows = read_report(path)
        problems = [
            f"row {i}: {err}"
            for i, row in enumerate(rows, start=2)
            for err in row_errors(row)
        ]
        assert not problems, "\n".join(problems[:20])

    def test_counts_are_non_negative(self, path):
        _, rows = read_report(path)
        for row in rows:
            for col in COUNT_COLUMNS:
                count = parse_count(row[col])
                assert count is None or count >= 0

    def test_no_duplicate_locations(self, path):
        _, rows = read_report(path)
        keys = Counter(
            (r["Province/State"].strip(), r["Country/Region"].strip()) for r in rows
        )
        dupes = [k for k, n in keys.items() if n > 1]
        assert not dupes, f"duplicate Province/State + Country/Region: {dupes}"

    def test_last_update_not_after_report_date(self, path):
        report_end = parse_filename_date(path.name) + timedelta(days=1)
        _, rows = read_report(path)
        late = [
            r["Last Update"]
            for r in rows
            if parse_last_update(r["Last Update"]).date() >= report_end
        ]
        assert not late, f"Last Update after report date: {late[:5]}"
