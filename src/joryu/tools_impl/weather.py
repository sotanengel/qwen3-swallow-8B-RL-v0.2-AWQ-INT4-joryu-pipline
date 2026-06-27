"""Open-Meteo 天気取得。"""

from __future__ import annotations

import os

import httpx

from joryu.datetime_context import now_jst

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT = 5.0

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


def _weather_label(code: int | None) -> str:
    if code is None:
        return "不明"
    return WMO_LABELS.get(code, f"コード{code}")


def _resolve_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return now_jst().date().isoformat()


def fetch_weather(location: str, date_str: str | None = None) -> str:
    """地点と日付 (ISO) で天気予報文字列を返す。"""
    if not location.strip():
        raise ValueError("weather requires non-empty 'location'")
    target_date = _resolve_date(date_str)
    provider = os.environ.get("JORYU_WEATHER_PROVIDER", "open_meteo")
    if provider != "open_meteo":
        raise ValueError(f"unsupported weather provider: {provider!r}")

    timeout = httpx.Timeout(DEFAULT_TIMEOUT)
    with httpx.Client(timeout=timeout) as client:
        geo_resp = client.get(
            GEOCODING_URL,
            params={"name": location.strip(), "language": "ja", "count": 1},
        )
        geo_resp.raise_for_status()
        geo = geo_resp.json()
        results = geo.get("results") or []
        if not results:
            raise ValueError(f"location not found: {location!r}")
        place = results[0]
        lat = place["latitude"]
        lon = place["longitude"]
        place_name = place.get("name") or location.strip()

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

    codes = daily.get("weathercode") or [None]
    tmax = daily.get("temperature_2m_max") or [None]
    tmin = daily.get("temperature_2m_min") or [None]
    precip = daily.get("precipitation_probability_max") or [None]
    label = _weather_label(codes[0] if codes else None)
    hi = tmax[0] if tmax else "?"
    lo = tmin[0] if tmin else "?"
    rain = precip[0] if precip else "?"
    return f"{place_name} {target_date}: {label}、最高{hi}℃ / 最低{lo}℃、降水確率 {rain}%"
