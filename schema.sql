-- =============================================================
-- EngageVision — AI-Based Student Engagement Monitoring System
-- Complete Database Schema v2.0
-- Database: engagevision
-- =============================================================
-- USAGE:
--   mysql -u root -p < database/schema.sql
--   Then run: python setup_admin.py
-- =============================================================

CREATE DATABASE IF NOT EXISTS engagevision
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE engagevision;

SET FOREIGN_KEY_CHECKS = 0;

-- =============================================================
-- Table: users
-- Unified auth table for admin and teacher roles only.
-- Students are NOT system users — they appear via video analysis.
-- =============================================================
CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    username        VARCHAR(50)              DEFAULT NULL,
    email           VARCHAR(150)    NOT NULL,
    password_hash   VARCHAR(255)             DEFAULT NULL,
    role            ENUM('admin','teacher')
                                    NOT NULL DEFAULT 'teacher',
    first_name      VARCHAR(80)     NOT NULL DEFAULT '',
    last_name       VARCHAR(80)     NOT NULL DEFAULT '',
    staff_id        VARCHAR(20)              DEFAULT NULL,
    department      VARCHAR(100)             DEFAULT NULL,
    phone           VARCHAR(20)              DEFAULT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_signed_in  DATETIME                 DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_username (username),
    UNIQUE KEY uq_email    (email),
    UNIQUE KEY uq_staff_id (staff_id),
    INDEX idx_role         (role),
    INDEX idx_is_active    (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: classes
-- Represents a subject/course (e.g., "Database", "Python")
-- Created and managed by Admin only.
-- =============================================================
CREATE TABLE IF NOT EXISTS classes (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    class_name      VARCHAR(150)    NOT NULL,
    course_code     VARCHAR(30)              DEFAULT NULL,
    semester        VARCHAR(30)              DEFAULT NULL,
    academic_year   VARCHAR(20)              DEFAULT NULL,
    description     TEXT                     DEFAULT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_class_name (class_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: sections
-- A section belongs to a class (e.g., Class=Database, Section=A)
-- =============================================================
CREATE TABLE IF NOT EXISTS sections (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    class_id        INT UNSIGNED    NOT NULL,
    section_name    VARCHAR(20)     NOT NULL,
    student_count   INT UNSIGNED    NOT NULL DEFAULT 0,
    room_number     VARCHAR(30)              DEFAULT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_class_section (class_id, section_name),
    CONSTRAINT fk_section_class
        FOREIGN KEY (class_id) REFERENCES classes(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_sec_class (class_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: teacher_assignments
-- Maps a teacher to a specific class + section combination.
-- A teacher can be assigned to multiple class/section combos.
-- =============================================================
CREATE TABLE IF NOT EXISTS teacher_assignments (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    teacher_id      INT UNSIGNED    NOT NULL,
    class_id        INT UNSIGNED    NOT NULL,
    section_id      INT UNSIGNED    NOT NULL,
    assigned_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_assignment (teacher_id, class_id, section_id),
    CONSTRAINT fk_ta_teacher
        FOREIGN KEY (teacher_id)  REFERENCES users(id)     ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ta_class
        FOREIGN KEY (class_id)    REFERENCES classes(id)   ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ta_section
        FOREIGN KEY (section_id)  REFERENCES sections(id)  ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_ta_teacher  (teacher_id),
    INDEX idx_ta_class    (class_id),
    INDEX idx_ta_section  (section_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: students
-- Classroom participant records for student count management.
-- Students do NOT have login accounts.
-- =============================================================
CREATE TABLE IF NOT EXISTS students (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name            VARCHAR(150)    NOT NULL,
    roll_number     VARCHAR(30)              DEFAULT NULL,
    class_id        INT UNSIGNED             DEFAULT NULL,
    section_id      INT UNSIGNED             DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_student_class
        FOREIGN KEY (class_id)   REFERENCES classes(id)   ON DELETE SET NULL,
    CONSTRAINT fk_student_section
        FOREIGN KEY (section_id) REFERENCES sections(id)  ON DELETE SET NULL,
    INDEX idx_stu_class   (class_id),
    INDEX idx_stu_section (section_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: class_students
-- Many-to-many between students and sections
-- =============================================================
CREATE TABLE IF NOT EXISTS class_students (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    student_id  INT UNSIGNED    NOT NULL,
    section_id  INT UNSIGNED    NOT NULL,
    enrolled_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_cs (student_id, section_id),
    CONSTRAINT fk_cs_student
        FOREIGN KEY (student_id) REFERENCES students(id)  ON DELETE CASCADE,
    CONSTRAINT fk_cs_section
        FOREIGN KEY (section_id) REFERENCES sections(id)  ON DELETE CASCADE,
    INDEX idx_cs_section (section_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: monitoring_sessions
-- Linked to a teacher (users.id), class, and section.
-- =============================================================
CREATE TABLE IF NOT EXISTS monitoring_sessions (
    id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    teacher_id          INT UNSIGNED    NOT NULL,
    class_id            INT UNSIGNED             DEFAULT NULL,
    section_id          INT UNSIGNED             DEFAULT NULL,
    session_name        VARCHAR(200)    NOT NULL DEFAULT 'Unnamed Session',
    session_date        DATE                     DEFAULT NULL,
    video_filename      VARCHAR(255)    NOT NULL,
    video_path          VARCHAR(500)    NOT NULL,
    start_time          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time            DATETIME                 DEFAULT NULL,
    duration_seconds    INT UNSIGNED             DEFAULT NULL,
    status              ENUM('pending','processing','completed','failed')
                                        NOT NULL DEFAULT 'pending',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_session_teacher
        FOREIGN KEY (teacher_id)  REFERENCES users(id)     ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_session_class
        FOREIGN KEY (class_id)    REFERENCES classes(id)   ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_session_section
        FOREIGN KEY (section_id)  REFERENCES sections(id)  ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX idx_ms_teacher  (teacher_id),
    INDEX idx_ms_class    (class_id),
    INDEX idx_ms_section  (section_id),
    INDEX idx_ms_status   (status),
    INDEX idx_ms_date     (session_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: engagement_reports
-- Summary statistics per monitoring session
-- =============================================================
CREATE TABLE IF NOT EXISTS engagement_reports (
    id                      INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    session_id              INT UNSIGNED    NOT NULL UNIQUE,
    total_faces             INT UNSIGNED    NOT NULL DEFAULT 0,
    active_count            INT UNSIGNED    NOT NULL DEFAULT 0,
    inactive_count          INT UNSIGNED    NOT NULL DEFAULT 0,
    high_count              INT UNSIGNED    NOT NULL DEFAULT 0,
    medium_count            INT UNSIGNED    NOT NULL DEFAULT 0,
    low_count               INT UNSIGNED    NOT NULL DEFAULT 0,
    overall_percentage      DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    high_percentage         DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    medium_percentage       DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    low_percentage          DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    face_data               JSON                     DEFAULT NULL,
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_report_session
        FOREIGN KEY (session_id) REFERENCES monitoring_sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_er_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: engagement_scores
-- Per-face engagement score from AI analysis
-- =============================================================
CREATE TABLE IF NOT EXISTS engagement_scores (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    session_id      INT UNSIGNED    NOT NULL,
    face_index      INT UNSIGNED    NOT NULL,
    score           DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    level           ENUM('High','Medium','Low') NOT NULL DEFAULT 'Low',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    ear_score       DECIMAL(5,3)             DEFAULT NULL,
    head_pose_score DECIMAL(5,3)             DEFAULT NULL,
    mouth_score     DECIMAL(5,3)             DEFAULT NULL,
    crop_path       VARCHAR(500)             DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_es_session
        FOREIGN KEY (session_id) REFERENCES monitoring_sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_es_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================
-- Table: reports
-- Report metadata — PDF generated on demand
-- =============================================================
CREATE TABLE IF NOT EXISTS reports (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    session_id      INT UNSIGNED    NOT NULL UNIQUE,
    teacher_id      INT UNSIGNED    NOT NULL,
    report_title    VARCHAR(200)             DEFAULT NULL,
    report_type     VARCHAR(50)     NOT NULL DEFAULT 'engagement',
    report_file_path VARCHAR(500)            DEFAULT NULL,
    generated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_rep_session
        FOREIGN KEY (session_id)  REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_rep_teacher
        FOREIGN KEY (teacher_id)  REFERENCES users(id)               ON DELETE CASCADE,
    INDEX idx_rep_teacher (teacher_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================
-- Seed Data: Admin account placeholder
-- IMPORTANT: Run `python setup_admin.py` after this to set
-- the real password hash for the admin account.
-- =============================================================
INSERT INTO users (username, email, password_hash, role, first_name, last_name, is_active)
VALUES (
    'admin',
    'admin@engagevision.edu',
    'placeholder_run_setup_admin',
    'admin',
    'System',
    'Admin',
    1
)
ON DUPLICATE KEY UPDATE id = id;


-- =============================================================
-- NOTE:
--   1. Run `python setup_admin.py`   to set the real admin password.
--   2. Use the Admin UI to create teacher accounts.
--   3. Use the Admin UI to create classes and sections.
--   4. Use the Admin UI to assign teachers to classes/sections.
--   5. Run `python run.py` to start the application.
-- =============================================================
