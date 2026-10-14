import os
import concurrent.futures
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

os.environ["MONGO_DB"] = "attendance_concurrency_test_db"

from app.main import app, db, init_indexes

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    db.employees.drop()
    db.attendance_logs.drop()
    init_indexes()
    yield
    db.employees.drop()
    db.attendance_logs.drop()


def test_concurrent_punch_ins():
    # Setup employee
    client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Race Tester",
        "email": "race@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })

    dt_in = datetime(2026, 7, 6, 4, 0, 0, tzinfo=timezone.utc)
    ms_in = int(dt_in.timestamp() * 1000)

    # Launch 10 simultaneous punch-in requests
    def do_punch_in():
        c = TestClient(app)
        return c.post("/attendance/punch-in", json={
            "emp_code": "EMP0001",
            "punched_at": ms_in
        }).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: do_punch_in(), range(10)))

    assert results.count(201) == 1
    assert results.count(409) == 9


def test_concurrent_punch_outs():
    client.post("/employees", json={
        "emp_code": "EMP0001",
        "name": "Race Tester",
        "email": "race@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })

    dt_in = datetime(2026, 7, 6, 4, 0, 0, tzinfo=timezone.utc)
    ms_in = int(dt_in.timestamp() * 1000)
    client.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": ms_in})

    dt_out = datetime(2026, 7, 6, 13, 0, 0, tzinfo=timezone.utc)
    ms_out = int(dt_out.timestamp() * 1000)

    def do_punch_out():
        c = TestClient(app)
        return c.post("/attendance/punch-out", json={
            "emp_code": "EMP0001",
            "punched_at": ms_out
        }).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: do_punch_out(), range(10)))

    assert results.count(200) == 1
    assert results.count(409) == 9


def test_explain_index_scan_and_no_collscan():
    # Insert 50 employees and 200 attendance records
    for i in range(1, 51):
        client.post("/employees", json={
            "emp_code": f"EMP{i:04d}",
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "department": "Engineering" if i % 2 == 0 else "Marketing",
            "shift_start": "09:30",
            "shift_end": "18:30",
            "joined_on": "2026-01-01"
        })

    def check_no_collscan(plan):
        plan_str = str(plan)
        assert "COLLSCAN" not in plan_str
        assert "IXSCAN" in plan_str

    # 1. attendance_list
    res = client.get("/admin/explain/attendance_list?emp_code=EMP0001")
    assert res.status_code == 200
    check_no_collscan(res.json()["explain"])

    # 2. employee_monthly
    res = client.get("/admin/explain/employee_monthly?emp_code=EMP0001&month=2026-07")
    assert res.status_code == 200
    check_no_collscan(res.json()["explain"])

    # 3. department_summary
    res = client.get("/admin/explain/department_summary?month=2026-07")
    assert res.status_code == 200
    check_no_collscan(res.json()["explain"])

    # 4. late_leaderboard
    res = client.get("/admin/explain/late_leaderboard?month=2026-07")
    assert res.status_code == 200
    check_no_collscan(res.json()["explain"])

    # 5. department_trend
    res = client.get("/admin/explain/department_trend?department=Engineering&from=2026-07-01&to=2026-07-10")
    assert res.status_code == 200
    check_no_collscan(res.json()["explain"])
