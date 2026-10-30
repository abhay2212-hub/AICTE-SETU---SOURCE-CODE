# Owner: Dev A
import pytest

from engine.blind_match.encoder import dice


def test_identical() -> None:
    a = bytes([0b10110000, 0b00001111])
    assert dice(a, a) == 1.0


def test_disjoint() -> None:
    a = bytes([0b11110000, 0b00000000])
    b = bytes([0b00001111, 0b11111111])
    assert dice(a, b) == 0.0


def test_partial_overlap() -> None:
    a = bytes([0b11110000])  # 4 bits set
    b = bytes([0b11001100])  # 4 bits set, 2 shared
    assert dice(a, b) == pytest.approx(0.5)


def test_both_empty() -> None:
    assert dice(bytes(4), bytes(4)) == 1.0


def test_length_mismatch() -> None:
    with pytest.raises(ValueError):
        dice(bytes(2), bytes(3))
