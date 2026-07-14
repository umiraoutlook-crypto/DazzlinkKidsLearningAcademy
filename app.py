import os
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import cloudinary
import cloudinary.uploader
from bson import ObjectId
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from pymongo import ASCENDING, DESCENDING, MongoClient

# ─────────────────────────────────────────────
# Configuration — edit values here
# ─────────────────────────────────────────────
SECRET_KEY = "dazzlin-kids-academy-secret-key-2026-change-in-production"
MONGO_URI = "mongodb+srv://umiraoutlook_db_user:umira123@cluster0.x4b4h0j.mongodb.net/?appName=Cluster0"
MONGO_DB_NAME = "dazzlin_preschool"
ADMIN_PASSWORD = "dkacademy2026"

CLOUDINARY_CLOUD_NAME = "l9fufbyv"
CLOUDINARY_API_KEY = "739868479654765"
CLOUDINARY_API_SECRET = "OudNzC62otdVp-fjEoBawu1DoW4"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
MAIL_USERNAME = "dk.academy022026@gmail.com"
MAIL_PASSWORD = ""
ADMIN_EMAIL = "dk.academy022026@gmail.com"

BUSINESS_NAME = "Dazzling Kids Learning Academy"
BUSINESS_PHONE = "88384 78500"
BUSINESS_LOCATION = "Tiruvottiyur, Chennai"
BUSINESS_REG = "TN/9525"

STATIC_GALLERY = [
    ("assets/1.jpeg", "Early Motor Exploration", "Milestones"),
    ("assets/2.jpeg", "Sensory Peg Boards", "Montessori Play"),
    ("assets/3.jpeg", "Creative Block Building", "Cognitive Tasks"),
    ("assets/4.jpeg", "Mental Abacus Math", "Math Champ"),
    ("assets/5.jpeg", "Creative Art Studio", "Arts & Crafts"),
    ("assets/6.jpeg", "Interactive Coloring Session", "Creative Play"),
    ("assets/7.jpeg", "Early Phonics Reading", "Language Circle"),
    ("assets/8.jpeg", "Morning Kids Yoga", "Wellness"),
    ("assets/9.jpeg", "Wooden Shapes Puzzles", "Problem Solving"),
    ("assets/10.jpeg", "Sorting & Classification", "Milestones"),
    ("assets/11.jpeg", "Montessori Balance Play", "Sensory Gym"),
    ("assets/12.jpeg", "Public Speaking Intro", "Special Class"),
    ("assets/13.jpeg", "Graduation Achievement", "Celebrations"),
]

# ─────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY

_mongo_client = None
_db = None


# ─────────────────────────────────────────────
# MongoDB
# ─────────────────────────────────────────────
def get_db():
    global _mongo_client, _db
    if _db is None:
        _mongo_client = MongoClient(MONGO_URI)
        _db = _mongo_client[MONGO_DB_NAME]
    return _db


def utcnow():
    return datetime.now(timezone.utc)


def init_db():
    db = get_db()
    db.inquiries.create_index([("created_at", DESCENDING)])
    db.gallery_images.create_index([("created_at", DESCENDING)])


# ─────────────────────────────────────────────
# Cloudinary
# ─────────────────────────────────────────────
def cloudinary_is_ready():
    return bool(
        CLOUDINARY_CLOUD_NAME
        and CLOUDINARY_API_KEY
        and CLOUDINARY_API_SECRET
        and CLOUDINARY_API_SECRET != CLOUDINARY_API_KEY
    )


def configure_cloudinary():
    if not cloudinary_is_ready():
        return False
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )
    return True


