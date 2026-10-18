"""Use the computer's local time for every welcome surface."""
from datetime import datetime


def greeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if 5 <= hour < 12:
        return "صبح بخیر"
    if 12 <= hour < 15:
        return "ظهر بخیر"
    if 15 <= hour < 19:
        return "عصر بخیر"
    return "شب بخیر"
