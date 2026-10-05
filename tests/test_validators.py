"""Unit tests for the validation helpers, using synthetic edge-case data."""

from datetime import date, datetime

import pytest

from validators import (
    REQUIRED_COLUMNS,
    daily_report_files,
    missing_columns,
    parse_count,
    parse_filename_date,
    parse_last_update,
    read_report,
    row_errors,
)

HEADER = ",".join(REQUIRED_COLUMNS)


def _row(**overrides):
    row = {
        "Province/State": "Hubei",
        "Country/Region": "Mainland China",
        "Last Update": "2020-03-16T14:38:45",
        "Confirmed": "67798",
        "Deaths": "3099",
        "Recovered": "56003",
    }
    row.update(overrides)
    return row


class TestParseFilenameDate:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("01-22-2020.csv", date(2020, 1, 22)),
            ("02-29-2020.csv", date(2020, 2, 29)),
            ("12-31-2020.csv", date(2020, 12, 31)),
            ("01-01-2021.csv", date(2021, 1, 1)),
        ],
    )
    def test_valid(self, name, expected):
        assert parse_filename_date(name) == expected

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "README.md",
            "2020-01-22.csv",
            "1-22-2020.csv",
            "01-22-20.csv",
            "01-22-2020.CSV",
            "01-22-2020.csv.bak",
            "01_22_2020.csv",
        ],
    )
    def test_wrong_pattern(self, name):
        with pytest.raises(ValueError, match="MM-DD-YYYY"):
            parse_filename_date(name)

    @pytest.mark.parametrize(
        "name", ["13-01-2020.csv", "00-10-2020.csv", "02-30-2020.csv", "02-29-2019.csv"]
    )
    def test_impossible_date(self, name):
        with pytest.raises(ValueError, match="calendar date"):
            parse_filename_date(name)


class TestParseCount:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("0", 0),
            ("1", 1),
            ("67798", 67798),
            (" 42 ", 42),
            ("5.0", 5),
            ("1e3", 1000),
            ("-0", 0),
            ("9007199254740993", 9007199254740993),
            ("12345678901234567890", 12345678901234567890),
        ],
    )
    def test_valid(self, value, expected):
        assert parse_count(value) == expected

    @pytest.mark.parametrize("value", ["", "   "])
    def test_blank_is_not_reported(self, value):
        assert parse_count(value) is None

    @pytest.mark.parametrize(
        "value, message",
        [
            ("-1", "negative"),
            ("-0.5", "whole"),
            ("-1e-30", "whole"),
            ("9007199254740993.5", "whole"),
            ("1.5", "whole"),
            ("abc", "numeric"),
            ("1,000", "numeric"),
            ("nan", "finite"),
            ("inf", "finite"),
            ("-Infinity", "finite"),
        ],
    )
    def test_invalid(self, value, message):
        with pytest.raises(ValueError, match=message):
            parse_count(value)


class TestParseLastUpdate:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1/22/2020 17:00", datetime(2020, 1, 22, 17, 0)),
            ("01/31/2020 23:59", datetime(2020, 1, 31, 23, 59)),
            ("2/1/20 1:52", datetime(2020, 2, 1, 1, 52)),
            ("2020-03-16T14:38:45", datetime(2020, 3, 16, 14, 38, 45)),
            (" 2020-02-29T00:00:00 ", datetime(2020, 2, 29, 0, 0, 0)),
        ],
    )
    def test_valid(self, value, expected):
        assert parse_last_update(value) == expected

    @pytest.mark.parametrize(
        "value", ["", "yesterday", "2020-02-30T00:00:00", "13/01/2020 10:00", "1/22/2020"]
    )
    def test_invalid(self, value):
        with pytest.raises(ValueError, match="Last Update"):
            parse_last_update(value)


