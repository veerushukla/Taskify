"""
Daily Task Tracker Web App (Flask + SQLite)

Run:
1) pip install flask
2) python first.py
3) Open http://127.0.0.1:5000
"""

from __future__ import annotations

import sqlite3
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from flask import Flask, redirect, render_template_string, request, url_for


# Vercel serverless filesystem is read-only except /tmp.
DB_FILE = Path("/tmp/tasks.db") if os.getenv("VERCEL") else Path(__file__).with_name("tasks.db")
EXAM_DATE = date(2026, 6, 6)

app = Flask(__name__)


@dataclass
class Task:
    id: int
    task_date: str
    title: str
    details: str
    status: str
    created_at: str
    completed_at: Optional[str]


class TaskTracker:
    def __init__(self, db_path: Path = DB_FILE) -> None:
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_date TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'done')),
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_task_date ON tasks(task_date)"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_reports (
                task_date TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                trigger_type TEXT NOT NULL
                    CHECK(trigger_type IN ('manual', 'auto')),
                first_assigned_at TEXT,
                auto_due_at TEXT,
                total INTEGER NOT NULL,
                completed INTEGER NOT NULL,
                pending INTEGER NOT NULL,
                completion_pct REAL NOT NULL
            )
            """
        )
        self.conn.commit()

    def add_task(self, title: str, details: str = "", task_date: Optional[str] = None) -> int:
        task_date = task_date or str(date.today())
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """
            INSERT INTO tasks (task_date, title, details, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (task_date, title.strip(), details.strip(), now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_tasks(self, task_date: Optional[str] = None) -> list[Task]:
        if task_date:
            rows = self.conn.execute(
                """
                SELECT id, task_date, title, details, status, created_at, completed_at
                FROM tasks
                WHERE task_date = ?
                ORDER BY id ASC
                """,
                (task_date,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT id, task_date, title, details, status, created_at, completed_at
                FROM tasks
                ORDER BY task_date DESC, id ASC
                """
            ).fetchall()

        return [
            Task(
                id=row["id"],
                task_date=row["task_date"],
                title=row["title"],
                details=row["details"],
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )
            for row in rows
        ]

    def get_task(self, task_id: int) -> Optional[Task]:
        row = self.conn.execute(
            """
            SELECT id, task_date, title, details, status, created_at, completed_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            return None
        return Task(
            id=row["id"],
            task_date=row["task_date"],
            title=row["title"],
            details=row["details"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    def mark_status(self, task_id: int, done: bool) -> bool:
        exists = self.conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not exists:
            return False

        if done:
            self.conn.execute(
                """
                UPDATE tasks
                SET status = 'done',
                    completed_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(timespec="seconds"), task_id),
            )
        else:
            self.conn.execute(
                """
                UPDATE tasks
                SET status = 'pending',
                    completed_at = NULL
                WHERE id = ?
                """,
                (task_id,),
            )
        self.conn.commit()
        return True

    def edit_task(self, task_id: int, new_title: str, new_details: str, new_date: str) -> bool:
        if not new_title.strip():
            return False
        self.conn.execute(
            """
            UPDATE tasks
            SET title = ?, details = ?, task_date = ?
            WHERE id = ?
            """,
            (new_title.strip(), new_details.strip(), new_date, task_id),
        )
        self.conn.commit()
        return True

    def delete_task(self, task_id: int) -> bool:
        cursor = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def daily_report(self, task_date: str) -> dict[str, float | int | str]:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS completed
            FROM tasks
            WHERE task_date = ?
            """,
            (task_date,),
        ).fetchone()

        total = int(row["total"] or 0)
        completed = int(row["completed"] or 0)
        pending = total - completed
        completion_pct = (completed / total * 100.0) if total > 0 else 0.0
        return {
            "date": task_date,
            "total": total,
            "completed": completed,
            "pending": pending,
            "completion_pct": round(completion_pct, 2),
        }

    def get_generated_report(self, task_date: str) -> Optional[dict[str, float | int | str]]:
        row = self.conn.execute(
            """
            SELECT
                task_date, generated_at, trigger_type, first_assigned_at, auto_due_at,
                total, completed, pending, completion_pct
            FROM daily_reports
            WHERE task_date = ?
            """,
            (task_date,),
        ).fetchone()
        if not row:
            return None
        return {
            "task_date": row["task_date"],
            "generated_at": row["generated_at"],
            "trigger_type": row["trigger_type"],
            "first_assigned_at": row["first_assigned_at"] or "",
            "auto_due_at": row["auto_due_at"] or "",
            "total": int(row["total"]),
            "completed": int(row["completed"]),
            "pending": int(row["pending"]),
            "completion_pct": round(float(row["completion_pct"]), 2),
        }

    def generate_daily_report(self, task_date: str, trigger_type: str = "manual") -> Optional[dict[str, float | int | str]]:
        if trigger_type not in {"manual", "auto"}:
            trigger_type = "manual"

        report = self.daily_report(task_date)
        if int(report["total"]) == 0:
            return None

        first_row = self.conn.execute(
            """
            SELECT MIN(created_at) AS first_assigned_at
            FROM tasks
            WHERE task_date = ?
            """,
            (task_date,),
        ).fetchone()
        first_assigned_at = first_row["first_assigned_at"] if first_row else None
        auto_due_at = ""
        if first_assigned_at:
            try:
                due = datetime.fromisoformat(first_assigned_at) + timedelta(hours=16)
                auto_due_at = due.isoformat(timespec="seconds")
            except ValueError:
                auto_due_at = ""

        generated_at = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO daily_reports (
                task_date, generated_at, trigger_type, first_assigned_at, auto_due_at,
                total, completed, pending, completion_pct
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_date) DO UPDATE SET
                generated_at = excluded.generated_at,
                trigger_type = excluded.trigger_type,
                first_assigned_at = excluded.first_assigned_at,
                auto_due_at = excluded.auto_due_at,
                total = excluded.total,
                completed = excluded.completed,
                pending = excluded.pending,
                completion_pct = excluded.completion_pct
            """,
            (
                task_date,
                generated_at,
                trigger_type,
                first_assigned_at or "",
                auto_due_at,
                int(report["total"]),
                int(report["completed"]),
                int(report["pending"]),
                float(report["completion_pct"]),
            ),
        )
        self.conn.commit()
        return self.get_generated_report(task_date)

    def auto_generate_due_reports(self, after_hours: int = 16) -> int:
        now = datetime.now()
        rows = self.conn.execute(
            """
            SELECT
                t.task_date,
                MIN(t.created_at) AS first_assigned_at
            FROM tasks t
            LEFT JOIN daily_reports r
                ON r.task_date = t.task_date
            WHERE r.task_date IS NULL
            GROUP BY t.task_date
            """
        ).fetchall()

        generated_count = 0
        for row in rows:
            first_assigned_at = row["first_assigned_at"]
            if not first_assigned_at:
                continue
            try:
                due_time = datetime.fromisoformat(first_assigned_at) + timedelta(hours=after_hours)
            except ValueError:
                continue
            if now >= due_time:
                generated = self.generate_daily_report(row["task_date"], trigger_type="auto")
                if generated is not None:
                    generated_count += 1
        return generated_count


tracker = TaskTracker()


def normalize_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return str(date.today())
    try:
        return str(datetime.strptime(raw, "%Y-%m-%d").date())
    except ValueError:
        return str(date.today())


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily Task Tracker</title>
  <style>
    :root {
      --bg: #f6f7fb;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --accent: #0f766e;
      --danger: #b91c1c;
      --line: #e5e7eb;
      --done: #166534;
      --pending: #92400e;
    }
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--text); }
    .wrap { max-width: 1000px; margin: 30px auto; padding: 0 14px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px; margin-bottom: 14px; }
    h1, h2 { margin-top: 0; }
    form { display: grid; gap: 10px; }
    .row { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
    input, textarea, button { font: inherit; padding: 9px 10px; border-radius: 8px; border: 1px solid #cbd5e1; }
    button { background: var(--accent); color: #fff; border: none; cursor: pointer; }
    button.secondary { background: #475569; }
    button.danger { background: var(--danger); }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--line); text-align: left; padding: 8px; vertical-align: top; }
    .status-done { color: var(--done); font-weight: 600; }
    .status-pending { color: var(--pending); font-weight: 600; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; }
    .inline { display: inline; }
    .muted { color: var(--muted); }
    .report { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
    .pill { background: #f8fafc; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
    .flash { background: #ecfeff; border: 1px solid #99f6e4; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
    .small { font-size: 13px; }
    .reminder { background: linear-gradient(135deg, #0f766e, #115e59); color: #fff; }
    .reminder h2, .reminder p { margin: 0; }
    .countline { margin-top: 10px; background: rgba(255, 255, 255, 0.22); border-radius: 999px; overflow: hidden; height: 12px; }
    .countline > div { height: 12px; background: #fef08a; }
    .exam-meta { margin-top: 6px; color: #d1fae5; font-size: 14px; }
    .viz-wrap { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
    .donut {
      width: 150px;
      height: 150px;
      border-radius: 50%;
      background: conic-gradient(#0f766e calc(var(--pct) * 1%), #e2e8f0 0);
      display: grid;
      place-items: center;
      margin: 0 auto;
    }
    .donut::after {
      content: attr(data-label);
      width: 108px;
      height: 108px;
      background: #fff;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-weight: 700;
      color: #0f172a;
    }
    .bar-group { display: grid; gap: 10px; }
    .bar { background: #e2e8f0; border-radius: 999px; overflow: hidden; height: 16px; }
    .bar > div { height: 16px; }
    .bar-done { background: #16a34a; }
    .bar-pending { background: #d97706; }
    .flow { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .step {
      border: 1px solid var(--line);
      background: #f8fafc;
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 14px;
      font-weight: 600;
    }
    .arrow { color: #64748b; font-weight: 700; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Daily Task Tracker</h1>
    {% if message %}
      <div class="flash">{{ message }}</div>
    {% endif %}

    <div class="card reminder">
      <h2>NIMCET Reminder (June 6, 2026)</h2>
      <p>{{ exam_message }}</p>
      <div class="countline">
        <div style="width: {{ exam_progress_pct }}%;"></div>
      </div>
      <p class="exam-meta">Today: {{ today_date }} | Days left: {{ exam_days_left }}</p>
    </div>

    <div class="card">
      <h2>Add Task</h2>
      <form method="post" action="{{ url_for('add_task') }}">
        <div class="row">
          <input type="text" name="title" placeholder="Task title" required>
          <input type="date" name="task_date" value="{{ selected_date }}" required>
        </div>
        <textarea name="details" placeholder="Task details (optional)"></textarea>
        <button type="submit">Add Task</button>
      </form>
    </div>

    <div class="card">
      <h2>Filter & Report</h2>
      <form method="get" action="{{ url_for('home') }}">
        <div class="row">
          <input type="date" name="date" value="{{ selected_date }}">
          <button type="submit">Load Date</button>
        </div>
      </form>
      <div class="report" style="margin-top:12px;">
        <div class="pill"><strong>Total:</strong> {{ report.total }}</div>
        <div class="pill"><strong>Completed:</strong> {{ report.completed }}</div>
        <div class="pill"><strong>Pending:</strong> {{ report.pending }}</div>
        <div class="pill"><strong>Completion:</strong> {{ report.completion_pct }}%</div>
      </div>
      <form method="post" action="{{ url_for('generate_report') }}" style="margin-top:12px;">
        <input type="hidden" name="task_date" value="{{ selected_date }}">
        <button type="submit">Generate Whole-Day Report</button>
      </form>
      {% if generated_report %}
      <div class="pill small" style="margin-top:12px;">
        <strong>Saved report status:</strong><br>
        Date: {{ generated_report.task_date }}<br>
        Generated at: {{ generated_report.generated_at }}<br>
        Trigger: {{ generated_report.trigger_type }}<br>
        First assigned at: {{ generated_report.first_assigned_at or 'N/A' }}<br>
        Auto due at (+16h): {{ generated_report.auto_due_at or 'N/A' }}
      </div>
      {% else %}
      <div class="pill small" style="margin-top:12px;">
        No saved report yet for this date. Use the button above or wait for auto-generation after 16 hours.
      </div>
      {% endif %}
    </div>

    <div class="card">
      <h2>Graphs & Flow</h2>
      <div class="viz-wrap">
        <div class="pill">
          <h3>Completion Donut</h3>
          <div class="donut" style="--pct: {{ report.completion_pct }};" data-label="{{ report.completion_pct }}%"></div>
        </div>
        <div class="pill">
          <h3>Status Bars</h3>
          <div class="bar-group">
            <div>
              <div class="muted">Done ({{ report.completed }})</div>
              <div class="bar"><div class="bar-done" style="width: {{ report.completion_pct }}%;"></div></div>
            </div>
            <div>
              <div class="muted">Pending ({{ report.pending }})</div>
              <div class="bar"><div class="bar-pending" style="width: {{ pending_pct }}%;"></div></div>
            </div>
          </div>
        </div>
      </div>
      <div class="pill" style="margin-top:12px;">
        <h3>Study Flow Chart</h3>
        <div class="flow">
          <div class="step">Morning Plan</div>
          <div class="arrow">→</div>
          <div class="step">Add Daily Tasks</div>
          <div class="arrow">→</div>
          <div class="step">Study / Practice</div>
          <div class="arrow">→</div>
          <div class="step">Mark Done / Pending</div>
          <div class="arrow">→</div>
          <div class="step">End-of-Day Report</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Tasks for {{ selected_date }}</h2>
      {% if tasks %}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Details</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for task in tasks %}
          <tr>
            <td>{{ task.id }}</td>
            <td>{{ task.title }}</td>
            <td class="muted">{{ task.details }}</td>
            <td>
              {% if task.status == "done" %}
                <span class="status-done">Done</span>
              {% else %}
                <span class="status-pending">Pending</span>
              {% endif %}
            </td>
            <td>
              <div class="actions">
                {% if task.status == "pending" %}
                  <form class="inline" method="post" action="{{ url_for('mark_done', task_id=task.id) }}">
                    <input type="hidden" name="date" value="{{ selected_date }}">
                    <button type="submit">Mark Done</button>
                  </form>
                {% else %}
                  <form class="inline" method="post" action="{{ url_for('mark_pending', task_id=task.id) }}">
                    <input type="hidden" name="date" value="{{ selected_date }}">
                    <button class="secondary" type="submit">Mark Pending</button>
                  </form>
                {% endif %}

                <form class="inline" method="get" action="{{ url_for('edit_task_page', task_id=task.id) }}">
                  <button class="secondary" type="submit">Edit</button>
                </form>

                <form class="inline" method="post" action="{{ url_for('delete_task', task_id=task.id) }}" onsubmit="return confirm('Delete this task?');">
                  <input type="hidden" name="date" value="{{ selected_date }}">
                  <button class="danger" type="submit">Delete</button>
                </form>
              </div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
        <p class="muted">No tasks for this date yet.</p>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""


EDIT_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Edit Task</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; max-width: 760px; margin: 30px auto; padding: 0 14px; background: #f8fafc; }
    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; }
    form { display: grid; gap: 10px; }
    input, textarea, button { font: inherit; padding: 9px 10px; border-radius: 8px; border: 1px solid #cbd5e1; }
    button { background: #0f766e; color: #fff; border: none; cursor: pointer; }
    a { color: #0f766e; text-decoration: none; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Edit Task #{{ task.id }}</h2>
    <form method="post" action="{{ url_for('edit_task_action', task_id=task.id) }}">
      <input type="text" name="title" value="{{ task.title }}" required>
      <input type="date" name="task_date" value="{{ task.task_date }}" required>
      <textarea name="details">{{ task.details }}</textarea>
      <button type="submit">Save Changes</button>
    </form>
    <p><a href="{{ url_for('home', date=task.task_date) }}">Back to tasks</a></p>
  </div>
</body>
</html>
"""


@app.get("/")
def home():
    tracker.auto_generate_due_reports(after_hours=16)
    selected_date = normalize_date(request.args.get("date", ""))
    tasks = tracker.list_tasks(selected_date)
    report = tracker.daily_report(selected_date)
    generated_report = tracker.get_generated_report(selected_date)
    pending_pct = round((100.0 - float(report["completion_pct"])) if report["total"] > 0 else 0.0, 2)
    today = date.today()
    exam_days_left = (EXAM_DATE - today).days
    if exam_days_left > 0:
        exam_message = f"{exam_days_left} days left for NIMCET. Stay consistent."
    elif exam_days_left == 0:
        exam_message = "NIMCET is today. Give your best."
    else:
        exam_message = f"NIMCET date (June 6, 2026) has passed by {abs(exam_days_left)} days."
    total_exam_window_days = max((EXAM_DATE - date(2026, 1, 1)).days, 1)
    elapsed_days = max(0, min((today - date(2026, 1, 1)).days, total_exam_window_days))
    exam_progress_pct = round((elapsed_days / total_exam_window_days) * 100, 2)
    message = request.args.get("msg", "")
    return render_template_string(
        PAGE,
        selected_date=selected_date,
        tasks=tasks,
        report=report,
        generated_report=generated_report,
        pending_pct=pending_pct,
        exam_days_left=exam_days_left,
        exam_message=exam_message,
        today_date=str(today),
        exam_progress_pct=exam_progress_pct,
        message=message,
    )


@app.post("/reports/generate")
def generate_report():
    task_date = normalize_date(request.form.get("task_date", ""))
    generated = tracker.generate_daily_report(task_date, trigger_type="manual")
    if generated is None:
        msg = "No tasks for this date, so report was not generated."
    else:
        msg = "Whole-day report generated and saved."
    return redirect(url_for("home", date=task_date, msg=msg))


@app.post("/tasks/add")
def add_task():
    title = request.form.get("title", "").strip()
    details = request.form.get("details", "").strip()
    task_date = normalize_date(request.form.get("task_date", ""))
    if title:
        tracker.add_task(title=title, details=details, task_date=task_date)
        msg = "Task added."
    else:
        msg = "Title is required."
    return redirect(url_for("home", date=task_date, msg=msg))


@app.post("/tasks/<int:task_id>/done")
def mark_done(task_id: int):
    task_date = normalize_date(request.form.get("date", ""))
    tracker.mark_status(task_id, done=True)
    return redirect(url_for("home", date=task_date, msg="Task marked done."))


@app.post("/tasks/<int:task_id>/pending")
def mark_pending(task_id: int):
    task_date = normalize_date(request.form.get("date", ""))
    tracker.mark_status(task_id, done=False)
    return redirect(url_for("home", date=task_date, msg="Task marked pending."))


@app.post("/tasks/<int:task_id>/delete")
def delete_task(task_id: int):
    task_date = normalize_date(request.form.get("date", ""))
    tracker.delete_task(task_id)
    return redirect(url_for("home", date=task_date, msg="Task deleted."))


@app.get("/tasks/<int:task_id>/edit")
def edit_task_page(task_id: int):
    task = tracker.get_task(task_id)
    if not task:
        return redirect(url_for("home", msg="Task not found."))
    return render_template_string(EDIT_PAGE, task=task)


@app.post("/tasks/<int:task_id>/edit")
def edit_task_action(task_id: int):
    title = request.form.get("title", "").strip()
    details = request.form.get("details", "").strip()
    task_date = normalize_date(request.form.get("task_date", ""))
    ok = tracker.edit_task(task_id, title, details, task_date)
    msg = "Task updated." if ok else "Could not update task."
    return redirect(url_for("home", date=task_date, msg=msg))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
