from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import random
from datetime import date
from datetime import timedelta
import calendar as cal

app = Flask(__name__)
app.secret_key = "habit_tracker_secret_key"

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Dashboard analytics rules are defined centrally so every future card
# and ranking uses the same thresholds and time windows.
DASHBOARD_ANALYTICS_WINDOW_DAYS = 7
DASHBOARD_TOP_HABIT_MIN_SCHEDULED_DAYS = 2
DASHBOARD_TOP_CATEGORY_MIN_SCHEDULED_DAYS = 2
DASHBOARD_AT_RISK_RATE_THRESHOLD = 60
DASHBOARD_STREAK_COOLDOWN_MIN_BEST_STREAK = 3
DEFAULT_SHARE_PROGRESS_WITH_FRIENDS = 1


def ensure_column_exists(cursor, table_name, column_name, column_definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [column[1] for column in cursor.fetchall()]

    if column_name not in existing_columns:
        cursor.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {column_definition}"
        )


def normalize_progress_visibility(value):
    return 0 if str(value).strip() in {"0", "false", "False"} else 1


def get_user_progress_visibility(cursor, user_id):
    cursor.execute(
        """
        SELECT share_progress_with_friends
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        return DEFAULT_SHARE_PROGRESS_WITH_FRIENDS

    return normalize_progress_visibility(row[0])


def update_user_progress_visibility(cursor, user_id, is_visible):
    cursor.execute(
        """
        UPDATE users
        SET share_progress_with_friends = ?
        WHERE id = ?
        """,
        (normalize_progress_visibility(is_visible), user_id)
    )


def parse_schedule(schedule_value):
    if not schedule_value:
        return []

    return [
        day.strip()
        for day in schedule_value.split(",")
        if day.strip()
    ]


def is_habit_scheduled_for_date(schedule_value, target_date):
    scheduled_days = parse_schedule(schedule_value)

    # Empty schedules represent legacy habits and should behave as daily.
    if not scheduled_days:
        return True

    return target_date.strftime("%a") in scheduled_days


def format_schedule_label(schedule_value):
    scheduled_days = parse_schedule(schedule_value)

    if not scheduled_days:
        return "Every day"

    return ", ".join(scheduled_days)


def parse_optional_date(date_value, fallback_date):
    if not date_value:
        return fallback_date

    try:
        return date.fromisoformat(date_value)
    except ValueError:
        return fallback_date


def get_trailing_dates(reference_date, length, trailing_offset=0):
    """Return ascending dates for a trailing window ending before offset days."""
    return [
        reference_date - timedelta(days=offset)
        for offset in range(length + trailing_offset - 1, trailing_offset - 1, -1)
    ]


def get_week_dates_sunday_first(reference_date, week_offset=0):
    """Return one calendar week in Sun-Sat order for the reference date."""
    days_since_sunday = (reference_date.weekday() + 1) % 7
    week_start = reference_date - timedelta(days=days_since_sunday)
    week_start -= timedelta(days=week_offset * 7)
    return [week_start + timedelta(days=offset) for offset in range(7)]


def calculate_habit_streak(
    schedule_value,
    created_date,
    completion_dates,
    reference_date=None
):
    if reference_date is None:
        reference_date = date.today()

    if isinstance(created_date, str):
        created_date = date.fromisoformat(created_date)

    if reference_date < created_date:
        return 0

    completion_set = set(completion_dates)
    streak = 0
    streak_date = reference_date

    while streak_date >= created_date:
        if not is_habit_scheduled_for_date(schedule_value, streak_date):
            streak_date -= timedelta(days=1)
            continue

        if streak_date.isoformat() not in completion_set:
            break

        streak += 1
        streak_date -= timedelta(days=1)

    return streak


def calculate_completion_day_streak(completion_dates, reference_date=None):
    """Count consecutive calendar days with at least one habit completion."""
    if reference_date is None:
        reference_date = date.today()

    completion_set = set(completion_dates)
    streak = 0
    streak_date = reference_date

    while streak_date.isoformat() in completion_set:
        streak += 1
        streak_date -= timedelta(days=1)

    return streak


def calculate_longest_completion_day_streak(completion_dates):
    """Track the best consecutive completion-day streak across all habits."""
    if not completion_dates:
        return 0

    completion_days = sorted({
        date.fromisoformat(completion_date)
        for completion_date in completion_dates
    })

    longest_streak = 1
    current_streak = 1

    for index in range(1, len(completion_days)):
        if completion_days[index] - completion_days[index - 1] == timedelta(days=1):
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 1

    return longest_streak


def calculate_longest_habit_streak(
    schedule_value,
    created_date,
    completion_dates,
    reference_date=None
):
    """Track the best scheduled completion streak achieved by one habit."""
    if reference_date is None:
        reference_date = date.today()

    if isinstance(created_date, str):
        created_date = date.fromisoformat(created_date)

    if reference_date < created_date:
        return 0

    completion_set = set(completion_dates)
    longest_streak = 0
    current_streak = 0
    streak_date = created_date

    while streak_date <= reference_date:
        if is_habit_scheduled_for_date(schedule_value, streak_date):
            if streak_date.isoformat() in completion_set:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 0

        streak_date += timedelta(days=1)

    return longest_streak


def summarize_scheduled_progress(
    habits,
    completion_records,
    target_dates,
    available_through_date=None
):
    """Average daily completion % across days with scheduled habits only."""
    progress = []
    active_days = 0

    for target_date in target_dates:
        if (
            available_through_date is not None
            and target_date > available_through_date
        ):
            progress.append({
                "label": target_date.strftime("%a"),
                "completed": 0,
                "goal": 0,
                "percentage": 0,
                "is_future": True
            })
            continue

        day_string = target_date.isoformat()
        scheduled_habit_ids = [
            habit_id
            for habit_id, created_date, schedule in habits
            if created_date <= day_string
            and is_habit_scheduled_for_date(schedule, target_date)
        ]
        goal = len(scheduled_habit_ids)
        completed = sum(
            1
            for habit_id in scheduled_habit_ids
            if (habit_id, day_string) in completion_records
        )

        if goal > 0:
            active_days += 1

        progress.append({
            "label": target_date.strftime("%a"),
            "completed": completed,
            "goal": goal,
            "percentage": 0 if goal == 0 else int((completed / goal) * 100),
            "is_future": False
        })

    average_progress = 0
    if active_days > 0:
        average_progress = int(
            sum(day["percentage"] for day in progress) / active_days
        )

    return progress, average_progress, active_days


def summarize_week_over_week_change(
    current_average,
    previous_average,
    current_active_days,
    previous_active_days
):
    """Describe weekly movement using the same scheduled-day completion rule."""
    if current_active_days == 0:
        return "No scheduled check-ins yet this week."

    if previous_active_days == 0:
        return "This is the first week with enough scheduled data to compare."

    delta = current_average - previous_average
    if delta > 0:
        return f"Up {delta} points from last week"

    if delta < 0:
        return f"Down {abs(delta)} points from last week"

    return "Steady with last week"


def should_rank_dashboard_habit(scheduled_days):
    """Only rank habits with enough scheduled check-ins to compare fairly."""
    return scheduled_days >= DASHBOARD_TOP_HABIT_MIN_SCHEDULED_DAYS


def should_rank_dashboard_category(scheduled_days):
    """Only rank categories once they have enough scheduled habit volume."""
    return scheduled_days >= DASHBOARD_TOP_CATEGORY_MIN_SCHEDULED_DAYS


def select_top_dashboard_habit(habit_summaries):
    """Pick the top habit using the dashboard's fair ranking rules."""
    eligible_habits = [
        habit for habit in habit_summaries
        if habit["rank_eligible"]
    ]

    if not eligible_habits:
        return {
            "has_data": False,
            "name": "Ranking unlocks soon",
            "summary": (
                "Habits need at least "
                f"{DASHBOARD_TOP_HABIT_MIN_SCHEDULED_DAYS} scheduled check-ins "
                "this week before this card can rank them fairly."
            ),
            "detail": "Once a habit has a fuller week, the leader will appear here."
        }

    top_habit = sorted(
        eligible_habits,
        key=lambda habit: (
            -habit["weekly_rate"],
            -habit["current_streak"],
            -habit["scheduled_days"],
            -habit["completed_days"],
            habit["name"].lower()
        )
    )[0]

    return {
        "has_data": True,
        "name": top_habit["name"],
        "summary": (
            f"{top_habit['weekly_rate']}% this week "
            f"({top_habit['completed_days']}/{top_habit['scheduled_days']})"
        ),
        "detail": (
            f"{top_habit['current_streak']}-day current streak in "
            f"{top_habit['category']}"
        )
    }


def summarize_dashboard_risk(habit_summaries):
    """Summarize how many habits currently need attention on the dashboard."""
    risk_counts = {
        "due_today": 0,
        "below_pace": 0,
        "cooling_off": 0
    }

    for habit in habit_summaries:
        risk_code = habit["risk_code"]
        if risk_code in risk_counts:
            risk_counts[risk_code] += 1

    total_flagged = sum(risk_counts.values())
    if total_flagged == 0:
        return {
            "count": 0,
            "summary": "Everything is on track",
            "detail": "Nothing is due, behind pace, or losing momentum right now."
        }

    if risk_counts["due_today"] > 0:
        summary = f"{risk_counts['due_today']} due today"
    elif risk_counts["below_pace"] > 0:
        summary = f"{risk_counts['below_pace']} below pace"
    else:
        summary = f"{risk_counts['cooling_off']} cooling off"

    detail_parts = []
    if risk_counts["due_today"] > 0:
        detail_parts.append(f"{risk_counts['due_today']} due today")
    if risk_counts["below_pace"] > 0:
        detail_parts.append(f"{risk_counts['below_pace']} below pace")
    if risk_counts["cooling_off"] > 0:
        detail_parts.append(f"{risk_counts['cooling_off']} cooling off")

    return {
        "count": total_flagged,
        "summary": summary,
        "detail": ", ".join(detail_parts)
    }


def build_streak_progress_summary(
    current_streak,
    personal_best_streak,
    habit_summaries,
    weekly_average,
    weekly_change_summary
):
    """Create a dashboard-friendly streak progress summary."""
    milestones = [3, 7, 14, 21, 30]
    next_goal = milestones[-1]
    for milestone in milestones:
        if current_streak < milestone:
            next_goal = milestone
            break
    else:
        extra_weeks = max(1, ((current_streak - milestones[-1]) // 7) + 1)
        next_goal = milestones[-1] + (extra_weeks * 7)

    progress_percentage = 0
    if next_goal > 0:
        progress_percentage = min(100, int((current_streak / next_goal) * 100))

    carrying_habit = {
        "name": "No habit is carrying it yet",
        "current_streak": 0,
        "category": "Build a run first"
    }
    if habit_summaries:
        carrying_habit = max(
            habit_summaries,
            key=lambda habit: (
                habit["current_streak"],
                habit["best_streak"],
                habit["weekly_rate"],
                habit["name"].lower()
            )
        )
        if carrying_habit["current_streak"] <= 0:
            carrying_habit = {
                "name": "No habit is carrying it yet",
                "current_streak": 0,
                "category": "Build a run first"
            }

    personal_best_streak = max(personal_best_streak, current_streak)
    if personal_best_streak <= current_streak:
        days_to_personal_best = 0
        personal_best_label = "Personal best matched"
        personal_best_detail = (
            "This run is already matching your best streak so far."
            if current_streak > 0 else
            "Complete a habit streak to set your first personal best."
        )
    else:
        days_to_personal_best = personal_best_streak - current_streak
        personal_best_label = "Days to personal best"
        personal_best_detail = (
            f"{days_to_personal_best} more day"
            f"{'' if days_to_personal_best == 1 else 's'} to match {personal_best_streak}."
        )

    if current_streak <= 0:
        headline = "Start a new streak"
        detail = "Complete today's habits to start building momentum again."
    else:
        headline = "Momentum is building"
        detail = (
            f"Stay with it and push toward your {next_goal}-day milestone."
        )

    return {
        "current": current_streak,
        "next_goal": next_goal,
        "progress_percentage": progress_percentage,
        "headline": headline,
        "detail": detail,
        "current_label": (
            f"{current_streak} day streak"
            if current_streak > 0 else
            "No streak yet"
        ),
        "next_milestone_label": f"{next_goal}-day milestone",
        "personal_best": personal_best_streak,
        "days_to_personal_best": days_to_personal_best,
        "personal_best_label": personal_best_label,
        "personal_best_detail": personal_best_detail,
        "carrying_habit_name": carrying_habit["name"],
        "carrying_habit_detail": (
            f"{carrying_habit['current_streak']}-day streak in {carrying_habit['category']}"
            if carrying_habit["current_streak"] > 0 else
            "Complete a few habits in a row and one will lead here."
        ),
        "weekly_completion_value": weekly_average,
        "weekly_completion_trend": weekly_change_summary
    }


def build_dashboard_focus_items(habit_summaries):
    """Select the most actionable habits to surface in the dashboard focus panel."""
    risk_priority = {
        "due_today": 0,
        "below_pace": 1,
        "cooling_off": 2
    }
    reason_labels = {
        "due_today": "Due today",
        "below_pace": "Below pace",
        "cooling_off": "Cooling off"
    }

    focus_candidates = []
    for habit in habit_summaries:
        risk_code = habit["risk_code"]
        if risk_code not in risk_priority:
            continue

        detail = ""
        if risk_code == "due_today":
            detail = (
                f"{habit['completed_days']}/{habit['scheduled_days']} completed "
                f"this week in {habit['category']}."
            )
        elif risk_code == "below_pace":
            detail = (
                f"{habit['weekly_rate']}% this week "
                f"({habit['completed_days']}/{habit['scheduled_days']}) in "
                f"{habit['category']}."
            )
        else:
            detail = (
                f"Best streak {habit['best_streak']} days, current streak "
                f"{habit['current_streak']} in {habit['category']}."
            )

        focus_candidates.append({
            "id": habit["id"],
            "name": habit["name"],
            "reason": reason_labels[risk_code],
            "detail": detail,
            "risk_code": risk_code,
            "priority": risk_priority[risk_code],
            "weekly_rate": habit["weekly_rate"],
            "current_streak": habit["current_streak"]
        })

    return sorted(
        focus_candidates,
        key=lambda habit: (
            habit["priority"],
            habit["weekly_rate"],
            habit["current_streak"],
            habit["name"].lower()
        )
    )[:3]


def classify_dashboard_habit_risk(
    *,
    scheduled_today,
    completed_today,
    weekly_rate,
    current_streak,
    best_streak
):
    """Flag habits that are due today, below pace, or losing momentum."""
    if scheduled_today and not completed_today:
        return "due_today"

    if weekly_rate < DASHBOARD_AT_RISK_RATE_THRESHOLD:
        return "below_pace"

    if (
        best_streak >= DASHBOARD_STREAK_COOLDOWN_MIN_BEST_STREAK
        and current_streak == 0
        and not completed_today
    ):
        return "cooling_off"

    return None


def recalculate_habit_streak(cursor, habit_id, user_id, reference_date=None):
    cursor.execute(
        """
        SELECT schedule, created_date
        FROM habits
        WHERE id = ? AND user_id = ?
        """,
        (habit_id, user_id)
    )
    habit = cursor.fetchone()

    if habit is None:
        return 0

    cursor.execute(
        """
        SELECT completion_date
        FROM habit_completions
        WHERE habit_id = ? AND user_id = ?
        """,
        (habit_id, user_id)
    )
    completion_dates = [row[0] for row in cursor.fetchall()]

    streak = calculate_habit_streak(
        habit[0],
        habit[1],
        completion_dates,
        reference_date
    )

    cursor.execute(
        """
        UPDATE habits
        SET streak = ?
        WHERE id = ? AND user_id = ?
        """,
        (streak, habit_id, user_id)
    )

    return streak


def attach_calculated_streaks(cursor, habits, user_id, reference_date=None):
    if not habits:
        return habits

    cursor.execute(
        """
        SELECT habit_id, completion_date
        FROM habit_completions
        WHERE user_id = ?
        """,
        (user_id,)
    )

    completion_map = {}
    for habit_id, completion_date in cursor.fetchall():
        completion_map.setdefault(habit_id, set()).add(completion_date)

    habits_with_streaks = []
    for habit in habits:
        calculated_streak = calculate_habit_streak(
            habit[10],
            habit[5],
            completion_map.get(habit[0], set()),
            reference_date
        )
        habit_values = list(habit)
        habit_values[6] = calculated_streak
        habits_with_streaks.append(tuple(habit_values))

    return habits_with_streaks


def get_habits_for_user_with_today_status(user_id, target_date):
    day_string = target_date.isoformat()
    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.id, h.habit_name, h.category, h.priority,
               h.notes, h.created_date, h.streak,
               CASE
                   WHEN c.id IS NOT NULL THEN 'Completed'
                   ELSE 'Not Completed'
               END,
               h.target_value, h.target_unit, h.schedule
        FROM habits h
        LEFT JOIN habit_completions c
        ON h.id = c.habit_id
        AND c.completion_date = ?
        WHERE h.user_id = ?
        ORDER BY h.id DESC
    """, (day_string, user_id))

    habits = cursor.fetchall()
    habits = attach_calculated_streaks(cursor, habits, user_id, target_date)
    conn.close()
    return habits


def get_active_habits_for_user(user_id, target_date):
    return [
        habit for habit in get_habits_for_user_with_today_status(user_id, target_date)
        if is_habit_scheduled_for_date(habit[10], target_date)
    ]


def build_progress_snapshot(user_id, reference_date=None):
    """Build one dashboard analytics payload for all future progress widgets."""
    if reference_date is None:
        reference_date = date.today()

    today_string = reference_date.isoformat()
    week_dates = get_week_dates_sunday_first(reference_date)
    previous_week_dates = get_week_dates_sunday_first(reference_date, week_offset=1)

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, habit_name, category, created_date, schedule
        FROM habits
        WHERE user_id = ?
        ORDER BY habit_name COLLATE NOCASE
        """,
        (user_id,)
    )
    habit_rows = cursor.fetchall()

    cursor.execute(
        """
        SELECT habit_id, completion_date
        FROM habit_completions
        WHERE user_id = ?
        """,
        (user_id,)
    )
    completion_rows = cursor.fetchall()
    conn.close()

    completion_records = set(completion_rows)
    completion_days = {completion_date for _, completion_date in completion_rows}
    completion_map = {}
    for habit_id, completion_date in completion_rows:
        completion_map.setdefault(habit_id, set()).add(completion_date)

    progress_habits = [
        (habit_id, created_date, schedule)
        for habit_id, _, _, created_date, schedule in habit_rows
    ]

    weekly_progress, weekly_average, active_days = summarize_scheduled_progress(
        progress_habits,
        completion_records,
        week_dates,
        available_through_date=reference_date
    )
    _, previous_week_average, previous_active_days = summarize_scheduled_progress(
        progress_habits,
        completion_records,
        previous_week_dates,
        available_through_date=previous_week_dates[-1]
    )

    habit_summaries = []
    category_totals = {}

    for habit_id, habit_name, category, created_date, schedule in habit_rows:
        completion_dates = completion_map.get(habit_id, set())
        current_streak = calculate_habit_streak(
            schedule,
            created_date,
            completion_dates,
            reference_date
        )
        best_streak = calculate_longest_habit_streak(
            schedule,
            created_date,
            completion_dates,
            reference_date
        )

        scheduled_days = 0
        completed_days = 0
        for week_day in week_dates:
            if week_day > reference_date:
                continue

            day_string = week_day.isoformat()
            if created_date > day_string:
                continue

            if not is_habit_scheduled_for_date(schedule, week_day):
                continue

            scheduled_days += 1
            if (habit_id, day_string) in completion_records:
                completed_days += 1

        weekly_rate = 0 if scheduled_days == 0 else int(
            (completed_days / scheduled_days) * 100
        )
        scheduled_today = (
            created_date <= today_string
            and is_habit_scheduled_for_date(schedule, reference_date)
        )
        completed_today = (habit_id, today_string) in completion_records
        risk_code = None
        if scheduled_days > 0 or scheduled_today:
            risk_code = classify_dashboard_habit_risk(
                scheduled_today=scheduled_today,
                completed_today=completed_today,
                weekly_rate=weekly_rate,
                current_streak=current_streak,
                best_streak=best_streak
            )

        habit_category = category or "Uncategorized"
        habit_summary = {
            "id": habit_id,
            "name": habit_name,
            "category": habit_category,
            "scheduled_days": scheduled_days,
            "completed_days": completed_days,
            "weekly_rate": weekly_rate,
            "current_streak": current_streak,
            "best_streak": best_streak,
            "scheduled_today": scheduled_today,
            "completed_today": completed_today,
            "risk_code": risk_code,
            "rank_eligible": should_rank_dashboard_habit(scheduled_days)
        }
        habit_summaries.append(habit_summary)

        category_totals.setdefault(
            habit_category,
            {"completed_days": 0, "scheduled_days": 0}
        )
        category_totals[habit_category]["completed_days"] += completed_days
        category_totals[habit_category]["scheduled_days"] += scheduled_days

    category_summaries = []
    for category_name, totals in sorted(category_totals.items()):
        scheduled_days = totals["scheduled_days"]
        completed_days = totals["completed_days"]
        weekly_rate = 0 if scheduled_days == 0 else int(
            (completed_days / scheduled_days) * 100
        )
        category_summaries.append({
            "name": category_name,
            "scheduled_days": scheduled_days,
            "completed_days": completed_days,
            "weekly_rate": weekly_rate,
            "rank_eligible": should_rank_dashboard_category(scheduled_days)
        })

    best_day = {"label": "No data", "completed": 0, "goal": 0}
    completed_week_days = [day for day in weekly_progress if not day["is_future"]]
    if completed_week_days:
        best_day = max(
            completed_week_days,
            key=lambda item: (item["percentage"], item["completed"])
        )

    completion_day_streak = calculate_completion_day_streak(
        completion_days,
        reference_date
    )
    personal_best_streak = calculate_longest_completion_day_streak(
        completion_days
    )
    weekly_change_summary = summarize_week_over_week_change(
        weekly_average,
        previous_week_average,
        active_days,
        previous_active_days
    )

    return {
        "reference_date": today_string,
        "weekly_progress": weekly_progress,
        "weekly_average": weekly_average,
        "previous_week_average": previous_week_average,
        "weekly_change_summary": weekly_change_summary,
        "current_streak": completion_day_streak,
        "has_scheduled_data": active_days > 0,
        "best_day": best_day,
        "at_risk": summarize_dashboard_risk(habit_summaries),
        "focus_items": build_dashboard_focus_items(habit_summaries),
        "top_habit": select_top_dashboard_habit(habit_summaries),
        "streak_summary": build_streak_progress_summary(
            completion_day_streak,
            personal_best_streak,
            habit_summaries,
            weekly_average,
            weekly_change_summary
        ),
        "habit_summaries": habit_summaries,
        "category_summaries": category_summaries
    }


def init_db():
    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            share_progress_with_friends INTEGER NOT NULL DEFAULT 1
        )
    """)

    ensure_column_exists(
        cursor,
        "users",
        "share_progress_with_friends",
        f"INTEGER NOT NULL DEFAULT {DEFAULT_SHARE_PROGRESS_WITH_FRIENDS}"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            habit_name TEXT NOT NULL,
            category TEXT,
            schedule TEXT,
            priority TEXT,
            target_value TEXT,
            target_unit TEXT,
            notes TEXT,
            created_date TEXT NOT NULL,
            streak INTEGER DEFAULT 0
        )
    """)

    ensure_column_exists(cursor, "habits", "schedule", "TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            completion_date TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS health_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight REAL,
            height REAL,
            age INTEGER,
            goal TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            step_date TEXT NOT NULL,
            steps INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("habit_tracker.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO users (
                    name, email, password, share_progress_with_friends
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    password,
                    DEFAULT_SHARE_PROGRESS_WITH_FRIENDS
                )
            )
            conn.commit()
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already exists.")
            return redirect(url_for("register"))
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("habit_tracker.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    today_date = date.today()
    today = today_date.isoformat()
    progress_snapshot = build_progress_snapshot(session["user_id"], today_date)

    quotes = [
        "Small progress is still progress.",
        "Build habits, build your future.",
        "Discipline today leads to strength tomorrow.",
        "Stay focused and trust the process.",
        "Consistency beats motivation."
    ]

    habits = get_active_habits_for_user(session["user_id"], today_date)

    total = len(habits)
    completed = len([h for h in habits if h[7] == "Completed"])
    reminders = [h for h in habits if h[7] == "Not Completed"]
    preview_habits = habits[:3]

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT weight, height, age, goal FROM health_profile WHERE user_id = ?",
        (session["user_id"],)
    )
    health_profile = cursor.fetchone()

    bmi = None
    if health_profile and health_profile[0] and health_profile[1]:
        weight = health_profile[0]
        height = health_profile[1] / 100
        bmi = round(weight / (height * height), 1)

    cursor.execute(
        "SELECT steps FROM daily_steps WHERE user_id = ? AND step_date = ?",
        (session["user_id"], today)
    )
    step_data = cursor.fetchone()
    today_steps = step_data[0] if step_data else 0

    today_videos = [
        {
            "title": "How to Build Better Habits",
            "thumbnail": "https://img.youtube.com/vi/TQMbvJNRpLE/hqdefault.jpg",
            "watch_url": "https://www.youtube.com/watch?v=TQMbvJNRpLE"
        },
        {
            "title": "Study Motivation",
            "thumbnail": "https://img.youtube.com/vi/ZXsQAXx_ao0/hqdefault.jpg",
            "watch_url": "https://www.youtube.com/watch?v=ZXsQAXx_ao0"
        },
        {
            "title": "Stop Procrastinating",
            "thumbnail": "https://img.youtube.com/vi/arj7oStGLkU/hqdefault.jpg",
            "watch_url": "https://www.youtube.com/watch?v=arj7oStGLkU"
        }
    ]

    conn.close()

    return render_template(
        "dashboard.html",
        habits=habits,
        total=total,
        completed=completed,
        reminders=reminders,
        preview_habits=preview_habits,
        quote=random.choice(quotes),
        format_schedule_label=format_schedule_label,
        health_profile=health_profile,
        bmi=bmi,
        today_steps=today_steps,
        today_videos=today_videos,
        progress_snapshot=progress_snapshot
    )


