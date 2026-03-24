"""
app.py - Main Flask Application
AI Based Adaptive Learning and Forgetting Prediction System
"""
from dotenv import load_dotenv
load_dotenv()
import os
import json
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename

from pdf_utils import extract_text_from_pdf
from summarizer import summarize_text
from quiz_generator import generate_quiz

# ---------------------------------------------------------------------------
# Flask app configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "adaptive_learning_secret_key_2024"   # needed for session

# Folder where uploaded PDFs are temporarily saved
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    """Return True if the uploaded file has a .pdf extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Render the PDF upload page."""
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    """
    Handle PDF upload:
      1. Validate and save the file.
      2. Extract text with pdfplumber.
      3. Summarise with facebook/bart-large-cnn.
      4. Generate quiz with Groq (llama3-8b-8192).
      5. Store quiz in session and redirect to quiz page.
    """
    # --- validate upload ---
    if "pdf_file" not in request.files:
        return render_template("upload.html", error="No file part found in the request.")

    file = request.files["pdf_file"]

    if file.filename == "":
        return render_template("upload.html", error="Please select a PDF file before uploading.")

    if not allowed_file(file.filename):
        return render_template("upload.html", error="Only PDF files are supported.")

    # --- save file ---
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

        # Store quiz in session so the result page can score it
        session["quiz"] = quiz_questions
        session["summary"] = summary

        return render_template("quiz.html", questions=quiz_questions, summary=summary)

    except Exception as exc:
        print(f"[ERROR] {exc}")
        return render_template("upload.html",
                               error=f"An error occurred while processing your PDF: {str(exc)}")

    finally:
        # Clean up the uploaded file after processing
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/submit", methods=["POST"])
def submit():
    """
    Score the submitted quiz answers and render the result page.
    Answers arrive as form fields: answer_0, answer_1, … answer_9
    """
    quiz_questions = session.get("quiz", [])

    if not quiz_questions:
        return redirect(url_for("index"))

    total = len(quiz_questions)
    correct = 0
    results = []

    for i, question in enumerate(quiz_questions):
        user_answer = request.form.get(f"answer_{i}", "").strip()
        correct_answer = question.get("correct_answer", "").strip()

        is_correct = user_answer.upper() == correct_answer.upper()
        if is_correct:
            correct += 1

        results.append({
            "question": question["question"],
            "options": question["options"],
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct
        })

    score_percent = round((correct / total) * 100, 2) if total > 0 else 0

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
