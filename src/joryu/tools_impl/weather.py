"""Open-Meteo 天気取得。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import httpx

from joryu.datetime_context import now_jst

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT = 5.0
DEFAULT_PROVIDER = "open_meteo"

WMO_LABELS: dict[int, str] = {
    0: "快晴",
    1: "晴れ",
    2: "晴れ時々曇り",
    3: "曇り",
    45: "霧",
    48: "霧氷",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    61: "弱い雨",
    63: "雨",
    65: "強い雨",
    71: "弱い雪",
    73: "雪",
    75: "強い雪",
    80: "にわか雨",
    81: "にわか雨",
    82: "激しいにわか雨",
    95: "雷雨",
}


@dataclass(frozen=True)
class WeatherSettings:
    timeout: float = DEFAULT_TIMEOUT
    provider: str = DEFAULT_PROVIDER


_settings = WeatherSettings()


def apply_weather_config(*, timeout: float, provider: str) -> None:
    """config.yaml の tools.weather をモジュール設定へ反映。"""
    global _settings
    _settings = WeatherSettings(timeout=timeout, provider=provider)


def _resolve_timeout() -> float:
    env = os.environ.get("JORYU_WEATHER_TIMEOUT")
    if env is not None and env.strip():
        return float(env)
    return _settings.timeout


def _resolve_provider() -> str:
    env = os.environ.get("JORYU_WEATHER_PROVIDER")
    if env is not None and env.strip():
        return env
    return _settings.provider


def _weather_label(code: int | None) -> str:
    if code is None:
        return "不明"
    return WMO_LABELS.get(code, f"コード{code}")


def _resolve_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return now_jst().date().isoformat()


def _http_timeout() -> httpx.Timeout:
    seconds = _resolve_timeout()
    return httpx.Timeout(seconds)


@lru_cache(maxsize=128)
def _geocode_location(location: str) -> tuple[float, float, str]:
    """地点名 → (lat, lon, place_name)。結果は lru_cache で保持。"""
    timeout = _http_timeout()
    try:
        with httpx.Client(timeout=timeout) as client:
            geo_resp = client.get(
                GEOCODING_URL,
                params={"name": location, "language": "ja", "count": 1},
            )
            geo_resp.raise_for_status()
            geo = geo_resp.json()
    except httpx.TimeoutException as exc:
        raise ValueError("weather upstream timeout") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"weather geocoding failed: {exc}") from exc

    results = geo.get("results") or []
    if not results:
        raise ValueError(f"location not found: {location!r}")
    place = results[0]
    lat = place["latitude"]
    lon = place["longitude"]
    place_name = place.get("name") or location
    return float(lat), float(lon), str(place_name)


def fetch_weather(location: str, date_str: str | None = None) -> str:
    """地点と日付 (ISO) で天気予報文字列を返す。"""
    if not location.strip():
        raise ValueError("weather requires non-empty 'location'")
    target_date = _resolve_date(date_str)
    provider = _resolve_provider()
    if provider != "open_meteo":
        raise ValueError(f"unsupported weather provider: {provider!r}")

    lat, lon, place_name = _geocode_location(location.strip())

    timeout = _http_timeout()
    try:
        with httpx.Client(timeout=timeout) as client:
            forecast_resp = client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": (
                        "weathercode,temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max"
                    ),
                    "timezone": "Asia/Tokyo",
                    "start_date": target_date,
                    "end_date": target_date,
                },
            )
            forecast_resp.raise_for_status()
            daily = forecast_resp.json().get("daily") or {}
    except httpx.TimeoutException as exc:
        raise ValueError("weather upstream timeout") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"weather forecast failed: {exc}") from exc

    codes = daily.get("weathercode") or [None]
    tmax = daily.get("temperature_2m_max") or [None]
    tmin = daily.get("temperature_2m_min") or [None]
    precip = daily.get("precipitation_probability_max") or [None]
    label = _weather_label(codes[0] if codes else None)
    hi = tmax[0] if tmax else "?"
    lo = tmin[0] if tmin else "?"
    rain = precip[0] if precip else "?"
    return f"{place_name} {target_date}: {label}、最高{hi}℃ / 最低{lo}℃、降水確率 {rain}%"
