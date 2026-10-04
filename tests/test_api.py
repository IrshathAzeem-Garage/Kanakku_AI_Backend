import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.shop import Shop
from app.models.record import DailyRecord
from app.services.auth_service import get_password_hash, create_access_token

client = TestClient(app)


def test_health_check_endpoint():
    """Verify cold-start Render wake-up endpoint on both /health and /api/health."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "kanakku-ai"

    api_response = client.get("/api/health")
    assert api_response.status_code == 200
    api_data = api_response.json()
    assert api_data["status"] == "ok"
    assert api_data["service"] == "kanakku-ai"


def test_login_flow_and_auth_me():
    """Verify login authentication, user profile, and shop information."""
    # Test invalid login
    bad_resp = client.post("/api/auth/login", json={
        "username": "iqbal",
        "password": "wrongpassword"
    })
    assert bad_resp.status_code == 401

    # Test valid login
    resp = client.post("/api/auth/login", json={
        "username": settings.INITIAL_ADMIN_USERNAME,
        "password": settings.INITIAL_ADMIN_PASSWORD
    })
    assert resp.status_code == 200
    token_data = resp.json()
    assert "access_token" in token_data
    token = token_data["access_token"]
    assert token_data["user"]["fullname"] == settings.INITIAL_ADMIN_FULLNAME
    assert token_data["user"]["email"] == settings.INITIAL_ADMIN_EMAIL
    assert token_data["shop"]["name"] == settings.INITIAL_SHOP_NAME

    # Test /auth/me with bearer token
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == settings.INITIAL_ADMIN_USERNAME
    assert me_data["fullname"] == settings.INITIAL_ADMIN_FULLNAME
    assert me_data["shop"]["name"] == settings.INITIAL_SHOP_NAME


def test_update_profile_and_shop():
    """Verify profile and shop updating without modifying frontend code."""
    login_resp = client.post("/api/auth/login", json={
        "username": settings.INITIAL_ADMIN_USERNAME,
        "password": settings.INITIAL_ADMIN_PASSWORD
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Update profile
    prof_resp = client.put(
        "/api/auth/profile",
        json={"fullname": "Mohamed Iqbal Updated", "email": "updated@chellamtraders.com"},
        headers=headers
    )
    assert prof_resp.status_code == 200
    assert prof_resp.json()["fullname"] == "Mohamed Iqbal Updated"

    # Update shop
    shop_resp = client.put(
        "/api/shop",
        json={"name": "Chellam Traders & Sons", "phone": "9876543210"},
        headers=headers
    )
    assert shop_resp.status_code == 200
    assert shop_resp.json()["name"] == "Chellam Traders & Sons"

    # Reset back to original
    client.put("/api/auth/profile", json={"fullname": settings.INITIAL_ADMIN_FULLNAME, "email": settings.INITIAL_ADMIN_EMAIL}, headers=headers)
    client.put("/api/shop", json={"name": settings.INITIAL_SHOP_NAME}, headers=headers)


def test_dashboard_summary_and_empty_state():
    """Verify /dashboard/summary returns database calculated values or 0s."""
    login_resp = client.post("/api/auth/login", json={
        "username": settings.INITIAL_ADMIN_USERNAME,
        "password": settings.INITIAL_ADMIN_PASSWORD
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Test for a date with no records -> returns 0s
    res = client.get("/api/dashboard/summary?date=2020-01-01", headers=headers)
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_customer_money"] == 0.0
    assert summary["in_hand_money"] == 0.0
    assert summary["record_count"] == 0


def test_multi_user_shop_isolation():
    """
    Test 8: Multi-user isolation.
    User 1 creates a record. User 2 must NOT see or access User 1's record.
    """
    db = SessionLocal()
    try:
        # Create second user and second shop
        user2 = db.query(User).filter(User.username == "otheruser").first()
        if not user2:
            user2 = User(
                username="otheruser",
                fullname="Second Owner",
                email="second@otherbusiness.com",
                password_hash=get_password_hash("Other@2026"),
                role="owner",
                is_active=True
            )
            db.add(user2)
            db.commit()
            db.refresh(user2)

        shop2 = db.query(Shop).filter(Shop.owner_user_id == user2.id).first()
        if not shop2:
            shop2 = Shop(
                name="Second Business",
                owner_user_id=user2.id,
                currency="INR",
                timezone="Asia/Kolkata"
            )
            db.add(shop2)
            db.commit()
            db.refresh(shop2)
    finally:
        db.close()

    # Login as User 1
    t1 = client.post("/api/auth/login", json={"username": settings.INITIAL_ADMIN_USERNAME, "password": settings.INITIAL_ADMIN_PASSWORD}).json()["access_token"]
    # Login as User 2
    t2 = client.post("/api/auth/login", json={"username": "otheruser", "password": "Other@2026"}).json()["access_token"]

    # User 1 creates a record
    rec1_resp = client.post(
        "/api/records",
        json={
            "record_date": "2026-10-04",
            "customer_receipts": [{"amount": 5000.0}],
            "digital_entries": [],
            "expenses": []
        },
        headers={"Authorization": f"Bearer {t1}"}
    )
    assert rec1_resp.status_code == 201
    rec1_id = rec1_resp.json()["id"]

    # User 2 tries to fetch User 1's record by ID -> 404 forbidden/not found
    u2_get = client.get(f"/api/records/{rec1_id}", headers={"Authorization": f"Bearer {t2}"})
    assert u2_get.status_code == 404

    # User 2 lists records -> must NOT see User 1's record
    u2_list = client.get("/api/records", headers={"Authorization": f"Bearer {t2}"})
    assert all(r["id"] != rec1_id for r in u2_list.json())

    # User 2 tries to delete User 1's record -> 404
    u2_del = client.delete(f"/api/records/{rec1_id}", headers={"Authorization": f"Bearer {t2}"})
    assert u2_del.status_code == 404
