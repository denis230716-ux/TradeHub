import json

from tools.pocket_option_signal_probe import compact_signal


def test_compact_signal_keeps_known_fields():
    result = compact_signal(
        {
            "asset": "CSCO_otc",
            "direction": "CALL",
            "confidence": 64,
            "payout": 86,
            "internal": "ignored",
        }
    )

    assert result == {
        "asset": "CSCO_otc",
        "direction": "CALL",
        "confidence": 64,
        "payout": 86,
    }


def test_compact_signal_reports_unknown_keys():
    assert compact_signal(
        {
            "foo": 1,
            "bar": 2,
        }
    ) == {
        "data_type": "dict",
        "keys": ["bar", "foo"],
    }


def test_compact_signal_is_json_serializable():
    result = compact_signal(["CALL", "EURJPY_otc"])

    json.dumps(result)

    assert result["length"] == 2