class TestReadReport:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "03-16-2020.csv"
        f.write_text(HEADER + "\nHubei,Mainland China,2020-03-16T14:38:45,1,0,0\n")
        header, rows = read_report(f)
        assert header == list(REQUIRED_COLUMNS)
        assert rows == [_row(Confirmed="1", Deaths="0", Recovered="0")]

    def test_strips_utf8_bom(self, tmp_path):
        f = tmp_path / "bom.csv"
        f.write_bytes(("\ufeff" + HEADER + "\n,Japan,2/1/20 1:52,20,,1\n").encode("utf-8"))
        header, rows = read_report(f)
        assert header[0] == "Province/State"
        assert rows[0]["Country/Region"] == "Japan"

    def test_quoted_fields_with_commas(self, tmp_path):
        f = tmp_path / "quoted.csv"
        f.write_text(HEADER + '\n"King County, WA",US,2020-03-01T19:43:03,10,1,0\n')
        _, rows = read_report(f)
        assert rows[0]["Province/State"] == "King County, WA"

    def test_header_only(self, tmp_path):
        f = tmp_path / "header.csv"
        f.write_text(HEADER + "\n")
        assert read_report(f) == (list(REQUIRED_COLUMNS), [])

    def test_blank_lines_skipped(self, tmp_path):
        f = tmp_path / "blank.csv"
        f.write_text(HEADER + "\n\n,Italy,2020-03-01T23:23:02,1694,34,83\n\n")
        _, rows = read_report(f)
        assert len(rows) == 1

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("")
        with pytest.raises(ValueError, match="empty"):
            read_report(f)

    def test_ragged_row(self, tmp_path):
        f = tmp_path / "ragged.csv"
        f.write_text(HEADER + "\nHubei,Mainland China,2020-03-16T14:38:45,1,0\n")
        with pytest.raises(ValueError, match=":2: expected 6 fields, got 5"):
            read_report(f)

    def test_unclosed_quote(self, tmp_path):
        f = tmp_path / "unclosed.csv"
        f.write_text(HEADER + '\nHubei,Mainland China,2020-03-16T14:38:45,1,0,"0\n')
        with pytest.raises(ValueError, match="malformed CSV"):
            read_report(f)

    def test_stray_quote_in_unquoted_field(self, tmp_path):
        f = tmp_path / "stray.csv"
        f.write_text(HEADER + '\nHubei,Mainland China,2020-03-16T14:38:45,"1"x,0,0\n')
        with pytest.raises(ValueError, match=":2: malformed CSV"):
            read_report(f)

    def test_malformed_header(self, tmp_path):
        f = tmp_path / "badhdr.csv"
        f.write_text('"Province/State\n')
        with pytest.raises(ValueError, match=":1: malformed CSV"):
            read_report(f)

    def test_blank_header_name(self, tmp_path):
        f = tmp_path / "blankhdr.csv"
        f.write_text(HEADER + ",\n")
        with pytest.raises(ValueError, match="blank column"):
            read_report(f)

    def test_duplicate_header_name(self, tmp_path):
        f = tmp_path / "duphdr.csv"
        f.write_text(HEADER + ",Deaths\n")
        with pytest.raises(ValueError, match="duplicate"):
            read_report(f)


class TestMissingColumns:
    def test_all_present(self):
        assert missing_columns(list(REQUIRED_COLUMNS)) == []

    def test_extra_columns_allowed(self):
        assert missing_columns(list(REQUIRED_COLUMNS) + ["Latitude", "Longitude"]) == []

    def test_reports_missing_in_order(self):
        assert missing_columns(["Country/Region", "Confirmed"]) == [
            "Province/State",
            "Last Update",
            "Deaths",
            "Recovered",
        ]

    def test_empty_header(self):
        assert missing_columns([]) == list(REQUIRED_COLUMNS)


class TestRowErrors:
    def test_valid_row(self):
        assert row_errors(_row()) == []

    def test_blank_counts_and_province_allowed(self):
        assert row_errors(_row(**{"Province/State": ""}, Deaths="", Recovered="")) == []

    def test_blank_country(self):
        assert row_errors(_row(**{"Country/Region": "  "})) == ["Country/Region is blank"]

    def test_negative_and_malformed_counts(self):
        errors = row_errors(_row(Confirmed="-3", Deaths="x"))
        assert errors == ["Confirmed: '-3' is negative", "Deaths: 'x' is not numeric"]

    def test_bad_last_update(self):
        assert len(row_errors(_row(**{"Last Update": "soon"}))) == 1

    def test_missing_keys(self):
        errors = row_errors({})
        assert "Country/Region is blank" in errors
        assert any(e.startswith("Last Update") for e in errors)

    @pytest.mark.parametrize(
        "lat, lon", [("90", "180"), ("-90", "-180"), ("0", "0"), ("", "")]
    )
    def test_coordinate_boundaries_ok(self, lat, lon):
        assert row_errors(_row(Latitude=lat, Longitude=lon)) == []

    @pytest.mark.parametrize(
        "lat, lon, bad",
        [("90.0001", "0", "Latitude"), ("0", "-180.5", "Longitude"), ("n/a", "0", "Latitude")],
    )
    def test_coordinate_out_of_range(self, lat, lon, bad):
        errors = row_errors(_row(Latitude=lat, Longitude=lon))
        assert len(errors) == 1 and errors[0].startswith(bad)


def test_daily_report_files_only_csv_sorted(tmp_path):
    for name in ["02-01-2020.csv", "01-31-2020.csv", "README.md", ".DS_Store"]:
        (tmp_path / name).write_text("")
    assert [p.name for p in daily_report_files(tmp_path)] == [
        "01-31-2020.csv",
        "02-01-2020.csv",
    ]


def test_daily_report_files_empty_directory(tmp_path):
    assert daily_report_files(tmp_path) == []
