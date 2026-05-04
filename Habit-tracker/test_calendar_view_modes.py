import os
import sqlite3
import unittest

import app as habit_app


class CalendarViewModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_connect = sqlite3.connect
        cls.db_path = os.path.join(
            os.path.dirname(__file__),
            "calendar_view_test.db"
        )

        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

        def connect_override(*args, **kwargs):
            return cls.real_connect(cls.db_path, **kwargs)

        habit_app.sqlite3.connect = connect_override
        habit_app.app.config["TESTING"] = True

        habit_app.init_db()

        conn = cls.real_connect(cls.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            ("Calendar Tester", "calendar@test.com", "demo123")
        )
        cls.user_id = cursor.lastrowid

        habits = [
            ("Daily Done", "Health", "Mon,Tue,Wed,Thu,Fri,Sat,Sun", "High", "2026-05-01"),
            ("Monday Habit", "Fitness", "Mon", "Medium", "2026-05-01"),
            ("Tuesday Habit", "Study", "Tue", "Low", "2026-05-01"),
            ("Future Habit", "Health", "Mon,Tue,Wed,Thu,Fri,Sat,Sun", "Low", "2026-05-10"),
        ]

        cls.habit_ids = {}
        for name, category, schedule, priority, created_date in habits:
            cursor.execute(
                """
                INSERT INTO habits (
                    user_id, habit_name, category, schedule, priority,
                    target_value, target_unit, notes, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cls.user_id, name, category, schedule, priority,
                    "1", "check", "", created_date
                )
            )
            cls.habit_ids[name] = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO habit_completions (habit_id, user_id, completion_date)
            VALUES (?, ?, ?)
            """,
            (cls.habit_ids["Daily Done"], cls.user_id, "2026-05-04")
        )

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        habit_app.sqlite3.connect = cls.real_connect
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def setUp(self):
        self.client = habit_app.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["user_name"] = "Calendar Tester"

    def test_calendar_defaults_to_monthly_view(self):
        response = self.client.get("/calendar?date=2026-05-04")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Monthly Overview", body)
        self.assertIn("May 2026", body)

    def test_invalid_view_falls_back_to_monthly(self):
        response = self.client.get("/calendar?view=weekly&date=2026-05-04")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Monthly Overview", body)
        self.assertNotIn("Daily Overview", body)

    def test_daily_view_shows_only_relevant_habits_for_selected_day(self):
        response = self.client.get("/calendar?view=daily&date=2026-05-04")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Daily Overview", body)
        self.assertIn("Monday, 04 May 2026", body)
        self.assertIn("Daily Done", body)
        self.assertIn("Monday Habit", body)
        self.assertNotIn("Tuesday Habit", body)
        self.assertNotIn("Future Habit", body)
        self.assertIn("Completed", body)
        self.assertIn("Pending", body)


if __name__ == "__main__":
    unittest.main()
