# Smart Habit Tracker

## Overview

Smart Habit Tracker is a Flask-based web application developed as part of the Agile Web Development course at The University of Western Australia.

The application helps users build and maintain positive habits through intelligent tracking, streak monitoring, progress visualization, rewards, and social interaction features. Users can create habits, record daily completions, review statistics, compare activity with friends and monitor long-term consistency through an interactive dashboard.

This project was developed using Agile software development practices including feature branching, pull requests, GitHub Issues, iterative development and collaborative code reviews.

---

## Features

### Authentication
- User registration and login
- Session-based authentication
- Protected routes for authenticated users

### Habit Management
- Create new habits
- Edit existing habits
- Delete habits
- Mark daily completions
- Track active habits

### Dashboard & Tracking
- Daily dashboard view
- Habit streak tracking
- Completion summaries
- Progress monitoring

### Statistics & Insights
- Weekly progress tracking
- Completion statistics
- Best-day tracking
- Progress visualization

### Social Features
- Friends system
- Leaderboard comparison
- Privacy mode support
- User messaging/contact functionality

### Additional Features
- Reward and trophy system
- Profile management
- Calendar-based tracking
- Contact page

---

## Tech Stack

### Backend
- Flask
- Python
- SQLite

### Frontend
- HTML
- CSS
- Bootstrap 5
- Jinja2 Templates

### Development Tools
- Git
- GitHub
- VS Code

---

## Project Structure

```text
Agile-Web-Development-Project/
|
+-- Habit-tracker/
|   +-- app.py
|   +-- requirements.txt
|   +-- templates/
|   |   +-- dashboard.html
|   |   +-- stats.html
|   |   +-- profile.html
|   |   +-- friends.html
|   |   +-- login.html
|   |   +-- register.html
|   |   +-- ...
|   +-- static/
|   |   +-- style.css
|   |   +-- images/
|   +-- tests/
|   +-- habit_tracker.db  [generated locally after running the app]
|
+-- README.md
```

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/wenghengan-source/Agile-Web-Development-Project.git
```

### 2. Navigate to the Project Folder

```bash
cd Agile-Web-Development-Project/Habit-tracker
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Flask Application

```bash
python app.py
```

The SQLite database file `habit_tracker.db` is created locally when the app runs for the first time.

### 5. Open the Application

Open the browser and visit:

```text
http://127.0.0.1:5000
```

---

## Database

The application uses SQLite as a lightweight local database solution.

A fresh local database is created when the app runs for the first time. Demo or presentation data is not included in the repository by default.

Main database tables include:
- `users`
- `habits`
- `habit_completions`
- `friends`
- `messages`

SQLite was chosen because it is lightweight, easy to set up and suitable for small-to-medium scale web applications.

---

## Agile Development Workflow

This project followed Agile software development practices throughout development.

### Workflow Practices
- Feature branches for isolated development
- Pull requests before merging into `main`
- GitHub Issues for task management
- Code reviews and peer feedback
- Iterative development and continuous improvement

### Collaboration
The team collaborated through GitHub using:
- Branch-based development
- Pull request reviews
- Merge conflict resolution
- Shared issue tracking

---

## Testing

Basic route and functionality testing was performed for:
- Authentication
- Habit creation/editing
- Dashboard rendering
- Statistics pages
- Friends and leaderboard functionality

---

## Future Improvements

Potential future enhancements include:
- Email and push notifications
- Mobile responsiveness improvements
- Advanced analytics and insights
- Cloud database deployment
- OAuth login integration
- AI-based habit recommendations

---

## Team Members

- Hengan Weng - 24201874
- Yukendar Naidu - 24781111
- Pengfei Luo - 24036668

---
