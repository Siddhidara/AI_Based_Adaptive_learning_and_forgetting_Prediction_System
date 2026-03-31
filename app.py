"""
app.py - Main Flask Application
AI Based Adaptive Learning and Forgetting Prediction System
"""
from dotenv import load_dotenv
load_dotenv()
import os
import json
import traceback
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from config import CONFIG
from models import db, User, Document, Concept, Question, Attempt, ConceptMastery, update_concept_mastery, schedule_next_revision
from pdf_utils import extract_text_from_pdf
from summarizer import summarize_text
from quiz_generator import generate_quiz

# ---------------------------------------------------------------------------
# Flask app configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(CONFIG)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    return User.query.get(int(user_id))

# Folder where uploaded PDFs are temporarily saved
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Create app context for database operations
with app.app_context():
    db.create_all()


def allowed_file(filename):
    """Return True if the uploaded file has a .pdf extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user account"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()
        full_name = request.form.get("full_name", "").strip()
        
        # Validation
        if not username or not email or not password:
            flash("Username, email, and password are required.", "error")
            return render_template("register.html")
        
        if password != password_confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("register.html")
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Please choose a different username.", "error")
            return render_template("register.html")
        
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please use a different email.", "error")
            return render_template("register.html")
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            full_name=full_name or username,
            role="student"
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash("Registration successful! Please log in with your credentials.", "success")
        return redirect(url_for("login"))
    
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login user"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("login.html")
        
        # Find user by username or email
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User.query.filter_by(email=username).first()
        
        if not user or not user.check_password(password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")
        
        # Login user
        login_user(user)
        flash(f"Welcome back, {user.username}!", "success")
        
        # Redirect to next page or index
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("index"))
    
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Render the PDF upload page (requires login)."""
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("upload.html", user=current_user)


@app.route("/my-documents", methods=["GET"])
@login_required
def my_documents():
    """Show all documents uploaded by the current user."""
    documents = Document.query.filter_by(uploader_id=current_user.id).order_by(
        Document.created_at.desc()
    ).all()
    
    # Enrich with stats
    doc_stats = []
    for doc in documents:
        concept_count = Concept.query.filter_by(document_id=doc.id).count()
        question_count = Question.query.filter(
            Question.concept_id.in_([c.id for c in doc.concepts])
        ).count()
        attempt_count = Attempt.query.filter(
            Attempt.user_id == current_user.id,
            Attempt.question_id.in_([q.id for q in Question.query.filter(
                Question.concept_id.in_([c.id for c in doc.concepts])
            )])
        ).count()
        
        doc_stats.append({
            "doc": doc,
            "concepts": concept_count,
            "questions": question_count,
            "attempts": attempt_count
        })
    
    return render_template("my_documents.html", document_stats=doc_stats, user=current_user)


