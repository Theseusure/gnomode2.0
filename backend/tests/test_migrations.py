from app.migrations import _flap, _pons


def test_pons_requires_confirmed_graduation():
    base = {
        "token": "0x1111111111111111111111111111111111111111",
        "name": "One",
        "symbol": "ONE",
        "pool": "0x2222222222222222222222222222222222222222",
    }
    assert _pons({**base, "graduated": False}) is None
    token = _pons(
        {
            **base,
            "graduated": True,
            "graduatedAt": "2026-07-30T01:31:46.689Z",
        }
    )
    assert token is not None
    assert token["launchpad"] == "pons"
    assert token["verification"] == "official_indexer"


def test_flap_decodes_launched_to_dex_payload():
    token = "11" * 20
    pool = "22" * 20
    row = {
        "data": "0x" + "0" * 24 + token + "0" * 24 + pool,
        "timeStamp": hex(1_785_375_000),
        "transactionHash": "0x" + "ab" * 32,
    }
    decoded = _flap(row)
    assert decoded is not None
    assert decoded["address"].lower() == "0x" + token
    assert decoded["pool_address"].lower() == "0x" + pool
    assert decoded["verification"] == "onchain"
