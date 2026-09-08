from datetime import datetime
import os
import re

from dotenv import load_dotenv

load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user
)
from werkzeug.security import generate_password_hash, check_password_hash

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

# Session cookie security
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
app.config["RATELIMIT_STORAGE_URI"] = os.getenv(
    "RATELIMIT_STORAGE_URI",
    "memory://"
)
# Request size limits
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
app.config["MAX_FORM_MEMORY_SIZE"] = 100 * 1024
app.config["MAX_FORM_PARTS"] = 50

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=app.config["RATELIMIT_STORAGE_URI"]
)

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template(
        "csrf_error.html",
        error_message="Your form session has expired or the security token is invalid. Please refresh the page and try again."
    ), 400

@app.errorhandler(429)
def handle_rate_limit_error(e):
    return render_template(
        "rate_limit_error.html",
        error_message="Too many login attempts. Please wait a minute and try again."
    ), 429

@app.errorhandler(500)
def handle_internal_server_error(e):
    return render_template("500.html"), 500

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///glownest.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin_login"


# ==============================
# Admin Model
# ==============================

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


# ==============================
# Appointment Model
# ==============================

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    service = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text)
    status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending"
    )


# ==============================
# Service Model
# ==============================

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


# ==============================
# Flask-Login User Loader
# ==============================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))


# ==============================
# Database Initialization
# ==============================

with app.app_context():
    db.create_all()

    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if admin_username and admin_password:
        existing_admin = Admin.query.filter_by(
            username=admin_username
        ).first()

        if not existing_admin:
            admin = Admin(
                username=admin_username,
                password_hash=generate_password_hash(admin_password)
            )

            db.session.add(admin)
            db.session.commit()

# ==============================
# Public Routes
# ==============================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/appointment", methods=["GET", "POST"])
def appointment():

    services = Service.query.filter_by(
        is_active=True
    ).order_by(
        Service.name.asc()
    ).all()

    def render_appointment_form(
        name="",
        email="",
        phone="",
        service_name="",
        date="",
        time="",
        message=""
    ):
        return render_template(
            "appointment.html",
            services=services,
            name=name,
            email=email,
            phone=phone,
            selected_service_name=service_name,
            date=date,
            time=time,
            message=message
        )

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        service_name = request.form.get("service", "").strip()
        date = request.form.get("date", "").strip()
        time = request.form.get("time", "").strip()
        message = request.form.get("message", "").strip()

        # Validate required fields
        if not name:
            flash("Please enter your full name.", "error")
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        if not email:
            flash("Please enter your email address.", "error")
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        if not phone:
            flash("Please enter your phone number.", "error")
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        if not service_name:
            flash("Please select a service.", "error")
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        if not date:
            flash("Please select a preferred date.", "error")
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        if not time:
            flash("Please select a preferred time.", "error")
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        # Validate phone number
        if not re.fullmatch(r"\d{10}", phone):
            flash(
                "Please enter a valid 10-digit phone number.",
                "error"
            )
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        # Check whether the selected service is active
        selected_service = Service.query.filter_by(
            name=service_name,
            is_active=True
        ).first()

        if not selected_service:
            flash(
                "The selected service is no longer available.",
                "error"
            )
            return render_appointment_form(
                name, email, phone, service_name,
                date, time, message
            )

        # Validate appointment date and time
        try:
            appointment_datetime = datetime.strptime(
        f"{date} {time}",
        "%Y-%m-%d %H:%M"
    )

        except ValueError:
            flash(
        "Please enter a valid appointment date and time.",
        "error"
    )
            return render_appointment_form(
        name, email, phone, service_name,
        date, time, message
    )

# Check whether the selected date is Sunday
        if appointment_datetime.weekday() == 6:
            flash(
        "GlowNest is closed on Sundays. Please select another date.",
        "error"
    )
            return render_appointment_form(
        name, email, phone, service_name,
        date, time, message
    )

        # Prevent past appointments
        if appointment_datetime < datetime.now():
            flash(
        "Please select a future date and time.",
        "error"
    )
            return render_appointment_form(
        name, email, phone, service_name,
        date, time, message
    )

        # Validate salon business hours
        business_open = datetime.strptime(
    f"{date} 10:00",
    "%Y-%m-%d %H:%M"
)

        business_close = datetime.strptime(
    f"{date} 19:00",
    "%Y-%m-%d %H:%M"
)

        if not (
    business_open <= appointment_datetime < business_close
):
            flash(
        "Please select an appointment time between 10:00 AM and 7:00 PM.",
        "error"
    )
            return render_appointment_form(
        name, email, phone, service_name,
        date, time, message
    )

        # Check whether the appointment slot is already booked
        existing_appointment = Appointment.query.filter_by(
    date=date,
    time=time
).filter(
            Appointment.status != "Cancelled"
).first()

        if existing_appointment:
            flash(
        "This appointment time is already booked. Please select another time.",
        "error"
    )
            return render_appointment_form(
        name, email, phone, service_name,
        date, time, message
    )

        # Create appointment
        new_appointment = Appointment(
            name=name,
            email=email,
            phone=phone,
            service=service_name,
            date=date,
            time=time,
            message=message
        )

        db.session.add(new_appointment)
        db.session.commit()

        flash(
            "Appointment request submitted successfully.",
            "success"
        )

        return redirect(url_for("appointment_success"))

    # GET request
    return render_appointment_form()
