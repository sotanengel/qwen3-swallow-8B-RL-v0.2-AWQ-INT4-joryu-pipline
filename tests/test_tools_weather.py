"""tools_impl.weather のテスト。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from joryu.tools_impl import weather as weather_mod


@respx.mock
def test_weather_fn_calls_geocoding_then_forecast(monkeypatch) -> None:
    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setattr(weather_mod, "now_jst", lambda: fixed)
    respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"name": "東京", "latitude": 35.68, "longitude": 139.76}],
            },
        )
    )
    respx.get(weather_mod.FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "daily": {
                    "weathercode": [1],
                    "temperature_2m_max": [31.0],
                    "temperature_2m_min": [24.0],
                    "precipitation_probability_max": [20],
                }
            },
        )
    )
    out = weather_mod.fetch_weather("東京")
    assert "東京" in out
    assert "2026-06-27" in out
    assert "31" in out


def test_weather_fn_validates_location() -> None:
    with pytest.raises(ValueError, match="location"):
        weather_mod.fetch_weather("  ")


@respx.mock
def test_weather_fn_handles_geocoding_404(monkeypatch) -> None:
    respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    with pytest.raises(ValueError, match="not found"):
        weather_mod.fetch_weather("UnknownCityXYZ")


@respx.mock
def test_weather_fn_default_date_is_today_jst(monkeypatch) -> None:
    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setattr(weather_mod, "now_jst", lambda: fixed)
    respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"name": "東京", "latitude": 35.68, "longitude": 139.76}]},
        )
    )
    route = respx.get(weather_mod.FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "daily": {
                    "weathercode": [0],
                    "temperature_2m_max": [30.0],
                    "temperature_2m_min": [22.0],
                    "precipitation_probability_max": [10],
                }
            },
        )
    )
    weather_mod.fetch_weather("東京")
    assert route.calls.last.request.url.params["start_date"] == "2026-06-27"
