"""
Reports Blueprint Routes — EngageVision
Teacher sees only own reports; Admin sees all.
"""

import json
import os
import io
from datetime import datetime

from flask import (
    render_template, redirect, url_for, session,
    flash, current_app, send_file, request, Blueprint
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from app.decorators import teacher_required, login_required
from app.models import (
    get_sessions_by_teacher,
    get_session_by_id,
    get_report_by_session,
    get_classes_for_teacher,
    get_user_by_id,
)

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@teacher_required
def index():
    uid     = session['user_id']
    # Filters
    class_id    = request.args.get('class_id', type=int)
    section_id  = request.args.get('section_id', type=int)
    date_filter = request.args.get('date', '') or None

    sessions_list = get_sessions_by_teacher(
        uid,
        class_id    = class_id,
        section_id  = section_id,
        date_filter = date_filter
    )
    teacher_classes = get_classes_for_teacher(uid)

    return render_template(
        'reports/index.html',
        sessions=sessions_list,
        teacher_classes=teacher_classes,
        filters={
            'class_id':  class_id or '',
            'section_id': section_id or '',
            'date': date_filter or '',
        }
    )


@reports_bp.route('/<int:session_id>')
@login_required
def detail(session_id: int):
    uid        = session['user_id']
    role       = session.get('role')
    db_session = get_session_by_id(session_id)

    # Admin can view any session; teacher can only view their own
    if not db_session or (role != 'admin' and db_session['teacher_id'] != uid):
        flash('Report not found.', 'danger')
        return redirect(url_for('reports.index'))

    report    = get_report_by_session(session_id)
    face_data = []
    if report and report['face_data']:
        face_data = (json.loads(report['face_data'])
                     if isinstance(report['face_data'], str)
                     else report['face_data'])

    return render_template(
        'reports/detail.html',
        db_session=db_session,
        report=report,
        face_data=face_data,
    )


@reports_bp.route('/<int:session_id>/download')
@login_required
def download(session_id: int):
    """Generate and download a PDF engagement report."""
    uid        = session['user_id']
    role       = session.get('role')
    db_session = get_session_by_id(session_id)

    # Admin can download any session; teacher can only download their own
    if not db_session or (role != 'admin' and db_session['teacher_id'] != uid):
        flash('Report not found.', 'danger')
        return redirect(url_for('reports.index'))

    report    = get_report_by_session(session_id)
    face_data = []
    if report and report['face_data']:
        face_data = (json.loads(report['face_data'])
                     if isinstance(report['face_data'], str)
                     else report['face_data'])

    # For PDF: use session's teacher, not the logged-in admin
    teacher  = get_user_by_id(db_session['teacher_id']) if db_session.get('teacher_id') else None
    pdf_buf  = _build_pdf(db_session, report, face_data, teacher)
    filename = f"EngageVision_Report_{db_session.get('class_name','')}_" \
               f"{db_session.get('section_name','')}_{session_id}.pdf"

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf',
    )


# ─── PDF Generator ───────────────────────────────────────────────────────────

