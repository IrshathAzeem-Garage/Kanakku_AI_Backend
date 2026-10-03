"""
Gmail SMTP Email Delivery Service for KANAKKU AI.
Replaces WhatsApp delivery to reliably dispatch generated daily accounting PDFs
to designated business email addresses using Gmail SMTP and 16-character App Passwords.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import datetime as dt
from typing import Dict, Any, Optional, Tuple, Union
import os
import base64
import requests

from app.config import settings
from app.utils.logger import logger


def format_report_date(report_date: Union[dt.date, str, None]) -> str:
    """Formats date into DD-MM-YYYY format for subject and attachment filename."""
    if not report_date:
        return dt.date.today().strftime("%d-%m-%Y")
    if isinstance(report_date, (dt.date, dt.datetime)):
        return report_date.strftime("%d-%m-%Y")
    
    # If string like YYYY-MM-DD
    try:
        parsed = dt.datetime.strptime(str(report_date)[:10], "%Y-%m-%d").date()
        return parsed.strftime("%d-%m-%Y")
    except Exception:
        # Fallback to DD-MM-YYYY format if matching DD-MM-YYYY
        parts = str(report_date).split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return str(report_date).replace("/", "-")


def build_email_subject(shop_name: Optional[str], formatted_date: str) -> str:
    """Constructs email subject: Chellam Traders - Daily Account - DD-MM-YYYY"""
    name = (shop_name or settings.BUSINESS_NAME or "Chellam Traders").strip()
    return f"{name} - Daily Account - {formatted_date}"


def build_attachment_filename(shop_name: Optional[str], formatted_date: str) -> str:
    """Constructs attachment filename: Chellam-Traders-Daily-Account-DD-MM-YYYY.pdf"""
    name = (shop_name or settings.BUSINESS_NAME or "Chellam Traders").strip()
    hyphenated_name = "-".join(name.split())
    return f"{hyphenated_name}-Daily-Account-{formatted_date}.pdf"


def get_email_body(shop_name: Optional[str] = None) -> str:
    """Builds standard email body for daily business report."""
    name = (shop_name or settings.BUSINESS_NAME or "Chellam Traders").strip()
    return (
        f"Hello,\n\n"
        f"Today's daily account report for {name} is attached to this email.\n\n"
        f"The report contains:\n"
        f"- Total Sales\n"
        f"- Digital Payments (PP)\n"
        f"- Cash Sales\n"
        f"- Expenses\n"
        f"- Net Cash\n"
        f"- Other existing calculations already included in the PDF\n\n"
        f"Regards,\n"
        f"KANAKKU AI"
    )


def send_via_resend_api(
    pdf_bytes: bytes,
    recipient_email: str,
    subject: str,
    body_text: str,
    attachment_name: str,
    resend_api_key: Optional[str] = None,
    from_email: Optional[str] = None,
    timeout: int = 15
) -> Dict[str, Any]:
    """
    Sends daily PDF report via Resend HTTPS REST API (Port 443).
    Bypasses cloud provider SMTP firewall blocks (e.g. Render Free Tier).
    """
    api_key = (resend_api_key or getattr(settings, "RESEND_API_KEY", "") or os.getenv("RESEND_API_KEY", "")).strip()
    if not api_key:
        return {"success": False, "detail": "RESEND_API_KEY not configured"}

    sender = (from_email or getattr(settings, "RESEND_FROM_EMAIL", "") or os.getenv("RESEND_FROM_EMAIL", "KANAKKU AI <onboarding@resend.dev>")).strip()
    
    # Resend requires sending from a verified domain or 'onboarding@resend.dev'.
    # Sending FROM public domains like @gmail.com or @yahoo.com will be rejected by Resend with 403.
    if not sender or "@gmail.com" in sender.lower() or "@yahoo.com" in sender.lower() or "@outlook.com" in sender.lower():
        sender = "KANAKKU AI <onboarding@resend.dev>"

    reply_to = (getattr(settings, "GMAIL_USER", "") or os.getenv("GMAIL_USER", "")).strip()
    
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    payload = {
        "from": sender,
        "to": [recipient_email],
        "subject": subject,
        "text": body_text,
        "attachments": [
            {
                "filename": attachment_name,
                "content": encoded_pdf
            }
        ]
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=timeout
        )
        if response.status_code in (200, 201):
            data = response.json()
            logger.info(f"Daily report PDF emailed via Resend HTTPS to {recipient_email}. ID: {data.get('id')}")
            return {
                "success": True,
                "email_sent": True,
                "email_status": "sent",
                "message": "Daily account PDF generated and emailed successfully",
                "recipient": recipient_email,
                "attachment_filename": attachment_name,
                "subject": subject
            }
        else:
            err_text = response.text
            logger.warning(f"Resend HTTPS dispatch returned {response.status_code}: {err_text}")
            return {
                "success": False,
                "email_sent": False,
                "email_status": "failed",
                "message": "PDF was generated but email sending failed",
                "detail": f"Resend API error ({response.status_code}): {err_text}",
                "error_type": "RESEND_API_ERROR"
            }
    except Exception as e:
        logger.error(f"Resend HTTPS connection failed: {e}")
        return {
            "success": False,
            "email_sent": False,
            "email_status": "failed",
            "message": "PDF was generated but email sending failed",
            "detail": f"Failed to connect to Resend API: {e}",
            "error_type": "RESEND_API_ERROR"
        }


def verify_smtp_credentials(
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    gmail_user: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    timeout: int = 10
) -> Tuple[bool, str]:
    """
    Verifies Gmail SMTP authentication without sending an email.
    Safely tests credentials without logging passwords.
    """
    host = smtp_host or getattr(settings, "SMTP_HOST", "smtp.gmail.com") or os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(smtp_port or getattr(settings, "SMTP_PORT", 465) or os.getenv("SMTP_PORT", 465))
    user = (gmail_user if gmail_user is not None else (getattr(settings, "GMAIL_USER", "") or os.getenv("GMAIL_USER", ""))).strip()
    pwd = (gmail_app_password if gmail_app_password is not None else (getattr(settings, "GMAIL_APP_PASSWORD", "") or os.getenv("GMAIL_APP_PASSWORD", ""))).strip().replace(" ", "")

    if not user:
        return False, "Missing GMAIL_USER environment variable"
    if not pwd:
        return False, "Missing GMAIL_APP_PASSWORD environment variable"

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as server:
                server.login(user, pwd)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, pwd)
        return True, "SMTP Authentication Successful"
    except smtplib.SMTPAuthenticationError:
        logger.error(f"Gmail SMTP authentication failed for user: {user} (invalid app password or username)")
        return False, "Gmail authentication failed: Invalid App Password or Username"
    except Exception as e:
        logger.error(f"Gmail SMTP verification error: {type(e).__name__} - {e}")
        return False, f"SMTP connection error: {type(e).__name__}"


def send_daily_report_email(
    pdf_bytes: bytes,
    filename: Optional[str] = None,
    report_date: Optional[Union[dt.date, str]] = None,
    recipient_email: Optional[str] = None,
    sender_email: Optional[str] = None,
    app_password: Optional[str] = None,
    shop_name: Optional[str] = None,
    timeout: int = 15
) -> Dict[str, Any]:
    """
    Sends the generated daily account PDF to recipient_email via Gmail SMTP.

    Returns a standardized dictionary:
    {
        "success": bool,
        "email_sent": bool,
        "email_status": "sent" | "failed" | "not_configured",
        "message": str,
        "error_type": Optional[str],
        "detail": Optional[str],
        "recipient": Optional[str],
        "attachment_filename": Optional[str]
    }
    """
    # 1. Validate PDF bytes
    if not pdf_bytes or len(pdf_bytes) == 0:
        logger.error("Email sending aborted: pdf_bytes is empty or invalid")
        return {
            "success": False,
            "email_sent": False,
            "email_status": "failed",
            "message": "PDF was generated but email sending failed",
            "detail": "Generated PDF document was empty or unreadable",
            "error_type": "PDF_ATTACHMENT_FAILED"
        }

    # 2. Extract and sanitize environment credentials
    user = (sender_email if sender_email is not None else (getattr(settings, "GMAIL_USER", "") or os.getenv("GMAIL_USER", ""))).strip()
    pwd = (app_password if app_password is not None else (getattr(settings, "GMAIL_APP_PASSWORD", "") or os.getenv("GMAIL_APP_PASSWORD", ""))).strip().replace(" ", "")
    recipient = (recipient_email if recipient_email is not None else (getattr(settings, "REPORT_EMAIL", "") or os.getenv("REPORT_EMAIL", ""))).strip()
    smtp_host = getattr(settings, "SMTP_HOST", "smtp.gmail.com") or os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(getattr(settings, "SMTP_PORT", 465) or os.getenv("SMTP_PORT", 465))

    if not user or not pwd or not recipient:
        missing = []
        if not user:
            missing.append("GMAIL_USER")
        if not pwd:
            missing.append("GMAIL_APP_PASSWORD")
        if not recipient:
            missing.append("REPORT_EMAIL")
        msg = f"Gmail email service is not configured. Missing environment variable(s): {', '.join(missing)}"
        logger.warning(msg)
        return {
            "success": False,
            "email_sent": False,
            "email_status": "not_configured",
            "message": "PDF was generated but email sending failed",
            "detail": msg,
            "error_type": "MISSING_ENV_VARS"
        }

    # 3. Construct Subject, Filename, and Body
    formatted_date = format_report_date(report_date)
    subject = build_email_subject(shop_name, formatted_date)
    attachment_name = filename or build_attachment_filename(shop_name, formatted_date)
    body_text = get_email_body(shop_name)

    # 3b. Try Resend HTTPS API (Port 443 - Recommended for Render Free Tier)
    resend_key = (getattr(settings, "RESEND_API_KEY", "") or os.getenv("RESEND_API_KEY", "")).strip()
    if resend_key:
        logger.info(f"Attempting email delivery via Resend HTTPS (port 443) to {recipient}...")
        resend_result = send_via_resend_api(
            pdf_bytes=pdf_bytes,
            recipient_email=recipient,
            subject=subject,
            body_text=body_text,
            attachment_name=attachment_name,
            resend_api_key=resend_key
        )
        if resend_result.get("success"):
            return resend_result
        logger.warning(f"Resend HTTPS dispatch failed: {resend_result.get('detail')}. Falling back to Gmail SMTP...")

    # 4. Construct MIME Multipart Message
    msg = MIMEMultipart()
    msg["From"] = f"{shop_name or 'Chellam Traders'} <{user}>"
    msg["To"] = recipient
    msg["Subject"] = subject

    # Plain text body
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    # PDF Attachment
    try:
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment_name
        )
        msg.attach(pdf_attachment)
    except Exception as attach_err:
        logger.error(f"Failed to attach PDF to email message: {attach_err}")
        return {
            "success": False,
            "email_sent": False,
            "email_status": "failed",
            "message": "PDF was generated but email sending failed",
            "detail": "Failed to create email attachment from PDF buffer",
            "error_type": "PDF_ATTACHMENT_FAILED"
        }

    # 5. Connect and Send via SMTP with fallback (SSL 465 -> STARTTLS 587)
    try:
        if smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=timeout) as server:
                server.login(user, pwd)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, pwd)
                server.send_message(msg)

        logger.info(
            f"Daily report email successfully sent to {recipient}. "
            f"Subject: '{subject}', Attachment: '{attachment_name}', Size: {len(pdf_bytes)} bytes"
        )
        return {
            "success": True,
            "email_sent": True,
            "email_status": "sent",
            "message": "Daily account PDF generated and emailed successfully",
            "recipient": recipient,
            "attachment_filename": attachment_name,
            "subject": subject
        }

    except smtplib.SMTPAuthenticationError as auth_err:
        logger.error(f"Gmail SMTP authentication failed for {user}: (check GMAIL_APP_PASSWORD)")
        return {
            "success": False,
            "email_sent": False,
            "email_status": "failed",
            "message": "PDF was generated but email sending failed",
            "detail": "Gmail authentication failed. Please verify GMAIL_USER and GMAIL_APP_PASSWORD.",
            "error_type": "GMAIL_AUTH_FAILED"
        }

    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError) as net_err:
        # Try fallback port 587 with STARTTLS if 465 timed out or connection failed
        if smtp_port == 465:
            try:
                logger.info("Retrying email delivery via port 587 with STARTTLS...")
                with smtplib.SMTP(smtp_host, 587, timeout=timeout) as server:
                    server.ehlo()
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(user, pwd)
                    server.send_message(msg)

                logger.info(f"Daily report email successfully sent via 587 STARTTLS to {recipient}.")
                return {
                    "success": True,
                    "email_sent": True,
                    "email_status": "sent",
                    "message": "Daily account PDF generated and emailed successfully",
                    "recipient": recipient,
                    "attachment_filename": attachment_name,
                    "subject": subject
                }
            except Exception as retry_err:
                logger.error(f"Fallback STARTTLS 587 also failed: {retry_err}")

        logger.error(f"SMTP network/connection error: {net_err}")
        return {
            "success": False,
            "email_sent": False,
            "email_status": "failed",
            "message": "PDF was generated but email sending failed",
            "detail": "Failed to connect to Gmail SMTP server. Please check internet connection.",
            "error_type": "EMAIL_SENDING_FAILED"
        }

    except Exception as general_err:
        err_msg = str(general_err).lower()
        logger.error(f"Unexpected error while sending daily report email: {type(general_err).__name__} - {general_err}")
        if any(term in err_msg for term in ["network is unreachable", "connection timed out", "connection refused", "timeout", "errno 101", "errno 110"]):
            detail_msg = "Render Free Tier blocks outbound SMTP ports 465/587. Please configure RESEND_API_KEY to send emails via HTTPS port 443."
        else:
            detail_msg = "An unexpected error occurred during email dispatch."
        return {
            "success": False,
            "email_sent": False,
            "email_status": "failed",
            "message": "PDF was generated but email sending failed",
            "detail": detail_msg,
            "error_type": "EMAIL_SENDING_FAILED"
        }
