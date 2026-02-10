# API Specification (Current Codebase)

This document reflects the current implementation in:
- `job_search_backend/urls.py`
- `authentication/urls.py`, `authentication/views.py`
- `job_search/urls.py`, `job_search/views.py`

## Base URL
- Local: `http://127.0.0.1:8000`
- API Prefixes:
  - Auth APIs: `/api/auth/`
  - Job/Candidate APIs: `/api/`

---

## Authentication Summary

### Auth endpoints (`/api/auth/*`)
- `signup`, `signin`, `google`: `AllowAny`
- `profile`: `IsAuthenticated` (default DRF auth classes)
- `resume/parse/v1`: explicit `JWTAuthentication`, `SessionAuthentication`, `BasicAuthentication`

### Job/Candidate endpoints (`/api/*`)
All job_search endpoints are explicitly:
- `BasicAuthentication`
- `IsAuthenticated`

Use header:
```http
Authorization: Basic <base64(username:password)>
```

---

## Feature Flags

- `AGENT_MATCHING_ENABLED` (default `true`)
  - Controls: `POST /api/matching/runs/`
- `CANDIDATE_AI_ENABLED` (default `true`)
  - Controls: `POST /api/company-task-jobs/ranking-runs/`

---

## 1) Authentication APIs

### 1.1 Signup
`POST /api/auth/signup/`

