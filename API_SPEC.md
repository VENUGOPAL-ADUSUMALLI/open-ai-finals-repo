# API Specification

## Base URL
- Local: `http://127.0.0.1:8000`
- API Prefix: `/api`

## Authentication
All documented endpoints require authentication.

Current implementation uses HTTP Basic Authentication.

Example header:
```http
Authorization: Basic <base64(username:password)>
```

---

## Current Flow
1. Client submits preferences.
2. Backend validates + normalizes preference data.
3. Deterministic filtering runs on jobs data.
4. For async flow, a `MatchingRun` is created and ranking is executed via task pipeline.
5. Client polls run detail endpoint for status and top results.

---

## Common Preference Object
Used by both deterministic and async APIs.

```json
{
  "work_mode": "REMOTE",
  "employment_type": "INTERNSHIP",
  "internship_duration_weeks": 12,
  "location": "Bangalore",
  "company_size_preference": "STARTUP",
  "stipend_min": "10000.00",
  "stipend_max": "20000.00",
  "stipend_currency": "INR",
  "save_preference": true
}
```

### Preference Fields
- `work_mode` (required, enum): `REMOTE`, `ONSITE`
- `employment_type` (required, enum): `FULL_TIME`, `INTERNSHIP`
- `internship_duration_weeks` (conditional, integer)
  - Required when `employment_type=INTERNSHIP`
  - Must be omitted for `employment_type=FULL_TIME`
- `location` (required, string, max 200)
- `company_size_preference` (required, enum): `SME`, `STARTUP`, `MNC`
- `stipend_min` (optional decimal)
- `stipend_max` (optional decimal)
- `stipend_currency` (optional string, max 3, default `INR`)
- `save_preference` (optional boolean, default `true`)

### Validation Rules
- Internship duration rule enforced as above.
- If stipend is provided, both `stipend_min` and `stipend_max` are required.
- `stipend_min <= stipend_max`.

### Deterministic Filtering Rules
- Exact match: `work_mode`, `employment_type`, `company_size`.
- Location: case-insensitive contains (`location__icontains`) after normalization.
- Internship: exact `internship_duration_weeks` match.
- Stipend overlap (when provided):
  - `job.stipend_max >= preference.stipend_min`
  - `job.stipend_min <= preference.stipend_max`
  - currency match
- Ordering: `published_at DESC`, then `created_at DESC`.

---

## 1) Deterministic Preference Match API

### Endpoint
`POST /api/preferences/match-jobs/`

### Purpose
Returns filtered jobs immediately and optionally saves active preference for the user.

### Request Body
Use the **Common Preference Object**.

### Success Response
Status: `200 OK`

```json
{
  "preference": {
    "work_mode": "REMOTE",
    "employment_type": "INTERNSHIP",
    "internship_duration_weeks": 12,
    "location": "bangalore",
    "company_size_preference": "STARTUP",
    "stipend_min": "10000.00",
    "stipend_max": "20000.00",
    "stipend_currency": "INR"
  },
  "count": 12,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "job_id": "12345",
      "title": "Backend Intern",
      "company_name": "Acme",
      "location": "Bangalore, India",
      "work_mode": "REMOTE",
      "employment_type": "INTERNSHIP",
      "internship_duration_weeks": 12,
      "company_size": "STARTUP",
      "stipend_min": "12000.00",
      "stipend_max": "18000.00",
      "stipend_currency": "INR",
      "job_url": "https://example.com/job/12345",
      "apply_url": "https://example.com/apply/12345",
      "apply_type": "EASY_APPLY",
      "published_at": "2026-02-06"
    }
  ]
}
```

### Errors
- `400 Bad Request` (validation failure)
- `401 Unauthorized` (missing/invalid auth)
- `405 Method Not Allowed` (non-POST)

---

## 2) Create Async Matching Run

### Endpoint
`POST /api/matching/runs/`

### Purpose
Creates an async matching run and starts pipeline execution.

### Feature Flag
If `AGENT_MATCHING_ENABLED=false`, this endpoint returns `503`.

