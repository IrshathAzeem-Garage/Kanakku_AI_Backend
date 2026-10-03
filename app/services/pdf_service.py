"""
PDF Generation Service for KANAKKU AI.
Generates professional, printable, mobile-friendly daily business accounting reports
strictly from confirmed PostgreSQL data using ReportLab.
"""

import io
import os
import re
import datetime as dt
from typing import Tuple, Optional
import pytz

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.record import DailyRecord
from app.models.shop import Shop
from app.models.user import User
from app.config import settings
from app.utils.logger import logger


# ============================================================================
# Font & Currency Setup
# ============================================================================

_FONT_FAMILY = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_CURRENCY_SYMBOL = "Rs. "

def _initialize_pdf_fonts():
    """Attempts to register TrueType fonts with unicode Rupee sign support."""
    global _FONT_FAMILY, _FONT_BOLD, _CURRENCY_SYMBOL
    
    candidates = [
        ("SegoeUI", "SegoeUI-Bold", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("Arial", "Arial-Bold", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("DejaVuSans", "DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("LiberationSans", "LiberationSans-Bold", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("FreeSans", "FreeSans-Bold", "/usr/share/fonts/truetype/freefont/FreeSans.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    ]
    
    for reg_name, bold_name, regular_path, bold_path in candidates:
        if os.path.exists(regular_path) and os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont(reg_name, regular_path))
                pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                _FONT_FAMILY = reg_name
                _FONT_BOLD = bold_name
                _CURRENCY_SYMBOL = "₹"
                return
            except Exception as e:
                logger.warning(f"Failed to register font {reg_name}: {e}")
                continue

_initialize_pdf_fonts()


def format_inr(amount: Optional[float], symbol: Optional[str] = None) -> str:
    """Formats numeric amount into Indian Currency representation (e.g. ₹25,500.00)."""
    if amount is None:
        amount = 0.0
    val = float(amount)
    is_neg = val < 0
    val = abs(val)
    parts = f"{val:.2f}".split(".")
    int_p, dec_p = parts[0], parts[1]
    
    if len(int_p) > 3:
        last3 = int_p[-3:]
        rem = int_p[:-3]
        groups = []
        while len(rem) > 2:
            groups.insert(0, rem[-2:])
            rem = rem[:-2]
        if rem:
            groups.insert(0, rem)
        fmt = ",".join(groups) + "," + last3
    else:
        fmt = int_p
        
    formatted = f"{fmt}.{dec_p}"
    sym = symbol if symbol is not None else _CURRENCY_SYMBOL
    return f"-{sym}{formatted}" if is_neg else f"{sym}{formatted}"


def sanitize_filename_component(text: str) -> str:
    """Sanitizes text for safe inclusion in filenames."""
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]+', '_', text.strip())
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned or "Shop"


# ============================================================================
# Two-Pass Numbered Canvas for "Page X of Y" and Running Header/Footer
# ============================================================================

class NumberedCanvas(canvas.Canvas):
    """
    Subclass of canvas.Canvas that intercepts showPage & save to compute total pages
    and stamp running footers on every page cleanly.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        
        # Color palette
        border_color = colors.HexColor("#CBD5E1")  # Slate-300
        text_color = colors.HexColor("#64748B")    # Slate-500
        
        # Margins & positions
        page_width, page_height = self._pagesize
        margin = 36  # 0.5 inch margin
        footer_y = 26
        
        # Footer dividing line
        self.setStrokeColor(border_color)
        self.setLineWidth(0.6)
        self.line(margin, footer_y + 12, page_width - margin, footer_y + 12)
        
        # Footer text
        self.setFont(_FONT_FAMILY, 8)
        self.setFillColor(text_color)
        
        # Left footer: Shop Name & System Tag
        shop_title = getattr(self, "_shop_title", "KANAKKU AI")
        self.drawString(margin, footer_y, f"KANAKKU AI • {shop_title}")
        
        # Center footer: Timestamp
        gen_timestamp = getattr(self, "_generated_str", "")
        if gen_timestamp:
            self.drawCentredString(page_width / 2.0, footer_y, f"Generated: {gen_timestamp}")
        
        # Right footer: Page X of Y
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_width - margin, footer_y, page_str)
        
        self.restoreState()


# ============================================================================
# Daily Report PDF Generator
# ============================================================================

def generate_daily_report_pdf(
    record_id: int,
    db: Session,
    shop_id: int
) -> Tuple[bytes, str]:
    """
    Generates a professional business accounting daily PDF report for a confirmed DailyRecord.
    1. Fetches record, shop, user from PostgreSQL.
    2. Strictly uses backend-calculated totals from PostgreSQL.
    3. Builds styled ReportLab PDF.
    4. Returns (pdf_bytes, filename).
    """
    record = db.query(DailyRecord).filter(
        DailyRecord.id == record_id,
        DailyRecord.shop_id == shop_id
    ).first()
    
    if not record:
        raise HTTPException(
            status_code=404,
            detail="Daily record not found or access denied for this shop"
        )
        
    shop = db.query(Shop).filter(Shop.id == record.shop_id).first()
    user = db.query(User).filter(User.id == record.user_id).first()
    
    shop_name = shop.name if shop and shop.name else settings.BUSINESS_NAME
    user_name = user.fullname if user and user.fullname else "Business Owner"
    
    # Timezone handling for Kolkata
    kolkata_tz = pytz.timezone(settings.APP_TIMEZONE)
    now_kolkata = dt.datetime.now(kolkata_tz)
    generated_on_str = now_kolkata.strftime("%d %b %Y, %I:%M %p IST")
    
    # Format report date
    rec_date = record.record_date
    if isinstance(rec_date, dt.date):
        report_date_str = rec_date.strftime("%d %B %Y")
        file_date_str = rec_date.strftime("%Y-%m-%d")
    else:
        report_date_str = str(rec_date)
        file_date_str = str(rec_date)
        
    sanitized_shop = sanitize_filename_component(shop_name)
    dynamic_filename = f"{sanitized_shop}_Daily_Report_{file_date_str}.pdf"

    # Setup Document Buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=46
    )
    
    usable_width = doc.width  # approx 523.27 pt on A4
    
    # Styles
    base_styles = getSampleStyleSheet()
    
    # Custom Palette
    c_primary = colors.HexColor("#0F172A")    # Slate 900
    c_secondary = colors.HexColor("#334155")  # Slate 700
    c_muted = colors.HexColor("#64748B")      # Slate 500
    c_border = colors.HexColor("#E2E8F0")     # Slate 200
    c_dark_border = colors.HexColor("#94A3B8")# Slate 400
    c_bg_subtle = colors.HexColor("#F8FAFC")  # Slate 50
    c_bg_highlight = colors.HexColor("#F1F5F9") # Slate 100
    c_accent_green = colors.HexColor("#059669")# Emerald 600
    c_text_green = colors.HexColor("#065F46")  # Emerald 800
    c_bg_green = colors.HexColor("#ECFDF5")    # Emerald 50
    
    style_shop_title = ParagraphStyle(
        'ShopTitle',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=18,
        leading=22,
        alignment=1, # Center
        textColor=c_primary
    )
    
    style_report_title = ParagraphStyle(
        'ReportTitle',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=12,
        leading=16,
        alignment=1,
        textColor=c_secondary
    )
    
    style_contact_line = ParagraphStyle(
        'ContactLine',
        parent=base_styles['Normal'],
        fontName=_FONT_FAMILY,
        fontSize=8.5,
        leading=12,
        alignment=1,
        textColor=c_muted
    )
    
    style_section_heading = ParagraphStyle(
        'SectionHeading',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=10,
        leading=14,
        textColor=c_primary,
        spaceAfter=4
    )
    
    style_meta_label = ParagraphStyle(
        'MetaLabel',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=8.5,
        leading=12,
        textColor=c_secondary
    )
    
    style_meta_value = ParagraphStyle(
        'MetaValue',
        parent=base_styles['Normal'],
        fontName=_FONT_FAMILY,
        fontSize=8.5,
        leading=12,
        textColor=c_primary
    )
    
    style_cell_left = ParagraphStyle(
        'CellLeft',
        parent=base_styles['Normal'],
        fontName=_FONT_FAMILY,
        fontSize=8.5,
        leading=11,
        textColor=c_primary
    )
    
    style_cell_center = ParagraphStyle(
        'CellCenter',
        parent=base_styles['Normal'],
        fontName=_FONT_FAMILY,
        fontSize=8.5,
        leading=11,
        alignment=1,
        textColor=c_primary
    )
    
    style_cell_right = ParagraphStyle(
        'CellRight',
        parent=base_styles['Normal'],
        fontName=_FONT_FAMILY,
        fontSize=8.5,
        leading=11,
        alignment=2, # Right
        textColor=c_primary
    )
    
    style_th_left = ParagraphStyle(
        'THLeft',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=8.5,
        leading=11,
        textColor=c_secondary
    )
    
    style_th_center = ParagraphStyle(
        'THCenter',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=8.5,
        leading=11,
        alignment=1,
        textColor=c_secondary
    )
    
    style_th_right = ParagraphStyle(
        'THRight',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=c_secondary
    )
    
    style_tot_label = ParagraphStyle(
        'TotLabel',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=9,
        leading=12,
        textColor=c_primary
    )
    
    style_tot_val = ParagraphStyle(
        'TotVal',
        parent=base_styles['Normal'],
        fontName=_FONT_BOLD,
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=c_primary
    )

    style_note_text = ParagraphStyle(
        'NoteText',
        parent=base_styles['Normal'],
        fontName=_FONT_FAMILY,
        fontSize=7.5,
        leading=11,
        textColor=c_muted
    )

    elements = []

    # ------------------------------------------------------------------------
    # 1. Header Box
    # ------------------------------------------------------------------------
    contact_parts = []
    if shop and shop.phone:
        contact_parts.append(f"Phone: {shop.phone}")
    if shop and shop.email:
        contact_parts.append(f"Email: {shop.email}")
    if shop and shop.address:
        contact_parts.append(f"Address: {shop.address}")
    contact_str = "   •   ".join(contact_parts)

    header_table_data = [
        [Paragraph(shop_name.upper(), style_shop_title)],
        [Paragraph("DAILY BUSINESS REPORT", style_report_title)],
    ]
    if contact_str:
        header_table_data.append([Paragraph(contact_str, style_contact_line)])

    header_table = Table(header_table_data, colWidths=[usable_width])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1, color=c_dark_border, spaceAfter=8, spaceBefore=2))

    # ------------------------------------------------------------------------
    # 2. Meta Information Card
    # ------------------------------------------------------------------------
    meta_data = [
        [
            Paragraph("<b>Report Date:</b>", style_meta_label),
            Paragraph(report_date_str, style_meta_value),
            Paragraph("<b>Prepared For:</b>", style_meta_label),
            Paragraph(user_name, style_meta_value),
        ],
        [
            Paragraph("<b>Generated On:</b>", style_meta_label),
            Paragraph(generated_on_str, style_meta_value),
            Paragraph("<b>Shop Currency:</b>", style_meta_label),
            Paragraph(shop.currency if shop and shop.currency else "INR", style_meta_value),
        ]
    ]
    col_w_meta = [usable_width * 0.18, usable_width * 0.32, usable_width * 0.18, usable_width * 0.32]
    meta_table = Table(meta_data, colWidths=col_w_meta)
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_subtle),
        ('BOX', (0, 0), (-1, -1), 0.75, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # ------------------------------------------------------------------------
    # 3. Executive Summary (Backend Calculated Source of Truth)
    # ------------------------------------------------------------------------
    elements.append(Paragraph("EXECUTIVE SUMMARY", style_section_heading))
    
    t_cust = float(record.total_customer_money or 0.0)
    t_dig = float(record.total_digital_money or 0.0)
    t_cash_rec = float(record.total_cash_received or 0.0)
    t_exp = float(record.total_expenses or 0.0)
    t_own = float(record.total_own_money or 0.0)
    t_cash_box = float(record.total_cash_box_expenses or 0.0)
    in_hand = float(record.in_hand_money or 0.0)

    summary_grid_data = [
        [
            Paragraph("<b>CUSTOMER MONEY</b>", style_th_left),
            Paragraph(format_inr(t_cust), style_tot_val),
            Paragraph("<b>DIGITAL RECEIVED</b>", style_th_left),
            Paragraph(format_inr(t_dig), style_tot_val),
        ],
        [
            Paragraph("<b>CASH RECEIVED</b>", style_th_left),
            Paragraph(format_inr(t_cash_rec), style_tot_val),
            Paragraph("<b>TOTAL EXPENSES</b>", style_th_left),
            Paragraph(format_inr(t_exp), style_tot_val),
        ],
        [
            Paragraph("<b>OWN MONEY</b>", style_th_left),
            Paragraph(format_inr(t_own), style_tot_val),
            Paragraph("<b>CASH BOX EXPENSES</b>", style_th_left),
            Paragraph(format_inr(t_cash_box), style_tot_val),
        ]
    ]
    w_sum = [usable_width * 0.28, usable_width * 0.22, usable_width * 0.28, usable_width * 0.22]
    sum_table = Table(summary_grid_data, colWidths=w_sum)
    sum_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_subtle),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(sum_table)
    elements.append(Spacer(1, 6))

    # Prominent In-Hand Money Highlight Card
    in_hand_data = [
        [
            Paragraph("<font size=10><b>NET CASH BALANCE IN-HAND</b></font>", ParagraphStyle(
                'InHandL', parent=base_styles['Normal'], fontName=_FONT_BOLD, textColor=c_text_green
            )),
            Paragraph(f"<font size=14><b>{format_inr(in_hand)}</b></font>", ParagraphStyle(
                'InHandV', parent=base_styles['Normal'], fontName=_FONT_BOLD, alignment=2, textColor=c_text_green
            ))
        ]
    ]
    in_hand_table = Table(in_hand_data, colWidths=[usable_width * 0.6, usable_width * 0.4])
    in_hand_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_green),
        ('BOX', (0, 0), (-1, -1), 1.2, c_accent_green),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(in_hand_table)
    elements.append(Spacer(1, 14))

    # ------------------------------------------------------------------------
    # 4. Customer Money Received Table
    # ------------------------------------------------------------------------
    elements.append(Paragraph("CUSTOMER MONEY RECEIVED", style_section_heading))
    cust_rows = [
        [
            Paragraph("No.", style_th_center),
            Paragraph("Reference / Note", style_th_left),
            Paragraph("Amount", style_th_right)
        ]
    ]
    
    receipts = record.customer_receipts or []
    if receipts:
        for idx, rec in enumerate(receipts, start=1):
            ref = rec.description or rec.source_reference or rec.raw_text or "Customer"
            cust_rows.append([
                Paragraph(str(idx), style_cell_center),
                Paragraph(ref, style_cell_left),
                Paragraph(format_inr(rec.amount), style_cell_right)
            ])
    else:
        cust_rows.append([
            Paragraph("1", style_cell_center),
            Paragraph("Customer", style_cell_left),
            Paragraph(format_inr(t_cust), style_cell_right)
        ])

    # Total row
    cust_rows.append([
        Paragraph("", style_tot_label),
        Paragraph("<b>Total Customer Money</b>", style_tot_label),
        Paragraph(f"<b>{format_inr(t_cust)}</b>", style_tot_val)
    ])

    w_cust = [40, usable_width - 160, 120]
    cust_table = Table(cust_rows, colWidths=w_cust, repeatRows=1)
    cust_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_highlight),
        ('BACKGROUND', (0, -1), (-1, -1), c_bg_subtle),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(cust_table)
    elements.append(Spacer(1, 14))

    # ------------------------------------------------------------------------
    # 5. Digital Payments Section
    # ------------------------------------------------------------------------
    elements.append(Paragraph("DIGITAL PAYMENTS", style_section_heading))
    dig_rows = [
        [
            Paragraph("No.", style_th_center),
            Paragraph("Reference / Method", style_th_left),
            Paragraph("Amount", style_th_right)
        ]
    ]

    digital_entries = record.digital_entries or []
    if digital_entries:
        for idx, entry in enumerate(digital_entries, start=1):
            ref = entry.raw_text or "Digital Payment"
            dig_rows.append([
                Paragraph(str(idx), style_cell_center),
                Paragraph(ref, style_cell_left),
                Paragraph(format_inr(entry.amount), style_cell_right)
            ])
    else:
        dig_rows.append([
            Paragraph("-", style_cell_center),
            Paragraph("None recorded", style_cell_left),
            Paragraph(format_inr(0.0), style_cell_right)
        ])

    dig_rows.append([
        Paragraph("", style_tot_label),
        Paragraph("<b>Total Digital Received</b>", style_tot_label),
        Paragraph(f"<b>{format_inr(t_dig)}</b>", style_tot_val)
    ])

    dig_table = Table(dig_rows, colWidths=w_cust, repeatRows=1)
    dig_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_highlight),
        ('BACKGROUND', (0, -1), (-1, -1), c_bg_subtle),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(dig_table)
    elements.append(Spacer(1, 14))

    # ------------------------------------------------------------------------
    # 6. Expenses Section
    # ------------------------------------------------------------------------
    elements.append(Paragraph("EXPENSES", style_section_heading))
    exp_rows = [
        [
            Paragraph("No.", style_th_center),
            Paragraph("Description", style_th_left),
            Paragraph("Total Amount", style_th_right),
            Paragraph("Own Money", style_th_right),
            Paragraph("Cash Box", style_th_right),
        ]
    ]

    expenses = record.expenses or []
    if expenses:
        for idx, exp in enumerate(expenses, start=1):
            desc = exp.description or exp.raw_text or "Expense"
            exp_rows.append([
                Paragraph(str(idx), style_cell_center),
                Paragraph(desc, style_cell_left),
                Paragraph(format_inr(exp.total_amount), style_cell_right),
                Paragraph(format_inr(exp.own_amount), style_cell_right),
                Paragraph(format_inr(exp.cash_box_amount), style_cell_right),
            ])
    else:
        exp_rows.append([
            Paragraph("-", style_cell_center),
            Paragraph("No expenses recorded", style_cell_left),
            Paragraph(format_inr(0.0), style_cell_right),
            Paragraph(format_inr(0.0), style_cell_right),
            Paragraph(format_inr(0.0), style_cell_right),
        ])

    exp_rows.append([
        Paragraph("", style_tot_label),
        Paragraph("<b>Total Expenses</b>", style_tot_label),
        Paragraph(f"<b>{format_inr(t_exp)}</b>", style_tot_val),
        Paragraph(f"<b>{format_inr(t_own)}</b>", style_tot_val),
        Paragraph(f"<b>{format_inr(t_cash_box)}</b>", style_tot_val),
    ])

    w_exp = [35, usable_width - 325, 95, 95, 100]
    exp_table = Table(exp_rows, colWidths=w_exp, repeatRows=1)
    exp_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_highlight),
        ('BACKGROUND', (0, -1), (-1, -1), c_bg_subtle),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(exp_table)
    elements.append(Spacer(1, 14))

    # ------------------------------------------------------------------------
    # 7. Cash Flow Summary & Important Note (Kept together if possible)
    # ------------------------------------------------------------------------
    closing_elements = []
    closing_elements.append(Paragraph("CASH FLOW SUMMARY", style_section_heading))

    cf_rows = [
        [Paragraph("Customer Money (Total Received)", style_cell_left), Paragraph(format_inr(t_cust), style_cell_right)],
        [Paragraph("Less: Digital Received", style_cell_left), Paragraph(format_inr(-t_dig), style_cell_right)],
        [Paragraph("<b>Cash Received</b>", style_tot_label), Paragraph(f"<b>{format_inr(t_cash_rec)}</b>", style_tot_val)],
        [Paragraph("Less: Cash Box Expenses", style_cell_left), Paragraph(format_inr(-t_cash_box), style_cell_right)],
        [Paragraph("<font size=10><b>IN-HAND MONEY (Final Balance)</b></font>", ParagraphStyle('CFInHandL', parent=style_tot_label, textColor=c_text_green)),
         Paragraph(f"<font size=11><b>{format_inr(in_hand)}</b></font>", ParagraphStyle('CFInHandV', parent=style_tot_val, textColor=c_text_green))],
    ]
    w_cf = [usable_width * 0.65, usable_width * 0.35]
    cf_table = Table(cf_rows, colWidths=w_cf)
    cf_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 2), (-1, 2), c_bg_subtle),
        ('BACKGROUND', (0, 4), (-1, 4), c_bg_green),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    closing_elements.append(cf_table)
    closing_elements.append(Spacer(1, 10))

    # Accounting Note
    note_box_data = [
        [
            Paragraph(
                "<b>Accounting Note:</b><br/>"
                "• Digital payments are already included in Total Customer Money.<br/>"
                "• Only expenses paid from the <b>Cash Box</b> are deducted from In-Hand Money.<br/>"
                "• Expenses paid using <b>Own Money</b> do not reduce the shop's physical cash balance.",
                style_note_text
            )
        ]
    ]
    note_table = Table(note_box_data, colWidths=[usable_width])
    note_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_subtle),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    closing_elements.append(note_table)

    elements.append(KeepTogether(closing_elements))

    # ------------------------------------------------------------------------
    # Build Document with NumberedCanvas
    # ------------------------------------------------------------------------
    def canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c._shop_title = shop_name
        c._generated_str = generated_on_str
        return c

    doc.build(elements, canvasmaker=canvas_factory)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(
        f"Generated Daily Report PDF for record_id={record_id}, shop_id={shop_id}, "
        f"size_bytes={len(pdf_bytes)}, filename={dynamic_filename}"
    )

    return pdf_bytes, dynamic_filename
