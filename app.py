# """
# app.py - Clean Stable Version (Jinja Safe)
# """

# from dotenv import load_dotenv
# load_dotenv()

# import os
# import traceback
# from datetime import datetime

# from flask import Flask, request, render_template, redirect, url_for, session, flash
# from flask_login import LoginManager, login_user, logout_user, login_required, current_user
# from werkzeug.utils import secure_filename

# from config import CONFIG
# from models import db, User, Document, Concept, Question, Attempt, ConceptMastery, update_concept_mastery
# from pdf_utils import extract_text_from_pdf
# from summarizer import summarize_text
# from quiz_generator import generate_quiz
# from predictor import predict_revision

# # -------------------------------------------------
# # APP CONFIG
# # -------------------------------------------------
# app = Flask(__name__)
# app.config.from_object(CONFIG)
# app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# db.init_app(app)

# # -------------------------------------------------
# # LOGIN
# # -------------------------------------------------
# login_manager = LoginManager()
# login_manager.init_app(app)
# login_manager.login_view = "login"

# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))

# # -------------------------------------------------
# # FILE CONFIG
# # -------------------------------------------------
# UPLOAD_FOLDER = "uploads"
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# # -------------------------------------------------
# # DB INIT
# # -------------------------------------------------
# with app.app_context():
#     db.create_all()

# # -------------------------------------------------
# # ROUTES
# # -------------------------------------------------
# @app.route("/")
# def index():
#     if not current_user.is_authenticated:
#         return redirect(url_for("login"))
#     return render_template("upload.html", user=current_user)


# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         username = request.form.get("username", "").strip()
#         password = request.form.get("password", "").strip()

#         user = User.query.filter_by(username=username).first()

#         if not user or not user.check_password(password):
#             flash("Invalid credentials", "error")
#             return render_template("login.html")

#         login_user(user)
#         return redirect(url_for("index"))

#     return render_template("login.html")


# @app.route("/register", methods=["GET", "POST"])
# def register():
#     if request.method == "POST":
#         username = request.form.get("username", "").strip()
#         email = request.form.get("email", "").strip()
#         password = request.form.get("password", "").strip()

#         if User.query.filter_by(username=username).first():
#             flash("Username exists", "error")
#             return render_template("register.html")

#         user = User(username=username, email=email)
#         user.set_password(password)

#         db.session.add(user)
#         db.session.commit()

#         return redirect(url_for("login"))

#     return render_template("register.html")


# @app.route("/logout")
# @login_required
# def logout():
#     logout_user()
#     return redirect(url_for("login"))


# # -------------------------------------------------
# # UPLOAD
# # -------------------------------------------------
# @app.route("/upload", methods=["POST"])
# @login_required
# def upload():
#     try:
#         file = request.files.get("pdf_file")

#         if not file or file.filename == "":
#             flash("No file selected", "error")
#             return redirect(url_for("index"))

#         filename = secure_filename(file.filename)
#         path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
#         file.save(path)

#         # Extract + Process
#         text = extract_text_from_pdf(path)
#         summary = summarize_text(text)
#         quiz = generate_quiz(summary)

#         # Save document
#         doc = Document(
#             title=filename,
#             filename=filename,
#             uploader_id=current_user.id,
#             extracted_text=text,
#             summary=summary
#         )
#         db.session.add(doc)
#         db.session.commit()

#         # Store session safely
#         session["quiz"] = quiz if quiz else []
#         session["document_id"] = doc.id
#         session["student_user_id"] = current_user.id

#         return render_template(
#             "quiz.html",
#             questions=session["quiz"],   # ✅ always safe
#             summary=summary or "",
#             document_title=filename or ""
#         )

#     except Exception as e:
#         print(traceback.format_exc())
#         flash("Upload failed", "error")
#         return redirect(url_for("index"))


# # -------------------------------------------------
# # SUBMIT QUIZ
# # -------------------------------------------------
# @app.route("/submit", methods=["POST"])
# @login_required
# def submit():
#     quiz_questions = session.get("quiz", [])
#     student_user_id = session.get("student_user_id")
#     document_id = session.get("document_id")

