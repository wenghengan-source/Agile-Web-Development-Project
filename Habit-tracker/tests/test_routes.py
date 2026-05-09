import os
import shutil
import runpy
import sqlite3
from datetime import date, timedelta

import pytest


DB = "habit_tracker.db"


@pytest.fixture(scope="module")
def app_client():
    # Backup existing DB if present
    backup = None
    if os.path.exists(DB):
        backup = DB + ".bak"
        shutil.copy(DB, backup)
        os.remove(DB)

    # Load app (won't call app.run because __name__ != '__main__')
    module = runpy.run_path(os.path.join("Habit-tracker", "app.py"), run_name="app_module")
    app = module["app"]
    init_db = module.get("init_db")
    if init_db:
        init_db()

    client = app.test_client()

    yield client

    # Teardown: remove test DB and restore backup if exists
    try:
        if os.path.exists(DB):
            os.remove(DB)
        if backup:
            shutil.move(backup, DB)
    except Exception:
        pass


def register_and_login(client, email="test@example.com"):
    client.post("/register", data={"name": "Test User", "email": email, "password": "pass"}, follow_redirects=True)
    client.post("/login", data={"email": email, "password": "pass"}, follow_redirects=True)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row[0]


def test_stats_custom_streak(app_client):
    client = app_client
    uid = register_and_login(client)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    today = date.today().isoformat()
    yest = (date.today() - timedelta(days=1)).isoformat()

    # create a habit
    cur.execute(
        "INSERT INTO habits (user_id, habit_name, category, priority, target_value, target_unit, notes, created_date, streak) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, 'T1', 'cat', 'low', '1', 'times', '', today, 0)
    )
    hid = cur.lastrowid

    # add two completion days to make streak 2
    cur.execute('INSERT INTO habit_completions (habit_id, user_id, completion_date) VALUES (?, ?, ?)', (hid, uid, yest))
    cur.execute('INSERT INTO habit_completions (habit_id, user_id, completion_date) VALUES (?, ?, ?)', (hid, uid, today))
    conn.commit()
    conn.close()

    resp = client.get('/stats_custom', follow_redirects=True)
    text = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # old custom page showed 'Current streak' with <strong> markup; canonical /stats shows 'Streak momentum'
    assert 'Streak momentum' in text
    assert 'Streak momentum: 2' in text


def test_contact_prefill_and_message_saved(app_client):
    client = app_client
    email = 'sender@example.com'
    uid = register_and_login(client, email=email)

    # GET contact should prefill user's email
    resp = client.get('/contact')
    t = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert f'value="{email}"' in t

    # POST a message
    client.post('/contact', data={'name': 'Sender', 'email': email, 'message': 'Hello', 'to_email': ''}, follow_redirects=True)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute('SELECT sender_email, message FROM messages WHERE sender_email = ? ORDER BY id DESC LIMIT 1', (email,))
    row = cur.fetchone()
    conn.close()

    assert row is not None and row[0] == email and row[1] == 'Hello'


def test_edit_profile_updates_db(app_client):
    client = app_client
    email = 'editme@example.com'
    uid = register_and_login(client, email=email)

    # GET edit page
    resp = client.get('/edit_profile')
    assert resp.status_code == 200

    # POST changes
    client.post('/edit_profile', data={'name': 'New Name', 'email': 'new@example.com', 'password': ''}, follow_redirects=True)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute('SELECT name, email FROM users WHERE id = ?', (uid,))
    row = cur.fetchone()
    conn.close()

    assert row[0] == 'New Name' and row[1] == 'new@example.com'


def test_friends_modal_prefill_user_email(app_client):
    client = app_client
    email = 'friendtest@example.com'
    uid = register_and_login(client, email=email)

    # create friend user and relation
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', ('F', 'f@example.com', 'p'))
    conn.commit()
    cur.execute('SELECT id FROM users WHERE email = ?', ('f@example.com',))
    fid = cur.fetchone()[0]
    cur.execute('INSERT INTO friends (user_id, friend_id) VALUES (?, ?)', (uid, fid))
    conn.commit()
    conn.close()

    resp = client.get('/friends')
    t = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # check modal email input has the current user's email as value
    assert 'id="modal_email"' in t
    assert f'value="{email}"' in t
