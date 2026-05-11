from datetime import date, timedelta
from pathlib import Path
import sqlite3

import app as habit_app


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "habit_tracker.db"
DEMO_PASSWORD = "demo123"
TODAY = date.today()
START_DATE = TODAY - timedelta(days=6)

PRIMARY_USER = {
    "name": "Streak Demo",
    "email": "streak.demo@example.com",
    "share_progress_with_friends": 1,
}
FRIEND_USER = {
    "name": "Support Friend",
    "email": "streak.friend@example.com",
    "share_progress_with_friends": 0,
}
DEMO_EMAILS = [PRIMARY_USER["email"], FRIEND_USER["email"]]


def make_placeholders(values):
    return ",".join("?" for _ in values)


def cleanup_existing_demo_data(cursor):
    placeholders = make_placeholders(DEMO_EMAILS)
    cursor.execute(
        f"SELECT id FROM users WHERE email IN ({placeholders})",
        DEMO_EMAILS,
    )
    user_ids = [row[0] for row in cursor.fetchall()]

    if not user_ids:
        return

    user_placeholders = make_placeholders(user_ids)
    cursor.execute(
        f"SELECT id FROM habits WHERE user_id IN ({user_placeholders})",
        user_ids,
    )
    habit_ids = [row[0] for row in cursor.fetchall()]

    if habit_ids:
        habit_placeholders = make_placeholders(habit_ids)
        cursor.execute(
            f"DELETE FROM habit_completions WHERE habit_id IN ({habit_placeholders})",
            habit_ids,
        )

    cursor.execute(
        f"DELETE FROM habit_completions WHERE user_id IN ({user_placeholders})",
        user_ids,
    )
    cursor.execute(
        f"DELETE FROM daily_steps WHERE user_id IN ({user_placeholders})",
        user_ids,
    )
    cursor.execute(
        f"DELETE FROM health_profile WHERE user_id IN ({user_placeholders})",
        user_ids,
    )
    cursor.execute(
        f"DELETE FROM friends "
        f"WHERE user_id IN ({user_placeholders}) OR friend_id IN ({user_placeholders})",
        user_ids + user_ids,
    )
    cursor.execute(
        f"DELETE FROM habits WHERE user_id IN ({user_placeholders})",
        user_ids,
    )
    cursor.execute(
        f"DELETE FROM users WHERE id IN ({user_placeholders})",
        user_ids,
    )


def create_user(cursor, user):
    cursor.execute(
        """
        INSERT INTO users (
            name, email, password, share_progress_with_friends
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            user["name"],
            user["email"],
            DEMO_PASSWORD,
            user.get(
                "share_progress_with_friends",
                habit_app.DEFAULT_SHARE_PROGRESS_WITH_FRIENDS
            ),
        ),
    )
    return cursor.lastrowid


def create_habit(cursor, user_id, habit):
    cursor.execute(
        """
        INSERT INTO habits (
            user_id, habit_name, category, schedule, priority,
            target_value, target_unit, notes, created_date, streak
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            user_id,
            habit["habit_name"],
            habit["category"],
            habit["schedule"],
            habit["priority"],
            habit["target_value"],
            habit["target_unit"],
            habit["notes"],
            habit["created_date"],
        ),
    )
    return cursor.lastrowid


def add_completions(cursor, habit_id, user_id, completion_dates):
    cursor.executemany(
        """
        INSERT INTO habit_completions (habit_id, user_id, completion_date)
        VALUES (?, ?, ?)
        """,
        [(habit_id, user_id, completion_date) for completion_date in completion_dates],
    )


def add_steps(cursor, user_id, step_values):
    cursor.executemany(
        """
        INSERT INTO daily_steps (user_id, step_date, steps)
        VALUES (?, ?, ?)
        """,
        [(user_id, step_date, steps) for step_date, steps in step_values],
    )