#     if not quiz_questions or not student_user_id:
#         return redirect(url_for("index"))

#     total = len(quiz_questions)
#     correct = 0
#     results = []

#     doc = Document.query.get(document_id) if document_id else None
#     questions_from_db = Question.query.filter(
#         Question.concept_id.in_([c.id for c in (doc.concepts if doc else [])])
#     ).all() if doc else []

#     for i, question in enumerate(quiz_questions):
#         user_answer = request.form.get(f"answer_{i}", "").strip()
#         correct_answer = question.get("correct_answer", "").strip()

#         is_correct = user_answer.upper() == correct_answer.upper()
#         if is_correct:
#             correct += 1

#         question_obj = questions_from_db[i] if i < len(questions_from_db) else None

#         if question_obj:
#             last_attempt = Attempt.query.filter_by(
#                 user_id=student_user_id,
#                 question_id=question_obj.id
#             ).order_by(Attempt.attempted_at.desc()).first()

#             days_since_last = None
#             if last_attempt:
#                 time_diff = datetime.utcnow() - last_attempt.attempted_at
#                 days_since_last = time_diff.total_seconds() / (24 * 3600)

#             previous_attempts = Attempt.query.filter_by(
#                 user_id=student_user_id,
#                 question_id=question_obj.id
#             ).count()

#             attempt = Attempt(
#                 user_id=student_user_id,
#                 question_id=question_obj.id,
#                 user_answer=user_answer,
#                 is_correct=is_correct,
#                 response_time_seconds=0,
#                 attempt_number=previous_attempts + 1,
#                 days_since_last_attempt=days_since_last
#             )
#             db.session.add(attempt)

#             if question_obj.concept_id:
#                 update_concept_mastery(student_user_id, question_obj.concept_id, is_correct)

#         results.append({
#             "question": question["question"],
#             "options": question["options"],
#             "user_answer": user_answer,
#             "correct_answer": correct_answer,
#             "is_correct": is_correct
#         })

#     db.session.commit()

#     score_percent = round((correct / total) * 100, 2) if total > 0 else 0
#     print(f"[INFO] Quiz attempt saved: {correct}/{total} ({score_percent}%)")

#     # ✅ PREDICTION BLOCK (FIXED)
#     revision_info = None
#     try:
#         print("🔥 ENTERING PREDICTOR")

#         all_attempts = Attempt.query.filter_by(user_id=student_user_id).all()

#         if all_attempts:
#             student_historical_avg = round(
#                 sum(100 if a.is_correct else 0 for a in all_attempts) / len(all_attempts), 2
#             )
#         else:
#             student_historical_avg = score_percent

#         scores_this_concept = [score_percent]

#         days_since = 0

#         revision_info = predict_revision(
#             student_historical_avg=student_historical_avg,
#             diff_numeric=2,
#             all_scores_this_concept=scores_this_concept,
#             days_since_last_attempt=days_since
#         )

#         print("✅ PREDICTION RESULT:", revision_info)

#     except Exception as e:
#         print("❌ PREDICTOR ERROR:", e)

#     return render_template(
#         "result.html",
#         results=results,
#         total=total,
#         correct=correct,
#         score_percent=score_percent,
#         revision_info=revision_info
#     )


# # -------------------------------------------------
# # RUN
# # -------------------------------------------------
# if __name__ == "__main__":
#     app.run(debug=True)
# """
# app.py - Clean Stable Version (Jinja Safe)
# """

# from dotenv import load_dotenv
# load_dotenv()

# import os
# import traceback
# from datetime import datetime

# from flask import Flask, request, render_template, redirect, url_for, session, flash
# from flask_login import LoginManager, login_user, logout_user, login_required, current_user
# from werkzeug.utils import secure_filename