@app.route("/quiz-from-document/<int:document_id>", methods=["GET"])
@login_required
def quiz_from_document(document_id):
    """Generate a fresh quiz from an existing document."""
    doc = Document.query.get(document_id)
    
    if not doc or doc.uploader_id != current_user.id:
        flash("Document not found or you don't have access.", "error")
        return redirect(url_for("my_documents"))
    
    try:
        # Regenerate quiz from the document's summary
        print("[INFO] Regenerating quiz from document...")
        quiz_questions = generate_quiz(doc.summary)
        
        # Store in session
        session["quiz"] = quiz_questions
        session["summary"] = doc.summary
        session["document_id"] = doc.id
        session["student_user_id"] = current_user.id
        
        print(f"[SUCCESS] Quiz regenerated from document {doc.id}")
        return render_template("quiz.html", questions=quiz_questions, summary=doc.summary, 
                             document_title=doc.title)
    
    except Exception as exc:
        error_trace = traceback.format_exc()
        print(f"[ERROR] Failed to regenerate quiz: {error_trace}")
        flash(f"Error regenerating quiz: {str(exc)}", "error")
        return redirect(url_for("my_documents"))


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    """
    Handle PDF upload:
      1. Validate and save the file.
      2. Extract text with pdfplumber.
      3. Summarise with facebook/bart-large-cnn.
      4. Generate quiz with Groq (llama3-8b-8192).
      5. Save to database: Document, Concepts, Questions
      6. Redirect to quiz page.
    """
    # --- validate upload ---
    if "pdf_file" not in request.files:
        return render_template("upload.html", error="No file part found in the request.")

    file = request.files["pdf_file"]

    if file.filename == "":
        return render_template("upload.html", error="Please select a PDF file before uploading.")

    if not allowed_file(file.filename):
        return render_template("upload.html", error="Only PDF files are supported.")

    # --- save file temporarily ---
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        # Step 1 – Extract text
        print("[INFO] Extracting text from PDF …")
        extracted_text = extract_text_from_pdf(filepath)

        if not extracted_text or len(extracted_text.strip()) < 100:
            return render_template("upload.html",
                                   error="Could not extract enough text from the PDF. "
                                         "Make sure it is a text-based (not scanned) PDF.")

        # Step 2 – Summarise
        print("[INFO] Summarising text …")
        summary = summarize_text(extracted_text)

        # Step 3 – Generate quiz
        print("[INFO] Generating quiz questions …")
        quiz_questions = generate_quiz(summary)

        # --- Save to Database ---
        print("[INFO] Saving to database…")
        
        # Use the currently logged-in user
        student_user = current_user
        
        # Create Document record
        doc = Document(
            title=filename,
            filename=filename,
            uploader_id=student_user.id,
            extracted_text=extracted_text,
            summary=summary,
            file_size=os.path.getsize(filepath)
        )
        db.session.add(doc)
        db.session.commit()
        
        # Create Concept records (split text into chunks)
        # For now, use simple split; later can use semantic chunking
        chunk_size = 500  # characters
        chunks = [extracted_text[i:i+chunk_size] for i in range(0, len(extracted_text), chunk_size)]
        
        concepts = []
        for idx, chunk in enumerate(chunks[:10]):  # Limit to 10 concepts for performance
            if len(chunk.strip()) > 50:
                concept = Concept(
                    document_id=doc.id,
                    title=f"Concept {idx + 1}",
                    content=chunk,
                    chunk_index=idx
                )
                db.session.add(concept)
                concepts.append(concept)
        
        db.session.commit()
        
        # Create Question records from generated quiz
        for q_idx, question in enumerate(quiz_questions):
            # Link question to a concept (round-robin)
            concept = concepts[q_idx % len(concepts)] if concepts else None
            
            q = Question(
                concept_id=concept.id if concept else None,
                question_text=question.get("question", ""),
                question_type=question.get("type", "mcq"),
                options=question.get("options", []),
                correct_answer=question.get("correct_answer", "")
            )
            db.session.add(q)
        
        db.session.commit()
        
        # Store quiz and document ID in session for the quiz page
        session["quiz"] = quiz_questions
        session["summary"] = summary
        session["document_id"] = doc.id
        session["student_user_id"] = student_user.id

        print(f"[SUCCESS] Document saved with ID {doc.id}")
        return render_template("quiz.html", questions=quiz_questions, summary=summary, 
                             document_title=filename)

    except Exception as exc:
        error_trace = traceback.format_exc()
        print(f"[ERROR] Full traceback:\n{error_trace}")
        error_msg = f"Error: {type(exc).__name__}: {str(exc)}"
        return render_template("upload.html",
                               error=f"An error occurred while processing your PDF:\n{error_msg}")

    finally:
        # Clean up the uploaded file after processing
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/submit", methods=["POST"])
@login_required
def submit():
    """
    Score the submitted quiz answers and save to database:
    - Create Attempt records
    - Update ConceptMastery
    - Predict next revision date (placeholder)
    """
    quiz_questions = session.get("quiz", [])
    student_user_id = session.get("student_user_id")
    document_id = session.get("document_id")

    if not quiz_questions or not student_user_id:
        return redirect(url_for("index"))

    total = len(quiz_questions)
    correct = 0
    results = []

    # Fetch questions from database (to get concept_id for linking)
    doc = Document.query.get(document_id) if document_id else None
    questions_from_db = Question.query.filter(
        Question.concept_id.in_([c.id for c in (doc.concepts if doc else [])])
    ).all() if doc else []

    for i, question in enumerate(quiz_questions):
        user_answer = request.form.get(f"answer_{i}", "").strip()
        correct_answer = question.get("correct_answer", "").strip()

        is_correct = user_answer.upper() == correct_answer.upper()
        if is_correct:
            correct += 1

        # Try to find the corresponding Question in database
        question_obj = questions_from_db[i] if i < len(questions_from_db) else None

        # Save Attempt to database
        if question_obj:
            # Calculate days since last attempt on this question
            last_attempt = Attempt.query.filter_by(
                user_id=student_user_id,
                question_id=question_obj.id
            ).order_by(Attempt.attempted_at.desc()).first()
            
            days_since_last = None
            if last_attempt:
                time_diff = datetime.utcnow() - last_attempt.attempted_at
                days_since_last = time_diff.total_seconds() / (24 * 3600)  # Convert to days
            
            # Calculate attempt number (count all previous attempts on this question)
            previous_attempts = Attempt.query.filter_by(
                user_id=student_user_id,
                question_id=question_obj.id
            ).count()
            
            attempt = Attempt(
                user_id=student_user_id,
                question_id=question_obj.id,
                user_answer=user_answer,
                is_correct=is_correct,
                response_time_seconds=0,  # Can be captured from frontend timing
                attempt_number=previous_attempts + 1,
                days_since_last_attempt=days_since_last
            )
            db.session.add(attempt)
            
            # Update ConceptMastery for this concept
            if question_obj.concept_id:
                update_concept_mastery(student_user_id, question_obj.concept_id, is_correct)
        
        results.append({
            "question": question["question"],
            "options": question["options"],
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct
        })

    db.session.commit()
    
    score_percent = round((correct / total) * 100, 2) if total > 0 else 0

    print(f"[INFO] Quiz attempt saved: {correct}/{total} ({score_percent}%)")

    return render_template(
        "result.html",
        results=results,
        total=total,
        correct=correct,
        score_percent=score_percent
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
