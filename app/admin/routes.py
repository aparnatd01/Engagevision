"""
Admin Blueprint — Complete CRUD for EngageVision Admin
Routes: dashboard, teachers, classes, sections, assignments, reports, profile
"""

import re
import io
import json
from datetime import datetime, date, timedelta
from flask import (
    render_template, request, redirect, url_for,
    session, flash, Blueprint, jsonify, abort, send_file, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash

from app.decorators import admin_required
from app.models import (
    # Users
    get_user_by_id, get_all_teachers, get_active_teachers,
    create_user, update_user, delete_user,
    update_user_status, update_user_password,
    username_exists, email_exists, staff_id_exists,
    # New Staff-ID-based workflow
    create_teacher_pending_simple,
    # Classes
    get_all_classes, get_class_by_id, create_class, update_class, toggle_class_status, delete_class,
    # Sections
    get_all_sections, get_sections_by_class, get_section_by_id,
    create_section, update_section,
    # Assignments
    get_all_assignments, get_assignments_by_teacher, create_assignment,
    delete_assignment, assignment_exists,
    # Sessions/Reports
    get_all_sessions, get_session_by_id, get_report_by_session,
    # Stats
    get_admin_summary_stats, get_admin_engagement_overview,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ═══════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    stats    = get_admin_summary_stats()
    overview = get_admin_engagement_overview()
    return render_template('admin/dashboard.html',
                           stats=stats, overview=overview)


# ═══════════════════════════════════════════════════════════════
# TEACHERS
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/teachers')
@admin_required
def teachers():
    all_teachers = get_all_teachers()
    return render_template('admin/teachers.html', teachers=all_teachers)


@admin_bp.route('/teachers/add', methods=['GET', 'POST'])
@admin_required
def add_teacher():
    """
    Admin creates a Teacher record with personal details only.
    No username, password, activation link, or email is involved.
    The teacher sets up their own credentials later via Staff ID on the login page.
    """
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip().lower()
        staff_id   = request.form.get('staff_id', '').strip() or None
        department = request.form.get('department', '').strip() or None
        phone      = request.form.get('phone', '').strip() or None

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('A valid email address is required.')
        elif email_exists(email):
            errors.append('An account with this email address already exists.')
        if not staff_id:
            errors.append('Staff ID is required.')
        elif staff_id_exists(staff_id):
            errors.append('This Staff ID is already in use.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/teacher_form.html',
                                   action='add', form=request.form)

        # Create teacher record: no username, no password, is_active=0
        create_teacher_pending_simple(
            first_name, last_name, email, staff_id,
            department, phone
        )

        flash(
            f'Teacher "{first_name} {last_name}" created successfully. '
            f'Status: Account Setup Pending. '
            f'The teacher can set up their account using Staff ID: {staff_id}',
            'success'
        )
        return redirect(url_for('admin.teachers'))

    return render_template('admin/teacher_form.html', action='add', form={})


@admin_bp.route('/teachers/<int:teacher_id>/view')
@admin_required
def view_teacher(teacher_id):
    teacher = get_user_by_id(teacher_id)
    if not teacher or teacher['role'] != 'teacher':
        flash('Teacher not found.', 'danger')
        return redirect(url_for('admin.teachers'))
    return render_template('admin/view_teacher.html', teacher=teacher)


@admin_bp.route('/teachers/<int:teacher_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_teacher(teacher_id):
    teacher = get_user_by_id(teacher_id)
    if not teacher or teacher['role'] != 'teacher':
        flash('Teacher not found.', 'danger')
        return redirect(url_for('admin.teachers'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip()
        staff_id   = request.form.get('staff_id', '').strip() or None
        department = request.form.get('department', '').strip() or None
        phone      = request.form.get('phone', '').strip() or None
        is_active  = 1 if request.form.get('is_active') == '1' else 0

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('Valid email is required.')
        if email_exists(email, exclude_id=teacher_id):
            errors.append('Email is already in use by another account.')
        if staff_id and staff_id_exists(staff_id, exclude_id=teacher_id):
            errors.append('Staff ID is already in use.')

        # Block activating a not-yet-setup teacher via the edit form
        if is_active == 1 and teacher.get('username') is None:
            errors.append(
                'This teacher has not completed account setup. '
                'They cannot be set to Active until they set up their account using their Staff ID.'
            )

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/teacher_form.html',
                                   action='edit', teacher=teacher, form=request.form)

        update_user(teacher_id, first_name, last_name, email, staff_id, department, phone)
        # Only update status for teachers who have activated
        if teacher.get('username') is not None:
            update_user_status(teacher_id, is_active)
        flash(f'Teacher "{first_name} {last_name}" updated successfully.', 'success')
        return redirect(url_for('admin.teachers'))

    return render_template('admin/teacher_form.html',
                           action='edit', teacher=teacher, form=teacher)


@admin_bp.route('/teachers/<int:teacher_id>/toggle', methods=['POST'])
@admin_required
def toggle_teacher(teacher_id):
    teacher = get_user_by_id(teacher_id)
    if not teacher or teacher['role'] != 'teacher':
        flash('Teacher not found.', 'danger')
        return redirect(url_for('admin.teachers'))

    # Cannot toggle a not-yet-setup teacher
    if teacher.get('username') is None:
        flash(
            'This teacher has not yet set up their account. '
            'They need to complete account setup using their Staff ID on the login page.',
            'warning'
        )
        return redirect(url_for('admin.teachers'))

    new_status = 0 if teacher['is_active'] else 1
    update_user_status(teacher_id, new_status)
    action = 'activated' if new_status else 'deactivated'
    flash(f'Teacher "{teacher["first_name"]} {teacher["last_name"]}" {action}.', 'success')
    return redirect(url_for('admin.teachers'))



# ═══════════════════════════════════════════════════════════════
# CLASSES
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/classes')
@admin_required
def classes():
    all_classes = get_all_classes()
    return render_template('admin/classes.html', classes=all_classes)


@admin_bp.route('/classes/add', methods=['GET', 'POST'])
@admin_required
def add_class():
    if request.method == 'POST':
        class_name    = request.form.get('class_name', '').strip()
        course_code   = request.form.get('course_code', '').strip() or None
        semester      = request.form.get('semester', '').strip() or None
        academic_year = request.form.get('academic_year', '').strip() or None
        description   = request.form.get('description', '').strip() or None

        if not class_name:
            flash('Class name is required.', 'danger')
            return render_template('admin/class_form.html', action='add', form=request.form)

        create_class(class_name, course_code, semester, academic_year, description)
        flash(f'Class "{class_name}" created successfully.', 'success')
        return redirect(url_for('admin.classes'))

    return render_template('admin/class_form.html', action='add', form={})


@admin_bp.route('/classes/<int:class_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_class(class_id):
    cls = get_class_by_id(class_id)
    if not cls:
        flash('Class not found.', 'danger')
        return redirect(url_for('admin.classes'))

    if request.method == 'POST':
        class_name    = request.form.get('class_name', '').strip()
        course_code   = request.form.get('course_code', '').strip() or None
        semester      = request.form.get('semester', '').strip() or None
        academic_year = request.form.get('academic_year', '').strip() or None
        description   = request.form.get('description', '').strip() or None

        if not class_name:
            flash('Class name is required.', 'danger')
            return render_template('admin/class_form.html', action='edit', cls=cls, form=request.form)

        update_class(class_id, class_name, course_code, semester, academic_year, description)
        flash(f'Class "{class_name}" updated.', 'success')
        return redirect(url_for('admin.classes'))

    return render_template('admin/class_form.html', action='edit', cls=cls, form=cls)


@admin_bp.route('/classes/<int:class_id>/toggle', methods=['POST'])
@admin_required
def toggle_class(class_id):
    cls = get_class_by_id(class_id)
    if not cls:
        abort(404)
    new_status = 0 if cls['is_active'] else 1
    toggle_class_status(class_id, new_status)
    action = 'activated' if new_status else 'deactivated'
    flash(f'Class "{cls["class_name"]}" {action}.', 'success')
    return redirect(url_for('admin.classes'))


@admin_bp.route('/classes/<int:class_id>/delete', methods=['POST'], endpoint='delete_class')
@admin_required
def delete_class_route(class_id):
    cls = get_class_by_id(class_id)
    if not cls:
        flash('Class not found.', 'danger')
        return redirect(url_for('admin.classes'))

    name = cls['class_name']
    delete_class(class_id)
    flash(f'Class "{name}" and all its sections have been deleted.', 'success')
    return redirect(url_for('admin.classes'))


@admin_bp.route('/teachers/<int:teacher_id>/delete', methods=['POST'])
@admin_required
def delete_teacher(teacher_id):
    teacher = get_user_by_id(teacher_id)

    if not teacher or teacher['role'] != 'teacher':
        flash('Teacher not found.', 'danger')
        return redirect(url_for('admin.teachers'))

    name = f"{teacher['first_name']} {teacher['last_name']}"

    success, message = delete_user(teacher_id)

    if success:
        flash(f'Teacher "{name}" has been permanently deleted.', 'success')
    else:
        flash(f'Failed to delete teacher "{name}": {message}', 'danger')

    return redirect(url_for('admin.teachers'))

# ═══════════════════════════════════════════════════════════════
# SECTIONS
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/sections')
@admin_required
def sections():
    """Display all sections with assigned teacher info."""
    all_sections = get_all_sections()
    all_classes = get_all_classes()
    active_teachers = get_active_teachers()
    all_assignments = get_all_assignments()

    # Build a lookup: section_id -> list of assignment dicts
    section_assignments = {}
    for a in (all_assignments or []):
        sid = a['section_id']
        if sid not in section_assignments:
            section_assignments[sid] = []
        section_assignments[sid].append(a)

    return render_template(
        'admin/sections.html',
        sections=all_sections or [],
        classes=all_classes or [],
        teachers=active_teachers or [],
        section_assignments=section_assignments,
    )


@admin_bp.route('/sections/add', methods=['GET', 'POST'])
@admin_required
def add_section():
    """Add a new section to a class."""

    all_classes = get_all_classes() or []

    if request.method == 'POST':

        # Get form values
        class_id = request.form.get('class_id', type=int)
        section_name = request.form.get('section_name', '').strip()
        student_count = request.form.get('student_count', 0, type=int)
        room_number = request.form.get('room_number', '').strip()

        # Convert empty room to None
        if not room_number:
            room_number = None

        errors = []

        # ---------------- VALIDATION ----------------

        if not class_id:
            errors.append('Please select a class.')

        # Check class actually exists
        if class_id:
            selected_class = get_class_by_id(class_id)

            if not selected_class:
                errors.append('Selected class does not exist.')

        if not section_name:
            errors.append('Section name is required.')

        elif len(section_name) > 10:
            errors.append('Section name must not exceed 10 characters.')

        if student_count < 0:
            errors.append('Student count cannot be negative.')

        # Check duplicate section
        if class_id and section_name:
            existing_sections = get_sections_by_class(class_id) or []

            for sec in existing_sections:
                if sec['section_name'].strip().lower() == section_name.lower():
                    errors.append(
                        f'Section "{section_name}" already exists for this class.'
                    )
                    break

        # ---------------- IF ERROR ----------------

        if errors:

            for error in errors:
                flash(error, 'danger')

            # Send simple dictionary to template
            form_data = {
                'class_id': class_id,
                'section_name': section_name,
                'student_count': student_count,
                'room_number': room_number or ''
            }

            return render_template(
                'admin/section_form.html',
                action='add',
                section=None,
                form=form_data,
                classes=all_classes
            )

        # ---------------- SAVE ----------------

        try:
            create_section(
                class_id,
                section_name,
                student_count,
                room_number
            )

            flash(
                f'Section "{section_name}" created successfully.',
                'success'
            )

            return redirect(url_for('admin.sections'))

        except Exception as e:

            current_app.logger.exception(
                'Error creating section'
            )

            flash(
                'Unable to create section. Please try again.',
                'danger'
            )

            form_data = {
                'class_id': class_id,
                'section_name': section_name,
                'student_count': student_count,
                'room_number': room_number or ''
            }

            return render_template(
                'admin/section_form.html',
                action='add',
                section=None,
                form=form_data,
                classes=all_classes
            )

    # GET request
    return render_template(
        'admin/section_form.html',
        action='add',
        section=None,
        form={},
        classes=all_classes
    )


@admin_bp.route(
    '/sections/<int:section_id>/edit',
    methods=['GET', 'POST']
)
@admin_required
def edit_section(section_id):
    """Edit an existing section."""

    section = get_section_by_id(section_id)
    all_classes = get_all_classes() or []

    # Section doesn't exist
    if not section:
        flash('Section not found.', 'danger')
        return redirect(url_for('admin.sections'))

    if request.method == 'POST':

        # Get submitted values
        class_id = request.form.get('class_id', type=int)
        section_name = request.form.get('section_name', '').strip()
        student_count = request.form.get('student_count', 0, type=int)
        room_number = request.form.get('room_number', '').strip()

        if not room_number:
            room_number = None

        errors = []

        # ---------------- VALIDATION ----------------

        if not class_id:
            errors.append('Please select a class.')

        if class_id:
            selected_class = get_class_by_id(class_id)

            if not selected_class:
                errors.append('Selected class does not exist.')

        if not section_name:
            errors.append('Section name is required.')

        elif len(section_name) > 10:
            errors.append(
                'Section name must not exceed 10 characters.'
            )

        if student_count < 0:
            errors.append(
                'Student count cannot be negative.'
            )

        # Check duplicate section name
        if class_id and section_name:

            sections_in_class = get_sections_by_class(class_id) or []

            for sec in sections_in_class:

                # Ignore current section
                if sec['id'] == section_id:
                    continue

                if (
                    sec['section_name'].strip().lower()
                    == section_name.lower()
                ):
                    errors.append(
                        f'Section "{section_name}" already exists for this class.'
                    )
                    break

        # ---------------- ERROR ----------------

        if errors:

            for error in errors:
                flash(error, 'danger')

            form_data = {
                'class_id': class_id,
                'section_name': section_name,
                'student_count': student_count,
                'room_number': room_number or ''
            }

            # Keep currently submitted values
            section_for_form = dict(section)

            section_for_form['class_id'] = class_id
            section_for_form['section_name'] = section_name
            section_for_form['student_count'] = student_count
            section_for_form['room_number'] = room_number

            return render_template(
                'admin/section_form.html',
                action='edit',
                section=section_for_form,
                form=form_data,
                classes=all_classes
            )

        # ---------------- UPDATE ----------------

        try:

            # IMPORTANT:
            # update_section now also updates class_id
            update_section(
                section_id,
                section_name,
                student_count,
                room_number
            )

            flash(
                f'Section "{section_name}" updated successfully.',
                'success'
            )

            return redirect(url_for('admin.sections'))

        except Exception as e:

            current_app.logger.exception(
                'Error updating section'
            )

            flash(
                'Unable to update section. Please try again.',
                'danger'
            )

            form_data = {
                'class_id': class_id,
                'section_name': section_name,
                'student_count': student_count,
                'room_number': room_number or ''
            }

            return render_template(
                'admin/section_form.html',
                action='edit',
                section=section,
                form=form_data,
                classes=all_classes
            )

    # GET request
    return render_template(
        'admin/section_form.html',
        action='edit',
        section=section,
        form={
            'class_id': section['class_id'],
            'section_name': section['section_name'],
            'student_count': section['student_count'],
            'room_number': section['room_number'] or ''
        },
        classes=all_classes
    )


# ═══════════════════════════════════════════════════════════════
# ASSIGN / REMOVE TEACHER FROM SECTIONS PAGE
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/sections/<int:section_id>/assign-teacher', methods=['POST'])
@admin_required
def assign_teacher_to_section(section_id):
    """Assign a teacher to a section directly from the Sections page."""
    teacher_id = request.form.get('teacher_id', type=int)

    section = get_section_by_id(section_id)
    if not section:
        flash('Section not found.', 'danger')
        return redirect(url_for('admin.sections'))

    if not teacher_id:
        flash('Please select a teacher.', 'danger')
        return redirect(url_for('admin.sections'))

    class_id = section['class_id']

    if assignment_exists(teacher_id, class_id, section_id):
        flash('This teacher is already assigned to this section.', 'warning')
        return redirect(url_for('admin.sections'))

    create_assignment(teacher_id, class_id, section_id)

    teacher = get_user_by_id(teacher_id)
    teacher_name = f"{teacher['first_name']} {teacher['last_name']}" if teacher else "Teacher"
    flash(
        f'{teacher_name} assigned to {section["class_name"]} – Section {section["section_name"]}.',
        'success'
    )
    return redirect(url_for('admin.sections'))


@admin_bp.route('/sections/assignment/<int:assignment_id>/remove', methods=['POST'])
@admin_required
def remove_section_assignment(assignment_id):
    """Remove a teacher assignment from the Sections page."""
    delete_assignment(assignment_id)
    flash('Teacher assignment removed.', 'warning')
    return redirect(url_for('admin.sections'))


# ═══════════════════════════════════════════════════════════════
# AJAX: GET SECTIONS FOR A CLASS
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/api/sections/<int:class_id>')
@admin_required
def api_sections(class_id):

    sections = get_sections_by_class(class_id) or []

    return jsonify([
        {
            'id': section['id'],
            'name': section['section_name']
        }
        for section in sections
    ])

# ═══════════════════════════════════════════════════════════════
# ASSIGNMENTS
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/assignments')
@admin_required
def assignments():
    all_assignments = get_all_assignments()
    all_teachers    = get_all_teachers()
    all_classes     = get_all_classes()
    return render_template('admin/assignments.html',
                           assignments=all_assignments,
                           teachers=all_teachers,
                           classes=all_classes)


@admin_bp.route('/assignments/add', methods=['POST'])
@admin_required
def add_assignment():
    teacher_id = request.form.get('teacher_id', type=int)
    class_id   = request.form.get('class_id', type=int)
    section_id = request.form.get('section_id', type=int)

    errors = []
    if not teacher_id:
        errors.append('Please select a teacher.')
    if not class_id:
        errors.append('Please select a class.')
    if not section_id:
        errors.append('Please select a section.')

    if not errors and assignment_exists(teacher_id, class_id, section_id):
        errors.append('This teacher is already assigned to this class and section.')

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('admin.assignments'))

    create_assignment(teacher_id, class_id, section_id)
    flash('Teacher assigned successfully.', 'success')
    return redirect(url_for('admin.assignments'))


@admin_bp.route('/assignments/<int:assignment_id>/remove', methods=['POST'])
@admin_required
def remove_assignment(assignment_id):
    delete_assignment(assignment_id)
    flash('Assignment removed.', 'warning')
    return redirect(url_for('admin.assignments'))


# ═══════════════════════════════════════════════════════════════
# REPORTS (Admin View)
# ═══════════════════════════════════════════════════════════════

@admin_bp.route('/reports')
@admin_required
def reports():
    class_id    = request.args.get('class_id', type=int)
    section_id  = request.args.get('section_id', type=int)
    teacher_id  = request.args.get('teacher_id', type=int)
    from_date_s = request.args.get('from_date', '').strip()
    to_date_s   = request.args.get('to_date', '').strip()
    date_filter = request.args.get('date', '').strip() or None

    start_date = None
    end_date   = None

    if from_date_s and to_date_s:
        try:
            from_d = datetime.strptime(from_date_s, '%Y-%m-%d').date()
            to_d   = datetime.strptime(to_date_s, '%Y-%m-%d').date()
            if from_d > to_d:
                flash('From Date cannot be later than To Date.', 'danger')
            else:
                start_date = from_d
                end_date   = to_d
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
    elif from_date_s:
        try:
            start_date = datetime.strptime(from_date_s, '%Y-%m-%d').date()
        except ValueError:
            pass
    elif to_date_s:
        try:
            end_date = datetime.strptime(to_date_s, '%Y-%m-%d').date()
        except ValueError:
            pass

    all_classes = get_all_classes() or []
    valid_class_ids = {c['id'] for c in all_classes}
    if class_id and class_id not in valid_class_ids:
        flash('Selected class does not exist.', 'danger')
        class_id   = None
        section_id = None

    if class_id:
        sections = get_sections_by_class(class_id) or []
        valid_sec_ids = {s['id'] for s in sections}
        if section_id and section_id not in valid_sec_ids:
            flash('Selected section does not belong to the selected class.', 'danger')
            section_id = None
    else:
        sections = get_all_sections() or []
        if section_id:
            sec = get_section_by_id(section_id)
            if not sec:
                section_id = None

    all_sessions = get_all_sessions(
        class_id=class_id,
        section_id=section_id,
        teacher_id=teacher_id,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    all_teachers = get_all_teachers()

    def_from = (date.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    def_to   = date.today().strftime('%Y-%m-%d')

    return render_template('admin/reports.html',
                           sessions=all_sessions,
                           teachers=all_teachers,
                           classes=all_classes,
                           sections=sections,
                           filters={
                               'class_id':   class_id or '',
                               'section_id': section_id or '',
                               'teacher_id': teacher_id or '',
                               'from_date':  from_date_s or (date_filter or def_from),
                               'to_date':    to_date_s   or (date_filter or def_to),
                               'date':       date_filter or '',
                           })


@admin_bp.route('/reports/<int:session_id>')
@admin_required
def report_detail(session_id):
    """Admin view of a specific monitoring session report."""
    db_session = get_session_by_id(session_id)
    if not db_session:
        flash('Session not found.', 'danger')
        return redirect(url_for('admin.reports'))

    report    = get_report_by_session(session_id)
    face_data = []
    if report and report['face_data']:
        face_data = (json.loads(report['face_data'])
                     if isinstance(report['face_data'], str)
                     else report['face_data'])

    teacher = get_user_by_id(db_session['teacher_id']) if db_session.get('teacher_id') else None

    return render_template('admin/report_detail.html',
                           db_session=db_session,
                           report=report,
                           face_data=face_data,
                           teacher=teacher)


@admin_bp.route('/reports/<int:session_id>/download')
@admin_required
def download_report(session_id):
    """Admin: generate and download PDF for any session."""
    from app.reports.routes import _build_pdf
    db_session = get_session_by_id(session_id)
    if not db_session:
        flash('Session not found.', 'danger')
        return redirect(url_for('admin.reports'))

    report    = get_report_by_session(session_id)
    face_data = []
    if report and report['face_data']:
        face_data = (json.loads(report['face_data'])
                     if isinstance(report['face_data'], str)
                     else report['face_data'])

    teacher   = get_user_by_id(db_session['teacher_id']) if db_session.get('teacher_id') else None
    pdf_buf   = _build_pdf(db_session, report, face_data, teacher)
    filename  = (f"EngageVision_Report_"
                 f"{db_session.get('class_name','')}_"
                 f"{db_session.get('section_name','')}_{session_id}.pdf")

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf',
    )


def _handle_admin_period_download(period_name, default_days):
    """Helper for admin Weekly/Monthly PDF downloads with server validation."""
    from app.dashboard.routes import _build_period_pdf

    admin = get_user_by_id(session['user_id'])
    from_date_s = request.args.get('from_date', '').strip()
    to_date_s   = request.args.get('to_date', '').strip()
    class_id    = request.args.get('class_id', type=int)
    section_id  = request.args.get('section_id', type=int)
    teacher_id  = request.args.get('teacher_id', type=int)

    # Date range validation
    if from_date_s and to_date_s:
        try:
            start_date = datetime.strptime(from_date_s, '%Y-%m-%d').date()
            end_date   = datetime.strptime(to_date_s, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
            return redirect(url_for('admin.reports'))

        if start_date > end_date:
            flash('From Date cannot be later than To Date.', 'danger')
            return redirect(url_for('admin.reports'))
    elif from_date_s or to_date_s:
        flash('Both From Date and To Date must be provided.', 'danger')
        return redirect(url_for('admin.reports'))
    else:
        start_date = date.today() - timedelta(days=default_days)
        end_date   = date.today()

    # Class & Section validation
    class_name   = None
    section_name = None

    if class_id:
        cls = get_class_by_id(class_id)
        if not cls:
            flash('Selected class does not exist.', 'danger')
            return redirect(url_for('admin.reports'))
        class_name = cls['class_name']

        if section_id:
            sec = get_section_by_id(section_id)
            if not sec or sec['class_id'] != class_id:
                flash('Selected section does not belong to the selected class.', 'danger')
                return redirect(url_for('admin.reports'))
            section_name = sec['section_name']
    elif section_id:
        flash('Please select a class before selecting a section.', 'danger')
        return redirect(url_for('admin.reports'))

    teacher_obj = None
    if teacher_id:
        teacher_obj = get_user_by_id(teacher_id)
        if not teacher_obj:
            flash('Selected teacher does not exist.', 'danger')
            return redirect(url_for('admin.reports'))
    else:
        teacher_obj = {'first_name': 'All', 'last_name': 'Teachers'}

    all_sessions = get_all_sessions(
        class_id=class_id,
        section_id=section_id,
        teacher_id=teacher_id,
        start_date=start_date,
        end_date=end_date,
    )

    pdf_buf = _build_period_pdf(
        all_sessions, teacher_obj, period_name, start_date, end_date,
        class_name=class_name, section_name=section_name
    )
    fname = f"EngageVision_Admin_{period_name}_{start_date}_to_{end_date}.pdf"
    return send_file(pdf_buf, as_attachment=True,
                     download_name=fname, mimetype='application/pdf')


@admin_bp.route('/reports/download/weekly')
@admin_required
def download_weekly_report():
    """Admin: weekly PDF covering sessions from selected date range (all or filtered teachers/classes)."""
    return _handle_admin_period_download(period_name='Weekly', default_days=7)


@admin_bp.route('/reports/download/monthly')
@admin_required
def download_monthly_report():
    """Admin: monthly PDF covering sessions from selected date range (all or filtered teachers/classes)."""
    return _handle_admin_period_download(period_name='Monthly', default_days=30)


# ═══════════════════════════════════════════════════════════════
# PROFILE
# ═══════════════════════════════════════════════════════════════


@admin_bp.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    admin = get_user_by_id(session['user_id'])
    return render_template('admin/profile.html', admin=admin)


@admin_bp.route('/profile/change-password', methods=['POST'])
@admin_required
def change_password():
    admin      = get_user_by_id(session['user_id'])
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    errors = []
    if not current_pw:
        errors.append('Current password is required.')
    elif not check_password_hash(admin['password_hash'], current_pw):
        errors.append('Current password is incorrect.')

    pw_errors = _validate_password(new_pw, confirm_pw)
    errors.extend(pw_errors)

    # Check new password is different from current
    if not pw_errors and current_pw and check_password_hash(admin['password_hash'], new_pw):
        errors.append('New password must be different from your current password.')

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('admin.profile'))

    update_user_password(session['user_id'], generate_password_hash(new_pw))
    flash('Password changed successfully.', 'success')
    return redirect(url_for('admin.profile'))


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _validate_teacher_form(first_name, last_name, username, email, password,
                            staff_id, is_edit=False):
    errors = []
    if not first_name:
        errors.append('First name is required.')
    if not last_name:
        errors.append('Last name is required.')
    if not username or len(username) < 3:
        errors.append('Username must be at least 3 characters.')
    elif not re.match(r'^[A-Za-z0-9_]+$', username):
        errors.append('Username may only contain letters, numbers, and underscores.')
    elif username_exists(username):
        errors.append('Username is already taken.')
    if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        errors.append('Valid email is required.')
    elif email_exists(email):
        errors.append('Email is already in use.')
    if staff_id and staff_id_exists(staff_id):
        errors.append('Staff ID is already in use.')

    if not is_edit:
        errors.extend(_validate_password(password, password))

    return errors


def _validate_password(new_pw, confirm_pw):
    errors = []
    if not new_pw:
        errors.append('Password is required.')
    elif len(new_pw) < 8:
        errors.append('Password must be at least 8 characters.')
    elif not re.search(r'[A-Z]', new_pw):
        errors.append('Password must contain at least one uppercase letter.')
    elif not re.search(r'[a-z]', new_pw):
        errors.append('Password must contain at least one lowercase letter.')
    elif not re.search(r'[0-9]', new_pw):
        errors.append('Password must contain at least one digit.')
    if new_pw and new_pw != confirm_pw:
        errors.append('Passwords do not match.')
    return errors