# from config import CONFIG
# from models import db, User, Document, Concept, Question, Attempt, ConceptMastery, update_concept_mastery, schedule_next_revision
# from pdf_utils import extract_text_from_pdf
# from summarizer import summarize_text
# from quiz_generator import generate_quiz
# from predictor import predict_revision
# from sqlalchemy.exc import IntegrityError

# # -------------------------------------------------
# # APP CONFIG
# # -------------------------------------------------
# app = Flask(__name__)
# app.config.from_object(CONFIG)
# app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# db.init_app(app)

# # -------------------------------------------------
# # LOGIN
# # -------------------------------------------------
# login_manager = LoginManager()
# login_manager.init_app(app)
# login_manager.login_view = "login"

# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))

# # -------------------------------------------------
# # FILE CONFIG
# # -------------------------------------------------
# UPLOAD_FOLDER = "uploads"
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# # -------------------------------------------------
# # DB INIT
# # -------------------------------------------------
# with app.app_context():
#     db.create_all()

# # -------------------------------------------------
# # ROUTES
# # -------------------------------------------------
# @app.route("/")
# def index():
#     if not current_user.is_authenticated:
#         return redirect(url_for("login"))
#     return render_template("upload.html", user=current_user)


# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         username = request.form.get("username", "").strip()
#         password = request.form.get("password", "").strip()

#         user = User.query.filter_by(username=username).first()

#         if not user or not user.check_password(password):
#             flash("Invalid credentials", "error")
#             return render_template("login.html")

#         login_user(user)
#         return redirect(url_for("index"))

#     return render_template("login.html")


# @app.route("/register", methods=["GET", "POST"])
# def register():
#     if request.method == "POST":
#         username = request.form.get("username", "").strip()
#         email = request.form.get("email", "").strip()
#         password = request.form.get("password", "").strip()

#         # 🔹 Check username
#         if User.query.filter_by(username=username).first():
#             flash("Username already exists", "error")
#             return render_template("register.html")

#         # 🔹 Check email (THIS WAS MISSING)
#         if User.query.filter_by(email=email).first():
#             flash("Email already registered. Please login.", "error")
#             return render_template("register.html")

#         # 🔹 Create user
#         user = User(username=username, email=email)
#         user.set_password(password)

#         try:
#             db.session.add(user)
#             db.session.commit()
#             flash("Registration successful! Please login.", "success")
#             return redirect(url_for("login"))

#         except IntegrityError:
#             db.session.rollback()
#             flash("Something went wrong. Email or username might already exist.", "error")
#             return render_template("register.html")

#     return render_template("register.html")


# @app.route("/logout")
# @login_required
# def logout():
#     logout_user()
#     return redirect(url_for("login"))


# # -------------------------------------------------
# # UPLOAD
# # -------------------------------------------------
# @app.route("/upload", methods=["POST"])
# @login_required
# def upload():
#     try:
#         file = request.files.get("pdf_file")

#         if not file or file.filename == "":
#             flash("No file selected", "error")
#             return redirect(url_for("index"))

#         filename = secure_filename(file.filename)
#         path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
#         file.save(path)

#         text = extract_text_from_pdf(path)
#         summary = summarize_text(text)
#         quiz = generate_quiz(summary)

#         doc = Document(
#             title=filename,
#             filename=filename,
#             uploader_id=current_user.id,
#             extracted_text=text,
#             summary=summary
#         )
#         db.session.add(doc)
#         db.session.commit()

#         session["quiz"] = quiz if quiz else []
#         session["document_id"] = doc.id
#         session["student_user_id"] = current_user.id

#         return render_template(
#             "quiz.html",
#             questions=session["quiz"],
#             summary=summary or "",
#             document_title=filename or ""
#         )

#     except Exception as e:
#         print(traceback.format_exc())
#         flash("Upload failed", "error")
#         return redirect(url_for("index"))


# # -------------------------------------------------
# # SUBMIT QUIZ
# # -------------------------------------------------
# @app.route("/submit", methods=["POST"])
# @login_required
# def submit():
#     quiz_questions = session.get("quiz", [])
#     student_user_id = session.get("student_user_id")
#     document_id = session.get("document_id")

