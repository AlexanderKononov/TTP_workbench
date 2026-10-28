# Simple Trading Performance Dashboard — Project Memo

## Goal

Build a small private web dashboard for two participants (me and my friend) to:

* Log in securely.
* Upload small CSV/Parquet files containing session data.
* Process and summarise each uploaded session.
* Visualise session results.
* Store historical session statistics.
* Show monthly and multi-month summaries for each participant separately.
* Compare participants when needed.
* Download uploaded/processed data and reports.

The first version should be **simple and easy to maintain**. Do not build a complex frontend/backend architecture unless it becomes necessary.

---

# Recommended Stack

## 1. Streamlit — Web Dashboard

**Purpose:** UI, data upload, charts, tables, filters and reports.

Documentation:

https://docs.streamlit.io/

Community Cloud:

https://streamlit.io/cloud

Main concepts to use:

* `st.file_uploader()` — upload CSV/Parquet files.
* `st.dataframe()` — display tables.
* `st.metric()` — display KPIs.
* `st.line_chart()` / Plotly — visualisations.
* `st.download_button()` — download processed data/reports.
* `st.session_state` — temporary application state.
* Streamlit multipage apps — separate pages for Dashboard, Upload, History, etc.

Recommended initial pages:

```text
Dashboard
Upload Session
Session Details
History
Participant Summary
```

Keep the UI simple.

---

# 2. Supabase — Database, Authentication and File Storage

**Purpose:** persistent storage and user management.

Website:

https://supabase.com/

Documentation:

https://supabase.com/docs

Database documentation:

https://supabase.com/docs/guides/database

Authentication:

https://supabase.com/docs/guides/auth

Storage:

https://supabase.com/docs/guides/storage

Python client:

https://supabase.com/docs/reference/python/introduction

Supabase will provide:

* PostgreSQL database.
* User authentication.
* File storage.
* Persistent session history.
* Access control.

The application should NOT rely on Streamlit's local filesystem for persistent data.

---

# 3. GitHub — Source Code

**Purpose:** store and version the application code.

Website:

https://github.com/

The repository should contain approximately:

```text
trading-dashboard/
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── pages/
│   ├── dashboard.py
│   ├── upload.py
│   ├── history.py
│   └── participant.py
│
├── src/
│   ├── data_processing.py
│   ├── statistics.py
│   ├── database.py
│   └── visualisation.py
│
└── tests/
```

Do NOT commit:

* passwords
* API keys
* Supabase secrets
* `.env`
* uploaded datasets
* private trading data

Use environment variables / Streamlit secrets for credentials.

---

# 4. Streamlit Authentication

For the first version, authentication can use Streamlit's built-in authentication/OpenID Connect rather than implementing our own password system.

Documentation:

https://docs.streamlit.io/develop/concepts/connections/authentication

If simple email/password authentication is required instead, use Supabase Auth.

Do not implement custom password hashing/authentication unless there is a specific requirement.

For only two users, Google/email-based authentication is preferable to maintaining a shared password.

---

# Suggested Architecture

```text
                    GitHub
                      │
                      │ source code
                      ▼
              Streamlit Cloud
                      │
              ┌───────┴────────┐
              │                │
              ▼                ▼
         Dashboard         Authentication
              │
              │
              ▼
           Supabase
        ┌─────┼──────┐
        │     │      │
        ▼     ▼      ▼
       DB    Auth   Storage
        │
        ▼
 Session statistics
 Monthly statistics
 Participant history
```

---

# Database Concept

Keep the database model simple.

## participants / users

Supabase Auth provides the users.

Application-specific participant information can be stored separately if required:

```text
participants
-----------
id
user_id
name
created_at
```

## sessions

Each uploaded file represents a session.

```text
sessions
--------
id
participant_id
session_date
file_name
uploaded_at
status
```

## session_statistics

Store calculated statistics for each session.

Example:

```text
session_statistics
------------------
id
session_id
participant_id
metric_name
metric_value
created_at
```

Example metrics:

```text
pnl
roi
trade_count
win_rate
max_drawdown
sharpe
average_trade
profit_factor
```

If the metrics are well-defined and stable, a wider table can be used instead:

```text
session_statistics
------------------
session_id
participant_id
pnl
roi
trade_count
win_rate
max_drawdown
sharpe
profit_factor
```

Prefer the simplest structure that supports future reporting.

---

# File Storage

Uploaded files should be stored in Supabase Storage.

Suggested structure:

```text
sessions/
    <participant_id>/
        <session_id>/
            original.csv
            processed.parquet
```

The database should store metadata about each file rather than relying on filenames.

