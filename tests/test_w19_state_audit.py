"""Literal pins for the Week 19 D1 state audit (`reports/w19_state_audit.md`).

This report is an audit artefact: every number in it was measured on this host, so
the numbers may not drift silently.  The digest pin makes any edit to the report
explicit, and the literal list makes the machine-measured readings greppable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_state_audit.md"

REPORT_SHA256 = (
    "6deeaab6c32eef511336d02677dac654dfc6c8adf71c30f4b5df81cc3e723e1c"
)

# Literals that must survive any rewrite of the audit report.  Left column is the
# reading, right column is the asset or claim it belongs to.
MEASURED_LITERALS = (
    # --- plan input, hashed on this host ---
    "1ba6a239241200aef9f767c5203bd0c6ad0dc7e02d49eea9594f683d39752899",
    "24,077",
    # --- asset table: byte counts and digests ---
    "183,771,012",
    "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d",
    "c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d",
    "d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87",
    "1031abc49ee4f15d46211a519be6b5cdee3b68115e5e2f5141f7d155342ba493",
    "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "da82f748daeccbc9c7c045aa2369085b147c2124693c62dc72994a4cb629f5f4",
    "1,879,361",
    "115,756",
    "248,404",
    "20,753",
    "130,844",
    "42,941",
    "29,519",
    "29515",
    # --- transcript table rulings ---
    "128.941261",
    "18,316",
    "0.1223",
    "0.17662467232470583",
    "0.24935401611452185",
    "0.7349044734023142",
    "76 / 239",
    # --- epsilon >= 60 roster (all nine members) ---
    "N-methylacetamide",
    "vinylene carbonate",
    "formamide",
    "ethylene carbonate",
    "2-hydroxyethylammonium lactate",
    "water",
    "fluoroethylene carbonate",
    "propylene carbonate",
    "ethanolammonium nitrate",
    "178.47",
    "106.14",
    "60.9",
    # --- revision ledger and the kinematic contradiction ---
    "0.17477197208762",
    "0.15698877870055475",
    "0.15686276760094522",
    "214",
    "86",
    "Zhan-Yun",
    "AmanchukwuLab/ElectrolyteGPT",
)


def _report_bytes() -> bytes:
    assert REPORT_PATH.is_file(), f"missing audit report: {REPORT_PATH}"
    return REPORT_PATH.read_bytes()


def test_report_is_lf_utf8_without_bom() -> None:
    payload = _report_bytes()
    assert not payload.startswith(b"\xef\xbb\xbf"), "report must not carry a UTF-8 BOM"
    assert b"\r\n" not in payload, "report must be committed with LF endings"
    assert b"\x00" not in payload
    payload.decode("utf-8")


def test_report_digest_is_pinned() -> None:
    assert hashlib.sha256(_report_bytes()).hexdigest() == REPORT_SHA256


@pytest.mark.parametrize("literal", MEASURED_LITERALS)
def test_measured_literal_is_present(literal: str) -> None:
    assert literal in _report_bytes().decode("utf-8")

