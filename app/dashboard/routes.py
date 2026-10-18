"""
Teacher Dashboard Blueprint Routes — EngageVision
Includes: Dashboard, My Classes, Reports (full implementation), Profile
"""

import io
import re
from datetime import datetime, date, timedelta

from flask import (
    render_template, redirect, url_for, session, flash,
    request, Blueprint, send_file, current_app, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

from app.decorators import teacher_required
from app.models import (
    get_user_by_id, update_user, update_user_password,
    get_assignments_by_teacher,
    count_sessions_by_teacher,
    get_teacher_dashboard_stats,
    get_last_session,
    get_sessions_by_teacher,
    get_classes_for_teacher,
    get_sections_for_teacher_and_class,
    get_section_by_id,
    get_class_by_id,
    verify_teacher_assignment,
    get_session_by_id,
    get_report_by_session,
    get_engagement_scores_by_session,
)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/teacher')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@dashboard_bp.route('/dashboard')
@teacher_required
def index():
    uid            = session['user_id']
    teacher        = get_user_by_id(uid)
    assignments    = get_assignments_by_teacher(uid)
    stats          = get_teacher_dashboard_stats(uid)
    last_sess      = get_last_session(uid)
    total_sessions = count_sessions_by_teacher(uid)

    total_classes  = len({a['class_id'] for a in assignments}) if assignments else 0
    total_students = sum(a.get('student_count', 0) or 0 for a in assignments) if assignments else 0

    return render_template(
        'teacher/dashboard.html',
        teacher=teacher,
        assignments=assignments,
        stats=stats,
        last_session=last_sess,
        total_sessions=total_sessions,
        total_classes=total_classes,
        total_students=total_students,
        now=datetime.now(),
    )


# ── My Classes ────────────────────────────────────────────────────────────────

@dashboard_bp.route('/my-classes')
@teacher_required
def my_classes():
    uid         = session['user_id']
    teacher     = get_user_by_id(uid)
    assignments = get_assignments_by_teacher(uid)
    return render_template(
        'teacher/my_classes.html',
        teacher=teacher,
        assignments=assignments,
    )


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS — Teacher: filtered to logged-in teacher's sessions only
# ══════════════════════════════════════════════════════════════════════════════

@dashboard_bp.route('/reports')
@teacher_required
def reports():
    """
    List all monitoring sessions belonging to the logged-in teacher.
    Server-side filtered: teacher can only see their own sessions.
    Supports from_date, to_date, class_id, and section_id filters.
    """
    uid         = session['user_id']
    teacher     = get_user_by_id(uid)
    class_id    = request.args.get('class_id', type=int)
    section_id  = request.args.get('section_id', type=int)
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

    # Validate class and section authorization
    teacher_classes    = get_classes_for_teacher(uid)
    assigned_class_ids = {c['id'] for c in (teacher_classes or [])}

    if class_id and class_id not in assigned_class_ids:
        flash('You are not authorized to view the selected class.', 'danger')
        class_id   = None
        section_id = None

    teacher_sections = []
    if class_id:
        teacher_sections = get_sections_for_teacher_and_class(uid, class_id) or []
        assigned_sec_ids = {s['id'] for s in teacher_sections}
        if section_id and section_id not in assigned_sec_ids:
            flash('Selected section is invalid or not assigned to you for this class.', 'danger')
            section_id = None
    else:
        section_id = None

    teacher_sessions = get_sessions_by_teacher(
        uid,
        class_id=class_id,
        section_id=section_id,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
    )

    def_from = (date.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    def_to   = date.today().strftime('%Y-%m-%d')

    return render_template(
        'teacher/reports.html',
        teacher=teacher,
        sessions=teacher_sessions,
        teacher_classes=teacher_classes,
        teacher_sections=teacher_sections,
        filters={
            'class_id':   class_id or '',
            'section_id': section_id or '',
            'from_date':  from_date_s or (date_filter or def_from),
            'to_date':    to_date_s   or (date_filter or def_to),
            'date':       date_filter or '',
        },
    )


@dashboard_bp.route('/api/sections/<int:class_id>')
@teacher_required
def api_sections(class_id):
    """AJAX endpoint: returns sections assigned to the logged-in teacher for a class."""
    uid = session['user_id']
    sections = get_sections_for_teacher_and_class(uid, class_id) or []
    return jsonify([
        {
            'id': s['id'],
            'name': s['section_name'],
        }
        for s in sections
    ])


@dashboard_bp.route('/reports/<int:session_id>')
@teacher_required
def report_detail(session_id):
    """
    Detailed report for one monitoring session.
    SECURITY: teacher can only access sessions where teacher_id == their own uid.
    """
    uid        = session['user_id']
    db_session = get_session_by_id(session_id)

    # Strict server-side access control
    if not db_session or db_session.get('teacher_id') != uid:
        flash('Report not found or access denied.', 'danger')
        return redirect(url_for('dashboard.reports'))

    report  = get_report_by_session(session_id)
    scores  = get_engagement_scores_by_session(session_id)
    teacher = get_user_by_id(uid)

    return render_template(
        'teacher/report_detail.html',
        db_session=db_session,
        report=report,
        scores=scores,
        teacher=teacher,
    )


@dashboard_bp.route('/reports/<int:session_id>/download')
@teacher_required
def download_report(session_id):
    """Download individual session PDF. Enforces teacher ownership."""
    uid        = session['user_id']
    db_session = get_session_by_id(session_id)

    if not db_session or db_session.get('teacher_id') != uid:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.reports'))

    report  = get_report_by_session(session_id)
    scores  = get_engagement_scores_by_session(session_id)
    teacher = get_user_by_id(uid)

    pdf_buf = _build_session_pdf(db_session, report, scores, teacher)
    cn   = (db_session.get('class_name') or 'Class').replace(' ', '_')
    sn   = (db_session.get('section_name') or 'Sec').replace(' ', '_')
    fname = f"EngageVision_{cn}_{sn}_Session{session_id}.pdf"
    return send_file(pdf_buf, as_attachment=True,
                     download_name=fname, mimetype='application/pdf')


def _handle_teacher_period_download(period_name, default_days):
    """Helper for teacher Weekly/Monthly PDF downloads with server validation."""
    uid     = session['user_id']
    teacher = get_user_by_id(uid)

    from_date_s = request.args.get('from_date', '').strip()
    to_date_s   = request.args.get('to_date', '').strip()
    class_id    = request.args.get('class_id', type=int)
    section_id  = request.args.get('section_id', type=int)

    # Date range validation
    if from_date_s and to_date_s:
        try:
            start_date = datetime.strptime(from_date_s, '%Y-%m-%d').date()
            end_date   = datetime.strptime(to_date_s, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
            return redirect(url_for('dashboard.reports'))

        if start_date > end_date:
            flash('From Date cannot be later than To Date.', 'danger')
            return redirect(url_for('dashboard.reports'))
    elif from_date_s or to_date_s:
        flash('Both From Date and To Date must be provided.', 'danger')
        return redirect(url_for('dashboard.reports'))
    else:
        start_date = date.today() - timedelta(days=default_days)
        end_date   = date.today()

    # Class and Section authorization validation
    class_name   = None
    section_name = None

    if class_id:
        teacher_classes = get_classes_for_teacher(uid)
        cls_match = next((c for c in (teacher_classes or []) if c['id'] == class_id), None)
        if not cls_match:
            flash('You are not authorized to access the selected class.', 'danger')
            return redirect(url_for('dashboard.reports'))
        class_name = cls_match['class_name']

        if section_id:
            teacher_sections = get_sections_for_teacher_and_class(uid, class_id)
            sec_match = next((s for s in (teacher_sections or []) if s['id'] == section_id), None)
            if not sec_match:
                flash('Selected section is invalid or not assigned to you for this class.', 'danger')
                return redirect(url_for('dashboard.reports'))
            section_name = sec_match['section_name']
    elif section_id:
        flash('Please select a class before selecting a section.', 'danger')
        return redirect(url_for('dashboard.reports'))

    all_sessions = get_sessions_by_teacher(
        uid,
        class_id=class_id,
        section_id=section_id,
        start_date=start_date,
        end_date=end_date,
    )

    pdf_buf = _build_period_pdf(
        all_sessions, teacher, period_name, start_date, end_date,
        class_name=class_name, section_name=section_name
    )
    fname = f"EngageVision_{period_name}_{start_date}_to_{end_date}.pdf"
    return send_file(pdf_buf, as_attachment=True,
                     download_name=fname, mimetype='application/pdf')


@dashboard_bp.route('/reports/download/weekly')
@teacher_required
def download_weekly():
    """Weekly PDF: sessions from selected date range (defaults to last 7 days) and optional class/section."""
    return _handle_teacher_period_download(period_name='Weekly', default_days=7)


@dashboard_bp.route('/reports/download/monthly')
@teacher_required
def download_monthly():
    """Monthly PDF: sessions from selected date range (defaults to last 30 days) and optional class/section."""
    return _handle_teacher_period_download(period_name='Monthly', default_days=30)


# ══════════════════════════════════════════════════════════════════════════════
# PDF BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _build_session_pdf(db_session, report, scores, teacher):
    """
    Build a PDF for an individual monitoring session.
    - Session Details: Teacher, Class, Section, Date, Status (no Session Name)
    - Student table: real face crop image + Student ID + Score + Level + Status
    Returns a BytesIO buffer ready to send.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage,
    )
    from reportlab.lib.enums import TA_CENTER
    import os as _os

    NAVY  = colors.HexColor('#0f2342')
    TEAL  = colors.HexColor('#0e7490')
    GREY  = colors.HexColor('#64748b')
    LIGHT = colors.HexColor('#f0f7ff')
    WHITE = colors.white

    title_s  = ParagraphStyle('T',  fontName='Helvetica-Bold', fontSize=20,
                                textColor=NAVY, alignment=TA_CENTER, spaceAfter=6)
    sub_s    = ParagraphStyle('S',  fontName='Helvetica', fontSize=11,
                                textColor=TEAL, alignment=TA_CENTER, spaceAfter=10)
    h2_s     = ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=13,
                                textColor=NAVY, spaceBefore=14, spaceAfter=6, keepWithNext=True)
    footer_s = ParagraphStyle('F',  fontName='Helvetica-Oblique', fontSize=8,
                                textColor=GREY, alignment=TA_CENTER)
    cell_s   = ParagraphStyle('C',  fontName='Helvetica', fontSize=9,
                                textColor=NAVY)
    cell_b   = ParagraphStyle('CB', fontName='Helvetica-Bold', fontSize=9,
                                textColor=NAVY)
    cell_c   = ParagraphStyle('CC', fontName='Helvetica', fontSize=9,
                                textColor=NAVY, alignment=TA_CENTER)
    cell_b_c = ParagraphStyle('CBC', fontName='Helvetica-Bold', fontSize=9,
                                textColor=NAVY, alignment=TA_CENTER)
    hdr_c    = ParagraphStyle('HC', fontName='Helvetica-Bold', fontSize=9,
                                textColor=WHITE, alignment=TA_CENTER)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elems = []

    teacher_name     = (f"{teacher['first_name']} {teacher['last_name']}".strip()
                        if teacher else 'N/A')
    session_date_str = str(db_session.get('session_date') or 'N/A')

    # ── Header ────────────────────────────────────────────────────
    elems.append(Paragraph('EngageVision', title_s))
    elems.append(Paragraph('AI-Based Student Engagement Monitoring Report', sub_s))
    elems.append(HRFlowable(width='100%', thickness=2, color=TEAL, spaceAfter=10))

    # ── Session Details (5 fields only — no Session Name) ─────────
    elems.append(Paragraph('Session Details', h2_s))
    info = [
        ['Teacher', teacher_name],
        ['Class',   db_session.get('class_name')   or 'N/A'],
        ['Section', db_session.get('section_name') or 'N/A'],
        ['Date',    session_date_str],
        ['Status',  (db_session.get('status') or '').title()],
    ]
    from reportlab.platypus import Table as _T, TableStyle as _TS
    from reportlab.lib import colors as _c
    info_t = _T(info, colWidths=[4*cm, 13*cm])
    info_t.setStyle(_TS([
        ('FONTNAME',    (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',    (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE',    (0, 0), (-1,-1), 9),
        ('TEXTCOLOR',   (0, 0), (-1,-1), NAVY),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [LIGHT, WHITE]),
        ('GRID',        (0, 0), (-1,-1), 0.3, _c.lightgrey),
        ('VALIGN',      (0, 0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING',  (0, 0), (-1,-1), 6),
        ('LEFTPADDING', (0, 0), (-1,-1), 8),
        ('RIGHTPADDING', (0, 0), (-1,-1), 8),
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 0.4*cm))

    # ── Engagement Summary ────────────────────────────────────────
    if report:
        elems.append(Paragraph('Engagement Summary', h2_s))
        overall = float(report.get('overall_percentage', 0))
        summary = [
            ['Metric', 'Value', 'Metric', 'Value'],
            ['Overall Engagement', f"{overall:.1f}%",
             'Total Students',     str(report.get('total_faces', 0))],
            ['High Engagement',    str(report.get('high_count', 0)),
             'High %',             f"{float(report.get('high_percentage', 0)):.1f}%"],
            ['Medium Engagement',  str(report.get('medium_count', 0)),
             'Medium %',           f"{float(report.get('medium_percentage', 0)):.1f}%"],
            ['Low Engagement',     str(report.get('low_count', 0)),
             'Low %',              f"{float(report.get('low_percentage', 0)):.1f}%"],
            ['Active Students',    str(report.get('active_count', 0)),
             'Inactive',           str(report.get('inactive_count', 0))],
        ]
        _header_table(elems, summary, [4.8*cm, 3.7*cm, 4.8*cm, 3.7*cm],
                      NAVY, TEAL, LIGHT, WHITE)
        elems.append(Spacer(1, 0.4*cm))

    # ── Student-wise Results with real face crops ─────────────────
    if scores:
        elems.append(Paragraph('Student-wise Engagement Results', h2_s))

        # Build the uploads base path to resolve relative crop_path values
        import os as _oos
        from flask import current_app as _ca
        _uploads_base = _oos.path.abspath(
            _oos.path.join(_ca.root_path, '..', 'uploads')
        )

        FACE_SIZE = 1.4 * cm   # image cell dimensions in the PDF

        rows = [[
            Paragraph('Photo', hdr_c),
            Paragraph('Student ID', hdr_c),
            Paragraph('Engagement Score', hdr_c),
            Paragraph('Level', hdr_c),
            Paragraph('Status', hdr_c),
        ]]
        for sc in scores:
            face_idx  = sc.get('face_index') or sc.get('id', '?')
            score_val = float(sc.get('score', 0))
            level     = sc.get('level', 'N/A')
            is_active = sc.get('is_active', 1)

            # Try to embed the real face crop image
            img_cell = Paragraph('Face image<br/>unavailable', cell_c)
            rel_crop  = sc.get('crop_path') or ''
            if rel_crop:
                abs_crop = _oos.path.join(_uploads_base, rel_crop.replace('/', _oos.sep))
                if _oos.path.exists(abs_crop):
                    try:
                        img_cell = RLImage(abs_crop, width=FACE_SIZE, height=FACE_SIZE)
                    except Exception:
                        img_cell = Paragraph('—', cell_c)
                else:
                    img_cell = Paragraph('—', cell_c)

            level_color = {'High': '#16a34a', 'Medium': '#b45309', 'Low': '#dc2626'}.get(level, '#374151')
            rows.append([
                img_cell,
                Paragraph(f"<b>Student {face_idx}</b>", cell_b_c),
                Paragraph(f"{score_val:.1f}%", cell_c),
                Paragraph(f'<font color="{level_color}"><b>{level}</b></font>', cell_b_c),
                Paragraph('Active' if is_active else 'Inactive', cell_c),
            ])

        from reportlab.platypus import Table as _T2, TableStyle as _TS2
        col_ws = [2.5*cm, 3.5*cm, 3.8*cm, 3.6*cm, 3.6*cm]
        st = _T2(rows, colWidths=col_ws, repeatRows=1)
        st.setStyle(_TS2([
            ('BACKGROUND',    (0, 0), (-1, 0), TEAL),
            ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1,-1), 9),
            ('ROWBACKGROUNDS',(0, 1), (-1,-1), [LIGHT, WHITE]),
            ('GRID',          (0, 0), (-1,-1), 0.3, _c.lightgrey),
            ('VALIGN',        (0, 0), (-1,-1), 'MIDDLE'),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1,-1), 5),
            ('TOPPADDING',    (0, 0), (-1,-1), 5),
            ('LEFTPADDING',   (0, 0), (-1,-1), 4),
            ('RIGHTPADDING',  (0, 0), (-1,-1), 4),
        ]))
        elems.append(st)

    # ── Footer ────────────────────────────────────────────────────
    elems.append(Spacer(1, 0.5*cm))
    elems.append(HRFlowable(width='100%', thickness=0.5, color=colors.lightgrey))
    elems.append(Paragraph(
        f"EngageVision  •  Generated on {datetime.now().strftime('%d %B %Y at %I:%M %p')}",
        footer_s,
    ))

    doc.build(elems)
    buf.seek(0)
    return buf


def _build_period_pdf(sessions_list, teacher, period_name, start_date, end_date,
                       class_name=None, section_name=None):
    """
    Build a weekly or monthly summary PDF with:
    - Properly spaced heading (no overlap)
    - Session summary table (only completed sessions)
    - Detailed student-wise engagement table per session with real face crops
    - Aggregate statistics
    - Class and Section filters displayed when provided
    Returns a BytesIO buffer.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, Image as RLImage,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import os as _os

    NAVY  = colors.HexColor('#0f2342')
    TEAL  = colors.HexColor('#0e7490')
    GREY  = colors.HexColor('#64748b')
    LIGHT = colors.HexColor('#f0f7ff')
    WHITE = colors.white

    title_s  = ParagraphStyle('T',  fontName='Helvetica-Bold', fontSize=20,
                                textColor=NAVY, alignment=TA_CENTER, spaceAfter=6)
    sub_s    = ParagraphStyle('S',  fontName='Helvetica', fontSize=11,
                                textColor=TEAL, alignment=TA_CENTER, spaceAfter=10)
    h2_s     = ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=13,
                                textColor=NAVY, spaceBefore=14, spaceAfter=6, keepWithNext=True)
    h3_s     = ParagraphStyle('H3', fontName='Helvetica-Bold', fontSize=11,
                                textColor=TEAL, spaceBefore=10, spaceAfter=4, keepWithNext=True)
    note_s   = ParagraphStyle('N',  fontName='Helvetica-Oblique', fontSize=10,
                                textColor=GREY)
    cell_s   = ParagraphStyle('C',  fontName='Helvetica', fontSize=9,
                                textColor=NAVY)
    cell_b   = ParagraphStyle('CB', fontName='Helvetica-Bold', fontSize=9,
                                textColor=NAVY)
    cell_c   = ParagraphStyle('CC', fontName='Helvetica', fontSize=9,
                                textColor=NAVY, alignment=TA_CENTER)
    cell_b_c = ParagraphStyle('CBC', fontName='Helvetica-Bold', fontSize=9,
                                textColor=NAVY, alignment=TA_CENTER)
    hdr_c    = ParagraphStyle('HC', fontName='Helvetica-Bold', fontSize=9,
                                textColor=WHITE, alignment=TA_CENTER)
    footer_s = ParagraphStyle('F',  fontName='Helvetica-Oblique', fontSize=8,
                                textColor=GREY, alignment=TA_CENTER)

    teacher_name = (f"{teacher['first_name']} {teacher['last_name']}".strip()
                    if teacher else 'N/A')

    # --- Filter to only completed sessions with engagement data ---------------
    completed_sessions = [
        s for s in sessions_list
        if s.get('status') == 'completed'
    ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elems = []

    # ── Header (with proper spacing — no overlap) ─────────────────────────────
    elems.append(Paragraph('EngageVision', title_s))
    elems.append(Paragraph(f'{period_name} Engagement Report', sub_s))
    elems.append(HRFlowable(width='100%', thickness=2, color=TEAL, spaceAfter=12))

    # ── Report Summary (exact 17cm width with full date display) ─────────────
    elems.append(Paragraph('Report Summary', h2_s))
    info = [
        ['Teacher', teacher_name, 'Period', f"{period_name} Report"],
        ['From Date', str(start_date), 'To Date', str(end_date)],
        ['Class', class_name or 'All Classes', 'Section', section_name or 'All Sections'],
        ['Total Sessions', str(len(sessions_list)), 'Completed Sessions', str(len(completed_sessions))],
    ]
    _table(elems, info, [3.5*cm, 5.0*cm, 3.5*cm, 5.0*cm], NAVY, LIGHT, WHITE)
    elems.append(Spacer(1, 0.4*cm))

    if completed_sessions:
        # ── Session Summary Table (exact 17cm width with clean alignment) ────
        elems.append(Paragraph('Sessions Overview', h2_s))
        tbl_hdr_s = ParagraphStyle('THS', fontName='Helvetica-Bold', fontSize=8,
                                   textColor=WHITE, alignment=TA_LEFT)
        tbl_hdr_c = ParagraphStyle('THC', fontName='Helvetica-Bold', fontSize=8,
                                   textColor=WHITE, alignment=TA_CENTER)
        tbl_cell_s = ParagraphStyle('TCS', fontName='Helvetica', fontSize=8,
                                    textColor=NAVY, alignment=TA_LEFT)
        tbl_cell_c = ParagraphStyle('TCC', fontName='Helvetica', fontSize=8,
                                    textColor=NAVY, alignment=TA_CENTER)

        rows = [[
            Paragraph('Class', tbl_hdr_s),
            Paragraph('Section', tbl_hdr_s),
            Paragraph('Date', tbl_hdr_c),
            Paragraph('Overall %', tbl_hdr_c),
            Paragraph('High', tbl_hdr_c),
            Paragraph('Medium', tbl_hdr_c),
            Paragraph('Low', tbl_hdr_c),
            Paragraph('Students', tbl_hdr_c),
        ]]
        for s in completed_sessions:
            overall = float(s.get('overall_percentage') or 0)
            sec_raw = (s.get('section_name') or '—').strip()
            sec_val = sec_raw.title() if sec_raw != '—' else '—'
            rows.append([
                Paragraph(s.get('class_name') or '—', tbl_cell_s),
                Paragraph(sec_val, tbl_cell_s),
                Paragraph(str(s.get('session_date') or '—'), tbl_cell_c),
                Paragraph(f"{overall:.1f}%", tbl_cell_c),
                Paragraph(str(s.get('high_count') or 0), tbl_cell_c),
                Paragraph(str(s.get('medium_count') or 0), tbl_cell_c),
                Paragraph(str(s.get('low_count') or 0), tbl_cell_c),
                Paragraph(str(s.get('total_faces') or 0), tbl_cell_c),
            ])
        from reportlab.lib import colors as _colors
        from reportlab.platypus import Table as _Table, TableStyle as _TableStyle
        t = _Table(rows,
                   colWidths=[2.7*cm, 2.7*cm, 2.4*cm, 2.2*cm,
                               1.75*cm, 1.75*cm, 1.75*cm, 1.75*cm],
                   repeatRows=1)
        t.setStyle(_TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1,-1), 8),
            ('ROWBACKGROUNDS',(0, 1), (-1,-1), [LIGHT, WHITE]),
            ('TEXTCOLOR',     (0, 1), (-1,-1), NAVY),
            ('GRID',          (0, 0), (-1,-1), 0.3, _colors.lightgrey),
            ('VALIGN',        (0, 0), (-1,-1), 'MIDDLE'),
            ('ALIGN',         (0, 0), (1, -1), 'LEFT'),
            ('ALIGN',         (2, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1,-1), 5),
            ('TOPPADDING',    (0, 0), (-1,-1), 5),
            ('LEFTPADDING',   (0, 0), (-1,-1), 4),
            ('RIGHTPADDING',  (0, 0), (-1,-1), 4),
        ]))
        elems.append(t)

        # ── Aggregate Statistics (exact 17cm width with full date display) ───
        total_faces = sum(int(s.get('total_faces') or 0) for s in completed_sessions)
        pcts = [float(s['overall_percentage'])
                for s in completed_sessions if s.get('overall_percentage')]
        avg_overall = sum(pcts) / len(pcts) if pcts else 0.0

        elems.append(Spacer(1, 0.4*cm))
        elems.append(Paragraph('Aggregate Statistics', h2_s))
        agg = [
            ['Completed Sessions', str(len(completed_sessions)),
             'Total Students Tracked', str(total_faces)],
            ['Average Engagement', f"{avg_overall:.1f}%",
             'Period', f"{start_date} to {end_date}"],
        ]
        _table(elems, agg, [4.5*cm, 3.5*cm, 4.0*cm, 5.0*cm], NAVY, LIGHT, WHITE)

        # ── Detailed Student-wise Results per Session ─────────────────────────
        _uploads_base = _os.path.abspath(
            _os.path.join(current_app.root_path, '..', 'uploads')
        )
        FACE_SIZE = 1.4 * cm

        for idx, s in enumerate(completed_sessions):
            sess_id = s.get('id')
            if not sess_id:
                continue

            # Add page break before each session detail (except first)
            if idx > 0:
                elems.append(PageBreak())

            # Session sub-header
            sess_name   = s.get('session_name') or 'Unnamed Session'
            sess_class  = s.get('class_name') or '—'
            sess_sec    = s.get('section_name') or '—'
            sess_date   = str(s.get('session_date') or '—')
            overall_pct = float(s.get('overall_percentage') or 0)

            elems.append(Paragraph(
                f'Session: {sess_name}', h2_s
            ))
            elems.append(Paragraph(
                f'{sess_class} — Section {sess_sec} — {sess_date} — '
                f'Overall: {overall_pct:.1f}%',
                h3_s
            ))

            # Get student scores for this session
            scores = get_engagement_scores_by_session(sess_id)

            if not scores:
                elems.append(Paragraph(
                    'No student-level results available for this session.',
                    note_s
                ))
                continue

            # Build student-wise table: Photo | Student ID | Score | Level | Status
            detail_rows = [[
                Paragraph('Photo', hdr_c),
                Paragraph('Student ID', hdr_c),
                Paragraph('Engagement Score', hdr_c),
                Paragraph('Level', hdr_c),
                Paragraph('Status', hdr_c),
            ]]

            for sc in scores:
                face_idx  = sc.get('face_index') or sc.get('id', '?')
                score_val = float(sc.get('score', 0))
                level     = sc.get('level', 'N/A')
                is_active = sc.get('is_active', 1)

                # Resolve face crop image
                img_cell = Paragraph('Face image<br/>unavailable', cell_c)
                rel_crop = sc.get('crop_path') or ''
                if rel_crop:
                    abs_crop = _os.path.join(
                        _uploads_base,
                        rel_crop.replace('/', _os.sep)
                    )
                    if _os.path.exists(abs_crop):
                        try:
                            img_cell = RLImage(
                                abs_crop,
                                width=FACE_SIZE,
                                height=FACE_SIZE
                            )
                        except Exception:
                            img_cell = Paragraph('—', cell_c)

                level_color = {
                    'High': '#16a34a',
                    'Medium': '#b45309',
                    'Low': '#dc2626'
                }.get(level, '#374151')

                detail_rows.append([
                    img_cell,
                    Paragraph(f'<b>Student {face_idx}</b>', cell_b_c),
                    Paragraph(f'{score_val:.1f}%', cell_c),
                    Paragraph(
                        f'<font color="{level_color}"><b>{level}</b></font>',
                        cell_b_c
                    ),
                    Paragraph(
                        'Active' if is_active else 'Inactive',
                        cell_c
                    ),
                ])

            col_ws = [2.5*cm, 3.5*cm, 3.8*cm, 3.6*cm, 3.6*cm]
            st = _Table(detail_rows, colWidths=col_ws, repeatRows=1)
            st.setStyle(_TableStyle([
                ('BACKGROUND',    (0, 0), (-1, 0), TEAL),
                ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
                ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE',      (0, 0), (-1,-1), 9),
                ('ROWBACKGROUNDS',(0, 1), (-1,-1), [LIGHT, WHITE]),
                ('GRID',          (0, 0), (-1,-1), 0.3, _colors.lightgrey),
                ('VALIGN',        (0, 0), (-1,-1), 'MIDDLE'),
                ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1,-1), 5),
                ('TOPPADDING',    (0, 0), (-1,-1), 5),
                ('LEFTPADDING',   (0, 0), (-1,-1), 4),
                ('RIGHTPADDING',  (0, 0), (-1,-1), 4),
            ]))
            elems.append(st)

    else:
        elems.append(Spacer(1, 0.4*cm))
        elems.append(Paragraph(
            f'No records found for the selected filters and date range ({start_date} to {end_date}).',
            note_s,
        ))

    # ── Footer ────────────────────────────────────────────────────────────────
    elems.append(Spacer(1, 0.5*cm))
    elems.append(HRFlowable(width='100%', thickness=0.5, color=colors.lightgrey))
    elems.append(Paragraph(
        f"EngageVision  •  Generated on {datetime.now().strftime('%d %B %Y at %I:%M %p')}",
        footer_s,
    ))

    doc.build(elems)
    buf.seek(0)
    return buf


