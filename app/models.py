"""
models.py — Complete database query layer for EngageVision v2.0
All queries use %s parameterized placeholders (PyMySQL safe).

Tables:
  users, classes, sections, teacher_assignments, students,
  class_students, monitoring_sessions, engagement_reports,
  engagement_scores, reports
"""

from app.database import query_db, execute_db, get_db


# ═══════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════

def get_user_by_id(user_id):
    return query_db("SELECT * FROM users WHERE id = %s", (user_id,), one=True)


def get_user_by_username(username):
    return query_db("SELECT * FROM users WHERE username = %s", (username,), one=True)


def get_user_by_email(email):
    return query_db("SELECT * FROM users WHERE email = %s", (email,), one=True)


def get_users_by_role(role):
    return query_db(
        "SELECT * FROM users WHERE role = %s ORDER BY created_at DESC", (role,)
    )


def get_all_teachers():
    return query_db(
        """SELECT * FROM users WHERE role = 'teacher' ORDER BY first_name, last_name"""
    )


def get_active_teachers():
    return query_db(
        """SELECT * FROM users WHERE role = 'teacher' AND is_active = 1
           ORDER BY first_name, last_name"""
    )


def create_user(username, email, password_hash, role, first_name, last_name,
                staff_id=None, department=None, phone=None, is_active=1):
    """Create a user with all credentials supplied (admin, existing teachers)."""
    return execute_db(
        """INSERT INTO users
           (username, email, password_hash, role, first_name, last_name,
            staff_id, department, phone, is_active)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (username, email, password_hash, role, first_name, last_name,
         staff_id, department, phone, is_active)
    )


# ── Teacher Account Setup (Staff-ID-based workflow) ───────────────────────────

def create_teacher_pending_simple(first_name, last_name, email, staff_id,
                                  department, phone):
    """
    Create a teacher record with no username/password.
    is_active=0 until the teacher sets their own credentials via Staff ID setup.
    No activation token, email, or link is generated.
    """
    return execute_db(
        """INSERT INTO users
           (first_name, last_name, email, staff_id, department, phone,
            role, is_active, username, password_hash)
           VALUES (%s, %s, %s, %s, %s, %s, 'teacher', 0, NULL, NULL)""",
        (first_name, last_name, email, staff_id, department, phone)
    )


def get_teacher_by_staff_id(staff_id):
    """Find a teacher by staff_id for the account setup flow."""
    if not staff_id:
        return None
    return query_db(
        "SELECT * FROM users WHERE role = 'teacher' AND staff_id = %s LIMIT 1",
        (staff_id,), one=True
    )


def activate_teacher_account(user_id, username, password_hash):
    """
    Complete teacher account setup: set credentials and activate account.
    Called after the teacher chooses their own username + password via Staff ID setup.
    """
    execute_db(
        """UPDATE users
           SET username = %s,
               password_hash = %s,
               is_active = 1
           WHERE id = %s AND role = 'teacher' AND username IS NULL""",
        (username, password_hash, user_id)
    )



def get_active_teacher_by_email(email):
    """
    Find an activated, active teacher by email — used for Forgot Password.
    Only teachers who have completed activation (username IS NOT NULL) and
    are currently active (is_active=1) can request a password reset.
    """
    return query_db(
        """SELECT * FROM users
           WHERE role = 'teacher'
             AND is_active = 1
             AND username IS NOT NULL
             AND email = %s
           LIMIT 1""",
        (email,), one=True
    )


def update_user(user_id, first_name, last_name, email, staff_id, department, phone):
    execute_db(
        """UPDATE users SET first_name=%s, last_name=%s, email=%s,
           staff_id=%s, department=%s, phone=%s WHERE id=%s""",
        (first_name, last_name, email, staff_id, department, phone, user_id)
    )


def update_user_status(user_id, is_active):
    execute_db("UPDATE users SET is_active = %s WHERE id = %s", (is_active, user_id))


def update_user_password(user_id, new_hash):
    execute_db("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user_id))


def update_user_last_login(user_id):
    execute_db("UPDATE users SET last_signed_in = NOW() WHERE id = %s", (user_id,))


def delete_user(user_id):
    """
    Permanently delete a teacher and clean up ALL related records safely.

    Cleanup order:
      1. teacher_assignments  — explicit delete (also handled by CASCADE)
      2. password_reset_tokens — may exist without CASCADE; skip if table absent
      3. users record          — CASCADE handles monitoring_sessions, reports, etc.

    Returns:
        tuple: (success: bool, message: str)
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # 1. Remove all class/section assignments for this teacher
            cur.execute(
                "DELETE FROM teacher_assignments WHERE teacher_id = %s",
                (user_id,)
            )

            # 2. Remove password reset tokens (table may not exist in all deployments)
            try:
                cur.execute(
                    "DELETE FROM password_reset_tokens WHERE user_id = %s",
                    (user_id,)
                )
            except Exception:
                pass  # Table does not exist — safe to skip

            # 3. Delete the user record itself
            #    FK CASCADE handles monitoring_sessions, reports,
            #    engagement_reports, engagement_scores
            cur.execute(
                "DELETE FROM users WHERE id = %s",
                (user_id,)
            )

        conn.commit()
        return True, "Teacher deleted successfully."

    except Exception as exc:
        conn.rollback()
        return False, f"Database error while deleting teacher: {str(exc)}"


def count_users_by_role(role):
    row = query_db("SELECT COUNT(*) AS cnt FROM users WHERE role = %s", (role,), one=True)
    return row['cnt'] if row else 0


def username_exists(username, exclude_id=None):
    if exclude_id:
        row = query_db(
            "SELECT id FROM users WHERE username=%s AND id != %s", (username, exclude_id), one=True
        )
    else:
        row = query_db("SELECT id FROM users WHERE username=%s", (username,), one=True)
    return row is not None


def email_exists(email, exclude_id=None):
    if exclude_id:
        row = query_db(
            "SELECT id FROM users WHERE email=%s AND id != %s", (email, exclude_id), one=True
        )
    else:
        row = query_db("SELECT id FROM users WHERE email=%s", (email,), one=True)
    return row is not None


def staff_id_exists(staff_id, exclude_id=None):
    if not staff_id:
        return False
    if exclude_id:
        row = query_db(
            "SELECT id FROM users WHERE staff_id=%s AND id != %s", (staff_id, exclude_id), one=True
        )
    else:
        row = query_db("SELECT id FROM users WHERE staff_id=%s", (staff_id,), one=True)
    return row is not None


# ═══════════════════════════════════════════════════════════════
# CLASSES
# ═══════════════════════════════════════════════════════════════

def get_all_classes():
    return query_db(
        """SELECT c.*,
               COUNT(DISTINCT s.id) AS section_count
           FROM classes c
           LEFT JOIN sections s ON s.class_id = c.id
           GROUP BY c.id
           ORDER BY c.class_name"""
    )


def get_active_classes():
    return query_db(
        """SELECT c.*,
               COUNT(DISTINCT s.id) AS section_count
           FROM classes c
           LEFT JOIN sections s ON s.class_id = c.id
           WHERE c.is_active = 1
           GROUP BY c.id
           ORDER BY c.class_name"""
    )


def get_class_by_id(class_id):
    return query_db("SELECT * FROM classes WHERE id = %s", (class_id,), one=True)


def create_class(class_name, course_code=None, semester=None,
                 academic_year=None, description=None):
    return execute_db(
        """INSERT INTO classes (class_name, course_code, semester, academic_year, description)
           VALUES (%s, %s, %s, %s, %s)""",
        (class_name, course_code, semester, academic_year, description)
    )


def update_class(class_id, class_name, course_code, semester, academic_year, description):
    execute_db(
        """UPDATE classes SET class_name=%s, course_code=%s, semester=%s,
           academic_year=%s, description=%s WHERE id=%s""",
        (class_name, course_code, semester, academic_year, description, class_id)
    )


def toggle_class_status(class_id, is_active):
    execute_db("UPDATE classes SET is_active=%s WHERE id=%s", (is_active, class_id))


def delete_class(class_id):
    """Safely delete a class and its dependent records."""
    # Get section IDs for this class
    sections = query_db("SELECT id FROM sections WHERE class_id = %s", (class_id,))
    for sec in (sections or []):
        execute_db("DELETE FROM teacher_assignments WHERE section_id = %s", (sec['id'],))
    execute_db("UPDATE monitoring_sessions SET class_id = NULL, section_id = NULL WHERE class_id = %s", (class_id,))
    execute_db("DELETE FROM sections WHERE class_id = %s", (class_id,))
    execute_db("DELETE FROM teacher_assignments WHERE class_id = %s", (class_id,))
    execute_db("DELETE FROM classes WHERE id = %s", (class_id,))


def count_classes():
    row = query_db("SELECT COUNT(*) AS cnt FROM classes", one=True)
    return row['cnt'] if row else 0


# ═══════════════════════════════════════════════════════════════
# SECTIONS
# ═══════════════════════════════════════════════════════════════

def get_all_sections():
    return query_db(
        """SELECT s.*, c.class_name
           FROM sections s
           JOIN classes c ON c.id = s.class_id
           ORDER BY c.class_name, s.section_name"""
    )


def get_sections_by_class(class_id):
    return query_db(
        """SELECT * FROM sections WHERE class_id = %s AND is_active = 1
           ORDER BY section_name""",
        (class_id,)
    )


def get_section_by_id(section_id):
    return query_db(
        """SELECT s.*, c.class_name FROM sections s
           JOIN classes c ON c.id = s.class_id
           WHERE s.id = %s""",
        (section_id,), one=True
    )


def create_section(class_id, section_name, student_count=0, room_number=None):
    return execute_db(
        """INSERT INTO sections (class_id, section_name, student_count, room_number)
           VALUES (%s, %s, %s, %s)""",
        (class_id, section_name, student_count, room_number)
    )


def update_section(section_id, section_name, student_count, room_number):
    execute_db(
        """UPDATE sections SET section_name=%s, student_count=%s, room_number=%s
           WHERE id=%s""",
        (section_name, student_count, room_number, section_id)
    )


def count_sections():
    row = query_db("SELECT COUNT(*) AS cnt FROM sections", one=True)
    return row['cnt'] if row else 0


def get_total_students():
    """Sum of student_count across all active sections."""
    row = query_db(
        "SELECT COALESCE(SUM(student_count), 0) AS total FROM sections WHERE is_active=1",
        one=True
    )
    return int(row['total']) if row else 0


# ═══════════════════════════════════════════════════════════════
# TEACHER ASSIGNMENTS
# ═══════════════════════════════════════════════════════════════

def get_all_assignments():
    return query_db(
        """SELECT ta.*,
               u.first_name, u.last_name, u.staff_id, u.department,
               c.class_name, c.course_code,
               s.section_name, s.student_count
           FROM teacher_assignments ta
           JOIN users u    ON u.id = ta.teacher_id
           JOIN classes c  ON c.id = ta.class_id
           JOIN sections s ON s.id = ta.section_id
           ORDER BY c.class_name, s.section_name, u.first_name"""
    )


def get_assignments_by_teacher(teacher_id):
    return query_db(
        """SELECT ta.*,
               c.class_name, c.course_code, c.semester,
               s.section_name, s.student_count, s.room_number
           FROM teacher_assignments ta
           JOIN classes c  ON c.id = ta.class_id
           JOIN sections s ON s.id = ta.section_id
           WHERE ta.teacher_id = %s
           ORDER BY c.class_name, s.section_name""",
        (teacher_id,)
    )


def get_assignment_by_id(assignment_id):
    """Look up a single teacher assignment by its primary key."""
    return query_db(
        """SELECT ta.*, c.class_name, s.section_name
           FROM teacher_assignments ta
           JOIN classes c  ON c.id = ta.class_id
           JOIN sections s ON s.id = ta.section_id
           WHERE ta.id = %s""",
        (assignment_id,), one=True
    )


def get_classes_for_teacher(teacher_id):
    """Distinct classes assigned to a teacher."""
    return query_db(
        """SELECT DISTINCT c.*
           FROM teacher_assignments ta
           JOIN classes c ON c.id = ta.class_id
           WHERE ta.teacher_id = %s AND c.is_active = 1
           ORDER BY c.class_name""",
        (teacher_id,)
    )


def get_sections_for_teacher_and_class(teacher_id, class_id):
    """Sections a teacher is assigned to within a specific class."""
    return query_db(
        """SELECT s.*
           FROM teacher_assignments ta
           JOIN sections s ON s.id = ta.section_id
           WHERE ta.teacher_id = %s AND ta.class_id = %s AND s.is_active = 1
           ORDER BY s.section_name""",
        (teacher_id, class_id)
    )


def create_assignment(teacher_id, class_id, section_id):
    return execute_db(
        """INSERT IGNORE INTO teacher_assignments (teacher_id, class_id, section_id)
           VALUES (%s, %s, %s)""",
        (teacher_id, class_id, section_id)
    )


def delete_assignment(assignment_id):
    execute_db("DELETE FROM teacher_assignments WHERE id = %s", (assignment_id,))


def assignment_exists(teacher_id, class_id, section_id):
    row = query_db(
        """SELECT id FROM teacher_assignments
           WHERE teacher_id=%s AND class_id=%s AND section_id=%s""",
        (teacher_id, class_id, section_id), one=True
    )
    return row is not None


def verify_teacher_assignment(teacher_id, class_id, section_id):
    """Backend authorization: verify teacher is assigned to this class+section."""
    return assignment_exists(teacher_id, class_id, section_id)


# ═══════════════════════════════════════════════════════════════
# MONITORING SESSIONS
# ═══════════════════════════════════════════════════════════════

def create_session(teacher_id, class_id, section_id, session_name,
                   session_date, video_filename, video_path):
    return execute_db(
        """INSERT INTO monitoring_sessions
           (teacher_id, class_id, section_id, session_name, session_date,
            video_filename, video_path, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')""",
        (teacher_id, class_id, section_id, session_name,
         session_date, video_filename, video_path)
    )


def update_session_status(session_id, status):
    execute_db(
        "UPDATE monitoring_sessions SET status = %s WHERE id = %s",
        (status, session_id)
    )


def complete_session(session_id, duration_seconds):
    execute_db(
        """UPDATE monitoring_sessions
           SET status='completed', end_time=NOW(), duration_seconds=%s
           WHERE id=%s""",
        (duration_seconds, session_id)
    )


def get_session_by_id(session_id):
    return query_db(
        """SELECT ms.*,
               u.first_name, u.last_name, u.staff_id,
               c.class_name, c.course_code,
               s.section_name
           FROM monitoring_sessions ms
           LEFT JOIN users u    ON u.id = ms.teacher_id
           LEFT JOIN classes c  ON c.id = ms.class_id
           LEFT JOIN sections s ON s.id = ms.section_id
           WHERE ms.id = %s""",
        (session_id,), one=True
    )


def get_sessions_by_teacher(teacher_id, class_id=None, section_id=None, date_filter=None,
                            start_date=None, end_date=None):
    sql = """SELECT ms.*,
                 c.class_name, s.section_name,
                 er.overall_percentage, er.total_faces,
                 er.high_count, er.medium_count, er.low_count,
                 er.active_count, er.inactive_count
             FROM monitoring_sessions ms
             LEFT JOIN classes c  ON c.id = ms.class_id
             LEFT JOIN sections s ON s.id = ms.section_id
             LEFT JOIN engagement_reports er ON er.session_id = ms.id
             WHERE ms.teacher_id = %s"""
    params = [teacher_id]

    if class_id:
        sql += " AND ms.class_id = %s"
        params.append(class_id)
    if section_id:
        sql += " AND ms.section_id = %s"
        params.append(section_id)
    if date_filter:
        sql += " AND ms.session_date = %s"
        params.append(date_filter)
    if start_date:
        sql += " AND ms.session_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND ms.session_date <= %s"
        params.append(end_date)

    sql += " ORDER BY ms.created_at DESC"
    return query_db(sql, params)


def get_all_sessions(class_id=None, section_id=None, teacher_id=None, date_filter=None,
                     start_date=None, end_date=None):
    """Admin: get all sessions with optional filters."""
    sql = """SELECT ms.*,
                 u.first_name, u.last_name,
                 c.class_name, s.section_name,
                 er.overall_percentage, er.total_faces,
                 er.high_count, er.medium_count, er.low_count,
                 er.active_count, er.inactive_count
             FROM monitoring_sessions ms
             LEFT JOIN users u    ON u.id = ms.teacher_id
             LEFT JOIN classes c  ON c.id = ms.class_id
             LEFT JOIN sections s ON s.id = ms.section_id
             LEFT JOIN engagement_reports er ON er.session_id = ms.id
             WHERE 1=1"""
    params = []

    if teacher_id:
        sql += " AND ms.teacher_id = %s"
        params.append(teacher_id)
    if class_id:
        sql += " AND ms.class_id = %s"
        params.append(class_id)
    if section_id:
        sql += " AND ms.section_id = %s"
        params.append(section_id)
    if date_filter:
        sql += " AND ms.session_date = %s"
        params.append(date_filter)
    if start_date:
        sql += " AND ms.session_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND ms.session_date <= %s"
        params.append(end_date)

    sql += " ORDER BY ms.created_at DESC"
    return query_db(sql, params)


def count_sessions_by_teacher(teacher_id):
    row = query_db(
        "SELECT COUNT(*) AS cnt FROM monitoring_sessions WHERE teacher_id=%s AND status='completed'",
        (teacher_id,), one=True
    )
    return row['cnt'] if row else 0


def count_all_sessions():
    row = query_db(
        "SELECT COUNT(*) AS cnt FROM monitoring_sessions WHERE status='completed'",
        one=True
    )
    return row['cnt'] if row else 0


def get_last_session(teacher_id):
    return query_db(
        """SELECT ms.*, er.overall_percentage, c.class_name, s.section_name
           FROM monitoring_sessions ms
           LEFT JOIN engagement_reports er ON er.session_id = ms.id
           LEFT JOIN classes c  ON c.id = ms.class_id
           LEFT JOIN sections s ON s.id = ms.section_id
           WHERE ms.teacher_id = %s AND ms.status = 'completed'
           ORDER BY ms.created_at DESC LIMIT 1""",
        (teacher_id,), one=True
    )


# ═══════════════════════════════════════════════════════════════
# ENGAGEMENT REPORTS
# ═══════════════════════════════════════════════════════════════

def create_report(session_id, total_faces, active_count, inactive_count,
                  high_count, medium_count, low_count,
                  overall_percentage, high_percentage, medium_percentage,
                  low_percentage, face_data_json):
    return execute_db(
        """INSERT INTO engagement_reports
           (session_id, total_faces, active_count, inactive_count,
            high_count, medium_count, low_count,
            overall_percentage, high_percentage, medium_percentage,
            low_percentage, face_data)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (session_id, total_faces, active_count, inactive_count,
         high_count, medium_count, low_count,
         overall_percentage, high_percentage, medium_percentage,
         low_percentage, face_data_json)
    )


def get_report_by_session(session_id):
    return query_db(
        "SELECT * FROM engagement_reports WHERE session_id = %s",
        (session_id,), one=True
    )


def get_engagement_scores_by_session(session_id):
    """Get all per-student engagement scores for a session, ordered by face_index."""
    return query_db(
        """SELECT * FROM engagement_scores
           WHERE session_id = %s
           ORDER BY face_index""",
        (session_id,)
    ) or []


def get_overall_engagement_for_teacher(teacher_id):
    row = query_db(
        """SELECT AVG(er.overall_percentage) AS avg_eng
           FROM engagement_reports er
           JOIN monitoring_sessions ms ON ms.id = er.session_id
           WHERE ms.teacher_id = %s AND ms.status = 'completed'""",
        (teacher_id,), one=True
    )
    val = row['avg_eng'] if row else None
    return round(float(val), 1) if val is not None else 0.0


def get_teacher_dashboard_stats(teacher_id):
    """Aggregate stats for teacher dashboard from real monitoring data."""
    row = query_db(
        """SELECT
               COALESCE(SUM(er.total_faces), 0)    AS total_faces_all,
               COALESCE(SUM(er.active_count), 0)   AS total_active,
               COALESCE(SUM(er.inactive_count), 0) AS total_inactive,
               COALESCE(AVG(er.overall_percentage), 0) AS avg_overall,
               COALESCE(AVG(er.high_percentage), 0)    AS avg_high,
               COALESCE(AVG(er.medium_percentage), 0)  AS avg_medium,
               COALESCE(AVG(er.low_percentage), 0)     AS avg_low,
               COUNT(er.id) AS completed_sessions
           FROM engagement_reports er
           JOIN monitoring_sessions ms ON ms.id = er.session_id
           WHERE ms.teacher_id = %s AND ms.status = 'completed'""",
        (teacher_id,), one=True
    )
    if row:
        return {
            'total_faces':        int(row['total_faces_all']),
            'active_count':       int(row['total_active']),
            'inactive_count':     int(row['total_inactive']),
            'avg_overall':        round(float(row['avg_overall']), 1),
            'avg_high':           round(float(row['avg_high']), 1),
            'avg_medium':         round(float(row['avg_medium']), 1),
            'avg_low':            round(float(row['avg_low']), 1),
            'completed_sessions': int(row['completed_sessions']),
        }
    return {k: 0 for k in ['total_faces', 'active_count', 'inactive_count',
                            'avg_overall', 'avg_high', 'avg_medium', 'avg_low',
                            'completed_sessions']}


def get_admin_engagement_overview():
    """Admin dashboard: engagement stats grouped by class+section."""
    return query_db(
        """SELECT
               c.class_name,
               s.section_name,
               s.student_count,
               COUNT(DISTINCT ms.id)                  AS session_count,
               COALESCE(AVG(er.overall_percentage),0)  AS avg_overall,
               COALESCE(AVG(er.high_percentage),0)     AS avg_high,
               COALESCE(AVG(er.medium_percentage),0)   AS avg_medium,
               COALESCE(AVG(er.low_percentage),0)      AS avg_low,
               COALESCE(SUM(er.active_count),0)        AS total_active,
               COALESCE(SUM(er.inactive_count),0)      AS total_inactive
           FROM classes c
           JOIN sections s ON s.class_id = c.id
           LEFT JOIN monitoring_sessions ms ON ms.class_id=c.id AND ms.section_id=s.id
                                           AND ms.status='completed'
           LEFT JOIN engagement_reports er ON er.session_id = ms.id
           WHERE c.is_active=1 AND s.is_active=1
           GROUP BY c.id, s.id
           ORDER BY c.class_name, s.section_name"""
    )


def get_admin_summary_stats():
    """Top-level counts for admin dashboard."""
    teachers = count_users_by_role('teacher')
    classes  = count_classes()
    sections = count_sections()
    students = get_total_students()
    sessions = count_all_sessions()

    row = query_db(
        """SELECT
               COALESCE(AVG(er.overall_percentage), 0) AS avg_overall,
               COALESCE(AVG(er.high_percentage), 0)    AS avg_high,
               COALESCE(AVG(er.medium_percentage), 0)  AS avg_medium,
               COALESCE(AVG(er.low_percentage), 0)     AS avg_low,
               COALESCE(SUM(er.active_count), 0)       AS total_active,
               COALESCE(SUM(er.inactive_count), 0)     AS total_inactive,
               COALESCE(SUM(er.total_faces), 0)        AS total_faces,
               COUNT(er.id)                             AS completed_sessions
           FROM engagement_reports er
           JOIN monitoring_sessions ms ON ms.id = er.session_id
           WHERE ms.status = 'completed'""",
        one=True
    )

    return {
        'total_teachers':     teachers,
        'total_classes':      classes,
        'total_sections':     sections,
        'total_students':     students,
        'total_sessions':     sessions,
        'avg_overall':        round(float(row['avg_overall']), 1) if row else 0.0,
        'avg_high':           round(float(row['avg_high']), 1) if row else 0.0,
        'avg_medium':         round(float(row['avg_medium']), 1) if row else 0.0,
        'avg_low':            round(float(row['avg_low']), 1) if row else 0.0,
        'total_active':       int(row['total_active']) if row else 0,
        'total_inactive':     int(row['total_inactive']) if row else 0,
        'total_faces':        int(row['total_faces']) if row else 0,
        'completed_sessions': int(row['completed_sessions']) if row else 0,
    }


# ═══════════════════════════════════════════════════════════════
# REPORTS METADATA
# ═══════════════════════════════════════════════════════════════

def upsert_report_metadata(session_id, teacher_id, report_title):
    execute_db(
        """INSERT INTO reports (session_id, teacher_id, report_title)
           VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE report_title = VALUES(report_title),
                                   generated_at = NOW()""",
        (session_id, teacher_id, report_title)
    )


# ═══════════════════════════════════════════════════════════════
# PASSWORD RESET TOKENS  (Teacher Forgot Password)
# ═══════════════════════════════════════════════════════════════

def get_teacher_by_email_or_staff_id(identifier):
    """Look up an active teacher by email OR staff_id."""
    row = query_db(
        """SELECT * FROM users
           WHERE role = 'teacher' AND is_active = 1
             AND (email = %s OR staff_id = %s)
           LIMIT 1""",
        (identifier, identifier), one=True
    )
    return row


def get_teacher_by_email(email):
    """
    Look up a fully activated, active teacher by email — used for Forgot Password.
    Only teachers who have completed activation (username IS NOT NULL) qualify.
    """
    return query_db(
        """SELECT * FROM users
           WHERE role = 'teacher' AND is_active = 1
             AND username IS NOT NULL
             AND email = %s
           LIMIT 1""",
        (email,), one=True
    )


def create_reset_token(user_id, token_hash, expires_at):
    """Store a new reset token (hashed). Invalidate any previous unused tokens first."""
    # Invalidate old unused tokens for same user
    execute_db(
        """UPDATE password_reset_tokens
           SET used_at = NOW()
           WHERE user_id = %s AND used_at IS NULL""",
        (user_id,)
    )
    execute_db(
        """INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
           VALUES (%s, %s, %s)""",
        (user_id, token_hash, expires_at)
    )


def get_valid_reset_token(token_hash):
    """Return the token row if it exists, is unused, and has not expired."""
    return query_db(
        """SELECT prt.*, u.id AS uid, u.email, u.role, u.is_active
           FROM password_reset_tokens prt
           JOIN users u ON u.id = prt.user_id
           WHERE prt.token_hash = %s
             AND prt.used_at IS NULL
             AND prt.expires_at > NOW()
           LIMIT 1""",
        (token_hash,), one=True
    )


def invalidate_reset_token(token_id):
    """Mark a token as used (single-use enforcement)."""
    execute_db(
        "UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s",
        (token_id,)
    )


def cleanup_expired_tokens():
    """Remove tokens older than 48 hours (maintenance helper)."""
    execute_db(
        "DELETE FROM password_reset_tokens WHERE created_at < NOW() - INTERVAL 48 HOUR"
    )
