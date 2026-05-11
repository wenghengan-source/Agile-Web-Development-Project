from pathlib import Path
import sqlite3

import app as habit_app


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "habit_tracker.db"
PRIMARY_EMAIL = "streak.demo@example.com"
FRIEND_EMAIL = "streak.friend@example.com"


def fetch_user(cursor, email):
    cursor.execute(
        """
        SELECT id, name, share_progress_with_friends
        FROM users
        WHERE email = ?
        """,
        (email,),
    )
    return cursor.fetchone()


def fetch_today_completion_count(cursor, user_id):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM habit_completions
        WHERE user_id = ? AND completion_date = ?
        """,
        (user_id, habit_app.date.today().isoformat()),
    )
    return cursor.fetchone()[0]


def main():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        primary_user = fetch_user(cursor, PRIMARY_EMAIL)
        friend_user = fetch_user(cursor, FRIEND_EMAIL)

        if primary_user is None or friend_user is None:
            raise SystemExit(
                "Demo users not found. Run `python seed_week_data.py` first."
            )

        primary_id, primary_name, primary_visibility = primary_user
        friend_id, friend_name, friend_visibility = friend_user

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM friends
            WHERE user_id = ? AND friend_id = ?
            """,
            (primary_id, friend_id),
        )
        primary_has_friend = cursor.fetchone()[0] == 1

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM friends
            WHERE user_id = ? AND friend_id = ?
            """,
            (friend_id, primary_id),
        )
        friend_has_primary = cursor.fetchone()[0] == 1

        primary_count = fetch_today_completion_count(cursor, primary_id)
        friend_count = fetch_today_completion_count(cursor, friend_id)

    print("Privacy demo verification")
    print("-------------------------")
    print(
        f"{primary_name}: visible={primary_visibility}, "
        f"today_count={primary_count}"
    )
    print(
        f"{friend_name}: visible={friend_visibility}, "
        f"today_count={friend_count}"
    )
    print(
        "Friend links: "
        f"{primary_name}->{friend_name}={primary_has_friend}, "
        f"{friend_name}->{primary_name}={friend_has_primary}"
    )
    print()
    print("Expected leaderboard behavior")
    print(
        f"- {primary_name} can see their own count ({primary_count})."
    )
    print(
        f"- {friend_name} stays on the leaderboard but should display "
        "'Progress hidden' / 'Private'."
    )
    print(
        "- Both users should still appear in each other's friends list."
    )


if __name__ == "__main__":
    main()