@app.route("/active_habits")
def active_habits():
    if "user_id" not in session:
        return redirect(url_for("login"))

    today_date = date.today()
    all_habits = get_habits_for_user_with_today_status(session["user_id"], today_date)
    status_filter = request.args.get("status", "all").lower()
    search_query = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "priority")

    if search_query:
        lowered_query = search_query.lower()
        all_habits = [
            habit for habit in all_habits
            if lowered_query in habit[1].lower()
        ]

    priority_rank = {"High": 0, "Medium": 1, "Low": 2}

    if sort_by == "name":
        all_habits = sorted(all_habits, key=lambda habit: habit[1].lower())
    elif sort_by == "streak":
        all_habits = sorted(all_habits, key=lambda habit: (-habit[6], habit[1].lower()))
    else:
        sort_by = "priority"
        all_habits = sorted(
            all_habits,
            key=lambda habit: (
                priority_rank.get(habit[3], 99),
                habit[1].lower()
            )
        )

    active_habits = [
        habit for habit in all_habits
        if is_habit_scheduled_for_date(habit[10], today_date)
    ]
    inactive_habits = [
        habit for habit in all_habits
        if not is_habit_scheduled_for_date(habit[10], today_date)
    ]

    if status_filter == "completed":
        active_habits = [habit for habit in active_habits if habit[7] == "Completed"]
    elif status_filter == "incomplete":
        active_habits = [habit for habit in active_habits if habit[7] != "Completed"]
    else:
        status_filter = "all"

    return render_template(
        "active_habits.html",
        active_habits=active_habits,
        inactive_habits=inactive_habits,
        today_label=today_date.strftime("%A, %d %B %Y"),
        status_filter=status_filter,
        search_query=search_query,
        sort_by=sort_by,
        format_schedule_label=format_schedule_label,
        total_active=len([
            habit for habit in all_habits
            if is_habit_scheduled_for_date(habit[10], today_date)
        ]),
        completed_active=len([
            habit for habit in all_habits
            if is_habit_scheduled_for_date(habit[10], today_date)
            and habit[7] == "Completed"
        ]),
        incomplete_active=len([
            habit for habit in all_habits
            if is_habit_scheduled_for_date(habit[10], today_date)
            and habit[7] != "Completed"
        ]),
        total_inactive=len(inactive_habits)
    )


