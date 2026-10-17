from datetime import date

from libtrack.fines import calculate_fine, overdue_days


def test_late_return_is_charged(settings):
    assert calculate_fine(date(2026, 1, 10), date(2026, 1, 14), settings) > 0


def test_early_return_is_free(settings):
    assert overdue_days(date(2026, 1, 10), date(2026, 1, 5)) == 0
    assert calculate_fine(date(2026, 1, 10), date(2026, 1, 5), settings) == 0


def test_fine_is_capped(settings):
    assert calculate_fine(date(2026, 1, 1), date(2026, 6, 1), settings) == settings.max_fine_cents