#     if not quiz_questions or not student_user_id:
#         return redirect(url_for("index"))

#     total = len(quiz_questions)
#     correct = 0
#     results = []

#     doc = Document.query.get(document_id) if document_id else None
#     questions_from_db = Question.query.filter(
#         Question.concept_id.in_([c.id for c in (doc.concepts if doc else [])])
#     ).all() if doc else []

#     for i, question in enumerate(quiz_questions):
#         user_answer = request.form.get(f"answer_{i}", "").strip()
#         correct_answer = question.get("correct_answer", "").strip()

#         is_correct = user_answer.upper() == correct_answer.upper()
#         if is_correct:
#             correct += 1

#         question_obj = questions_from_db[i] if i < len(questions_from_db) else None

#         if question_obj:
#             last_attempt = Attempt.query.filter_by(
#                 user_id=student_user_id,
#                 question_id=question_obj.id
#             ).order_by(Attempt.attempted_at.desc()).first()

#             days_since_last = None
#             if last_attempt:
#                 time_diff = datetime.utcnow() - last_attempt.attempted_at
#                 days_since_last = time_diff.total_seconds() / (24 * 3600)

#             previous_attempts = Attempt.query.filter_by(
#                 user_id=student_user_id,
#                 question_id=question_obj.id
#             ).count()

#             attempt = Attempt(
#                 user_id=student_user_id,
#                 question_id=question_obj.id,
#                 user_answer=user_answer,
#                 is_correct=is_correct,
#                 response_time_seconds=0,
#                 attempt_number=previous_attempts + 1,
#                 days_since_last_attempt=days_since_last
#             )
#             db.session.add(attempt)

#             if question_obj.concept_id:
#                 update_concept_mastery(student_user_id, question_obj.concept_id, is_correct)

#         results.append({
#             "question": question["question"],
#             "options": question["options"],
#             "user_answer": user_answer,
#             "correct_answer": correct_answer,
#             "is_correct": is_correct
#         })

#     db.session.commit()
    
#     score_percent = round((correct / total) * 100, 2) if total > 0 else 0
#     print(f"[INFO] Quiz attempt saved: {correct}/{total} ({score_percent}%)")

#     # ── ADDED BY YOU: START ────────────────────────────────────────
#     revision_info = None
#     try:
#         print("🔥 ENTERING PREDICTOR")

#         all_attempts = Attempt.query.filter_by(user_id=student_user_id).all()

#         if all_attempts:
#             student_historical_avg = round(
#                 sum(100 if a.is_correct else 0 for a in all_attempts) / len(all_attempts), 2
#             )
#         else:
#             student_historical_avg = score_percent

#         scores_this_concept = [score_percent]
#         days_since = 0

#         revision_info = predict_revision(
#             student_historical_avg=student_historical_avg,
#             diff_numeric=2,
#             all_scores_this_concept=scores_this_concept,
#             days_since_last_attempt=days_since
#         )

#         print("✅ PREDICTION RESULT:", revision_info)

#         # save to revision_schedules table
#         if doc and doc.concepts:
#             for concept in doc.concepts:
#                 schedule_next_revision(
#                     user_id         = student_user_id,
#                     concept_id      = concept.id,
#                     interval_days   = int(revision_info["revise_in_days"]),
#                     forgetting_prob = round(1 - (score_percent / 100), 2),
#                     reason          = f"ML prediction: {revision_info['urgency']}"
#                 )
#             print(f"[PREDICTOR] Saved to DB for {len(doc.concepts)} concepts")

#     except Exception as e:
#         print("❌ PREDICTOR ERROR:", e)
#         print(traceback.format_exc())
#         revision_info = None
#     # ── ADDED BY YOU: END ──────────────────────────────────────────

#     return render_template(
#         "result.html",
#         results=results,
#         total=total,
#         correct=correct,
#         score_percent=score_percent,
#         revision_info=revision_info
#     )