@app.route("/update_health", methods=["POST"])
def update_health():
    if "user_id" not in session:
        return redirect(url_for("login"))

    weight = request.form["weight"]
    height = request.form["height"]
    age = request.form["age"]
    goal = request.form["goal"]

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM health_profile WHERE user_id = ?",
        (session["user_id"],)
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE health_profile
            SET weight = ?, height = ?, age = ?, goal = ?
            WHERE user_id = ?
        """, (weight, height, age, goal, session["user_id"]))
    else:
        cursor.execute("""
            INSERT INTO health_profile (user_id, weight, height, age, goal)
            VALUES (?, ?, ?, ?, ?)
        """, (session["user_id"], weight, height, age, goal))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/update_steps", methods=["POST"])
def update_steps():
    if "user_id" not in session:
        return redirect(url_for("login"))

    steps = request.form["steps"]
    today = date.today().isoformat()

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM daily_steps WHERE user_id = ? AND step_date = ?",
        (session["user_id"], today)
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE daily_steps
            SET steps = ?
            WHERE user_id = ? AND step_date = ?
        """, (steps, session["user_id"], today))
    else:
        cursor.execute("""
            INSERT INTO daily_steps (user_id, step_date, steps)
            VALUES (?, ?, ?)
        """, (session["user_id"], today, steps))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/new_habit", methods=["GET", "POST"])
