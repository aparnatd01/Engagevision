"""
EngageVision Monitoring
Teacher video upload + AI engagement processing + DB persistence
"""

import os
import json
from datetime import date

from flask import (
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
    current_app,
    send_from_directory,
    abort,
)

from werkzeug.utils import secure_filename

from app.decorators import teacher_required, login_required
from app.models import (
    get_assignments_by_teacher,
    get_assignment_by_id,
    get_session_by_id,
    create_session as db_create_session,
    update_session_status,
    complete_session,
    create_report,
    upsert_report_metadata,
)
from app.monitoring.video_processor import process_video

from . import monitoring_bp


ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "avi",
    "mov",
    "mkv",
    "webm",
}


def allowed_video(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_VIDEO_EXTENSIONS
    )


# ============================================================
# MONITORING PAGE
# ============================================================

@monitoring_bp.route("/")
@teacher_required
def index():
    """Monitoring page for teacher."""

    uid = session["user_id"]

    assignments = get_assignments_by_teacher(uid)

    return render_template(
        "teacher/monitoring.html",
        assignments=assignments,
    )


# ============================================================
# VIDEO UPLOAD + AI PROCESSING
# ============================================================

@monitoring_bp.route("/upload", methods=["POST"])
@teacher_required
def upload_video():
    """Upload classroom video and process it using EngageVision AI."""

    if "video" not in request.files:
        flash(
            "Please select a classroom video.",
            "danger",
        )

        return redirect(
            url_for("monitoring.index")
        )

    video = request.files["video"]

    if not video or video.filename == "":
        flash(
            "Please select a classroom video.",
            "danger",
        )

        return redirect(
            url_for("monitoring.index")
        )

    if not allowed_video(video.filename):
        flash(
            "Invalid video format. Allowed formats: MP4, AVI, MOV, MKV, WEBM.",
            "danger",
        )

        return redirect(
            url_for("monitoring.index")
        )

    # --------------------------------------------------------
    # Resolve assignment (class + section) from form
    # --------------------------------------------------------

    teacher_uid    = session["user_id"]
    assignment_id  = request.form.get("assignment_id", type=int)
    session_name   = request.form.get("session_name", "").strip() or "Unnamed Session"

    assignment = None
    class_id   = None
    section_id = None

    if assignment_id:
        assignment = get_assignment_by_id(assignment_id)
        if assignment and assignment["teacher_id"] == teacher_uid:
            class_id   = assignment["class_id"]
            section_id = assignment["section_id"]
        else:
            assignment = None  # Tampered / wrong teacher

    # Fall back: pick first assignment for this teacher
    if assignment is None:
        all_assignments = get_assignments_by_teacher(teacher_uid)
        if all_assignments:
            assignment = all_assignments[0]
            class_id   = assignment["class_id"]
            section_id = assignment["section_id"]

    # --------------------------------------------------------
    # Upload directory
    # --------------------------------------------------------

    upload_folder = os.path.abspath(
        os.path.join(
            current_app.root_path,
            "..",
            "uploads",
        )
    )

    os.makedirs(
        upload_folder,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Save uploaded video
    # --------------------------------------------------------

    original_name = secure_filename(
        video.filename
    )

    input_path = os.path.join(
        upload_folder,
        original_name,
    )

    video.save(input_path)

    # --------------------------------------------------------
    # Output file
    # --------------------------------------------------------

    base_name = os.path.splitext(
        original_name
    )[0]

    output_path = os.path.join(
        upload_folder,
        f"{base_name}_engagement.mp4",
    )

    # --------------------------------------------------------
    # Create monitoring_session record (status=pending)
    # --------------------------------------------------------

    db_session_id = None
    try:
        db_session_id = db_create_session(
            teacher_id     = teacher_uid,
            class_id       = class_id,
            section_id     = section_id,
            session_name   = session_name,
            session_date   = date.today().isoformat(),
            video_filename = original_name,
            video_path     = input_path,
        )
        update_session_status(db_session_id, "processing")
    except Exception as exc:
        current_app.logger.warning(
            "Could not create monitoring_session DB record: %s", exc
        )

    # --------------------------------------------------------
    # AI PROCESSING
    # --------------------------------------------------------

    # Directory where real per-student face crops will be saved.
    # Keyed by session ID so different sessions never collide.
    # Falls back gracefully if db_session_id is not yet known.
    _sid_key = db_session_id or "tmp"
    _crops_dir = os.path.abspath(
        os.path.join(current_app.root_path, "..", "uploads", "crops", f"session_{_sid_key}")
    )

    try:

        result = process_video(
            input_path,
            output_path,
            crops_dir=_crops_dir,
        )

    except Exception as e:

        current_app.logger.exception(
            "EngageVision video processing failed"
        )

        if db_session_id:
            try:
                update_session_status(db_session_id, "failed")
            except Exception:
                pass

        flash(
            f"Video processing failed: {str(e)}",
            "danger",
        )

        return redirect(
            url_for("monitoring.index")
        )

    # --------------------------------------------------------
    # Persist results to DB
    # --------------------------------------------------------

    if db_session_id:
        try:
            _save_monitoring_results(db_session_id, teacher_uid, session_name, result)
        except Exception as exc:
            current_app.logger.warning(
                "DB persistence after monitoring failed: %s", exc
            )

    # Attach DB session id to result so result page can link to reports
    result["db_session_id"] = db_session_id

    # --------------------------------------------------------
    # Store result in Flask session for the result page
    # --------------------------------------------------------

    session["monitoring_result"] = result

    # --------------------------------------------------------
    # Go to result page
    # --------------------------------------------------------

    return redirect(
        url_for("monitoring.result")
    )


def _save_monitoring_results(db_session_id, teacher_uid, session_name, result):
    """
    Persist AI results to DB after a successful monitoring run.
    Saves:
      - engagement_reports (aggregate stats + face_data JSON)
      - engagement_scores  (one row per detected student)
      - reports            (metadata row for PDF/report page)
      - completes the monitoring_session record
    """
    students   = result.get("students", [])
    n_students = len(students)

    if n_students == 0:
        complete_session(db_session_id, 0)
        return

    # --- Aggregate stats -------------------------------------------------------
    scores     = [s["engagement_pct"] for s in students]
    avg_score  = sum(scores) / len(scores) if scores else 0.0

    high_list   = [s for s in students if s["level"] == "High"]
    medium_list = [s for s in students if s["level"] == "Medium"]
    low_list    = [s for s in students if s["level"] == "Low"]

    high_count   = len(high_list)
    medium_count = len(medium_list)
    low_count    = len(low_list)
    active_count = len([s for s in students if s.get("engagement_pct", 0) >= 40])
    inactive_count = n_students - active_count

    overall_pct = round(avg_score, 2)
    high_pct    = round(100 * high_count   / n_students, 2)
    medium_pct  = round(100 * medium_count / n_students, 2)
    low_pct     = round(100 * low_count    / n_students, 2)

    # --- Collect real face crop paths from process_video() result ----------
    # process_video() saves one JPEG per confirmed student into crops_dir.
    # The files are already named student_N.jpg and the absolute path is in
    # each student's "crop_path" key.  Convert to relative URL paths here.
    crop_paths = {}   # face_index -> relative URL string
    base_uploads = os.path.abspath(
        os.path.join(current_app.root_path, "..", "uploads")
    )
    for s in students:
        face_idx  = s.get("student_id", 0)
        abs_crop  = s.get("crop_path")
        if abs_crop and os.path.exists(abs_crop):
            # Store relative to uploads/ folder for DB + serving
            try:
                rel = os.path.relpath(abs_crop, base_uploads).replace("\\", "/")
                crop_paths[face_idx] = rel
                s["crop_path"] = rel
            except Exception:
                pass

    # --- Build face_data for JSON storage (with crop_path) -------------------
    face_data = []
    for s in students:
        face_idx = s.get("student_id")
        face_data.append({
            "face_id":          face_idx,
            "engagement_score": s.get("engagement_pct", 0),
            "status":           s.get("level", "Low"),
            "is_active":        s.get("engagement_pct", 0) >= 40,
            "predictions":      s.get("predictions", 0),
            "features":         s.get("feature_scores", {}),
            "crop_path":        crop_paths.get(face_idx, ""),
        })

    face_data_json = json.dumps(face_data)

    # --- Insert engagement_reports -------------------------------------------
    create_report(
        session_id         = db_session_id,
        total_faces        = n_students,
        active_count       = active_count,
        inactive_count     = inactive_count,
        high_count         = high_count,
        medium_count       = medium_count,
        low_count          = low_count,
        overall_percentage = overall_pct,
        high_percentage    = high_pct,
        medium_percentage  = medium_pct,
        low_percentage     = low_pct,
        face_data_json     = face_data_json,
    )

    # --- Insert engagement_scores (one row per student) ----------------------
    from app.database import execute_db
    for s in students:
        face_idx  = s.get("student_id", 0)
        score     = s.get("engagement_pct", 0)
        level     = s.get("level", "Low")
        features  = s.get("feature_scores", {})
        crop_path = crop_paths.get(face_idx)

        try:
            execute_db(
                """INSERT INTO engagement_scores
                   (session_id, face_index, score, level, is_active,
                    ear_score, head_pose_score, mouth_score, crop_path)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    db_session_id,
                    face_idx,
                    round(score, 2),
                    level,
                    1 if score >= 40 else 0,
                    # Keys match what video_processor.py stores in feature_scores:
                    # "gaze" (eye/iris-based), "head" (head direction), "expression" (mouth/eyes)
                    round(features.get("gaze", 0), 3)       if features.get("gaze")       else None,
                    round(features.get("head", 0), 3)       if features.get("head")       else None,
                    round(features.get("expression", 0), 3) if features.get("expression") else None,
                    crop_path,
                )
            )
        except Exception as exc:
            current_app.logger.warning(
                "Failed to save engagement_score for student %s: %s",
                face_idx, exc
            )

    # --- Upsert reports metadata ---------------------------------------------
    upsert_report_metadata(
        session_id    = db_session_id,
        teacher_id    = teacher_uid,
        report_title  = session_name,
    )

    # --- Mark session completed ----------------------------------------------
    frames   = result.get("frames_processed", 0)
    fps      = result.get("fps", 25) or 25
    duration = int(frames / fps)
    complete_session(db_session_id, duration)




# ============================================================
# RESULT PAGE
# ============================================================

@monitoring_bp.route("/result")
@teacher_required
def result():
    """Display AI engagement results."""

    result_data = session.get(
        "monitoring_result"
    )

    if not result_data:

        flash(
            "No monitoring result available.",
            "warning",
        )

        return redirect(
            url_for("monitoring.index")
        )

    return render_template(
        "teacher/monitoring_result.html",
        result=result_data,
    )


# ============================================================
# SERVE PROCESSED VIDEO
# ============================================================

@monitoring_bp.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    """Serve uploaded/processed monitoring videos."""
    upload_folder = os.path.abspath(
        os.path.join(
            current_app.root_path,
            "..",
            "uploads",
        )
    )

    return send_from_directory(
        upload_folder,
        filename,
        as_attachment=False,
    )


# ============================================================
# SERVE FACE CROP IMAGES
# ============================================================

@monitoring_bp.route("/crops/<path:filename>")
def serve_crop(filename):
    """Serve per-student face crop images with role-based access control."""
    if "user_id" not in session:
        abort(403)

    role = session.get("role")
    uid = session.get("user_id")

    # If filename starts with "crops/", normalize by removing the prefix
    if filename.startswith("crops/"):
        filename = filename[len("crops/"):]

    # Admin is allowed to access any valid student crop image
    if role == "admin":
        pass
    elif role == "teacher":
        # Check that this crop belongs to a session assigned to / owned by this teacher
        # Filename pattern is session_{session_id}/student_{face_id}.jpg
        import re
        match = re.search(r"session_(\d+)", filename)
        if match:
            sess_id = int(match.group(1))
            db_session = get_session_by_id(sess_id)
            if not db_session or db_session.get("teacher_id") != uid:
                abort(403)
        else:
            abort(403)
    else:
        abort(403)

    upload_folder = os.path.abspath(
        os.path.join(current_app.root_path, "..", "uploads", "crops")
    )
    return send_from_directory(upload_folder, filename, as_attachment=False)