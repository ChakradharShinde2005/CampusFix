from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "campusfix_secret_key"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'student'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            email TEXT NOT NULL,
            title TEXT NOT NULL,
            department TEXT NOT NULL,
            description TEXT NOT NULL,
            image TEXT,
            status TEXT DEFAULT 'Pending',
            date TEXT,
            time TEXT
        )
    """)

    cursor.execute("SELECT * FROM users WHERE email='admin@gmail.com'")
    admin = cursor.fetchone()

    if not admin:
        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, ("Admin", "admin@gmail.com", "admin123", "admin"))

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

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, password)
            )
            conn.commit()
            conn.close()
            return redirect("/login")

        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered. Please login."

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["name"] = user[1]
            session["email"] = user[2]
            session["role"] = user[4]

            if session["role"] == "admin":
                return redirect("/admin_dashboard")
            else:
                return redirect("/student_dashboard")

        return "Invalid Email or Password"

    return render_template("login.html")


@app.route("/student_dashboard")
def student_dashboard():
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "student":
        return redirect("/admin_dashboard")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=?", (session["email"],))
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=? AND status='Pending'", (session["email"],))
    pending_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=? AND status='Resolved'", (session["email"],))
    resolved_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=? AND status='Rejected'", (session["email"],))
    rejected_complaints = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "student_dashboard.html",
        name=session["name"],
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints,
        rejected_complaints=rejected_complaints
    )


@app.route("/add_complaint", methods=["GET", "POST"])
def add_complaint():
    if "email" not in session:
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        department = request.form["department"]
        description = request.form["description"]

        image = request.files.get("image")
        image_name = ""

        if image and image.filename != "":
            image_name = secure_filename(image.filename)
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_name))

        today = datetime.now().strftime("%d-%m-%Y")
        current_time = datetime.now().strftime("%I:%M %p")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO complaints
            (student_name, email, title, department, description, image, date, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["name"],
            session["email"],
            title,
            department,
            description,
            image_name,
            today,
            current_time
        ))

        conn.commit()
        conn.close()

        return redirect("/my_complaints")

    return render_template("add_complaint.html")


@app.route("/my_complaints")
def my_complaints():
    if "email" not in session:
        return redirect("/login")

    search = request.args.get("search", "")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if search:
        cursor.execute("""
            SELECT * FROM complaints
            WHERE email=?
            AND (
                title LIKE ?
                OR department LIKE ?
                OR status LIKE ?
                OR date LIKE ?
            )
            ORDER BY id DESC
        """, (
            session["email"],
            f"%{search}%",
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        ))
    else:
        cursor.execute(
            "SELECT * FROM complaints WHERE email=? ORDER BY id DESC",
            (session["email"],)
        )

    complaints = cursor.fetchall()
    conn.close()

    return render_template(
        "my_complaints.html",
        complaints=complaints,
        search=search
    )


@app.route("/admin_dashboard")
def admin_dashboard():
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied! Admin only."

    search = request.args.get("search", "")
    status_filter = request.args.get("status", "")
    department_filter = request.args.get("department", "")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    query = "SELECT * FROM complaints WHERE 1=1"
    params = []

    if search:
        query += """
        AND (
            student_name LIKE ?
            OR email LIKE ?
            OR title LIKE ?
            OR department LIKE ?
            OR description LIKE ?
            OR date LIKE ?
        )
        """
        params.extend([f"%{search}%"] * 6)

    if status_filter:
        query += " AND status=?"
        params.append(status_filter)

    if department_filter:
        query += " AND department=?"
        params.append(department_filter)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    complaints = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM complaints")
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Pending'")
    pending_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='In Progress'")
    progress_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'")
    resolved_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Rejected'")
    rejected_complaints = cursor.fetchone()[0]

    cursor.execute("""
        SELECT department, COUNT(*)
        FROM complaints
        GROUP BY department
    """)
    department_data = cursor.fetchall()

    department_labels = [row[0] for row in department_data]
    department_counts = [row[1] for row in department_data]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        progress_complaints=progress_complaints,
        resolved_complaints=resolved_complaints,
        rejected_complaints=rejected_complaints,
                search=search,
        status_filter=status_filter,
        department_filter=department_filter,
        department_labels=department_labels,
        department_counts=department_counts
    )

@app.route("/update_status/<int:complaint_id>", methods=["POST"])
def update_status(complaint_id):
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied! Admin only."

    new_status = request.form["status"]

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE complaints SET status=? WHERE id=?",
        (new_status, complaint_id)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")


@app.route("/delete_complaint/<int:complaint_id>")
def delete_complaint(complaint_id):
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied! Admin only."

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM complaints WHERE id=?", (complaint_id,))

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")

@app.route("/profile")
def profile():
    if "email" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=?", (session["email"],))
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=? AND status='Pending'", (session["email"],))
    pending_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE email=? AND status='Resolved'", (session["email"],))
    resolved_complaints = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "profile.html",
        name=session["name"],
        email=session["email"],
        role=session["role"],
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints
    )


@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "email" not in session:
        return redirect("/login")

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            return "New password and confirm password do not match."

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT password FROM users WHERE email=?",
            (session["email"],)
        )
        user = cursor.fetchone()

        if user and user[0] == current_password:
            cursor.execute(
                "UPDATE users SET password=? WHERE email=?",
                (new_password, session["email"])
            )

            conn.commit()
            conn.close()

            return redirect("/profile")
        else:
            conn.close()
            return "Current password is incorrect."

    return render_template("change_password.html")
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)