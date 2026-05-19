"""
DRIVEWISE — FAT Report PDF Generator
Generates a Factory Acceptance Test report from test results.
"""
import os
import time
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                     TableStyle, PageBreak, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def generate_fat_report(test_summary, output_path=None):
    """Generate a PDF Factory Acceptance Test report."""
    if not HAS_REPORTLAB:
        print("[WARN] reportlab not installed — cannot generate PDF")
        return None

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), '..', 'FAT_Report.pdf')

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm,
                            leftMargin=20*mm, rightMargin=20*mm)

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
        fontSize=24, spaceAfter=5*mm, textColor=colors.HexColor('#1A1A3E'))
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
        fontSize=12, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=10*mm)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#1A1A3E'), spaceBefore=8*mm, spaceAfter=4*mm)
    body_style = ParagraphStyle('CustomBody', parent=styles['Normal'],
        fontSize=10, leading=14)
    small_style = ParagraphStyle('Small', parent=styles['Normal'],
        fontSize=8, textColor=colors.grey)

    elements = []
    now = datetime.now()

    # === Cover Page ===
    elements.append(Spacer(1, 30*mm))
    elements.append(Paragraph('DRIVEWISE', title_style))
    elements.append(Paragraph('Factory Acceptance Test Report', subtitle_style))
    elements.append(Spacer(1, 10*mm))

    cover_data = [
        ['Project', 'DRIVEWISE Multi-Drive Industrial Simulator'],
        ['Equipment', 'ABB ACS880 Coordinated Conveyor System (3 sections)'],
        ['Document', 'FAT-001 Rev A'],
        ['Date', now.strftime('%d %B %Y, %H:%M')],
        ['Operator', 'ENGINEER'],
        ['Test Standard', 'IEC 61131-3, IEC 60255, ISA-18.2'],
    ]
    cover_table = Table(cover_data, colWidths=[40*mm, 120*mm])
    cover_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(cover_table)
    elements.append(Spacer(1, 15*mm))

    # Overall result
    total = test_summary.get('total', 0)
    passed = test_summary.get('passed', 0)
    failed = test_summary.get('failed', 0)
    overall = 'PASS' if failed == 0 and total > 0 else 'FAIL'
    result_color = colors.HexColor('#4ADE80') if overall == 'PASS' else colors.HexColor('#FF3B30')

    result_style = ParagraphStyle('Result', parent=styles['Title'],
        fontSize=36, textColor=result_color, alignment=TA_CENTER)
    elements.append(Paragraph(f'Overall Result: {overall}', result_style))
    elements.append(Paragraph(f'{passed}/{total} tests passed', subtitle_style))

    elements.append(PageBreak())

    # === Executive Summary ===
    elements.append(Paragraph('1. Executive Summary', heading_style))
    elements.append(Paragraph(
        f'This report documents the Factory Acceptance Testing (FAT) of the DRIVEWISE '
        f'multi-drive coordinated conveyor simulation platform. A total of {total} test cases '
        f'were executed covering startup, emergency stop, master-follower synchronisation, '
        f'thermal protection, power quality, and fault cascade scenarios. '
        f'{passed} of {total} tests passed successfully.',
        body_style
    ))
    elements.append(Spacer(1, 5*mm))

    # Summary table
    summary_data = [['Test ID', 'Name', 'Duration', 'Assertions', 'Result']]
    for test in test_summary.get('tests', []):
        status = test.get('status', 'pending').upper()
        color = '#4ADE80' if status == 'PASS' else '#FF3B30' if status == 'FAIL' else '#8B8BA3'
        summary_data.append([
            test['testId'],
            test['name'],
            f"{test.get('duration', 0):.1f}s",
            f"{test.get('passedAssertions', 0)}/{test.get('totalAssertions', 0)}",
            status,
        ])

    summary_table = Table(summary_data, colWidths=[18*mm, 70*mm, 20*mm, 25*mm, 20*mm])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A1A3E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5FA')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(summary_table)

    # === Detailed Test Results ===
    elements.append(PageBreak())
    elements.append(Paragraph('2. Detailed Test Results', heading_style))

    for idx, test in enumerate(test_summary.get('tests', [])):
        elements.append(Paragraph(
            f"2.{idx+1} {test['testId']}: {test['name']}", heading_style))
        elements.append(Paragraph(test.get('description', ''), body_style))
        elements.append(Spacer(1, 3*mm))

        # Assertions table
        assertion_data = [['#', 'Assertion', 'Expected', 'Actual', 'Result']]
        for i, result in enumerate(test.get('results', [])):
            status = 'PASS' if result['passed'] else 'FAIL'
            assertion_data.append([
                str(i + 1),
                result.get('assertion', ''),
                str(result.get('expected', '')),
                str(result.get('actual', '')),
                status,
            ])

        if len(assertion_data) > 1:
            a_table = Table(assertion_data, colWidths=[8*mm, 55*mm, 35*mm, 30*mm, 15*mm])
            a_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2A2A5E')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(a_table)

        # Execution log
        elements.append(Spacer(1, 3*mm))
        elements.append(Paragraph('Execution Log:', ParagraphStyle('LogHeader',
            parent=body_style, fontSize=9, fontName='Helvetica-Bold')))
        for entry in test.get('log', []):
            level = entry.get('type', 'info')
            color = '#4ADE80' if level == 'pass' else '#FF3B30' if level == 'fail' else '#6B6B83'
            elements.append(Paragraph(
                f"<font color='{color}'>{entry['time']}  {entry['message']}</font>",
                ParagraphStyle('LogEntry', parent=small_style, fontSize=7, leading=10,
                    fontName='Courier')
            ))

        elements.append(Spacer(1, 5*mm))
        elements.append(HRFlowable(width='100%', thickness=0.5, color=colors.lightgrey))

    # === Sign-off ===
    elements.append(PageBreak())
    elements.append(Paragraph('3. Sign-Off', heading_style))
    signoff_data = [
        ['Role', 'Name', 'Signature', 'Date'],
        ['Test Engineer', '', '', ''],
        ['Project Manager', '', '', ''],
        ['Customer Rep', '', '', ''],
    ]
    signoff_table = Table(signoff_data, colWidths=[35*mm, 45*mm, 45*mm, 30*mm])
    signoff_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A1A3E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(signoff_table)

    # Build PDF
    doc.build(elements)
    print(f"[PDF] FAT report generated: {output_path}")
    return output_path