### Request Body
```json
{
  "preferences": {
    "work_mode": "REMOTE",
    "employment_type": "INTERNSHIP",
    "internship_duration_weeks": 12,
    "location": "Bangalore",
    "company_size_preference": "STARTUP",
    "stipend_min": "10000.00",
    "stipend_max": "20000.00",
    "stipend_currency": "INR",
    "save_preference": true
  },
  "candidate_profile": {
    "career_stage": "EARLY",
    "risk_tolerance": "LOW"
  }
}
```

### Success Response
Status: `202 Accepted`

```json
{
  "run_id": "0b3a7ef0-1f74-4e5e-bec4-7dd35f95c56c",
  "status": "PENDING",
  "submitted_at": "2026-02-07T11:20:10.123456Z"
}
```

### Errors
- `400 Bad Request` (invalid payload)
- `401 Unauthorized`
- `503 Service Unavailable` (agentic matching disabled)

---

## 3) List Async Matching Runs

### Endpoint
`GET /api/matching/runs/list/`

### Purpose
Returns paginated runs for the authenticated user only.

### Success Response
Status: `200 OK`

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "run_id": "0b3a7ef0-1f74-4e5e-bec4-7dd35f95c56c",
      "status": "COMPLETED",
      "filtered_jobs_count": 12,
      "created_at": "2026-02-07T11:20:10.123456Z",
      "completed_at": "2026-02-07T11:20:11.123456Z"
    }
  ]
}
```

### Errors
- `401 Unauthorized`

---

## 4) Get Matching Run Detail

### Endpoint
`GET /api/matching/runs/{run_id}/`

### Purpose
Returns run status, timings, preference used, and top jobs when completed.

### Run Status Values
- `PENDING`
- `FILTERING`
- `AGENT_RUNNING`
- `COMPLETED`
- `FAILED`

### Success Response (Completed)
Status: `200 OK`

```json
{
  "run_id": "0b3a7ef0-1f74-4e5e-bec4-7dd35f95c56c",
  "status": "COMPLETED",
  "filtered_jobs_count": 12,
  "preference_used": {
    "work_mode": "REMOTE",
    "employment_type": "INTERNSHIP",
    "internship_duration_weeks": 12,
    "location": "bangalore",
    "company_size_preference": "STARTUP",
    "stipend_min": "10000.00",
    "stipend_max": "20000.00",
    "stipend_currency": "INR"
  },
  "timings": {
    "filtering_ms": 13,
    "agent_ms_total": 45,
    "total_ms": 64,
    "deterministic_metrics": {
      "initial_count": 5000,
      "after_primary_filters": 220,
      "after_internship_duration": 180,
      "after_stipend_overlap": 120,
      "ordered_count": 120,
      "capped_count": 120
    }
  },
  "top_5_jobs": [
    {
      "rank": 1,
      "job_id": "12345",
      "selection_probability": "0.8123",
      "fit_score": "0.7800",
      "job_quality_score": "0.8300",
      "why": "Work mode match; Employment type match; Location alignment"
    }
  ],
  "error": null,
  "started_at": "2026-02-07T11:20:10.200000Z",
  "completed_at": "2026-02-07T11:20:11.123456Z",
  "created_at": "2026-02-07T11:20:10.123456Z"
}
```

### Success Response (Failed)
Status: `200 OK`

```json
{
  "run_id": "0b3a7ef0-1f74-4e5e-bec4-7dd35f95c56c",
  "status": "FAILED",
  "filtered_jobs_count": 120,
  "preference_used": {"work_mode": "REMOTE"},
  "timings": {},
  "top_5_jobs": [],
  "error": {
    "code": "AGENT_PIPELINE_ERROR",
    "message": "..."
  },
  "started_at": "2026-02-07T11:20:10.200000Z",
  "completed_at": null,
  "created_at": "2026-02-07T11:20:10.123456Z"
}
```

### Errors
- `401 Unauthorized`
- `404 Not Found` (run not owned by user or does not exist)

---

## Operational Notes
- Pagination size is 10 for list-style responses.
- Async execution uses Celery task `run_matching_pipeline`.
- If broker enqueue fails, implementation falls back to local `.run(...)` execution path.
- `save_preference=true` updates/creates active `JobPreference` for the user.
