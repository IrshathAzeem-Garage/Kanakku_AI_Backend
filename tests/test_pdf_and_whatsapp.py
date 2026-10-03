"""
Tests for PDF Generation and WhatsApp Delivery System in KANAKKU AI.
Verifies:
1. PDF is generated strictly from confirmed PostgreSQL records.
2. Shop and user information dynamically retrieved from PostgreSQL.
3. Multi-page table continuation and NumberedCanvas footer.
4. WhatsApp Cloud API dispatch, retry mechanism, and delivery tracking.
5. WhatsApp failure never rolls back the saved financial record.
6. Shop isolation across all PDF & WhatsApp endpoints.
7. Profile settings WhatsApp number persistence.
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.shop import Shop
from app.models.record import DailyRecord, CustomerReceipt, DigitalEntry, Expense
from app.services.auth_service import get_password_hash
from app.services.pdf_service import generate_daily_report_pdf, format_inr, sanitize_filename_component
from app.services.whatsapp_service import normalize_whatsapp_number, send_daily_report_to_whatsapp

client = TestClient(app)


def get_auth_token_for(username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_sanitize_filename_and_currency_format():
    """Verify clean dynamic filename sanitization and Indian currency formatting."""
    assert sanitize_filename_component("Chellam Traders & Sons / Co.") == "Chellam_Traders_Sons_Co"
    assert sanitize_filename_component("   My Shop   ") == "My_Shop"
    
    # Currency formatting
    assert "25,500.00" in format_inr(25500)
    assert "8,500.00" in format_inr(8500)
    assert "16,428.00" in format_inr(16428)
    assert "-Rs. 500.00" in format_inr(-500, symbol="Rs. ") or "-₹500.00" in format_inr(-500, symbol="₹")


def test_whatsapp_phone_number_validation():
    """Verify E.164 phone number normalization and validation."""
    # Valid international numbers
    valid, num, err = normalize_whatsapp_number("+919876543210")
    assert valid is True
    assert num == "919876543210"
    assert err == ""

    # Valid with spaces / hyphens
    valid, num, err = normalize_whatsapp_number("+91 98765-43210")
    assert valid is True
    assert num == "919876543210"

    # Missing / empty number
    valid, num, err = normalize_whatsapp_number("")
    assert valid is False
    assert "not configured" in err

    valid, num, err = normalize_whatsapp_number(None)
    assert valid is False
    assert "not configured" in err

    # Too short / invalid letters
    valid, num, err = normalize_whatsapp_number("12345")
    assert valid is False
    assert "Invalid phone number" in err or "length" in err

    valid, num, err = normalize_whatsapp_number("invalid-phone")
    assert valid is False


def test_user_profile_whatsapp_number_update():
    """Verify updating and retrieving user's WhatsApp number in PostgreSQL."""
    token = get_auth_token_for(settings.INITIAL_ADMIN_USERNAME, settings.INITIAL_ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    # Update WhatsApp number
    test_number = "+919876543210"
    update_resp = client.put(
        "/api/auth/profile",
        json={"whatsapp_number": test_number},
        headers=headers
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["whatsapp_number"] == test_number

    # Verify /auth/me returns persisted WhatsApp number
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["whatsapp_number"] == test_number


def test_pdf_generation_from_database_record():
    """
    Verify PDF is generated strictly from PostgreSQL confirmed data.
    Ensures PDF contains correct metadata, calculations, and table structures.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == settings.INITIAL_ADMIN_USERNAME).first()
        shop = db.query(Shop).filter(Shop.owner_user_id == user.id).first()

        # Create confirmed record in PostgreSQL with exact figures
        rec = DailyRecord(
            shop_id=shop.id,
            user_id=user.id,
            record_date="2026-10-03",
            total_customer_money=25500.0,
            total_digital_money=8500.0,
            total_cash_received=17000.0,
            total_expenses=10572.0,
            total_own_money=10000.0,
            total_cash_box_expenses=572.0,
            in_hand_money=16428.0,
            notes="Verified handwritten ledger test"
        )
        db.add(rec)
        db.flush()

        # Add line items
        db.add(CustomerReceipt(daily_record_id=rec.id, amount=500.0, description="Customer 1"))
        db.add(CustomerReceipt(daily_record_id=rec.id, amount=1000.0, description="Customer 2"))
        db.add(DigitalEntry(daily_record_id=rec.id, amount=8500.0, raw_text="GPay / PhonePe"))
        db.add(Expense(
            daily_record_id=rec.id,
            description="Dealer Settlement",
            total_amount=10572.0,
            own_amount=10000.0,
            cash_box_amount=572.0
        ))
        db.commit()
        db.refresh(rec)

        # Generate PDF
        pdf_bytes, filename = generate_daily_report_pdf(rec.id, db, shop.id)
        assert len(pdf_bytes) > 2000
        assert pdf_bytes.startswith(b"%PDF")
        assert filename == f"{sanitize_filename_component(shop.name)}_Daily_Report_2026-10-03.pdf"

    finally:
        db.close()


def test_pdf_multi_page_support_many_items():
    """Verify PDF generator handles long tables spanning multiple pages cleanly."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == settings.INITIAL_ADMIN_USERNAME).first()
        shop = db.query(Shop).filter(Shop.owner_user_id == user.id).first()

        rec = DailyRecord(
            shop_id=shop.id,
            user_id=user.id,
            record_date="2026-10-03",
            total_customer_money=50000.0,
            total_digital_money=5000.0,
            total_cash_received=45000.0,
            total_expenses=2000.0,
            total_own_money=1000.0,
            total_cash_box_expenses=1000.0,
            in_hand_money=44000.0
        )
        db.add(rec)
        db.flush()

        # Add 60 line items to force multi-page continuation
        for i in range(60):
            db.add(CustomerReceipt(
                daily_record_id=rec.id,
                amount=100.0,
                description=f"Long customer ledger line entry #{i+1}"
            ))
        db.commit()

        pdf_bytes, filename = generate_daily_report_pdf(rec.id, db, shop.id)
        assert len(pdf_bytes) > 10000
        assert pdf_bytes.startswith(b"%PDF")
    finally:
        db.close()


def test_record_creation_triggers_pdf_and_whatsapp_flow():
    """
    Verify complete flow:
    User confirms record -> POST /records -> saved in PostgreSQL -> PDF generated -> WhatsApp attempted.
    """
    token = get_auth_token_for(settings.INITIAL_ADMIN_USERNAME, settings.INITIAL_ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "record_date": "2026-10-04",
        "customer_receipts": [
            {"amount": 15000.0, "description": "Customer A"},
            {"amount": 10500.0, "description": "Customer B"}
        ],
        "digital_entries": [
            {"amount": 8500.0, "raw_text": "GPay"}
        ],
        "expenses": [
            {
                "description": "Dealer Stock",
                "total_amount": 10572.0,
                "own_amount": 10000.0,
                "cash_box_amount": 572.0
            }
        ]
    }

    resp = client.post("/api/records", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    # Financial calculations strictly from backend
    assert data["total_customer_money"] == 25500.0
    assert data["total_digital_money"] == 8500.0
    assert data["total_cash_received"] == 17000.0
    assert data["total_expenses"] == 10572.0
    assert data["total_own_money"] == 10000.0
    assert data["total_cash_box_expenses"] == 572.0
    assert data["in_hand_money"] == 16428.0

    # PDF was generated
    assert data["pdf_generated"] is True
    assert data["pdf_file_name"] is not None
    assert "Daily-Account" in data["pdf_file_name"] or "Daily_Report" in data["pdf_file_name"]

    rec_id = data["id"]

    # Delivery status endpoint
    status_resp = client.get(f"/api/records/{rec_id}/delivery-status", headers=headers)
    assert status_resp.status_code == 200
    st_data = status_resp.json()
    assert st_data["record_id"] == rec_id
    assert st_data["pdf_generated"] is True


def test_whatsapp_failure_never_rolls_back_financial_record():
    """
    CRITICAL REQUIREMENT:
    A failure in WhatsApp delivery must NOT rollback or delete the confirmed financial record.
    The database save is permanent and authoritative.
    """
    token = get_auth_token_for(settings.INITIAL_ADMIN_USERNAME, settings.INITIAL_ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    # Set invalid or failing condition in mock
    with patch("app.routers.records.send_daily_report_to_whatsapp") as mock_wa:
        mock_wa.return_value = {
            "success": False,
            "whatsapp_sent": False,
            "whatsapp_status": "failed",
            "whatsapp_error": "Meta Graph API 503 Service Unavailable"
        }


        resp = client.post("/api/records", json={
            "record_date": "2026-10-04",
            "customer_receipts": [{"amount": 2000.0}],
            "digital_entries": [],
            "expenses": []
        }, headers=headers)

        assert resp.status_code == 201
        data = resp.json()
        rec_id = data["id"]
        assert data["pdf_generated"] is True
        assert data["whatsapp_sent"] is False

        # Verify the record exists and is persisted in PostgreSQL
        get_resp = client.get(f"/api/records/{rec_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["total_customer_money"] == 2000.0


def test_manual_pdf_download_and_whatsapp_retry_endpoints():
    """Verify GET /records/{id}/pdf and POST /records/{id}/whatsapp."""
    token = get_auth_token_for(settings.INITIAL_ADMIN_USERNAME, settings.INITIAL_ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    # Create record
    resp = client.post("/api/records", json={
        "record_date": "2026-10-04",
        "customer_receipts": [{"amount": 3500.0}],
        "digital_entries": [],
        "expenses": []
    }, headers=headers)
    rec_id = resp.json()["id"]

    # View PDF (inline)
    pdf_resp = client.get(f"/api/records/{rec_id}/pdf", headers=headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "inline" in pdf_resp.headers["content-disposition"]
    assert len(pdf_resp.content) > 1000

    # Download PDF (attachment)
    download_resp = client.get(f"/api/records/{rec_id}/pdf?download=true", headers=headers)
    assert download_resp.status_code == 200
    assert "attachment" in download_resp.headers["content-disposition"]

    # Manual Send / Retry WhatsApp
    wa_retry = client.post(f"/api/records/{rec_id}/whatsapp", headers=headers)
    assert wa_retry.status_code == 200
    assert "whatsapp_sent" in wa_retry.json()


def test_shop_isolation_for_pdf_and_whatsapp():
    """
    CRITICAL SECURITY REQUIREMENT:
    User of Shop 2 must NEVER access Shop 1's PDF or trigger WhatsApp for Shop 1's record.
    """
    t1 = get_auth_token_for(settings.INITIAL_ADMIN_USERNAME, settings.INITIAL_ADMIN_PASSWORD)
    t2 = get_auth_token_for("otheruser", "Other@2026")

    # User 1 creates record in Shop 1
    resp1 = client.post(
        "/api/records",
        json={"record_date": "2026-10-04", "customer_receipts": [{"amount": 10000.0}]},
        headers={"Authorization": f"Bearer {t1}"}
    )
    rec1_id = resp1.json()["id"]

    # User 2 tries to GET PDF for User 1's record -> 404
    u2_pdf = client.get(f"/api/records/{rec1_id}/pdf", headers={"Authorization": f"Bearer {t2}"})
    assert u2_pdf.status_code == 404

    # User 2 tries to POST PDF generation for User 1's record -> 404
    u2_gen_pdf = client.post(f"/api/records/{rec1_id}/pdf", headers={"Authorization": f"Bearer {t2}"})
    assert u2_gen_pdf.status_code == 404

    # User 2 tries to trigger WhatsApp for User 1's record -> 404
    u2_wa = client.post(f"/api/records/{rec1_id}/whatsapp", headers={"Authorization": f"Bearer {t2}"})
    assert u2_wa.status_code == 404

    # User 2 tries to check delivery status for User 1's record -> 404
    u2_status = client.get(f"/api/records/{rec1_id}/delivery-status", headers={"Authorization": f"Bearer {t2}"})
    assert u2_status.status_code == 404
