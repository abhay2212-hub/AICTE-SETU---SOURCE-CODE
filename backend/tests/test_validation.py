# Owner: Dev B
import re
from pathlib import Path

import pytest

from app.core.rule_codes import RULE_SEVERITY, RuleCode
from app.services.validation import mask_apaar, validate_apaar


def test_valid_apaar():
    assert validate_apaar("999912345678", opted_out=False) is None


def test_valid_apaar_with_whitespace():
    assert validate_apaar(" 999912345678 ", opted_out=False) is None


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_opted_out(blank):
    assert validate_apaar(blank, opted_out=True) is RuleCode.APAAR_OPTED_OUT


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_not_opted_out(blank):
    assert validate_apaar(blank, opted_out=False) is RuleCode.APAAR_MISSING


@pytest.mark.parametrize("bad", ["99991234567", "9999123456789", "9999-1234-5678", "ABCD12345678"])
def test_bad_format(bad):
    assert validate_apaar(bad, opted_out=False) is RuleCode.APAAR_FORMAT


def test_value_present_while_opted_out_is_still_checked():
    assert validate_apaar("123", opted_out=True) is RuleCode.APAAR_FORMAT
    assert validate_apaar("999912345678", opted_out=True) is None


def test_mask():
    assert mask_apaar("999912341234") == "XXXX-XXXX-1234"
    assert mask_apaar(None) is None


def test_rule_codes_mirror_shared_doc():
    doc = Path(__file__).resolve().parents[2] / "shared" / "rule-codes.md"
    rows = re.findall(r"^\| `([A-Z_]+)` \| (\w+) \|", doc.read_text(encoding="utf-8"), re.M)
    assert {code: sev for code, sev in rows} == {c.value: s.value for c, s in RULE_SEVERITY.items()}
    assert set(RULE_SEVERITY) == set(RuleCode)