---

# Application Workflow

## Upload

User logs in.

```text
Upload Session

Participant: Alexander
Date: 2026-08-08

[Upload CSV/Parquet]

[Process Session]
```

The application should:

1. Validate the file.
2. Load it with pandas.
3. Validate required columns.
4. Calculate statistics.
5. Save the original file to Supabase Storage.
6. Save session metadata to PostgreSQL.
7. Save calculated statistics to PostgreSQL.
8. Display the results.

---

# Session Dashboard

After processing:

```text
Session Results

P&L             £124.50
Trades              37
Win Rate          62.2%
Max Drawdown      £45.20
Sharpe             1.42
```

Below this, show charts and the uploaded data.

---

# Historical Dashboard

Allow the user to select:

```text
Participant
Date range
Metric
```

Examples:

```text
Alexander
Last 6 months
P&L
```

Show:

* Monthly P&L.
* Monthly number of sessions.
* Monthly trade count.
* Win rate.
* Drawdown.
* Sharpe.
* Other relevant metrics.

Historical data should come from Supabase rather than recalculating everything from uploaded files every time.

---

# Participant Comparison

Provide an optional comparison view:

```text
                 Alexander     Friend

Sessions              12           9
Trades             1,245         932
P&L               £1,284        £846
Win rate            61.2%       57.8%
Sharpe                1.42        1.18
Max drawdown         £320        £285
```

Do not expose one participant's private data to another user unless explicitly intended.

Use Supabase Row Level Security (RLS) where appropriate.

Documentation:

https://supabase.com/docs/guides/database/postgres/row-level-security

---

# Deployment

Initial deployment should use Streamlit Community Cloud.

Documentation:

https://docs.streamlit.io/deploy/streamlit-community-cloud

General process:

```text
1. Develop locally.
2. Commit code to GitHub.
3. Create Streamlit Community Cloud application.
4. Connect GitHub repository.
5. Select app.py.
6. Configure Python dependencies.
7. Add Supabase credentials as Streamlit secrets.
8. Deploy.
```

The application should be accessible through a private URL.

---

# Environment / Secrets

Never put Supabase credentials directly in Python source code.

For local development use:

```text
.env
```

and for Streamlit Cloud use:

```text
Streamlit Secrets
```

Relevant Streamlit documentation:

https://docs.streamlit.io/develop/concepts/connections/secrets-management

Example configuration concept:

```text
SUPABASE_URL
SUPABASE_KEY
```

Use the appropriate Supabase key for the client architecture and follow Supabase's current security guidance.

---

# Python Libraries

Initial `requirements.txt` can contain approximately:

```text
streamlit
pandas
numpy
plotly
supabase
pyarrow
python-dotenv
```

Add other dependencies only when necessary.

Avoid unnecessary frameworks.

There is no need for React, FastAPI, Docker or Kubernetes for the first version.

---

# Development Principles

1. **Keep the first version small.**
2. Use Streamlit for the UI.
3. Use Supabase for persistent data.
4. Use GitHub for source control.
5. Keep processing/statistics code separate from UI code.
6. Do not store persistent application data locally.
7. Do not commit secrets or private datasets.
8. Validate uploaded files before processing.
9. Store calculated session statistics so historical reports are fast.
10. Design the database so additional participants can be added later.
11. Use Row Level Security if users should only see their own data.
12. Make the statistics calculation functions independently testable.
13. Prefer pandas/Plotly for the initial analysis and visualisation.
14. Avoid introducing a separate backend until the application actually requires it.

---

# Recommended Development Order

### Phase 1 — Local prototype

Build:

```text
Streamlit
    ↓
Upload CSV
    ↓
Pandas
    ↓
Calculate statistics
    ↓
Display charts
```

No authentication or database initially.

### Phase 2 — Persistence

Add:

```text
Supabase PostgreSQL
+
Supabase Storage
```

Save sessions and statistics.

### Phase 3 — Authentication

Add two users and associate sessions with participants.

### Phase 4 — Historical reporting

Add:

```text
Session history
Monthly summaries
Participant dashboards
Participant comparison
```

### Phase 5 — Deployment

Deploy to Streamlit Community Cloud and configure secrets.

---

# Important Scope Limitation

The initial application is a **small research/performance dashboard**, not a production trading system.

Do not over-engineer it.

The expected scale is:

* 2 initial users.
* Small uploaded datasets.
* A relatively small number of sessions.
* Historical statistics over months/years.
* Interactive charts and summary reports.

The architecture should remain simple until actual usage demonstrates a need for additional infrastructure.
