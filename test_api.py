import os
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Ensure MONGO_DB is set for tests
os.environ["MONGO_DB"] = "attendance_test_db"

from app.main import app, db, init_indexes

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup test DB
    db.employees.delete_many({})
    db.attendance_logs.delete_many({})
    init_indexes()
    yield
    db.employees.delete_many({})
    db.attendance_logs.delete_many({})


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_employee_crud():
    # Invalid emp_code format -> 422
    res = client.post("/employees", json={
        "emp_code": "INVALID",
        "name": "Test User",
        "email": "test@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })
    assert res.status_code == 422

    # Equal shift_start and shift_end -> 422
    res = client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Test User",
        "email": "test@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "09:30",
        "joined_on": "2026-01-01"
    })
    assert res.status_code == 422

    # Success create -> 201
    res = client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Asha Rao",
        "email": "asha@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-05"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["emp_code"] == "EMP0001"
    assert isinstance(data["created_at"], int)
    assert "_id" not in data

    # Duplicate emp_code -> 409
    res = client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Duplicate",
        "email": "dup@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-05"
    })
    assert res.status_code == 409

    # List employees with department filter
    client.post("/employees", json={
        "emp_code": "EMP0002",
        "name": "Bob",
        "email": "bob@example.com",
        "department": "HR",
        "shift_start": "10:00",
        "shift_end": "19:00",
        "joined_on": "2026-02-01"
    })

    res = client.get("/employees?department=Engineering")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["emp_code"] == "EMP0001"


def test_punch_in_and_punch_out():
    client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Asha Rao",
        "email": "asha@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-05"
    })

    # Punch in 09:40:00 IST (10 min grace: not late, 0 late minutes)
    # 2026-07-06 09:40:00 IST = 2026-07-06 04:10:00 UTC = 1783311000000 ms
    dt_in = datetime(2026, 7, 6, 4, 10, 0, tzinfo=timezone.utc)
    ms_in = int(dt_in.timestamp() * 1000)

    res = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": ms_in,
        "status": "PRESENT"
    })
    assert res.status_code == 201
    rec = res.json()
    assert rec["emp_code"] == "EMP0001"
    assert rec["date"] == "2026-07-06"
    assert rec["late_minutes"] == 0
    assert rec["punch_out"] is None
    assert rec["work_hours"] is None

    # Duplicate punch-in for same date -> 409
    res = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": ms_in + 1000
    })
    assert res.status_code == 409

    # Punch out at 19:10:00 IST (40 min overtime >= 30, work hours 9.5)
    # 2026-07-06 19:10:00 IST = 2026-07-06 13:40:00 UTC
    dt_out = datetime(2026, 7, 6, 13, 40, 0, tzinfo=timezone.utc)
    ms_out = int(dt_out.timestamp() * 1000)

    res = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0001",
        "punched_at": ms_out
    })
    assert res.status_code == 200
    rec = res.json()
    assert rec["punch_out"] == ms_out
    assert rec["work_hours"] == 9.5
    assert rec["overtime_minutes"] == 40
    assert rec["half_day"] is False

    # Second punch out -> 409
    res = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0001",
        "punched_at": ms_out + 1000
    })
    assert res.status_code == 409


def test_punch_in_strictly_more_than_grace():
    client.post("/employees", json={
        "emp_code": "EMP0003",
        "name": "Kavita",
        "email": "kavita@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-05"
    })
    # 09:40:01 IST -> 10 minutes late!
    dt_in = datetime(2026, 7, 6, 4, 10, 1, tzinfo=timezone.utc)
    ms_in = int(dt_in.timestamp() * 1000)

    res = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0003",
        "punched_at": ms_in
    })
    assert res.status_code == 201
    assert res.json()["late_minutes"] == 10


