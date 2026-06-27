"""tools_impl.weather の拡張テスト (#203)。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from joryu.tools_impl import weather as weather_mod


@pytest.fixture(autouse=True)
def _reset_weather_state(monkeypatch: pytest.MonkeyPatch) -> None:
    weather_mod._geocode_location.cache_clear()
    weather_mod.apply_weather_config(timeout=5.0, provider="open_meteo")
    monkeypatch.delenv("JORYU_WEATHER_TIMEOUT", raising=False)
    monkeypatch.delenv("JORYU_WEATHER_PROVIDER", raising=False)


def _mock_open_meteo_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setattr(weather_mod, "now_jst", lambda: fixed)
    respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"name": "東京", "latitude": 35.68, "longitude": 139.76}]},
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


@respx.mock
def test_weather_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_open_meteo_success(monkeypatch)
    out = weather_mod.fetch_weather("東京")
    assert "東京" in out
    assert "2026-06-27" in out
    assert "31" in out


@respx.mock
def test_weather_timeout_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_WEATHER_TIMEOUT", "0.001")
    respx.get(weather_mod.GEOCODING_URL).mock(side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(ValueError, match="weather upstream timeout"):
        weather_mod.fetch_weather("東京")


@respx.mock
def test_weather_5xx_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_open_meteo_success(monkeypatch)
    respx.get(weather_mod.FORECAST_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ValueError, match="weather forecast failed"):
        weather_mod.fetch_weather("東京")


@respx.mock
def test_geocoding_cache_hit_calls_api_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setattr(weather_mod, "now_jst", lambda: fixed)
    geo_route = respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"name": "東京", "latitude": 35.68, "longitude": 139.76}]},
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
    weather_mod.fetch_weather("東京")
    weather_mod.fetch_weather("東京")
    assert geo_route.call_count == 1
