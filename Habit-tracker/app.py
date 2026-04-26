from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import random
from datetime import date
import calendar as cal

app = Flask(__name__)
app.secret_key = "your_secret_key"


def init_db():
    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            habit_name TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            priority TEXT DEFAULT 'Medium',
            notes TEXT,
            created_date TEXT NOT NULL,
            streak INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            completion_date TEXT NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (friend_id) REFERENCES users(id)
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
            flash("Registration successful! Please login.")
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

    search = request.args.get("search", "")
    category = request.args.get("category", "")
    priority = request.args.get("priority", "")
    status_filter = request.args.get("status", "")

    quotes = [
        "Small progress is still progress.",
        "Build habits, build your future.",
        "One day at a time.",
        "Consistency is the key to success.",
        "Do something today your future self will thank you for."
    ]

    query = """
        SELECT h.id, h.habit_name, h.category, h.priority, h.notes,
               h.created_date, h.streak,
               CASE
                   WHEN c.id IS NOT NULL THEN 'Completed'
                   ELSE 'Not Completed'
               END AS today_status
        FROM habits h
        LEFT JOIN habit_completions c
        ON h.id = c.habit_id
        AND c.completion_date = ?
        WHERE h.user_id = ?
        AND h.created_date <= ?
    """

    params = [today, session["user_id"], today]

    if search:
        query += " AND h.habit_name LIKE ?"
        params.append(f"%{search}%")

    if category:
        query += " AND h.category = ?"
        params.append(category)

    if priority:
        query += " AND h.priority = ?"
        params.append(priority)

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(query, params)
    habits = cursor.fetchall()

    if status_filter:
        habits = [habit for habit in habits if habit[7] == status_filter]

    reminders = [habit for habit in habits if habit[7] == "Not Completed"]

    total = len(habits)
    completed = len([habit for habit in habits if habit[7] == "Completed"])
    percentage = 0 if total == 0 else int((completed / total) * 100)

    conn.close()

    return render_template(
        "dashboard.html",
        habits=habits,
        quote=random.choice(quotes),
        search=search,
        category=category,
        priority=priority,
        status=status_filter,
        reminders=reminders,
        total=total,
        completed=completed,
        percentage=percentage
    )


@app.route("/new_habit", methods=["GET", "POST"])
def new_habit():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        habit_name = request.form["habit_name"]
        category = request.form["category"]
        priority = request.form["priority"]
        notes = request.form["notes"]
        created_date = date.today().isoformat()

        conn = sqlite3.connect("habit_tracker.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO habits
            (user_id, habit_name, category, priority, notes, created_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session["user_id"], habit_name, category, priority, notes, created_date)
        )

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

    cursor.execute(
        """
        SELECT id FROM habit_completions
        WHERE habit_id = ? AND user_id = ? AND completion_date = ?
        """,
        (habit_id, session["user_id"], today)
    )

    existing = cursor.fetchone()

    if not existing:
        cursor.execute(
            """
            INSERT INTO habit_completions
            (habit_id, user_id, completion_date)
            VALUES (?, ?, ?)
            """,
            (habit_id, session["user_id"], today)
        )

        cursor.execute(
            """
            UPDATE habits
            SET streak = streak + 1
            WHERE id = ? AND user_id = ?
            """,
            (habit_id, session["user_id"])
        )

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

    cursor.execute(
        """
        DELETE FROM habit_completions
        WHERE habit_id = ? AND user_id = ? AND completion_date = ?
        """,
        (habit_id, session["user_id"], today)
    )

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
        notes = request.form["notes"]

        cursor.execute(
            """
            UPDATE habits
            SET habit_name = ?, category = ?, priority = ?, notes = ?
            WHERE id = ? AND user_id = ?
            """,
            (habit_name, category, priority, notes, habit_id, session["user_id"])
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    cursor.execute(
        """
        SELECT id, habit_name, category, priority, notes, created_date
        FROM habits
        WHERE id = ? AND user_id = ?
        """,
        (habit_id, session["user_id"])
    )

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


@app.route("/api/search_users")
def search_users():
    if "user_id" not in session:
        return {"users": []}

    search_text = request.args.get("q", "")

    if search_text.strip() == "":
        return {"users": []}

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, email
        FROM users
        WHERE name LIKE ?
        AND id != ?
        LIMIT 5
        """,
        (f"%{search_text}%", session["user_id"])
    )

    users = cursor.fetchall()
    conn.close()

    result = []

    for user in users:
        result.append({
            "id": user[0],
            "name": user[1],
            "email": user[2]
        })

    return {"users": result}


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
                flash("You cannot add yourself as a friend.")
            else:
                cursor.execute(
                    """
                    SELECT id FROM friends
                    WHERE user_id = ? AND friend_id = ?
                    """,
                    (session["user_id"], friend_id)
                )

                existing = cursor.fetchone()

                if existing:
                    flash("This user is already your friend.")
                else:
                    cursor.execute(
                        "INSERT INTO friends (user_id, friend_id) VALUES (?, ?)",
                        (session["user_id"], friend_id)
                    )
                    conn.commit()
                    flash("Friend added successfully.")
        else:
            flash("No user found with that email.")

        conn.close()
        return redirect(url_for("friends"))

    cursor.execute(
        """
        SELECT u.id, u.name, u.email
        FROM friends f
        JOIN users u ON f.friend_id = u.id
        WHERE f.user_id = ?
        """,
        (session["user_id"],)
    )
    friend_list = cursor.fetchall()

    user_ids = [session["user_id"]] + [friend[0] for friend in friend_list]
    leaderboard = []

    for user_id in user_ids:
        cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        user_name = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM habit_completions
            WHERE user_id = ? AND completion_date = ?
            """,
            (user_id, today)
        )
        completed_today = cursor.fetchone()[0]

        leaderboard.append((user_name, completed_today))

    leaderboard.sort(key=lambda x: x[1], reverse=True)

    conn.close()

    return render_template(
        "friends.html",
        friend_list=friend_list,
        leaderboard=leaderboard
    )


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("habit_tracker.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name, email FROM users WHERE id = ?", (session["user_id"],))
    user = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM habits WHERE user_id = ?", (session["user_id"],))
    total_habits = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM habit_completions WHERE user_id = ?", (session["user_id"],))
    completed_habits = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        total_habits=total_habits,
        completed_habits=completed_habits
    )


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

    cursor.execute(
        """
        SELECT id, habit_name, category, priority, created_date
        FROM habits
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )
    habits = cursor.fetchall()

    cursor.execute(
        """
        SELECT habit_id, completion_date
        FROM habit_completions
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )
    completions = cursor.fetchall()

    conn.close()

    completed_set = set()

    for habit_id, completion_date in completions:
        completed_set.add((habit_id, completion_date))

    return render_template(
        "calendar.html",
        month_name=month_name,
        month_days=month_days,
        habits=habits,
        completed_set=completed_set,
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