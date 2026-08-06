from flask import Flask, render_template, request, redirect, session, flash, make_response
import sqlite3
from datetime import datetime
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask_mail import Mail, Message
import csv
from google import genai
import random
from flask import session


load_dotenv()
print(os.getenv("GEMINI_API_KEY"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
def get_ai_response(prompt):
    try:
        response = client.models.generate_content(
            model="models/gemini-3.6-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Error: {e}"
    
app = Flask(__name__)
# Forgot Password OTP Store
otp_storage = {}
app.secret_key = os.getenv("SECRET_KEY", "campusfix_secret_key")

app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

mail = Mail(app)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

PROFILE_UPLOAD_FOLDER = "static/profile_photos"
app.config["PROFILE_UPLOAD_FOLDER"] = PROFILE_UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(PROFILE_UPLOAD_FOLDER):
    os.makedirs(PROFILE_UPLOAD_FOLDER)


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
        admin_reply TEXT DEFAULT '',
        last_updated TEXT,
        date TEXT,
        time TEXT,
        priority TEXT DEFAULT 'Medium',
        timeline TEXT DEFAULT 'Submitted'
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    )
  """)


    try:
        cursor.execute("ALTER TABLE complaints ADD COLUMN admin_reply TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE complaints ADD COLUMN last_updated TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'Medium'")
    except sqlite3.OperationalError:
        pass

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
@app.route("/test_ai")
def test_ai():
    answer = get_ai_response("Say Hello from CampusFix AI in one short sentence.")
    return answer


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        if name == "" or email == "" or password == "":
            flash("All fields are required.", "danger")
            return redirect("/register")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return redirect("/register")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, password)
            )
            conn.commit()
            conn.close()

            flash("Registration successful. Please login!", "success")
            return redirect("/login") 
        
        except sqlite3.IntegrityError:
            conn.close()

            flash("Email already registered. Please login.", "danger")
            return redirect("/register")

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

            flash("Login successful!", "success")

            if session["role"] == "admin":
                return redirect("/admin_dashboard")
            else:
                return redirect("/student_dashboard")

        flash("Invalid email or password!", "danger")
        return redirect("/login")

    return render_template("login.html")
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        )

        user = cursor.fetchone()

        conn.close()

        if not user:
            flash("Email not found!", "danger")
            return redirect("/forgot_password")

        otp = str(random.randint(100000, 999999))

        otp_storage[email] = otp

        msg = Message(
            "CampusFix Password Reset OTP",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email]
        )

        msg.body = f"""
        Hello,

        Your CampusFix Password Reset OTP is:

        {otp}

        This OTP is valid for one password reset request.

        If you did not request a password reset, please ignore this email.

        Thank You,
        CampusFix Team
        """

        mail.send(msg)
        session["reset_email"] = email

        flash("OTP sent successfully.", "success")

        return redirect("/verify_otp")

    return render_template("forgot_password.html")
@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():

    if "reset_email" not in session:
        return redirect("/forgot_password")

    email = session["reset_email"]

    if request.method == "POST":

        entered_otp = request.form["otp"]
        new_password = request.form["password"]

        if otp_storage.get(email) != entered_otp:
            flash("Invalid OTP!", "danger")
            return redirect("/verify_otp")

        # Database connection
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        # Update password
        cursor.execute(
            "UPDATE users SET password=? WHERE email=?",
            (new_password, email)
        )

        conn.commit()
        conn.close()

        # Clear OTP and session
        otp_storage.pop(email, None)
        session.pop("reset_email", None)

        flash("Password changed successfully! Please login.", "success")

        return redirect("/login")

    return render_template("verify_otp.html")
@app.route("/test_student")
def test_student():
    session["name"] = "Chakradhar"
    session["email"] = "student@gmail.com"
    session["role"] = "student"
    return redirect("/student_dashboard")
@app.route("/student_dashboard")
def student_dashboard():
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "student":
        return redirect("/admin_dashboard")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM complaints WHERE email=?",
        (session["email"],)
    )
    total_complaints = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM complaints WHERE email=? AND status='Pending'",
        (session["email"],)
    )
    pending_complaints = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM complaints WHERE email=? AND status='Resolved'",
        (session["email"],)
    )
    resolved_complaints = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM complaints WHERE email=? AND status='Rejected'",
        (session["email"],)
    )
    rejected_complaints = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM complaints WHERE email=? AND admin_reply != ''",
        (session["email"],)
    )
    notifications = cursor.fetchone()[0]

    cursor.execute("""
        SELECT id, title, status, date
        FROM complaints
        WHERE email=?
        ORDER BY id DESC
        LIMIT 5
    """, (session["email"],))

    recent_complaints = cursor.fetchall()

    conn.close()

    return render_template(
        "student_dashboard.html",
        name=session["name"],
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints,
        rejected_complaints=rejected_complaints,
        notifications=notifications,
        recent_complaints=recent_complaints
    )
@app.route("/ai_suggest", methods=["POST"])
def ai_suggest():
    if "email" not in session:
        return {"error": "Login required"}, 401

    data = request.get_json()

    title = data.get("title", "")
    department = data.get("department", "")
    description = data.get("description", "")

    prompt = f"""
You are an AI assistant for a College Complaint Management System.

Improve the following complaint.

Return ONLY in this format:

Title:
Description:
Priority:

Complaint Title: {title}
Department: {department}
Description: {description}
"""

    ai_response = get_ai_response(prompt)

    return {"response": ai_response}
@app.route("/add_complaint", methods=["GET", "POST"])
def add_complaint():
    if "email" not in session:
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"].strip()
        department = request.form["department"].strip()
        description = request.form["description"].strip()
        priority = request.form["priority"].strip()

        if title == "" or department == "" or description == "" or priority == "":
            flash("Please fill all complaint details.", "danger")
            return redirect("/add_complaint")

        image = request.files.get("image")
        image_name = ""

        if image and image.filename != "":
            if allowed_file(image.filename):
                image_name = secure_filename(image.filename)
                image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_name))
            else:
                flash("Only JPG, JPEG and PNG images are allowed.", "danger")
                return redirect("/add_complaint")
            
            
        today = datetime.now().strftime("%d-%m-%Y")
        current_time = datetime.now().strftime("%I:%M %p")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO complaints
            (student_name, email, title, department, description, image, date, time, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["name"],
            session["email"],
            title,
            department,
            description,
            image_name,
            today,
            current_time,
            priority
        ))
        cursor.execute("""
        INSERT INTO notifications(message, created_at)
        VALUES (?, ?)
        """, (
            f"New Complaint Submitted: {title}",
            datetime.now().strftime("%d-%m-%Y %I:%M %p")
        ))
        conn.commit()
        conn.close()

        return redirect("/my_complaints")

    return render_template("add_complaint.html")
@app.route("/generate_complaint", methods=["POST"])
def generate_complaint():

    if "email" not in session:
        return {"success": False, "message": "Unauthorized"}

    problem = request.form.get("problem", "").strip()

    if problem == "":
        return {
            "success": False,
            "message": "Please enter your problem."
        }

    prompt = f"""
You are an AI assistant for CampusFix.

Convert the student's problem into JSON.

Return ONLY valid JSON.

Example:

{{
"title":"Wi-Fi Issue",
"description":"Internet is not working in Lab 3.",
"department":"Wi-Fi",
"priority":"High"
}}

Departments:
Library
Computer Lab
Wi-Fi
Classroom
Canteen
Washroom
Electricity
Transport

Student Problem:
{problem}
"""

    try:
        import json

        response = client.models.generate_content(
            model="models/gemini-3.6-flash",
            contents=prompt
        )

        text = response.text.strip()

        print(text)

        if text.startswith("```json"):
            text = text.replace("```json", "").replace("```", "").strip()

        data = json.loads(text)

        return {
            "success": True,
            "title": data["title"],
            "description": data["description"],
            "department": data["department"],
            "priority": data["priority"]
        }

    except Exception as e:

        print(e)

        return {
            "success": False,
            "message": str(e)
        }

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

@app.route("/notifications")
def notifications():

    if "email" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title,status,admin_reply,last_updated
        FROM complaints
        WHERE email=?
        AND admin_reply!=''
        ORDER BY id DESC
    """,(session["email"],))

    notifications = cursor.fetchall()

    conn.close()

    return render_template(
        "notifications.html",
        notifications=notifications
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
    priority_filter = request.args.get("priority", "")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE is_read = 0
    """)

    notification_count = cursor.fetchone()[0]

    cursor.execute("""
    SELECT *
    FROM notifications
    ORDER BY id DESC
    LIMIT 5
    """)

    notifications = cursor.fetchall()

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
            OR priority LIKE ?
        )
        """
        params.extend([f"%{search}%"] * 7)

    if status_filter:
        query += " AND status=?"
        params.append(status_filter)

    if department_filter:
        query += " AND department=?"
        params.append(department_filter)

    if priority_filter:
        query += " AND priority=?"
        params.append(priority_filter)

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
        priority_filter=priority_filter,
        department_labels=department_labels,
        department_counts=department_counts,
        notification_count=notification_count,
        notifications=notifications
    )


@app.route("/update_status/<int:complaint_id>", methods=["POST"])
def update_status(complaint_id):
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied! Admin only."

    new_status = request.form["status"]
    admin_reply = request.form.get("admin_reply", "")
    last_updated = datetime.now().strftime("%d-%m-%Y %I:%M %p")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE complaints
        SET
            status=?,
            admin_reply=?,
            last_updated=?,
            timeline=?
        WHERE id=?
    """, (
        
        new_status,
        admin_reply,
        last_updated,
        new_status,
        complaint_id
    ))

    cursor.execute("""
        SELECT student_name, email, title
        FROM complaints
        WHERE id=?
    """, (complaint_id,))

    student = cursor.fetchone()

    if student:
        msg = Message(
            subject=f"MGMS CampusFix | Complaint #{complaint_id} Status Updated",
            sender=("CampusFix - MGMS College", app.config["MAIL_USERNAME"]),
            recipients=[student[1]]
        )

        msg.html = f"""
        <div style="background:#0d6efd;padding:20px;text-align:center;color:white;border-radius:8px;">
            <h2>CampusFix</h2>
            <p>MGMS College of Computer Science & Information Technology, Nanded</p>
        </div>

        <br>
        <h2>Hello {student[0]},</h2>

        <p>Your complaint status has been updated.</p>

        <table border="1" cellpadding="8" cellspacing="0">
            <tr>
                <td><b>Complaint</b></td>
                <td>{student[2]}</td>
            </tr>

            <tr>
                <td><b>New Status</b></td>
                <td>{new_status}</td>
            </tr>

            <tr>
                <td><b>Admin Reply</b></td>
                <td>{admin_reply if admin_reply else "No reply provided."}</td>
            </tr>

            <tr>
                <td><b>Updated On</b></td>
                <td>{last_updated}</td>
            </tr>
        </table>

        <br>

        <p>Thank you for using <b>CampusFix</b>.</p>

        <hr>

        <small>This is an automated email from CampusFix.</small>
        """

        try:
            mail.send(msg)
            print("✅ Email sent successfully.")
        except Exception as e:
            print("❌ Email sending failed:", e)

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")
@app.route("/export_pdf")
def export_pdf():
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied! Admin only."

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM complaints ORDER BY id DESC")
    complaints = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(180, y, "CampusFix Complaints Report")

    y -= 40
    pdf.setFont("Helvetica", 10)

    for c in complaints:
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)

        pdf.drawString(40, y, f"ID: CF-2026-{c[0]:04d}")
        y -= 15
        pdf.drawString(40, y, f"Student: {c[1]} | Email: {c[2]}")
        y -= 15
        pdf.drawString(40, y, f"Title: {c[3]} | Department: {c[4]} | Status: {c[7]}")
        y -= 15
        pdf.drawString(40, y, f"Date: {c[10]} {c[11]}")
        y -= 15
        pdf.drawString(40, y, f"Admin Reply: {c[8] if c[8] else 'No reply'}")
        y -= 25

    pdf.save()
    buffer.seek(0)

    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=CampusFix_Report.pdf"

    return response

@app.route("/export_csv")
def export_csv():
    if "email" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied! Admin only."

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM complaints ORDER BY id DESC")
    complaints = cursor.fetchall()
    conn.close()

    output = BytesIO()
    text_output = output

    data = "ID,Student Name,Email,Title,Department,Description,Status,Admin Reply,Last Updated,Date,Time\n"

    for c in complaints:
        data += f"CF-2026-{c[0]:04d},{c[1]},{c[2]},{c[3]},{c[4]},{c[5]},{c[7]},{c[8]},{c[9]},{c[10]},{c[11]}\n"

    response = make_response(data)
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=CampusFix_Report.csv"

    return response
@app.route("/download_receipt/<int:complaint_id>")
def download_receipt(complaint_id):

    if "email" not in session:
        return redirect("/login")


    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM complaints
        WHERE id=? AND email=?
    """, (complaint_id, session["email"]))

    complaint = cursor.fetchone()
    print("complaint Data =", complaint)
    conn.close()

    if not complaint:
        return "Complaint not found."

    buffer = BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4

    y = height - 60

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(160, y, "CampusFix")

    y -= 30
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, "Complaint Receipt")

    y -= 45

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Complaint ID:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, f"CF-2026-{complaint[0]:04d}")

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Student Name:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[1] or ""))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Email:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[2] or ""))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Title:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[3] or ""))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Department:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[4] or ""))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Priority:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[12] or "Medium"))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Status:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[7] or "pending"))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Date:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[10] or "Not Available"))

    y -= 25

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Time:")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(170, y, str(complaint[11] or "Not Available"))

    y -= 40

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Description:")

    y -= 20

    text = pdf.beginText(50, y)
    text.setFont("Helvetica", 11)

    for line in str(complaint[5] or "").split("\n"):
        text.textLine(line)

    pdf.drawText(text)

    pdf.save()

    buffer.seek(0)

    response = make_response(buffer.getvalue())

    response.headers["Content-Type"] = "application/pdf"

    response.headers["Content-Disposition"] = (
        f"attachment; filename=Complaint_{complaint[0]}.pdf"
    )

    return response
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

    cursor.execute("""
    SELECT mobile, department, student_id, profile_photo
    FROM users
    WHERE email=?
    """, (session["email"],))

    profile = cursor.fetchone()

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
        resolved_complaints=resolved_complaints,
        profile=profile
    )

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():

    if "email" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        name = request.form["name"]
        mobile = request.form["mobile"]
        department = request.form["department"]
        student_id = request.form["student_id"]

        photo = request.files.get("profile_photo")

        filename = None

        if photo and photo.filename != "" and allowed_file(photo.filename):

            filename = secure_filename(photo.filename)

            photo.save(
                os.path.join(
                    app.config["PROFILE_UPLOAD_FOLDER"],
                    filename
                )
            )

        if filename:

            cursor.execute("""
                UPDATE users
                SET name=?,
                    mobile=?,
                    department=?,
                    student_id=?,
                    profile_photo=?
                WHERE email=?
            """,
            (
                name,
                mobile,
                department,
                student_id,
                filename,
                session["email"]
            ))

        else:

            cursor.execute("""
                UPDATE users
                SET name=?,
                    mobile=?,
                    department=?,
                    student_id=?
                WHERE email=?
            """,
            (
                name,
                mobile,
                department,
                student_id,
                session["email"]
            ))

        conn.commit()

        session["name"] = name

        conn.close()

        flash("Profile updated successfully!", "success")

        return redirect("/profile")

    cursor.execute("""
        SELECT name,email,mobile,department,student_id
        FROM users
        WHERE email=?
    """, (session["email"],))

    user = cursor.fetchone()

    conn.close()

    return render_template("edit_profile.html", user=user)
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