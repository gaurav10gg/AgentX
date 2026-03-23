# tools/alarm.py
# Backend validates alarm data — React Native actually sets it via AlarmManager

from typing import List

async def set_alarm(
    hour: int,
    minute: int,
    label: str = "PhoneAgent Alarm",
    days: List[str] = []
) -> str:
    if not (0 <= hour <= 23):
        return f"Error: Invalid hour {hour}. Must be 0-23."
    if not (0 <= minute <= 59):
        return f"Error: Invalid minute {minute}. Must be 0-59."

    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    time_str = f"{display_hour}:{minute:02d} {period}"

    if days:
        days_str = ", ".join(d.capitalize() for d in days)
        return f"Alarm set for {time_str} on {days_str} | label: {label}"
    return f"Alarm set for {time_str} | label: {label}"

async def cancel_alarm(alarm_id: str) -> str:
    return f"Alarm {alarm_id} cancelled"