
import os
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATABASE_DIR = os.path.join(BASE_DIR, "database")

DATABASE_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(DATABASE_DIR, "skillconnect.db")
)

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

app = Flask(
    __name__,
    template_folder=FRONTEND_DIR,
    static_folder=FRONTEND_DIR,
    static_url_path="/static"
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "skillconnect-development-key"
)


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT NOT NULL,
            account_type TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [column["name"] for column in cursor.fetchall()]

    if "qualification" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN qualification TEXT")

    if "skills" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN skills TEXT")

    if "experience" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN experience TEXT")

    if "resume" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN resume TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id INTEGER NOT NULL,
            job_title TEXT NOT NULL,
            company_name TEXT NOT NULL,
            location TEXT NOT NULL,
            salary TEXT,
            job_type TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employer_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Pending',
            UNIQUE(job_id, candidate_id),
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (candidate_id) REFERENCES users(id)
        )
    """)

    cursor.execute("PRAGMA table_info(applications)")
    columns = [column["name"] for column in cursor.fetchall()]

    if "status" not in columns:
        cursor.execute("""
            ALTER TABLE applications
            ADD COLUMN status TEXT DEFAULT 'Pending'
        """)

    conn.commit()
    conn.close()


# HOME PAGE
@app.route("/")
def home():
    return render_template("index.html")


# USER REGISTRATION
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        account_type = request.form.get("account_type", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([
            full_name, email, mobile,
            account_type, password, confirm_password
        ]):
            return "Please fill all fields"

        if account_type not in ["candidate", "employer"]:
            return "Invalid account type"

        if password != confirm_password:
            return "Passwords do not match"

        if len(password) < 8:
            return "Password must be at least 8 characters"

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()

        try:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users
                (full_name, email, mobile, account_type, password)
                VALUES (?, ?, ?, ?, ?)
            """, (
                full_name,
                email,
                mobile,
                account_type,
                hashed_password
            ))

            conn.commit()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return "This email is already registered"

        finally:
            conn.close()

    return render_template("register.html")


# USER LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return "Please enter email and password"

        conn = get_db_connection()

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, full_name, account_type, password
                FROM users
                WHERE email = ?
            """, (email,))

            user = cursor.fetchone()

            if user and check_password_hash(user["password"], password):

                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["account_type"] = user["account_type"]

                return redirect(url_for("dashboard"))

            return "Invalid email or password"

        finally:
            conn.close()

    return render_template("login.html")


# USER DASHBOARD
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM jobs
        WHERE employer_id = ?
        ORDER BY id DESC
    """, (session["user_id"],))

    jobs = cursor.fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        user_name=session["user_name"],
        account_type=session["account_type"],
        jobs=jobs
    )


# EXPLORE JOBS
@app.route("/jobs")
def explore_jobs():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM jobs
        ORDER BY id DESC
    """)

    jobs = cursor.fetchall()
    conn.close()

    return render_template("jobs.html", jobs=jobs)


# APPLY FOR JOB
@app.route("/apply/<int:job_id>", methods=["POST"])
def apply_job(job_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "candidate":
        return "Only candidates can apply for jobs"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    job = cursor.fetchone()

    if not job:
        conn.close()
        return "Job not found"

    try:
        cursor.execute("""
            INSERT INTO applications (job_id, candidate_id)
            VALUES (?, ?)
        """, (job_id, session["user_id"]))

        conn.commit()
        message = "Application submitted successfully!"

    except sqlite3.IntegrityError:
        message = "You have already applied for this job."

    finally:
        conn.close()

    return message


# MY APPLICATIONS
@app.route("/my-applications")
def my_applications():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "candidate":
        return "Only candidates can view their applications"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            jobs.job_title,
            jobs.company_name,
            jobs.location,
            jobs.salary,
            jobs.job_type,
            applications.applied_at,
            applications.status
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        WHERE applications.candidate_id = ?
        ORDER BY applications.id DESC
    """, (session["user_id"],))

    applications = cursor.fetchall()
    conn.close()

    return render_template(
        "my_applications.html",
        applications=applications
    )


# VIEW JOB APPLICANTS
@app.route("/applicants/<int:job_id>")
def view_applicants(job_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "employer":
        return "Only employers can view applicants"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, job_title
        FROM jobs
        WHERE id = ? AND employer_id = ?
    """, (job_id, session["user_id"]))

    job = cursor.fetchone()

    if not job:
        conn.close()
        return "Job not found"

    cursor.execute("""
        SELECT
            applications.id,
            users.full_name,
            users.email,
            users.mobile,
            applications.applied_at,
            applications.status
        FROM applications
        JOIN users ON applications.candidate_id = users.id
        WHERE applications.job_id = ?
        ORDER BY applications.id DESC
    """, (job_id,))

    applicants = cursor.fetchall()
    conn.close()

    return render_template(
        "applicants.html",
        job=job,
        applicants=applicants
    )


# UPDATE APPLICATION STATUS
@app.route("/update-status/<int:application_id>", methods=["POST"])
def update_status(application_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "employer":
        return "Only employers can update application status"

    status = request.form.get("status")

    allowed_statuses = [
        "Pending",
        "Shortlisted",
        "Rejected",
        "Selected"
    ]

    if status not in allowed_statuses:
        return "Invalid application status"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT jobs.id AS job_id
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        WHERE applications.id = ?
        AND jobs.employer_id = ?
    """, (application_id, session["user_id"]))

    application = cursor.fetchone()

    if not application:
        conn.close()
        return "Application not found"

    cursor.execute("""
        UPDATE applications
        SET status = ?
        WHERE id = ?
    """, (status, application_id))

    conn.commit()
    conn.close()

    return redirect(
        url_for("view_applicants", job_id=application["job_id"])
    )


# POST A JOB
@app.route("/post-job", methods=["GET", "POST"])
def post_job():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "employer":
        return "Only employers can post jobs"

    if request.method == "POST":

        job_title = request.form.get("job_title", "").strip()
        company_name = request.form.get("company_name", "").strip()
        location = request.form.get("location", "").strip()
        salary = request.form.get("salary", "").strip()
        job_type = request.form.get("job_type", "")
        description = request.form.get("description", "").strip()

        if not all([
            job_title,
            company_name,
            location,
            job_type,
            description
        ]):
            return "Please fill all required fields"

        conn = get_db_connection()

        try:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO jobs
                (
                    employer_id,
                    job_title,
                    company_name,
                    location,
                    salary,
                    job_type,
                    description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session["user_id"],
                job_title,
                company_name,
                location,
                salary,
                job_type,
                description
            ))

            conn.commit()

            return redirect(url_for("dashboard"))

        finally:
            conn.close()

    return render_template("post_job.html")


# CANDIDATE PROFILE
@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "candidate":
        return "Only candidates can access this page"

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":

        qualification = request.form.get("qualification", "").strip()
        skills = request.form.get("skills", "").strip()
        experience = request.form.get("experience", "").strip()

        cursor.execute("""
            UPDATE users
            SET qualification = ?, skills = ?, experience = ?
            WHERE id = ?
        """, (
            qualification,
            skills,
            experience,
            session["user_id"]
        ))

        conn.commit()

    cursor.execute("""
        SELECT full_name, qualification, skills, experience
        FROM users
        WHERE id = ?
    """, (session["user_id"],))

    user = cursor.fetchone()
    conn.close()

    return render_template("profile.html", user=user)


# USER LOGOUT
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# CREATE DATABASE TABLES
create_table()


if __name__ == "__main__":
    app.run(debug=True)