def _table(elems, data, col_widths, navy, light, white):
    """Helper: plain info-style table (bold first and third column)."""
    from reportlab.platypus import Table as _T, TableStyle as _TS
    from reportlab.lib import colors as _c
    t = _T(data, colWidths=col_widths)
    t.setStyle(_TS([
        ('FONTNAME',    (0, 0), (-1,-1), 'Helvetica'),
        ('FONTNAME',    (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',    (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1,-1), 9),
        ('TEXTCOLOR',   (0, 0), (-1,-1), navy),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [light, white]),
        ('GRID',        (0, 0), (-1,-1), 0.3, _c.lightgrey),
        ('VALIGN',      (0, 0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING',  (0, 0), (-1,-1), 5),
        ('LEFTPADDING', (0, 0), (-1,-1), 6),
        ('RIGHTPADDING', (0, 0), (-1,-1), 6),
    ]))
    elems.append(t)


def _header_table(elems, data, col_widths, navy, teal, light, white):
    """Helper: table with a coloured header row."""
    from reportlab.platypus import Table as _T, TableStyle as _TS
    from reportlab.lib import colors as _c
    t = _T(data, colWidths=col_widths)
    t.setStyle(_TS([
        ('BACKGROUND',  (0, 0), (-1, 0), teal),
        ('TEXTCOLOR',   (0, 0), (-1, 0), white),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [light, white]),
        ('TEXTCOLOR',   (0, 1), (-1,-1), navy),
        ('GRID',        (0, 0), (-1,-1), 0.3, _c.lightgrey),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING',  (0, 0), (-1,-1), 5),
        ('LEFTPADDING', (0, 0), (-1,-1), 8),
        ('ALIGN',       (1, 1), (1, -1), 'CENTER'),
        ('ALIGN',       (2, 1), (2, -1), 'CENTER'),
        ('ALIGN',       (3, 1), (3, -1), 'CENTER'),
    ]))
    elems.append(t)


# ── Profile ───────────────────────────────────────────────────────────────────

@dashboard_bp.route('/profile', methods=['GET', 'POST'])
@teacher_required
def profile():
    uid     = session['user_id']
    teacher = get_user_by_id(uid)

    if request.method == 'POST' and request.form.get('action') == 'update_profile':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip()
        department = request.form.get('department', '').strip() or None
        phone      = request.form.get('phone', '').strip() or None

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('Valid email is required.')

        if errors:
            for err in errors:
                flash(err, 'danger')
        else:
            update_user(uid, first_name, last_name, email,
                        teacher.get('staff_id'), department, phone)
            session['full_name'] = f"{first_name} {last_name}".strip()
            flash('Profile updated successfully!', 'success')

        return redirect(url_for('dashboard.profile'))

    return render_template('teacher/profile.html', teacher=teacher)


@dashboard_bp.route('/profile/change-password', methods=['POST'])
@teacher_required
def change_password():
    uid     = session['user_id']
    teacher = get_user_by_id(uid)

    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    errors = []
    if not current_pw:
        errors.append('Current password is required.')
    elif not check_password_hash(teacher['password_hash'], current_pw):
        errors.append('Current password is incorrect.')

    if not new_pw:
        errors.append('New password is required.')
    elif len(new_pw) < 8:
        errors.append('New password must be at least 8 characters.')
    elif not re.search(r'[A-Z]', new_pw):
        errors.append('New password must contain at least one uppercase letter.')
    elif not re.search(r'[a-z]', new_pw):
        errors.append('New password must contain at least one lowercase letter.')
    elif not re.search(r'[0-9]', new_pw):
        errors.append('New password must contain at least one digit.')
    elif current_pw and check_password_hash(teacher['password_hash'], new_pw):
        errors.append('New password must be different from your current password.')

    if new_pw and new_pw != confirm_pw:
        errors.append('Passwords do not match.')

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('dashboard.profile'))

    update_user_password(uid, generate_password_hash(new_pw))
    flash('Password changed successfully.', 'success')
    return redirect(url_for('dashboard.profile'))