@app.route("/appointment/success")
def appointment_success():
    return render_template("appointment_success.html")


# ==============================
# Admin Routes
# ==============================

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        admin = Admin.query.filter_by(
            username=username
        ).first()

        if admin and check_password_hash(
            admin.password_hash,
            password
        ):
            login_user(admin)

            return redirect(
                url_for("admin_dashboard")
            )

        return render_template(
            "admin/login.html",
            error="Invalid username or password."
        )

    return render_template("admin/login.html")


@app.route("/admin")
@login_required
def admin_dashboard():

    status_filter = request.args.get("status", "").strip()
    search_query = request.args.get("search", "").strip()
    date_filter = request.args.get("date", "").strip()

    query = Appointment.query

    if status_filter in [
        "Pending",
        "Confirmed",
        "Completed",
        "Cancelled"
    ]:
        query = query.filter_by(
            status=status_filter
        )

    if search_query:
        search_pattern = f"%{search_query}%"

        query = query.filter(
            db.or_(
                Appointment.name.ilike(search_pattern),
                Appointment.email.ilike(search_pattern),
                Appointment.phone.ilike(search_pattern)
            )
        )
    if date_filter:
        query = query.filter(
        Appointment.date == date_filter
    )

    appointments = query.order_by(
        Appointment.id.desc()
    ).all()

    total_appointments = Appointment.query.count()

    pending_appointments = Appointment.query.filter_by(
        status="Pending"
    ).count()

    confirmed_appointments = Appointment.query.filter_by(
        status="Confirmed"
    ).count()

    completed_appointments = Appointment.query.filter_by(
        status="Completed"
    ).count()

    cancelled_appointments = Appointment.query.filter_by(
        status="Cancelled"
    ).count()

    return render_template(
        "admin/dashboard.html",
        appointments=appointments,
        total_appointments=total_appointments,
        pending_appointments=pending_appointments,
        confirmed_appointments=confirmed_appointments,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments
    )

@app.route("/admin/services")
@login_required
def admin_services():

    services = Service.query.order_by(
        Service.id.desc()
    ).all()

    return render_template(
        "admin/services.html",
        services=services
    )


@app.route("/admin/services/add", methods=["GET", "POST"])
@login_required
def add_service():

    if request.method == "POST":

        name = request.form["name"]
        description = request.form.get("description", "")
        price = request.form["price"]
        duration = request.form["duration"]

        new_service = Service(
            name=name,
            description=description,
            price=float(price),
            duration=int(duration)
        )

        db.session.add(new_service)
        db.session.commit()

        flash(
            "Service added successfully.",
            "success"
        )

        return redirect(url_for("admin_services"))

    return render_template("admin/add_service.html")


@app.route(
    "/admin/services/<int:service_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_service(service_id):

    service = db.session.get(Service, service_id)

    if not service:
        return "Service not found", 404

    if request.method == "POST":

        service.name = request.form["name"]
        service.description = request.form.get(
            "description",
            ""
        )
        service.price = float(
            request.form["price"]
        )
        service.duration = int(
            request.form["duration"]
        )

        db.session.commit()

        flash(
            "Service updated successfully.",
            "success"
        )

        return redirect(url_for("admin_services"))

    return render_template(
        "admin/edit_service.html",
        service=service
    )


@app.route(
    "/admin/services/<int:service_id>/toggle",
    methods=["POST"]
)
@login_required
def toggle_service(service_id):

    service = db.session.get(Service, service_id)

    if not service:
        flash(
            "Service not found.",
            "error"
        )
        return redirect(url_for("admin_services"))

    service.is_active = not service.is_active

    db.session.commit()

    if service.is_active:
        flash(
            "Service activated successfully.",
            "success"
        )
    else:
        flash(
            "Service deactivated successfully.",
            "success"
        )

    return redirect(url_for("admin_services"))


@app.route(
    "/admin/appointments/<int:appointment_id>/status",
    methods=["POST"]
)
@login_required
def update_appointment_status(appointment_id):

    appointment = db.session.get(
        Appointment,
        appointment_id
    )

    if not appointment:
        flash(
            "Appointment not found.",
            "error"
        )
        return redirect(url_for("admin_dashboard"))

    new_status = request.form.get("status")

    allowed_statuses = [
        "Pending",
        "Confirmed",
        "Completed",
        "Cancelled"
    ]

    if new_status not in allowed_statuses:
        flash(
            "Invalid appointment status.",
            "error"
        )
        return redirect(url_for("admin_dashboard"))

    appointment.status = new_status

    db.session.commit()

    if new_status == "Confirmed":
        flash(
            "Appointment confirmed.",
            "success"
        )

    elif new_status == "Cancelled":
        flash(
            "Appointment cancelled.",
            "success"
        )

    elif new_status == "Completed":
        flash(
            "Appointment marked as completed.",
            "success"
        )

    else:
        flash(
            "Appointment status updated.",
            "success"
        )

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
@login_required
def admin_logout():

    logout_user()

    return redirect(
        url_for("admin_login")
    )


if __name__ == "__main__":
    app.run(debug=False)
