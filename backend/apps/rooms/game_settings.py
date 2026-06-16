from typing import Any

from ninja.errors import HttpError

ANSWER_LIMIT_MODES = {"FIRST_ONLY", "FIVE_SECONDS", "ALL_CORRECT"}
PLAY_MODES = {"SOLO", "TEAM"}
TEAM_ASSIGN_MODES = {"SELF_SELECT", "RANDOM"}
ANSWER_FIELDS = {"TITLE_ONLY", "TITLE_AND_ARTIST"}
MODE_FLAGS = {"ON", "OFF"}

DEFAULT_ROOM_SETTINGS: dict[str, Any] = {
    "question_count": 20,
    "answer_limit_mode": "FIVE_SECONDS",
    "play_mode": "SOLO",
    "team_assign_mode": "SELF_SELECT",
    "team_count": 2,
    "item_mode": "OFF",
    "answer_fields": "TITLE_ONLY",
    "balance_mode": "OFF",
    "allow_late_join": True,
    "round_time_limit_sec": 20,
    "reveal_duration_sec": 5,
    "countdown_sec": 3,
}


def normalize_room_settings(raw_settings: dict[str, Any] | None) -> dict[str, Any]:
    settings = {**DEFAULT_ROOM_SETTINGS, **(raw_settings or {})}

    settings["question_count"] = _coerce_int(
        settings["question_count"],
        field_name="question_count",
        min_value=1,
        max_value=300,
    )
    settings["team_count"] = _coerce_int(
        settings["team_count"],
        field_name="team_count",
        min_value=2,
        max_value=4,
    )
    settings["round_time_limit_sec"] = _coerce_int(
        settings["round_time_limit_sec"],
        field_name="round_time_limit_sec",
        min_value=5,
        max_value=120,
    )
    settings["reveal_duration_sec"] = _coerce_int(
        settings["reveal_duration_sec"],
        field_name="reveal_duration_sec",
        min_value=1,
        max_value=10,
    )
    settings["countdown_sec"] = _coerce_int(
        settings["countdown_sec"],
        field_name="countdown_sec",
        min_value=0,
        max_value=10,
    )

    settings["allow_late_join"] = _coerce_bool(
        settings["allow_late_join"],
        field_name="allow_late_join",
    )

    _require_choice(settings, "answer_limit_mode", ANSWER_LIMIT_MODES)
    _require_choice(settings, "play_mode", PLAY_MODES)
    _require_choice(settings, "team_assign_mode", TEAM_ASSIGN_MODES)
    _require_choice(settings, "item_mode", MODE_FLAGS)
    _require_choice(settings, "answer_fields", ANSWER_FIELDS)
    _require_choice(settings, "balance_mode", MODE_FLAGS)

    if settings["play_mode"] == "SOLO":
        settings["team_assign_mode"] = DEFAULT_ROOM_SETTINGS["team_assign_mode"]
        settings["team_count"] = DEFAULT_ROOM_SETTINGS["team_count"]

    if settings["balance_mode"] == "ON" and settings["answer_limit_mode"] != "FIRST_ONLY":
        raise HttpError(400, "balance_mode can only be ON when answer_limit_mode is FIRST_ONLY.")

    return settings


def _coerce_int(value: Any, *, field_name: str, min_value: int, max_value: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, f"{field_name} must be a number.") from exc

    if coerced < min_value or coerced > max_value:
        raise HttpError(400, f"{field_name} must be between {min_value} and {max_value}.")
    return coerced


def _coerce_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise HttpError(400, f"{field_name} must be a boolean.")


def _require_choice(settings: dict[str, Any], field_name: str, choices: set[str]) -> None:
    value = settings[field_name]
    if not isinstance(value, str):
        raise HttpError(400, f"{field_name} must be a string.")

    normalized = value.strip().upper()
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise HttpError(400, f"{field_name} must be one of: {allowed}.")

    settings[field_name] = normalized