# # ── ADDED BY YOU: my-revisions route ──────────────────────────────
# @app.route("/my-revisions")
# @login_required
# def my_revisions():
#     from models import RevisionSchedule
#     schedules = RevisionSchedule.query.filter_by(
#         user_id=current_user.id,
#         was_revised=False
#     ).order_by(RevisionSchedule.next_revision_date.asc()).all()

#     revision_list = []
#     for s in schedules:
#         concept = Concept.query.get(s.concept_id)
#         doc     = Document.query.get(concept.document_id) if concept else None
#         days_left = (s.next_revision_date - datetime.utcnow()).days
#         revision_list.append({
#             "schedule":      s,
#             "concept":       concept,
#             "doc":           doc,
#             "revision_date": s.next_revision_date,
#             "days_left":     max(0, days_left),
#             "urgency":       s.schedule_reason,
#             "doc_id":        doc.id if doc else None,
#         })

#     return render_template("my_revisions.html", revision_list=revision_list)
# # ── END ADDED BY YOU ───────────────────────────────────────────────


# # -------------------------------------------------
# # RUN
# # -------------------------------------------------
# if __name__ == "__main__":
#     app.run(debug=True)
# """
# app.py - Clean Stable Version (Jinja Safe)
# """

# from dotenv import load_dotenv
# load_dotenv()

# import os
# import traceback
# from datetime import datetime

# from flask import Flask, request, render_template, redirect, url_for, session, flash
# from flask_login import LoginManager, login_user, logout_user, login_required, current_user
# from werkzeug.utils import secure_filename

# from config import CONFIG
# from models import db, User, Document, Concept, Question, Attempt, ConceptMastery, update_concept_mastery
# from pdf_utils import extract_text_from_pdf
# from summarizer import summarize_text
# from quiz_generator import generate_quiz
# from predictor import predict_revision

# # -------------------------------------------------
# # APP CONFIG
# # -------------------------------------------------
# app = Flask(__name__)
# app.config.from_object(CONFIG)
# app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# db.init_app(app)

# # -------------------------------------------------
# # LOGIN
# # -------------------------------------------------
# login_manager = LoginManager()
# login_manager.init_app(app)
# login_manager.login_view = "login"

# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))

# # -------------------------------------------------
# # FILE CONFIG
# # -------------------------------------------------
# UPLOAD_FOLDER = "uploads"
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# # -------------------------------------------------
# # DB INIT
# # -------------------------------------------------
# with app.app_context():
#     db.create_all()

# # -------------------------------------------------
# # ROUTES
# # -------------------------------------------------
# @app.route("/")
# def index():
#     if not current_user.is_authenticated:
#         return redirect(url_for("login"))
#     return render_template("upload.html", user=current_user)


# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         username = request.form.get("username", "").strip()
#         password = request.form.get("password", "").strip()

#         user = User.query.filter_by(username=username).first()

#         if not user or not user.check_password(password):
#             flash("Invalid credentials", "error")
#             return render_template("login.html")

#         login_user(user)
#         return redirect(url_for("index"))

#     return render_template("login.html")


# @app.route("/register", methods=["GET", "POST"])
# def register():
#     if request.method == "POST":
#         username = request.form.get("username", "").strip()
#         email = request.form.get("email", "").strip()
#         password = request.form.get("password", "").strip()

#         if User.query.filter_by(username=username).first():
#             flash("Username exists", "error")
#             return render_template("register.html")

#         user = User(username=username, email=email)
#         user.set_password(password)

#         db.session.add(user)
#         db.session.commit()

#         return redirect(url_for("login"))

#     return render_template("register.html")


# @app.route("/logout")
# @login_required
# def logout():
#     logout_user()
#     return redirect(url_for("login"))


# # -------------------------------------------------
# # UPLOAD
# # -------------------------------------------------
# @app.route("/upload", methods=["POST"])
# @login_required
# def upload():
#     try:
#         file = request.files.get("pdf_file")

