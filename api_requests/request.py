import requests
from settings import api_config


def get_city_coord(city: str) -> str:
    """
    Получает координаты города по его названию используя Yandex API Геокодер .

    :param city: Название города.
    :return: Строка с координатами в формате "широта долгота".
    """
    payload = {
        'geocode': city,
        'apikey': api_config.API_GEO_KEY,
        'format': 'json'
        }
    r = requests.get('https://geocode-maps.yandex.ru/1.x', params=payload)
    geo = r.json()
    return (
        geo['response']['GeoObjectCollection']['featureMember'][0]
        ['GeoObject']['Point']['pos']
    )


def get_weather(city: str) -> dict:
    """
    Получает текущую погоду в указанном городе используя API Yandex Погоды.

    :param city: Название города.
    :return: Словарь с данными о текущей погоде.
    """
    coordinates = get_city_coord(city).split()
    payload = {'lat': coordinates[1], 'lon': coordinates[0], 'lang': 'ru_RU'}
    headers = {'X-Yandex-API-Key': api_config.API_WEATHER_KEY}
    r = requests.get(
        'https://api.weather.yandex.ru/v2/forecast',
        params=payload, headers=headers
        )
    weather_data = r.json()
    return weather_data['fact']
