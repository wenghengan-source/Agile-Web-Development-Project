import unittest
from datetime import date

from app import calculate_habit_streak


class CalculateHabitStreakTests(unittest.TestCase):
    def test_daily_streak_counts_consecutive_completions(self):
        streak = calculate_habit_streak(
            "",
            "2026-05-01",
            {"2026-05-01", "2026-05-02", "2026-05-03"},
            date(2026, 5, 3)
        )

        self.assertEqual(streak, 3)

    def test_daily_streak_resets_after_a_missed_day(self):
        streak = calculate_habit_streak(
            "",
            "2026-05-01",
            {"2026-05-01", "2026-05-02"},
            date(2026, 5, 3)
        )

        self.assertEqual(streak, 0)

    def test_scheduled_streak_skips_unscheduled_days(self):
        streak = calculate_habit_streak(
            "Mon,Wed,Fri",
            "2026-04-27",
            {"2026-04-27", "2026-04-29", "2026-05-01"},
            date(2026, 5, 2)
        )

        self.assertEqual(streak, 3)

    def test_scheduled_streak_breaks_on_missed_scheduled_day(self):
        streak = calculate_habit_streak(
            "Mon,Wed,Fri",
            "2026-04-27",
            {"2026-04-27"},
            date(2026, 4, 30)
        )

        self.assertEqual(streak, 0)

    def test_days_before_creation_do_not_count_as_missed(self):
        streak = calculate_habit_streak(
            "Mon,Wed,Fri",
            "2026-05-01",
            {"2026-05-01"},
            date(2026, 5, 2)
        )

        self.assertEqual(streak, 1)


if __name__ == "__main__":
    unittest.main()