def upload_image(file_storage, folder="dazzlin"):
    if not cloudinary_is_ready():
        raise RuntimeError(
            "Cloudinary API Secret is missing or incorrect. "
            "Open Cloudinary Dashboard → Settings → API Keys, copy the API Secret, "
            "and set CLOUDINARY_API_SECRET at the top of app.py (or in a .env file)."
        )
    configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(file_storage, folder=folder, resource_type="image")
    except Exception as exc:
        if "Invalid Signature" in str(exc):
            raise RuntimeError(
                "Cloudinary API Secret is wrong. The API Secret must be different from the API Key. "
                "Get the correct secret from Cloudinary Dashboard → Settings → API Keys."
            ) from exc
        raise
    return {
        "url": result.get("secure_url") or result.get("url"),
        "public_id": result.get("public_id"),
    }


def delete_image(public_id):
    if public_id and configure_cloudinary():
        cloudinary.uploader.destroy(public_id)


# ─────────────────────────────────────────────
# Content helpers
# ─────────────────────────────────────────────
def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "post"


def serialize_doc(doc):
    if not doc:
        return None
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    for key in ("created_at", "updated_at"):
        if key in out and isinstance(out[key], datetime):
            out[key] = out[key].isoformat()
    return out


def get_static_gallery_items():
    return [
        {
            "id": f"static-{idx}",
            "title": title,
            "tag": tag,
            "image_url": f"/static/{path}",
            "is_admin": False,
        }
        for idx, (path, title, tag) in enumerate(STATIC_GALLERY)
    ]


def get_admin_gallery_images():
    db = get_db()
    cursor = db.gallery_images.find({"cloudinary_public_id": {"$ne": None}}).sort("created_at", -1)
    items = []
    for doc in cursor:
        item = serialize_doc(doc)
        item["is_admin"] = True
        items.append(item)
    return items


def get_gallery_for_display():
    """Admin-uploaded images first, then the built-in static gallery."""
    return get_admin_gallery_images() + get_static_gallery_items()






def save_gallery_image(data):
    db = get_db()
    doc = {
        "title": data["title"],
        "tag": data.get("tag", "Gallery"),
        "image_url": data["image_url"],
        "cloudinary_public_id": data.get("cloudinary_public_id"),
        "category": data.get("category", "gallery"),
        "created_at": utcnow(),
    }
    result = db.gallery_images.insert_one(doc)
    return serialize_doc(db.gallery_images.find_one({"_id": result.inserted_id}))


def delete_gallery_image(image_id):
    db = get_db()
    try:
        oid = ObjectId(image_id)
    except Exception:
        return None
    doc = db.gallery_images.find_one({"_id": oid})
    if not doc:
        return None
    db.gallery_images.delete_one({"_id": oid})
    return doc


def save_inquiry(name, email, mobile, message):
    db = get_db()
    db.inquiries.insert_one({
        "name": name,
        "email": email,
        "mobile": mobile,
        "message": message,
        "created_at": utcnow(),
    })


# ─────────────────────────────────────────────
# Email
# ─────────────────────────────────────────────
def _send_email(subject, to_email, html_body, text_body):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        raise RuntimeError("Mail credentials are not configured.")
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{BUSINESS_NAME} <{MAIL_USERNAME}>"
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, to_email, message.as_string())


def send_admin_notification(name, email, mobile, message):
    subject = f"{BUSINESS_NAME} | New Inquiry from {name}"
    text_body = f"Name: {name}\nEmail: {email}\nMobile: {mobile}\nMessage:\n{message}"
    html_body = f"<h2>{BUSINESS_NAME}</h2><p>New inquiry from <b>{name}</b> ({email}, {mobile})</p><p>{message}</p>"
    _send_email(subject, ADMIN_EMAIL, html_body, text_body)


def send_thank_you_email(name, email):
    subject = f"Thank You for Contacting {BUSINESS_NAME}"
    text_body = f"Dear {name},\n\nThank you for reaching out. We will contact you within 24 hours.\nCall: {BUSINESS_PHONE}"
    html_body = f"<h2>Thank You, {name}!</h2><p>We received your inquiry and will get back to you soon.</p>"
    _send_email(subject, email, html_body, text_body)