def new_habit():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        habit_name = request.form["habit_name"]
        category = request.form["category"]
        priority = request.form["priority"]
        schedule = ",".join(request.form.getlist("schedule"))
        target_value = request.form["target_value"]
        target_unit = request.form["target_unit"]
        notes = request.form["notes"]
        created_date = date.today().isoformat()

        conn = sqlite3.connect("habit_tracker.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO habits
            (user_id, habit_name, category, schedule, priority, target_value, target_unit, notes, created_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            habit_name,
            category,
            schedule,
            priority,
            target_value,
            target_unit,
            notes,
            created_date
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("new_habit.html")


@app.route("/complete_habit/<int:habit_id>")
def complete_habit(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = date.today().isoformat()

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM habit_completions
        WHERE habit_id = ? AND user_id = ? AND completion_date = ?
    """, (habit_id, session["user_id"], today))

    existing = cursor.fetchone()

    if not existing:
        cursor.execute("""
            INSERT INTO habit_completions
            (habit_id, user_id, completion_date)
            VALUES (?, ?, ?)
        """, (habit_id, session["user_id"], today))

    recalculate_habit_streak(cursor, habit_id, session["user_id"])

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/reset_habit/<int:habit_id>")
def reset_habit(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = date.today().isoformat()

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM habit_completions
        WHERE habit_id = ? AND user_id = ? AND completion_date = ?
    """, (habit_id, session["user_id"], today))

    recalculate_habit_streak(cursor, habit_id, session["user_id"])

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/edit_habit/<int:habit_id>", methods=["GET", "POST"])
def edit_habit(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    if request.method == "POST":
        habit_name = request.form["habit_name"]
        category = request.form["category"]
        schedule = ",".join(request.form.getlist("schedule"))
        priority = request.form["priority"]
        target_value = request.form["target_value"]
        target_unit = request.form["target_unit"]
        notes = request.form["notes"]

        cursor.execute("""
            UPDATE habits
            SET habit_name = ?, category = ?, schedule = ?, priority = ?, target_value = ?, target_unit = ?, notes = ?
            WHERE id = ? AND user_id = ?
        """, (
            habit_name,
            category,
            schedule,
            priority,
            target_value,
            target_unit,
            notes,
            habit_id,
            session["user_id"]
        ))

        recalculate_habit_streak(cursor, habit_id, session["user_id"])

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT id, habit_name, category, schedule, priority, target_value, target_unit, notes, created_date
        FROM habits
        WHERE id = ? AND user_id = ?
    """, (habit_id, session["user_id"]))

    habit = cursor.fetchone()
    conn.close()

    if habit is None:
        flash("Habit not found.")
        return redirect(url_for("dashboard"))

    selected_schedule = parse_schedule(habit[3])

    return render_template(
        "edit_habit.html",
        habit=habit,
        selected_schedule=selected_schedule
    )


@app.route("/delete_habit/<int:habit_id>", methods=["POST"])
def delete_habit(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM habit_completions WHERE habit_id = ? AND user_id = ?",
        (habit_id, session["user_id"])
    )

    cursor.execute(
        "DELETE FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/calendar")
def calendar():
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = date.today()
    requested_view = request.args.get("view", "monthly").lower()
    view_mode = requested_view if requested_view in {"monthly", "daily"} else "monthly"
    selected_date = parse_optional_date(request.args.get("date"), today)
    year = selected_date.year
    month = selected_date.month

    month_name = selected_date.strftime("%B %Y")
    month_days = cal.monthcalendar(year, month)

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, habit_name, category, priority, created_date, schedule
        FROM habits
        WHERE user_id = ?
    """, (session["user_id"],))
    habits = cursor.fetchall()

    cursor.execute("""
        SELECT habit_id, completion_date
        FROM habit_completions
        WHERE user_id = ?
    """, (session["user_id"],))
    completions = cursor.fetchall()

    completed_set = set(completions)

    chart_labels = []
    last_7_days = []

    for i in range(6, -1, -1):
        day = date.fromordinal(selected_date.toordinal() - i)
        chart_labels.append(day.strftime("%a"))
        last_7_days.append(day.isoformat())

    daily_habits = []

    for habit in habits:
        if (
            habit[4] <= selected_date.isoformat()
            and is_habit_scheduled_for_date(habit[5], selected_date)
        ):
            daily_habits.append({
                "id": habit[0],
                "name": habit[1],
                "category": habit[2],
                "priority": habit[3],
                "completed": (habit[0], selected_date.isoformat()) in completed_set
            })

    habits_for_chart = habits
    if view_mode == "daily":
        daily_habit_ids = {habit["id"] for habit in daily_habits}
        habits_for_chart = [
            habit for habit in habits
            if habit[0] in daily_habit_ids
        ]

    habit_lines = []

    for habit in habits_for_chart:
        habit_id = habit[0]
        habit_name = habit[1]
        created_date = habit[4]
        schedule = habit[5]

        data = []

        for day_string in last_7_days:
            day_date = date.fromisoformat(day_string)

            if day_string < created_date:
                data.append(None)
            elif not is_habit_scheduled_for_date(schedule, day_date):
                data.append(None)
            elif (habit_id, day_string) in completed_set:
                data.append(1)
            else:
                data.append(0)

        habit_lines.append({
            "label": habit_name,
            "data": data
        })

    calendar_habits_by_date = {}

    for week in month_days:
        for day in week:
            if day == 0:
                continue

            current_date = date(year, month, day)
            full_date = current_date.isoformat()
            visible_habits = []

            for habit in habits:
                if (
                    full_date >= habit[4]
                    and is_habit_scheduled_for_date(habit[5], current_date)
                ):
                    visible_habits.append(habit)

            calendar_habits_by_date[full_date] = visible_habits
    conn.close()

    return render_template(
        "calendar.html",
        view_mode=view_mode,
        today_value=today.isoformat(),
        is_today_selected=(selected_date == today),
        selected_date=selected_date,
        selected_date_label=selected_date.strftime("%A, %d %B %Y"),
        selected_date_value=selected_date.isoformat(),
        month_name=month_name,
        month_days=month_days,
        habits=habits,
        completed_set=completed_set,
        calendar_habits_by_date=calendar_habits_by_date,
        daily_habits=daily_habits,
        year=year,
        month=month,
        chart_labels=chart_labels,
        habit_lines=habit_lines
    )


@app.route("/friends", methods=["GET", "POST"])
def friends():
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = date.today().isoformat()

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    if request.method == "POST":
        friend_email = request.form["friend_email"]

        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (friend_email,)
        )
        friend = cursor.fetchone()

        if friend:
            friend_id = friend[0]

            if friend_id == session["user_id"]:
                flash("You cannot add yourself.")
            else:
                cursor.execute("""
                    SELECT id FROM friends
                    WHERE user_id = ? AND friend_id = ?
                """, (session["user_id"], friend_id))

                existing = cursor.fetchone()

                if existing:
                    flash("This user is already your friend.")
                else:
                    cursor.execute("""
                        INSERT INTO friends (user_id, friend_id)
                        VALUES (?, ?)
                    """, (session["user_id"], friend_id))
                    conn.commit()
                    flash("Friend added successfully.")
        else:
            flash("User not found.")

        conn.close()
        return redirect(url_for("friends"))

    cursor.execute("""
        SELECT u.id, u.name, u.email
        FROM friends f
        JOIN users u ON f.friend_id = u.id
        WHERE f.user_id = ?
    """, (session["user_id"],))
    friend_list = cursor.fetchall()

    user_ids = [session["user_id"]] + [friend[0] for friend in friend_list]

    leaderboard = []

    for uid in user_ids:
        cursor.execute("SELECT name FROM users WHERE id = ?", (uid,))
        user_row = cursor.fetchone()

        if user_row is None:
            continue

        user_name = user_row[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM habit_completions
            WHERE user_id = ? AND completion_date = ?
        """, (uid, today))

        count = cursor.fetchone()[0]
        leaderboard.append((user_name, count))

    leaderboard.sort(key=lambda x: x[1], reverse=True)

    conn.close()

    return render_template(
        "friends.html",
        friend_list=friend_list,
        leaderboard=leaderboard
    )


@app.route("/api/search_users")
def search_users():
    if "user_id" not in session:
        return jsonify({"users": []})

    query = request.args.get("q", "")

    if query.strip() == "":
        return jsonify({"users": []})

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, email
        FROM users
        WHERE name LIKE ?
        AND id != ?
        LIMIT 5
    """, (f"%{query}%", session["user_id"]))

    users = cursor.fetchall()
    conn.close()

    result = []

    for user in users:
        result.append({
            "id": user[0],
            "name": user[1],
            "email": user[2]
        })

    return jsonify({"users": result})


@app.route("/stats")
def stats():
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = date.today()
    week_dates = get_trailing_dates(today, DASHBOARD_ANALYTICS_WINDOW_DAYS)

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM habit_completions WHERE user_id = ?",
        (session["user_id"],)
    )
    total_completed = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ?",
        (session["user_id"],)
    )
    total_habits = cursor.fetchone()[0]

    cursor.execute(
        "SELECT id, created_date, schedule FROM habits WHERE user_id = ?",
        (session["user_id"],)
    )
    user_habits = cursor.fetchall()

    cursor.execute(
        """
        SELECT habit_id, completion_date
        FROM habit_completions
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )
    completion_records = set(cursor.fetchall())

    weekly_progress, average_progress, _ = summarize_scheduled_progress(
        user_habits,
        completion_records,
        week_dates
    )

    cursor.execute(
        """
        SELECT completion_date
        FROM habit_completions
        WHERE user_id = ?
        GROUP BY completion_date
        ORDER BY completion_date DESC
        """,
        (session["user_id"],)
    )
    completion_days = [row[0] for row in cursor.fetchall()]

    current_streak = calculate_completion_day_streak(completion_days, today)

    best_day = {"label": "No data", "completed": 0, "goal": 0}
    if weekly_progress:
        best_day = max(
            weekly_progress,
            key=lambda item: (item["percentage"], item["completed"])
        )

    conn.close()

    return render_template(
        "stats.html",
        total_completed=total_completed,
        current_streak=current_streak,
        average_progress=average_progress,
        total_habits=total_habits,
        weekly_progress=weekly_progress,
        best_day=best_day
    )


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, email FROM users WHERE id = ?",
        (session["user_id"],)
    )
    user = cursor.fetchone()

    if user is None:
        conn.close()
        session.clear()
        flash("Your session expired. Please login again.")
        return redirect(url_for("login"))

    cursor.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ?",
        (session["user_id"],)
    )
    total_habits = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM habit_completions WHERE user_id = ?",
        (session["user_id"],)
    )
    completed_habits = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT habit_name
        FROM habits
        WHERE user_id = ?
        ORDER BY created_date DESC, id DESC
        LIMIT 4
        """,
        (session["user_id"],)
    )
    goals = [row[0] for row in cursor.fetchall()]
    share_progress_with_friends = get_user_progress_visibility(
        cursor,
        session["user_id"]
    )

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        total_habits=total_habits,
        completed_habits=completed_habits,
        goals=goals,
        share_progress_with_friends=share_progress_with_friends
    )