def test_overnight_shift():
    # 22:00 to 06:00
    client.post("/employees", json={
        "emp_code": "EMP0005",
        "name": "Overnight Dev",
        "email": "overnight@example.com",
        "department": "Ops",
        "shift_start": "22:00",
        "shift_end": "06:00",
        "joined_on": "2026-01-01"
    })

    # Punch-in at 2026-07-07 00:15:00 IST (which is < 06:00, so belongs to 2026-07-06 shift)
    # 2026-07-06 18:45:00 UTC
    dt_in = datetime(2026, 7, 6, 18, 45, 0, tzinfo=timezone.utc)
    ms_in = int(dt_in.timestamp() * 1000)

    res = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0005",
        "punched_at": ms_in
    })
    assert res.status_code == 201
    rec = res.json()
    assert rec["date"] == "2026-07-06"
    # Late by 2 hours and 15 min = 135 minutes late
    assert rec["late_minutes"] == 135

    # Punch out at 2026-07-07 06:45:00 IST (45 min overtime)
    # 2026-07-07 01:15:00 UTC
    dt_out = datetime(2026, 7, 7, 1, 15, 0, tzinfo=timezone.utc)
    ms_out = int(dt_out.timestamp() * 1000)

    res = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0005",
        "punched_at": ms_out
    })
    assert res.status_code == 200
    rec = res.json()
    assert rec["overtime_minutes"] == 45
    assert rec["work_hours"] == 6.5
    assert rec["half_day"] is False


def test_regularize_patch():
    client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Asha",
        "email": "asha@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-05"
    })

    # Punch in 10:05 IST (35 min late)
    dt_in = datetime(2026, 7, 7, 4, 35, 0, tzinfo=timezone.utc)
    client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": int(dt_in.timestamp() * 1000)
    })

    # Correct punch-in to 09:28 IST (inside grace -> 0 late)
    dt_corrected = datetime(2026, 7, 7, 3, 58, 0, tzinfo=timezone.utc)
    ms_corrected = int(dt_corrected.timestamp() * 1000)

    res = client.patch("/attendance/EMP0001/2026-07-07", json={
        "punch_in": ms_corrected,
        "reason": "biometric malfunction",
        "regularized_by": "hr.admin"
    })
    assert res.status_code == 200
    rec = res.json()
    assert rec["punch_in"] == ms_corrected
    assert rec["late_minutes"] == 0
    assert len(rec["history"]) == 1
    assert rec["history"][0]["reason"] == "biometric malfunction"
    assert rec["history"][0]["changes"]["late_minutes"] == {"from": 35, "to": 0}

    # Setting ABSENT with punch_in must fail with 422
    res = client.patch("/attendance/EMP0001/2026-07-07", json={
        "status": "ABSENT",
        "punch_in": ms_corrected,
        "reason": "marked absent mistakenly with punch",
        "regularized_by": "hr.admin"
    })
    assert res.status_code == 422

    # Setting ABSENT clears punches
    res = client.patch("/attendance/EMP0001/2026-07-07", json={
        "status": "ABSENT",
        "reason": "marked absent",
        "regularized_by": "hr.admin"
    })
    assert res.status_code == 200
    rec = res.json()
    assert rec["status"] == "ABSENT"
    assert rec["punch_in"] is None
    assert rec["late_minutes"] == 0
    assert len(rec["history"]) == 2