def set_health_profile(cursor, user_id):
    cursor.execute(
        """
        INSERT INTO health_profile (user_id, weight, height, age, goal)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, 72.4, 178.0, 27, "Build a steady weekly routine"),
    )


def add_friendship(cursor, user_id, friend_id):
    cursor.execute(
        "INSERT INTO friends (user_id, friend_id) VALUES (?, ?)",
        (user_id, friend_id),
    )


def completion_dates(offsets):
    return [
        (START_DATE + timedelta(days=offset)).isoformat()
        for offset in offsets
    ]


def build_primary_habits():
    created_date = START_DATE.isoformat()
    return [
        {
            "habit_name": "Drink Water",
            "category": "Health",
            "schedule": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            "priority": "High",
            "target_value": "8",
            "target_unit": "glasses",
            "notes": "Spread hydration across the day.",
            "created_date": created_date,
            "completed_offsets": [0, 1, 2, 3, 4, 5, 6],
        },
        {
            "habit_name": "Read 20 Minutes",
            "category": "Learning",
            "schedule": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            "priority": "Medium",
            "target_value": "20",
            "target_unit": "minutes",
            "notes": "Read a book chapter or an article.",
            "created_date": created_date,
            "completed_offsets": [0, 1, 3, 4, 5, 6],
        },
        {
            "habit_name": "Go To Gym",
            "category": "Fitness",
            "schedule": "Mon,Wed,Fri",
            "priority": "High",
            "target_value": "1",
            "target_unit": "session",
            "notes": "Strength or cardio session.",
            "created_date": created_date,
            "completed_offsets": [0, 4],
        },
        {
            "habit_name": "Stretch",
            "category": "Mobility",
            "schedule": "Tue,Thu,Sat",
            "priority": "Low",
            "target_value": "10",
            "target_unit": "minutes",
            "notes": "Focus on hips and shoulders.",
            "created_date": created_date,
            "completed_offsets": [1, 3, 5],
        },
        {
            "habit_name": "Meal Prep",
            "category": "Nutrition",
            "schedule": "Sun",
            "priority": "Medium",
            "target_value": "1",
            "target_unit": "prep",
            "notes": "Prep lunches for the week ahead.",
            "created_date": created_date,
            "completed_offsets": [6],
        },
        {
            "habit_name": "Meditate",
            "category": "Mindfulness",
            "schedule": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            "priority": "Medium",
            "target_value": "5",
            "target_unit": "minutes",
            "notes": "Short guided breathing session.",
            "created_date": created_date,
            "completed_offsets": [2, 3, 4, 5],
        },
    ]


def build_friend_habits():
    created_date = START_DATE.isoformat()
    return [
        {
            "habit_name": "Evening Walk",
            "category": "Health",
            "schedule": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            "priority": "Medium",
            "target_value": "1",
            "target_unit": "walk",
            "notes": "Take a relaxed evening walk.",
            "created_date": created_date,
            "completed_offsets": [0, 1, 3, 5, 6],
        },
        {
            "habit_name": "Journal",
            "category": "Reflection",
            "schedule": "Tue,Thu,Sun",
            "priority": "Low",
            "target_value": "1",
            "target_unit": "entry",
            "notes": "Write a short reflection.",
            "created_date": created_date,
            "completed_offsets": [1, 3],
        },
    ]


def seed_user_habits(cursor, user_id, habits):
    inserted = []

    for habit in habits:
        habit_id = create_habit(cursor, user_id, habit)
        dates = completion_dates(habit["completed_offsets"])
        add_completions(cursor, habit_id, user_id, dates)

        streak = habit_app.calculate_habit_streak(
            habit["schedule"],
            habit["created_date"],
            dates,
            TODAY,
        )
        cursor.execute(
            "UPDATE habits SET streak = ? WHERE id = ?",
            (streak, habit_id),
        )
        inserted.append((habit_id, habit["habit_name"], len(dates), streak))

    return inserted


def main():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cleanup_existing_demo_data(cursor)

        primary_user_id = create_user(cursor, PRIMARY_USER)
        friend_user_id = create_user(cursor, FRIEND_USER)

        set_health_profile(cursor, primary_user_id)
        add_friendship(cursor, primary_user_id, friend_user_id)
        add_friendship(cursor, friend_user_id, primary_user_id)

        primary_steps = [
            ((START_DATE + timedelta(days=0)).isoformat(), 7240),
            ((START_DATE + timedelta(days=1)).isoformat(), 9035),
            ((START_DATE + timedelta(days=2)).isoformat(), 8120),
            ((START_DATE + timedelta(days=3)).isoformat(), 10890),
            ((START_DATE + timedelta(days=4)).isoformat(), 11640),
            ((START_DATE + timedelta(days=5)).isoformat(), 6785),
            ((START_DATE + timedelta(days=6)).isoformat(), 9540),
        ]
        add_steps(cursor, primary_user_id, primary_steps)

        primary_habits = seed_user_habits(cursor, primary_user_id, build_primary_habits())
        friend_habits = seed_user_habits(cursor, friend_user_id, build_friend_habits())

        conn.commit()

    print(
        f"Seeded demo data for {START_DATE.isoformat()} to {TODAY.isoformat()}."
    )
    print(
        f"Login: {PRIMARY_USER['email']} / {DEMO_PASSWORD}"
    )
    print(
        f"Friend login: {FRIEND_USER['email']} / {DEMO_PASSWORD}"
    )
    print(
        "Privacy states: "
        "Streak Demo = visible, Support Friend = hidden"
    )
    print(
        f"Primary user habits: {len(primary_habits)}, friend habits: {len(friend_habits)}"
    )


if __name__ == "__main__":
    main()