@app.route("/habit/<int:habit_id>")
def habit_detail(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = date.today()

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    # Get habit info
    cursor.execute("""
        SELECT id, habit_name, category, priority,
               target_value, target_unit, notes, created_date, schedule
        FROM habits
        WHERE id = ? AND user_id = ?
    """, (habit_id, session["user_id"]))

    habit = cursor.fetchone()

    if habit is None:
        flash("Habit not found.")
        return redirect(url_for("dashboard"))

    # Get completions
    cursor.execute("""
        SELECT completion_date
        FROM habit_completions
        WHERE habit_id = ? AND user_id = ?
    """, (habit_id, session["user_id"]))

    completions = cursor.fetchall()
    completion_set = set([c[0] for c in completions])

    # ---- 7 DAY TREND ----
    chart_labels = []
    chart_values = []

    for i in range(6, -1, -1):
        d = date.fromordinal(today.toordinal() - i)
        d_str = d.isoformat()

        chart_labels.append(d.strftime("%a"))

        if d_str < habit[7]:
            chart_values.append(None)
        elif not is_habit_scheduled_for_date(habit[8], d):
            chart_values.append(None)
        elif d_str in completion_set:
            chart_values.append(1)
        else:
            chart_values.append(0)

    # ---- MONTH CALENDAR ----
    year = today.year
    month = today.month

    month_name = today.strftime("%B %Y")
    month_days = cal.monthcalendar(year, month)

    conn.close()

    return render_template(
        "habit_detail.html",
        habit=habit,
        completion_set=completion_set,
        chart_labels=chart_labels,
        chart_values=chart_values,
        month_days=month_days,
        month_name=month_name,
        date=date,
        is_habit_scheduled_for_date=is_habit_scheduled_for_date,
        year=year,
        month=month
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