def test_leaderboard_competition_ranking():
    # 3 employees: EMP0001 (late 40), EMP0002 (late 40), EMP0003 (late 20)
    # Ranks should be 1, 1, 3 (skip rank 2!)
    for emp_code, name in [("EMP0001", "Alice"), ("EMP0002", "Bob"), ("EMP0003", "Charlie")]:
        client.post("/employees", json={
            "emp_code": emp_code,
            "name": name,
            "email": f"{emp_code}@example.com",
            "department": "Engineering",
            "shift_start": "09:30",
            "shift_end": "18:30",
            "joined_on": "2026-01-01"
        })

    # EMP0001 late 40 min
    db.attendance_logs.insert_one({
        "emp_code": "EMP0001",
        "date": "2026-07-06",
        "status": "PRESENT",
        "late_minutes": 40,
        "overtime_minutes": 0,
        "work_hours": 8.0,
        "half_day": False,
        "history": []
    })
    # EMP0002 late 40 min
    db.attendance_logs.insert_one({
        "emp_code": "EMP0002",
        "date": "2026-07-06",
        "status": "PRESENT",
        "late_minutes": 40,
        "overtime_minutes": 0,
        "work_hours": 8.0,
        "half_day": False,
        "history": []
    })
    # EMP0003 late 20 min
    db.attendance_logs.insert_one({
        "emp_code": "EMP0003",
        "date": "2026-07-06",
        "status": "PRESENT",
        "late_minutes": 20,
        "overtime_minutes": 0,
        "work_hours": 8.0,
        "half_day": False,
        "history": []
    })

    # If limit is 1, return rank <= 1 -> returns BOTH EMP0001 and EMP0002!
    res = client.get("/analytics/leaderboard/late?month=2026-07&limit=1")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 2
    assert items[0]["rank"] == 1
    assert items[1]["rank"] == 1
    assert items[0]["emp_code"] == "EMP0001"
    assert items[1]["emp_code"] == "EMP0002"

    # If limit is 3, return EMP0001 (1), EMP0002 (1), EMP0003 (3)
    res = client.get("/analytics/leaderboard/late?month=2026-07&limit=3")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 3
    assert items[2]["rank"] == 3
    assert items[2]["emp_code"] == "EMP0003"


def test_department_summary_includes_zero_log_employee():
    # 2 employees in Engineering: one with logs, one with zero logs
    client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Alice",
        "email": "alice@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })
    client.post("/employees", json={
        "emp_code": "EMP0002",
        "name": "Bob (no logs)",
        "email": "bob@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })
    # Future joiner: joined 2026-08-01 (should be excluded from July summary)
    client.post("/employees", json={
        "emp_code": "EMP0003",
        "name": "Charlie (future)",
        "email": "charlie@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-08-01"
    })

    # Only EMP0001 has a log on Mon 2026-07-06
    db.attendance_logs.insert_one({
        "emp_code": "EMP0001",
        "date": "2026-07-06",
        "status": "PRESENT",
        "late_minutes": 10,
        "overtime_minutes": 30,
        "work_hours": 8.5,
        "half_day": False,
        "history": []
    })

    res = client.get("/analytics/departments/summary?month=2026-07")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    eng = items[0]
    assert eng["department"] == "Engineering"
    assert eng["headcount"] == 2  # EMP0001 and EMP0002 (EMP0003 excluded)
    assert eng["present_days"] == 1.0
    assert eng["avg_work_hours"] == 8.5
    assert eng["late_count"] == 1
    assert eng["total_late_minutes"] == 10


def test_department_trend():
    client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Alice",
        "email": "alice@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-07-01"
    })

    res = client.get("/analytics/departments/Engineering/trend?from=2026-07-01&to=2026-07-05")
    assert res.status_code == 200
    items = res.json()["items"]
    # 5 calendar days: Jul 1 (Wed), Jul 2 (Thu), Jul 3 (Fri), Jul 4 (Sat), Jul 5 (Sun)
    assert len(items) == 5
    assert items[0]["date"] == "2026-07-01"
    assert items[0]["is_working_day"] is True
    assert items[0]["headcount"] == 1
    assert items[0]["attendance_rate"] == 0.0

    assert items[3]["date"] == "2026-07-04"
    assert items[3]["is_working_day"] is False
    assert items[3]["attendance_rate"] is None


def test_admin_explain():
    res = client.get("/admin/explain/attendance_list")
    assert res.status_code == 200
    assert "explain" in res.json()
    assert res.json()["collection"] == "attendance_logs"
