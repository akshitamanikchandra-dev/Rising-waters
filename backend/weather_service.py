"""
Weather lookups for saved locations.

Uses Open-Meteo (https://open-meteo.com) for geocoding and current/forecast
weather. Open-Meteo's public endpoints are free and require no API key,
which keeps this feature working out of the box with no extra configuration.
"""
import requests

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'

# WMO weather codes -> short human label (subset covering common conditions)
_WEATHER_CODES = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Depositing rime fog',
    51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
    61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
    66: 'Freezing rain', 67: 'Heavy freezing rain',
    71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow',
    80: 'Slight rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers',
    95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with heavy hail',
}


def weather_code_label(code):
    return _WEATHER_CODES.get(code, 'Unknown')


def geocode(query, count=5):
    """Look up place name -> list of {name, country, admin1, latitude, longitude}."""
    try:
        resp = requests.get(
            GEOCODE_URL,
            params={'name': query, 'count': count, 'language': 'en', 'format': 'json'},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException:
        return []

    results = []
    for item in data.get('results', []) or []:
        results.append({
            'name': item.get('name'),
            'country': item.get('country'),
            'admin1': item.get('admin1'),
            'latitude': item.get('latitude'),
            'longitude': item.get('longitude'),
        })
    return results


def get_weather(latitude, longitude):
    """Fetch current conditions + today's precipitation/humidity outlook for a point."""
    try:
        resp = requests.get(
            FORECAST_URL,
            params={
                'latitude': latitude,
                'longitude': longitude,
                'current': 'temperature_2m,relative_humidity_2m,precipitation,'
                           'weather_code,wind_speed_10m,visibility',
                'daily': 'precipitation_sum,precipitation_probability_max,'
                         'temperature_2m_max,temperature_2m_min',
                'forecast_days': 3,
                'timezone': 'auto',
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        return None, str(exc)

    current = data.get('current', {})
    daily = data.get('daily', {})

    weather = {
        'temperature': current.get('temperature_2m'),
        'humidity': current.get('relative_humidity_2m'),
        'precipitation': current.get('precipitation'),
        'wind_speed': current.get('wind_speed_10m'),
        'visibility_m': current.get('visibility'),
        'weather_code': current.get('weather_code'),
        'condition': weather_code_label(current.get('weather_code')),
        'today_precip_sum': (daily.get('precipitation_sum') or [None])[0],
        'today_precip_probability': (daily.get('precipitation_probability_max') or [None])[0],
        'today_temp_max': (daily.get('temperature_2m_max') or [None])[0],
        'today_temp_min': (daily.get('temperature_2m_min') or [None])[0],
        'forecast_dates': daily.get('time', []),
        'forecast_precip_sum': daily.get('precipitation_sum', []),
        'forecast_precip_probability': daily.get('precipitation_probability_max', []),
    }
    return weather, None


# ---------------------------------------------------------------------------
# Severe-condition thresholds. Kept simple and explainable rather than
# reusing the ML flood model (whose 5 input features don't map cleanly onto
# live weather-API fields).
# ---------------------------------------------------------------------------
HEAVY_RAIN_HOURLY_MM = 7.5        # current precipitation rate considered "heavy"
HEAVY_RAIN_DAILY_MM = 40.0        # today's forecast total considered "heavy"
HIGH_HUMIDITY_PCT = 85.0
HIGH_WIND_KMH = 50.0


def evaluate_alerts(weather):
    """Return a list of (severity, message) tuples for conditions worth alerting on."""
    if not weather:
        return []

    alerts = []
    precip = weather.get('precipitation') or 0
    daily_precip = weather.get('today_precip_sum') or 0
    humidity = weather.get('humidity') or 0
    wind = weather.get('wind_speed') or 0
    code = weather.get('weather_code')

    if precip >= HEAVY_RAIN_HOURLY_MM or (code in (65, 67, 82, 95, 96, 99)):
        alerts.append(('severe', f'Heavy rain is occurring now ({precip} mm/h, {weather.get("condition")}).'))
    elif daily_precip >= HEAVY_RAIN_DAILY_MM:
        alerts.append(('watch', f'Heavy rainfall expected today (forecast total {daily_precip} mm).'))

    if humidity >= HIGH_HUMIDITY_PCT:
        alerts.append(('watch', f'Very high humidity ({humidity}%), conditions favorable for flooding.'))

    if wind >= HIGH_WIND_KMH:
        alerts.append(('watch', f'Strong winds ({wind} km/h) may accompany storms.'))

    return alerts