#         if not file or file.filename == "":
#             flash("No file selected", "error")
#             return redirect(url_for("index"))

#         filename = secure_filename(file.filename)
#         path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
#         file.save(path)

#         # Extract + Process
#         text = extract_text_from_pdf(path)
#         summary = summarize_text(text)
#         quiz = generate_quiz(summary)

#         # Save document
#         doc = Document(
#             title=filename,
#             filename=filename,
#             uploader_id=current_user.id,
#             extracted_text=text,
#             summary=summary
#         )
#         db.session.add(doc)
#         db.session.commit()

#         # Store session safely
#         session["quiz"] = quiz if quiz else []
#         session["document_id"] = doc.id
#         session["student_user_id"] = current_user.id

#         return render_template(
#             "quiz.html",
#             questions=session["quiz"],   # ✅ always safe
#             summary=summary or "",
#             document_title=filename or ""
#         )

#     except Exception as e:
#         print(traceback.format_exc())
#         flash("Upload failed", "error")
#         return redirect(url_for("index"))


# # -------------------------------------------------
# # SUBMIT QUIZ
# # -------------------------------------------------
# @app.route("/submit", methods=["POST"])
# @login_required
# def submit():
#     quiz_questions = session.get("quiz", [])
#     student_user_id = session.get("student_user_id")
#     document_id = session.get("document_id")

#     if not quiz_questions or not student_user_id:
#         return redirect(url_for("index"))

#     total = len(quiz_questions)
#     correct = 0
#     results = []

#     doc = Document.query.get(document_id) if document_id else None
#     questions_from_db = Question.query.filter(
#         Question.concept_id.in_([c.id for c in (doc.concepts if doc else [])])
#     ).all() if doc else []

#     for i, question in enumerate(quiz_questions):
#         user_answer = request.form.get(f"answer_{i}", "").strip()
#         correct_answer = question.get("correct_answer", "").strip()

#         is_correct = user_answer.upper() == correct_answer.upper()
#         if is_correct:
#             correct += 1

#         question_obj = questions_from_db[i] if i < len(questions_from_db) else None

#         if question_obj:
#             last_attempt = Attempt.query.filter_by(
#                 user_id=student_user_id,
#                 question_id=question_obj.id
#             ).order_by(Attempt.attempted_at.desc()).first()

#             days_since_last = None
#             if last_attempt:
#                 time_diff = datetime.utcnow() - last_attempt.attempted_at
#                 days_since_last = time_diff.total_seconds() / (24 * 3600)

#             previous_attempts = Attempt.query.filter_by(
#                 user_id=student_user_id,
#                 question_id=question_obj.id
#             ).count()

#             attempt = Attempt(
#                 user_id=student_user_id,
#                 question_id=question_obj.id,
#                 user_answer=user_answer,
#                 is_correct=is_correct,
#                 response_time_seconds=0,
#                 attempt_number=previous_attempts + 1,
#                 days_since_last_attempt=days_since_last
#             )
#             db.session.add(attempt)

#             if question_obj.concept_id:
#                 update_concept_mastery(student_user_id, question_obj.concept_id, is_correct)

#         results.append({
#             "question": question["question"],
#             "options": question["options"],
#             "user_answer": user_answer,
#             "correct_answer": correct_answer,
#             "is_correct": is_correct
#         })

#     db.session.commit()

#     score_percent = round((correct / total) * 100, 2) if total > 0 else 0
#     print(f"[INFO] Quiz attempt saved: {correct}/{total} ({score_percent}%)")

#     # ✅ PREDICTION BLOCK (FIXED)
#     revision_info = None
#     try:
#         print("🔥 ENTERING PREDICTOR")

#         all_attempts = Attempt.query.filter_by(user_id=student_user_id).all()

#         if all_attempts:
#             student_historical_avg = round(
#                 sum(100 if a.is_correct else 0 for a in all_attempts) / len(all_attempts), 2
#             )
#         else:
#             student_historical_avg = score_percent

