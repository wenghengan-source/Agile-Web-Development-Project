from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import random
from datetime import date
import calendar as cal

app = Flask(__name__)
app.secret_key = "habit_tracker_secret_key"


def init_db():
    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            habit_name TEXT NOT NULL,
            category TEXT,
            priority TEXT,
            target_value TEXT,
            target_unit TEXT,
            notes TEXT,
            created_date TEXT NOT NULL,
            streak INTEGER DEFAULT 0
        )
    """)

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
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, password)
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

    today = date.today().isoformat()

    quotes = [
        "Small progress is still progress.",
        "Build habits, build your future.",
        "Discipline today leads to strength tomorrow.",
        "Stay focused and trust the process.",
        "Consistency beats motivation."
    ]

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.id, h.habit_name, h.category, h.priority,
               h.notes, h.created_date, h.streak,
               CASE
                   WHEN c.id IS NOT NULL THEN 'Completed'
                   ELSE 'Not Completed'
               END,
               h.target_value, h.target_unit
        FROM habits h
        LEFT JOIN habit_completions c
        ON h.id = c.habit_id
        AND c.completion_date = ?
        WHERE h.user_id = ?
        ORDER BY h.id DESC
    """, (today, session["user_id"]))

    habits = cursor.fetchall()

    total = len(habits)
    completed = len([h for h in habits if h[7] == "Completed"])
    percentage = int((completed / total) * 100) if total > 0 else 0
    reminders = [h for h in habits if h[7] == "Not Completed"]

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
        percentage=percentage,
        reminders=reminders,
        quote=random.choice(quotes),
        health_profile=health_profile,
        bmi=bmi,
        today_steps=today_steps,
        today_videos=today_videos
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
        target_value = request.form["target_value"]
        target_unit = request.form["target_unit"]
        notes = request.form["notes"]
        created_date = date.today().isoformat()

        conn = sqlite3.connect("habit_tracker.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO habits
            (user_id, habit_name, category, priority, target_value, target_unit, notes, created_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            habit_name,
            category,
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

        cursor.execute("""
            UPDATE habits
            SET streak = streak + 1
            WHERE id = ? AND user_id = ?
        """, (habit_id, session["user_id"]))

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
        priority = request.form["priority"]
        target_value = request.form["target_value"]
        target_unit = request.form["target_unit"]
        notes = request.form["notes"]

        cursor.execute("""
            UPDATE habits
            SET habit_name = ?, category = ?, priority = ?, target_value = ?, target_unit = ?, notes = ?
            WHERE id = ? AND user_id = ?
        """, (
            habit_name,
            category,
            priority,
            target_value,
            target_unit,
            notes,
            habit_id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT id, habit_name, category, priority, target_value, target_unit, notes, created_date
        FROM habits
        WHERE id = ? AND user_id = ?
    """, (habit_id, session["user_id"]))

    habit = cursor.fetchone()
    conn.close()

    if habit is None:
        flash("Habit not found.")
        return redirect(url_for("dashboard"))

    return render_template("edit_habit.html", habit=habit)


@app.route("/delete_habit/<int:habit_id>")
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
    year = today.year
    month = today.month

    month_name = today.strftime("%B %Y")
    month_days = cal.monthcalendar(year, month)

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, habit_name, category, priority, created_date
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
        day = date.fromordinal(today.toordinal() - i)
        chart_labels.append(day.strftime("%a"))
        last_7_days.append(day.isoformat())

    habit_lines = []

    for habit in habits:
        habit_id = habit[0]
        habit_name = habit[1]

        data = []

        for day_string in last_7_days:
            if (habit_id, day_string) in completed_set:
                data.append(1)
            else:
                data.append(0)

        habit_lines.append({
            "label": habit_name,
            "data": data
        })

    conn.close()

    return render_template(
        "calendar.html",
        month_name=month_name,
        month_days=month_days,
        habits=habits,
        completed_set=completed_set,
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

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        total_habits=total_habits,
        completed_habits=completed_habits
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
               target_value, target_unit, notes, created_date
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

        if d_str in completion_set:
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
