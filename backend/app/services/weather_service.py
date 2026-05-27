from typing import Protocol


class WeatherProvider(Protocol):
    async def get_weather(self, location: str) -> dict:
        raise NotImplementedError