#         scores_this_concept = [score_percent]

#         days_since = 0

#         revision_info = predict_revision(
#             student_historical_avg=student_historical_avg,
#             diff_numeric=2,
#             all_scores_this_concept=scores_this_concept,
#             days_since_last_attempt=days_since
#         )

#         print("✅ PREDICTION RESULT:", revision_info)

#     except Exception as e:
#         print("❌ PREDICTOR ERROR:", e)

#     return render_template(
#         "result.html",
#         results=results,
#         total=total,
#         correct=correct,
#         score_percent=score_percent,
#         revision_info=revision_info
#     )


# # -------------------------------------------------
# # RUN
# # -------------------------------------------------
# if __name__ == "__main__":
#     app.run(debug=True)
"""
app.py - FINAL CORRECTED VERSION (Dropdown + ML + DB Storage)
"""

from annotated_types import doc
from dotenv import load_dotenv
load_dotenv()

import os
import traceback
from datetime import datetime

from flask import Flask, request, render_template, redirect, url_for, session, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from config import CONFIG
from models import db, User, Document, Concept, Question, Attempt, ConceptMastery, update_concept_mastery, schedule_next_revision
from pdf_utils import extract_text_from_pdf
from summarizer import summarize_text
from quiz_generator import generate_quiz
from predictor import predict_revision
from sqlalchemy.exc import IntegrityError

# -------------------------------------------------
# APP CONFIG
# -------------------------------------------------
app = Flask(__name__)
app.config.from_object(CONFIG)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

db.init_app(app)

# -------------------------------------------------
# LOGIN
# -------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------------------------------
# FILE CONFIG
# -------------------------------------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -------------------------------------------------
# DB INIT
# -------------------------------------------------
with app.app_context():
    db.create_all()

# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("upload.html", user=current_user)


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("Invalid credentials", "error")
            return render_template("login.html")

        login_user(user)
        return redirect(url_for("index"))

    return render_template("login.html")


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "error")
            return render_template("register.html")

        user = User(username=username, email=email)
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
            flash("Registration successful!", "success")
            return redirect(url_for("login"))
        except:
            db.session.rollback()
            flash("Error occurred", "error")

    return render_template("register.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["POST"])
@login_required
def upload():
    try:
        file = request.files.get("pdf_file")

        if not file or file.filename == "":
            flash("No file selected", "error")
            return redirect(url_for("index"))

        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)

        text = extract_text_from_pdf(path)
        summary = summarize_text(text)
        quiz = generate_quiz(summary)

        doc = Document(
            title=filename,
            filename=filename,
            uploader_id=current_user.id,
            extracted_text=text,
            summary=summary
        )
        db.session.add(doc)
        db.session.commit()

        # Create a concept for the document
        concept = Concept(
            document_id=doc.id,
            title=filename,
            content=summary
        )
        db.session.add(concept)
        db.session.commit()

        session["quiz"] = quiz
        session["document_id"] = doc.id
        session["student_user_id"] = current_user.id

        return render_template("quiz.html", questions=quiz, summary=summary)

    except Exception:
        print(traceback.format_exc())
        flash("Upload failed", "error")
        return redirect(url_for("index"))

@app.route("/my-documents")
@login_required
def my_documents():
    documents = Document.query.filter_by(
        uploader_id=current_user.id
    ).order_by(Document.created_at.desc()).all()

    document_stats = []

    for doc in documents:
        concepts = Concept.query.filter_by(document_id=doc.id).count()

        questions = Question.query.join(Concept).filter(
            Concept.document_id == doc.id
        ).count()

        attempts = Attempt.query.join(Question).join(Concept).filter(
            Concept.document_id == doc.id,
            Attempt.user_id == current_user.id
        ).count()

        document_stats.append({
            "doc": doc,
            "concepts": concepts,
            "questions": questions,
            "attempts": attempts
        })

    return render_template("my_documents.html", document_stats=document_stats)