def _build_pdf(db_session: dict, report: dict, face_data: list, teacher: dict) -> io.BytesIO:
    """Build a professional EngageVision PDF report."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm,   bottomMargin=2*cm,
        title=f"EngageVision Engagement Report — Session {db_session['id']}",
    )

    # ── Color Palette ─────────────────────────────────────────────────────────
    NAVY    = colors.HexColor('#0f2342')
    BLUE    = colors.HexColor('#1e3a5f')
    TEAL    = colors.HexColor('#0e7490')
    GREEN   = colors.HexColor('#16a34a')
    AMBER   = colors.HexColor('#d97706')
    RED     = colors.HexColor('#dc2626')
    LIGHT   = colors.HexColor('#f0f7ff')
    WHITE   = colors.white
    GREY    = colors.HexColor('#64748b')

    # ── Styles ────────────────────────────────────────────────────────────────
    title_style   = ParagraphStyle('Title',   fontName='Helvetica-Bold',    fontSize=22,
                                   textColor=NAVY,  alignment=TA_CENTER, spaceAfter=6)
    sub_style     = ParagraphStyle('Sub',     fontName='Helvetica',         fontSize=11,
                                   textColor=TEAL,  alignment=TA_CENTER, spaceAfter=10)
    tagline_style = ParagraphStyle('Tag',     fontName='Helvetica-Oblique', fontSize=9,
                                   textColor=GREY,  alignment=TA_CENTER, spaceAfter=14)
    h2_style      = ParagraphStyle('H2',      fontName='Helvetica-Bold',    fontSize=13,
                                   textColor=BLUE,  spaceBefore=12, spaceAfter=6)
    body_style    = ParagraphStyle('Body',    fontName='Helvetica',         fontSize=10,
                                   textColor=NAVY,  leading=14)
    face_label    = ParagraphStyle('FaceLabel', fontName='Helvetica-Bold',  fontSize=9,
                                   textColor=NAVY,  alignment=TA_CENTER)
    footer_style  = ParagraphStyle('Footer',  fontName='Helvetica-Oblique', fontSize=8,
                                   textColor=GREY,  alignment=TA_CENTER, spaceBefore=4)

    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements.append(Paragraph("EngageVision", title_style))
    elements.append(Paragraph("AI-Based Student Engagement Monitoring System", sub_style))
    elements.append(Paragraph("Using Computer Vision · YOLOv8 + MediaPipe", tagline_style))
    elements.append(HRFlowable(width="100%", thickness=3, color=TEAL, spaceAfter=14))

    # ── Session Info ──────────────────────────────────────────────────────────
    elements.append(Paragraph("Session Details", h2_style))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8))

    created_at = db_session.get('created_at')
    date_str   = created_at.strftime('%d %B %Y')  if created_at else 'N/A'
    time_str   = created_at.strftime('%I:%M %p')  if created_at else 'N/A'
    duration   = db_session.get('duration_seconds', 0) or 0
    dur_str    = f"{duration // 60}m {duration % 60}s" if duration else 'N/A'
    teacher_nm = (f"{teacher['first_name']} {teacher['last_name']}".strip()
                  if teacher else 'N/A')

    info_data = [
        ['Session Name',  db_session.get('session_name','N/A'),    'Date',     date_str],
        ['Teacher',       teacher_nm,                               'Time',     time_str],
        ['Class',         db_session.get('class_name','N/A'),       'Duration', dur_str],
        ['Section',       db_session.get('section_name','N/A'),     'Status',   db_session.get('status','').title()],
        ['Session Date',  str(db_session.get('session_date') or 'N/A'), 'Session ID', str(db_session['id'])],
    ]
    info_table = Table(info_data, colWidths=[3.5*cm, 7*cm, 2.5*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME',   (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME',   (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',   (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,-1), 9),
        ('TEXTCOLOR',  (0,0), (-1,-1), NAVY),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [LIGHT, WHITE]),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.3, colors.lightgrey),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*cm))

    # ── Engagement Summary ────────────────────────────────────────────────────
    elements.append(Paragraph("Engagement Summary", h2_style))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8))

    if report:
        overall   = float(report.get('overall_percentage', 0))
        total_f   = int(report.get('total_faces', 0))
        active_c  = int(report.get('active_count', 0))
        inactive_c= int(report.get('inactive_count', 0))
        high_c    = int(report.get('high_count', 0))
        medium_c  = int(report.get('medium_count', 0))
        low_c     = int(report.get('low_count', 0))
        high_pct  = float(report.get('high_percentage', 0))
        med_pct   = float(report.get('medium_percentage', 0))
        low_pct   = float(report.get('low_percentage', 0))
    else:
        overall = total_f = active_c = inactive_c = 0
        high_c = medium_c = low_c = 0
        high_pct = med_pct = low_pct = 0.0

    summary_data = [
        ['Metric',                      'Value',         'Metric',               'Value'],
        ['Overall Engagement',          f"{overall:.1f}%", 'Total Faces Detected', str(total_f)],
        ['Active Students',             str(active_c),   'Inactive Students',    str(inactive_c)],
        ['High Engagement Students',    str(high_c),     'High Engagement %',    f"{high_pct:.1f}%"],
        ['Medium Engagement Students',  str(medium_c),   'Medium Engagement %',  f"{med_pct:.1f}%"],
        ['Low Engagement Students',     str(low_c),      'Low Engagement %',     f"{low_pct:.1f}%"],
    ]
    sum_table = Table(summary_data, colWidths=[5*cm, 3.5*cm, 5*cm, 3.5*cm])
    sum_table.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0), BLUE),
        ('TEXTCOLOR',   (0,0), (-1,0), WHITE),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [LIGHT, WHITE]),
        ('TEXTCOLOR',   (0,1), (-1,-1), NAVY),
        ('FONTNAME',    (0,1), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',    (2,1), (2,-1), 'Helvetica-Bold'),
        ('ALIGN',       (1,0), (1,-1), 'CENTER'),
        ('ALIGN',       (3,0), (3,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.3, colors.lightgrey),
    ]))
    elements.append(sum_table)
    elements.append(Spacer(1, 0.6*cm))

    # ── Per-Face Results ──────────────────────────────────────────────────────
    if face_data:
        elements.append(Paragraph("Individual Face Engagement Analysis", h2_style))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8))

        ROW_SIZE = 4
        for row_start in range(0, len(face_data), ROW_SIZE):
            row_faces = face_data[row_start:row_start + ROW_SIZE]
            img_cells  = []
            info_cells = []

            for fd in row_faces:
                score    = fd.get('engagement_score', 0)
                status   = fd.get('status', 'N/A')
                fid      = fd.get('face_id', '?')
                is_active= fd.get('is_active', True)
                crop     = fd.get('crop_path', '')

                badge_color = GREEN if status == 'High' else (AMBER if status == 'Medium' else RED)
                act_label   = 'Active' if is_active else 'Inactive'
                act_color   = GREEN if is_active else RED

                crop_abs = None
                if crop:
                    base      = current_app.config['BASE_DIR']
                    candidate = os.path.join(base, crop.lstrip('/').replace('/', os.sep))
                    if os.path.isfile(candidate):
                        crop_abs = candidate

                if crop_abs:
                    try:
                        img_cells.append(RLImage(crop_abs, width=3.2*cm, height=3.2*cm))
                    except Exception:
                        img_cells.append(Paragraph(f"[Face {fid}]", face_label))
                else:
                    img_cells.append(Paragraph(f"[Face {fid}]", face_label))

                info_cells.append(Paragraph(
                    f"<b>Face {fid}</b><br/>"
                    f"Score: <b>{score}%</b><br/>"
                    f"<font color='#{_hex(badge_color)}'><b>{status}</b></font><br/>"
                    f"<font color='#{_hex(act_color)}'>{act_label}</font>",
                    face_label
                ))

            while len(img_cells)  < ROW_SIZE: img_cells.append(Paragraph('', face_label))
            while len(info_cells) < ROW_SIZE: info_cells.append(Paragraph('', face_label))

            col_w = [4*cm] * ROW_SIZE
            ftable = Table([img_cells, info_cells], colWidths=col_w)
            ftable.setStyle(TableStyle([
                ('ALIGN',   (0,0), (-1,-1), 'CENTER'),
                ('VALIGN',  (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING',    (0,0), (-1,-1), 6),
                ('GRID', (0,0), (-1,-1), 0.3, colors.lightgrey),
            ]))
            elements.append(KeepTogether(ftable))
            elements.append(Spacer(1, 0.3*cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    elements.append(Paragraph(
        "<i>Note: Face Recognition is a future enhancement. Current system analyzes "
        "engagement without individual identification using YOLOv8 + MediaPipe FaceMesh.</i>",
        footer_style
    ))
    elements.append(Paragraph(
        f"EngageVision • AI-Based Student Engagement Monitoring System  •  "
        f"Generated on {datetime.now().strftime('%d %B %Y at %I:%M %p')}",
        footer_style
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _hex(color):
    """Extract hex string from ReportLab color object."""
    try:
        hx = color.hexval()
        return hx[1:] if hx.startswith('#') else hx
    except Exception:
        return '000000'
