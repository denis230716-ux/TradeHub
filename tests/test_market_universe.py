from app.market.universe import MarketUniverse


def test_market_universe_collects_assets():
    universe = MarketUniverse()
    assets = universe.update(
        {
            "assets": [
                {"asset": "EURUSD", "isActive": True},
                {"symbol": "GBPJPY_otc", "active": True},
                {"asset": "DISABLED", "isActive": False},
            ]
        }
    )

    assert "EURUSD" in assets
    assert "GBPJPY_otc" in assets
    assert "DISABLED" not in assets


def test_market_universe_deduplicates():
    universe = MarketUniverse(["EURUSD"])
    assert universe.update({"asset": "EURUSD"}) == ("EURUSD",)