def is_valid_email(email):
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def is_valid_mobile(mobile):
    return bool(re.match(r"^\d{10}$", mobile.replace(" ", "").replace("-", "")))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in as admin.", "error")
            return redirect(url_for("home", _anchor="admin-panel"))
        return view(*args, **kwargs)
    return wrapped


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────
configure_cloudinary()
init_db()


@app.context_processor
def inject_globals():
    return {
        "business_name": BUSINESS_NAME,
        "business_phone": BUSINESS_PHONE,
        "business_location": BUSINESS_LOCATION,
        "business_reg": BUSINESS_REG,
        "is_admin": session.get("admin_logged_in", False),
    }


# ─────────────────────────────────────────────
# Public routes
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return render_template(
        "index.html",
        gallery_items=get_gallery_for_display(),
        admin_gallery=get_admin_gallery_images() if session.get("admin_logged_in") else [],
    )




@app.route("/api/inquiry", methods=["POST"])
def submit_inquiry():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    mobile = (data.get("mobile") or "").strip()
    message = (data.get("message") or "").strip()
    honeypot = (data.get("_honey") or "").strip()

    if honeypot:
        return jsonify({"success": True, "message": "Thank you for contacting us."})

    errors = []
    if not name:
        errors.append("Name is required.")
    if not email or not is_valid_email(email):
        errors.append("A valid email address is required.")
    if not mobile or not is_valid_mobile(mobile):
        errors.append("A valid 10-digit mobile number is required.")
    if not message:
        errors.append("Message is required.")
    if errors:
        return jsonify({"success": False, "message": " ".join(errors)}), 400

    try:
        save_inquiry(name, email, mobile, message)
        send_admin_notification(name, email, mobile, message)
        send_thank_you_email(name, email)
    except Exception:
        return jsonify({
            "success": False,
            "message": "Unable to send your message right now. Please call us at 88384 78500.",
        }), 500

    return jsonify({
        "success": True,
        "message": "Your message has been sent successfully. A thank-you email is on its way to you.",
    })


# ─────────────────────────────────────────────
# In-page admin routes (same website)
# ─────────────────────────────────────────────
@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password", "")
    if password == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        flash("Welcome, Admin! You can now manage gallery.", "success")
        return redirect(url_for("home", _anchor="admin-panel"))
    flash("Invalid admin password.", "error")
    return redirect(url_for("home", _anchor="admin-panel"))


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))


@app.route("/admin/gallery/upload", methods=["POST"])
@admin_required
def admin_gallery_upload():
    title = (request.form.get("title") or "").strip()
    tag = (request.form.get("tag") or "New").strip()
    image_file = request.files.get("image")

    if not title or not image_file or not image_file.filename:
        return jsonify({"success": False, "message": "Title and image are required."}), 400

    try:
        uploaded = upload_image(image_file, folder="dazzlin/gallery")
        image_doc = save_gallery_image({
            "title": title,
            "tag": tag,
            "image_url": uploaded["url"],
            "cloudinary_public_id": uploaded["public_id"],
        })
        return jsonify({
            "success": True,
            "message": "Image uploaded successfully!",
            "image": image_doc
        })
    except Exception as exc:
        return jsonify({"success": False, "message": f"Upload failed: {exc}"}), 500


@app.route("/admin/gallery/<image_id>/delete", methods=["POST"])
@admin_required
def admin_gallery_delete(image_id):
    doc = delete_gallery_image(image_id)
    if doc and doc.get("cloudinary_public_id"):
        delete_image(doc["cloudinary_public_id"])
    return jsonify({"success": True, "message": "Gallery image removed."})




# Redirect old separate admin pages to homepage panel
@app.route("/admin")
@app.route("/admin/login", methods=["GET"])
def admin_legacy_redirect():
    return redirect(url_for("home", _anchor="admin-panel"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