# ---------------- SUBMIT QUIZ ----------------
@app.route("/submit", methods=["POST"])
@login_required
def submit():
    quiz_questions = session.get("quiz", [])
    student_user_id = session.get("student_user_id")

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
            "correct_answer": correct_answer,
            "user_answer": user_answer,
            "is_correct": is_correct
        })

    score_percent = round((correct / total) * 100, 2)

    # ✅ SAVE FOR RESULT PAGE
    session["total"] = total
    session["correct"] = correct
    session["results"] = results
    session["score_percent"] = score_percent

    print(f"[INFO] Score saved: {score_percent}")

    # 👉 NOW GO TO DROPDOWN PAGE
    return render_template("select_difficulty.html")


# ---------------- PREDICT (AFTER DROPDOWN) ----------------
@app.route("/predict", methods=["POST"])
@login_required
def predict():
    from models import StudentFeature

    student_user_id = current_user.id
    difficulty = request.form.get("difficulty")

    diff_map = {"easy": 1, "medium": 2, "hard": 3}
    diff_numeric = diff_map.get(difficulty.lower(), 2)

    score_percent = session.get("score_percent", 0)

    all_attempts = Attempt.query.filter_by(user_id=student_user_id).all()

    if all_attempts:
        avg = sum(100 if a.is_correct else 0 for a in all_attempts) / len(all_attempts)
    else:
        avg = score_percent

    # category
    if avg >= 75:
        category = "Topper"
    elif avg >= 50:
        category = "Average"
    else:
        category = "Weak"

    # ML prediction
    revision_info = predict_revision(
        student_historical_avg=avg,
        diff_numeric=diff_numeric,
        all_scores_this_concept=[score_percent],
        days_since_last_attempt=0
    )
    document_id = session.get("document_id")

    doc = Document.query.get(document_id)

    if doc and doc.concepts:
        for concept in doc.concepts:

            feature = StudentFeature(
            user_id=student_user_id,
            concept_id=concept.id,   # ✅ FIXED

            student_category=category,
            student_historical_avg=avg,

            concept_difficulty=difficulty,
            diff_numeric=diff_numeric,

            latest_quiz_score=score_percent,
            avg_quiz_score=score_percent,

            num_attempts=len(all_attempts),
            days_since_last_attempt=0,

            retention_score=100 - score_percent,
            days_until_revision=revision_info["revise_in_days"]
        )

        db.session.add(feature)
        db.session.commit()

        # Schedule next revision
        from models import schedule_next_revision
        schedule_next_revision(
            user_id=student_user_id,
            concept_id=concept.id,
            interval_days=int(revision_info["revise_in_days"]),
            forgetting_prob=0.5,  # placeholder
            reason=revision_info["urgency"]
        )
    return render_template(
        "result.html",
        total=session.get("total", 0),
        correct=session.get("correct", 0),
        results=session.get("results", []),
        score_percent=score_percent,
        revision_info=revision_info
    )


# ---------------- MY REVISIONS ----------------
@app.route("/my-revisions")
@login_required
def my_revisions():
    from models import RevisionSchedule

    schedules = RevisionSchedule.query.filter_by(
        user_id=current_user.id,
        was_revised=False
    ).order_by(RevisionSchedule.next_revision_date.asc()).all()

    revision_list = []

    for s in schedules:
        concept = Concept.query.get(s.concept_id)
        doc = Document.query.get(concept.document_id) if concept else None

        # days left calculation (safe)
        days_left = (s.next_revision_date - datetime.utcnow()).days

        revision_list.append({
            "concept_name": concept.title if concept else "Unknown",
            "document_title": doc.title if doc else "Unknown",
            "revision_date": s.next_revision_date.strftime("%b %d, %Y"),
            "days_left": max(0, days_left),
            "urgency": s.schedule_reason,
            "forgetting_prob": round(s.forgetting_probability * 100, 2)
        })

    return render_template("my_revisions.html", revision_list=revision_list)


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)