Request body:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "confirm_password": "password123",
  "username": "user1",
  "phone_number": "9999999999",
  "age": 22,
  "gender": "Male",
  "address": "Some address"
}
```

Success `201`:
```json
{
  "success": true,
  "message": "User created successfully",
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

Common errors:
- `400` validation/user already exists
- `500` server error

---

### 1.2 Signin
`POST /api/auth/signin/`

Request body:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

Success `200`:
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

Common errors:
- `400` validation error
- `401` invalid credentials

---

### 1.3 Profile
`GET /api/auth/profile/`

Requires auth.

Success `200`:
```json
{
  "success": true,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "user1",
    "phone_number": "9999999999",
    "age": 22,
    "gender": "Male",
    "address": "Some address",
    "profile_picture": null,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

---

### 1.4 Google Auth
`POST /api/auth/google/`

Request body:
```json
{
  "id_token": "<google-id-token>"
}
```

Success:
- `200` existing user
- `201` new user

Response includes:
- `success`, `message`, `is_new_user`, `is_profile_complete`
- `access`, `refresh`
- `user` object

Common errors:
- `400` validation
- `401` invalid Google token
- `409` account link error

---

### 1.5 Resume Parse V1
`POST /api/auth/resume/parse/v1/`

Auth: JWT / Session / Basic
Content type: `multipart/form-data`

Form field:
- `resume_file` (required, `.pdf` or `.docx`, max 5MB)

Success `200`:
- Returns parsed resume payload in schema fields:
  - `personal_info`, `summary`, `experience`, `education`, `skills`, `certifications`, `projects`, `languages`

Common errors:
- `400` invalid request / no text extracted
- `500` parsing error

---

## 2) Job Matching APIs (existing job dataset)

### 2.1 Deterministic Preference Match
`POST /api/preferences/match-jobs/`

Required fields:
- `work_mode`: `REMOTE | ONSITE`
- `employment_type`: `FULL_TIME | INTERNSHIP`
- `location`
- `company_size_preference`: `SME | STARTUP | MNC`

Conditional fields:
- `internship_duration_weeks` required for `INTERNSHIP`

Optional:
- `stipend_min`, `stipend_max`, `stipend_currency` (both min/max must be provided together)
- `save_preference` (default `true`)

Success `200`:
- `preference`, `count`, `next`, `previous`, `results[]`

---

### 2.2 Create Async Matching Run
`POST /api/matching/runs/`

Request body:
```json
{
  "preferences": {
    "work_mode": "REMOTE",
    "employment_type": "INTERNSHIP",
    "internship_duration_weeks": 12,
    "location": "Bangalore",
    "company_size_preference": "STARTUP"
  },
  "candidate_profile": {
    "career_stage": "EARLY",
    "risk_tolerance": "LOW"
  }
}
```

Success `202`:
```json
{
  "run_id": "<uuid>",
  "status": "PENDING",
  "submitted_at": "..."
}
```

Errors:
- `400` invalid payload
- `503` if `AGENT_MATCHING_ENABLED=false`

---

### 2.3 List Matching Runs
`GET /api/matching/runs/list/`

Success `200`:
- paginated `results[]` with run status/count/timestamps

---

### 2.4 Matching Run Detail
`GET /api/matching/runs/{run_id}/`

Success `200`:
- `status`, `filtered_jobs_count`, `preference_used`, `timings`
- `top_5_jobs` when completed
- `error` block when failed

`404` if not found/not owned

---

### 2.5 Skill-Based Job Recommendation
`POST /api/jobs/recommend/`

Uses `request.user.resume_metadata.skills`.

Optional filters:
- `work_mode`, `employment_type`, `location`, `company_size_preference`
- `internship_duration_weeks`, stipend filters
- `top_n` (default 10, range 1-50)

Success `200`:
- `preferences`, `total_jobs_considered`, `resume_skills_count`, `recommendations[]`

Error:
- `400` with `code: RESUME_NOT_FOUND` if resume metadata missing

---

## 3) Company Task Job + Candidate Import APIs

### 3.1 Create Company Task Job
`POST /api/company-task-jobs/`

Request body:
```json
{
  "job_description": "Backend engineer with Django + APIs"
}
```

Success `201`:
```json
{
  "id": 100,
  "job_description": "Backend engineer with Django + APIs",
  "created_at": "..."
}
```

Error:
- `400` if `job_description` missing/blank

---

### 3.2 Import Candidates from Google Sheet
`POST /api/company-task-jobs/import-candidates/`

Request body:
```json
{
  "job_id": 100,
  "spreadsheet_url": "https://docs.google.com/spreadsheets/d/<id>/edit",
  "range_name": "Sheet1!A1:Z1000",
  "batch_size": 10
}
```

Rules:
- Required sheet headers:
  - `name`
  - `email`
  - `resume_link` OR `Resume Link`
- `name`, `email`, `resume_link` required per row
- Duplicate candidates for same job+email are skipped
- Resume is parsed from Drive link and stored in `JobCandidate.resume_data` as JSON string

Success `200`:
```json
{
  "job_id": 100,
  "spreadsheet_id": "<id>",
  "range_name": "Sheet1!A1:Z1000",
  "batch_size": 10,
  "total_rows": 30,
  "processed": 30,
  "created": 25,
  "skipped": 3,
  "failed": 2,
  "batches": [
    {
      "start_row": 2,
      "end_row": 11,
      "created": 8,
      "skipped": 1,
      "failed": 1
    }
  ],
  "errors": [
    {"row": 7, "error": "Email is missing."}
  ]
}
```

Errors:
- `400` invalid input/headers/sheet fetch failure
- `404` job not found

---

## 4) Recruiter Preference API

### 4.1 Upsert Recruiter Preference for Job
`POST /api/company-task-jobs/preferences/`

Request body:
```json
{
  "job_id": 100,
  "college_tiers": ["TIER_1", "TIER_2"],
  "min_experience_years": 0,
  "max_experience_years": 2,
  "number_of_openings": 3,
  "coding_platform_criteria": [
    {"platform": "codeforces", "metric": "rating", "operator": "gte", "value": 1400}
  ]
}
```

Validation:
- `college_tiers` non-empty list, values in `TIER_1|TIER_2|TIER_3`
- no duplicate tiers
- `min_experience_years >= 0`
- `max_experience_years >= min_experience_years`
- `number_of_openings >= 1`
- coding criteria operator in `gte|lte|eq`

Success:
- `201` created
- `200` updated

Response:
```json
{
  "job_id": 100,
  "college_tiers": ["TIER_1", "TIER_2"],
  "min_experience_years": "0.0",
  "max_experience_years": "2.0",
  "number_of_openings": 3,
  "coding_platform_criteria": [...],
  "updated_at": "..."
}
```

Errors:
- `400` validation
- `404` job not found

---

## 5) AI Candidate Ranking Run APIs

### 5.1 Create/Trigger Ranking Run
`POST /api/company-task-jobs/ranking-runs/`

Request body:
```json
{
  "job_id": 100,
  "batch_size": 20,
  "force_recompute": false
}
```

Behavior:
- Requires recruiter preference for the job.
- If `force_recompute=false` and a completed run exists, API returns existing run (`reused=true`).
- Otherwise creates new run and queues Celery task `run_candidate_ranking_pipeline`.

Responses:
- `202 Accepted` for new run
- `200 OK` reused existing completed run
- `400` validation/missing recruiter preference
- `404` job not found
- `503` if `CANDIDATE_AI_ENABLED=false`

---

### 5.2 Ranking Run Detail
`GET /api/company-task-jobs/ranking-runs/{run_id}/`

Success `200`:
- run metadata:
  - `run_id`, `job_id`, `status`, counts, `batch_size`, `model_name`, errors, timings
- `results[]` sorted by rank with fields:
  - `rank`, `candidate_id`, `name`, `email`, `is_shortlisted`, `passes_hard_filter`, `final_score`, `sub_scores`, `filter_reasons`, `summary`

`404` if run not found

---

### 5.3 Ranking Run List for Job
`GET /api/company-task-jobs/{job_id}/ranking-runs/`

Success `200`:
- paginated list of run metadata (same as run summary)

---

## 6) Status Enums

### MatchingRun.status
- `PENDING`
- `FILTERING`
- `AGENT_RUNNING`
- `COMPLETED`
- `FAILED`

### CandidateRankingRun.status
- `PENDING`
- `RUNNING`
- `COMPLETED`
- `FAILED`

---

## 7) Notes

- Pagination size for list endpoints in `job_search/views.py` is `10`.
- Candidate ranking pipeline runs asynchronously via Celery task:
  - `run_candidate_ranking_pipeline`
- Candidate ranking traces and per-stage metadata are persisted in DB (`AgentTraceEvent`).
- `CompanyTaskJob` ids start from `100` via model save logic.
