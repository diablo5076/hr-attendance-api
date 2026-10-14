# Employee Attendance & Analytics API

FastAPI and MongoDB service for tracking employee attendance, punch events with business rules, manual corrections with audit trails, and aggregation-driven analytics.

## Prerequisites
- Python 3.11+
- MongoDB 6.0+ (Local instance, Docker container, or MongoDB Atlas cluster)

## Setup & Running

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional):**
   The application reads `MONGO_URI` and `MONGO_DB` directly from environment variables, falling back to defaults (`mongodb://localhost:27017` and `attendance_db`):
   ```bash
   export MONGO_URI="mongodb://localhost:27017"
   export MONGO_DB="attendance_db"
   ```

4. **Seed Sample Data (Optional):**
   ```bash
   python sample_seed.py
   ```

5. **Start the API Server:**
   ```bash
   uvicorn app.main:app --port 8000
   ```
   Interactive API documentation is available at `http://localhost:8000/docs`.

## Running Tests
Run the automated test suite with pytest:
```bash
pytest -v
```

## Submission Files
- `app/main.py`: Entire application codebase containing FastAPI endpoints, business rule engines (R1-R10), and aggregation pipelines.
- `requirements.txt`: Python package dependencies.
- `REVIEW.md`: Comprehensive defect analysis of the starter implementation with failing tests and remedies.
- `DECISIONS.md`: Architectural decisions regarding indexing, concurrency race handling, ranking tie handling, headcount aggregations, and 100x scalability.
