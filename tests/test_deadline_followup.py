from datetime import date

from src.legal_intake_service import deadline_follow_up


def test_deadline_inside_seven_days_gets_follow_up_today() -> None:
    today = date(2026, 9, 30)

    required, follow_up_on = deadline_follow_up(date(2026, 10, 5), today)

    assert required is True
    assert follow_up_on == today


def test_later_deadline_stays_off_the_follow_up_queue() -> None:
    today = date(2026, 9, 30)

    required, follow_up_on = deadline_follow_up(date(2026, 10, 20), today)

    assert required is False
    assert follow_up_on is None

