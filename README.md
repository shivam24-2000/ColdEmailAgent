# ColdEmailAgent

An autonomous, AI-driven cold outreach and job application lifecycle platform. ColdEmailAgent automates the end-to-end recruitment pipeline—from discovering recruiter and engineering leads, crafting hyper-personalized email pitches via LLMs, staging drafts for human review, dispatching via Gmail API with human-like jitter, to monitoring replies and triggering smart follow-ups.

---

## Architecture Overview

```
                      ┌──────────────────────────────────────┐
                      │          React 19 Dashboard          │
                      │  (Draft Review, Analytics, Metrics)  │
                      └──────────────────┬───────────────────┘
                                         │ REST API
                                         ▼
                      ┌──────────────────────────────────────┐
                      │          FastAPI Backend             │
                      │  (Routers, APScheduler, Validation)  │
                      └───────┬──────────┬───────────┬───────┘
                              │          │           │
            ┌─────────────────┴─┐        │       ┌───┴─────────────────┐
            │   Discovery &     │        │       │   Gmail OAuth 2.0   │
            │   Verification    │        │       │   Service           │
            │  (Hunter, Scraping│        │       │  (Drafting, Sending,│
            │   DNS / MX verify)│        │       │   Polling, Labels)  │
            └───────────────────┘        │       └───┬─────────────────┘
                                         │           │
            ┌───────────────────┐        │           │
            │   OpenAI LLM      │        │           │
            │  Personalization  │◄───────┘           │
            │  & Classification │                    │
            └───────────────────┘                    │
                                                     ▼
                      ┌──────────────────────────────────────┐
                      │      Supabase PostgreSQL Database    │
                      │ (Companies, Contacts, Apps, Replies) │
                      └──────────────────────────────────────┘
```

---

## Key Features

- **Lead & Contact Discovery**:
  - Multi-tier discovery engine combining **Hunter.io API**, custom **BeautifulSoup** web scraping on company team/about pages, and pattern-based email synthesis (`first.last@domain.com`, `first@domain.com`).
  - Real-time DNS MX record verification and SMTP mailbox checking to eliminate bounces before dispatch.

- **AI-Powered Cold Outreach Personalization**:
  - Deep personalization powered by **OpenAI (GPT-4o / GPT-5-mini)**.
  - Matches candidate background, resume details, availability, and portfolio links directly against target company technical challenges, open roles, and recent news.
  - Generates concise, engaging cold pitches with custom subject lines.

- **Human-in-the-Loop Review Dashboard**:
  - Interactive, modern React single-page application.
  - Review, edit, approve, or reject drafts prior to dispatching.
  - Scheduled bulk sending queue with progress polling and live application status funnel.

- **Native Gmail OAuth 2.0 Integration**:
  - Connects directly to personal Gmail via Google Cloud OAuth 2.0 Desktop app flow.
  - Dispatches emails from your authenticated inbox.
  - Creates dedicated labels (`ColdEmailer`) and maintains full email thread persistence (`gmail_thread_id`).

- **Automated Reply Classification & Event Tracking**:
  - Periodic background polling of Gmail threads.
  - LLM-powered reply classification categorizing incoming responses into:
    - `interview_request`
    - `recruiter_reply` / `interested`
    - `referral`
    - `more_information`
    - `out_of_office`
    - `rejection`

- **Smart Nudges & Ghosting Detection**:
  - Automated follow-up drafts generated after customizable business-day inactivity windows (Nudge 1, Nudge 2).
  - Automatically identifies dead opportunities and updates stage to `ghosted_dead`.

- **Enterprise-Grade Safety Guardrails**:
  - Hard daily send limits (`DAILY_SEND_CAP`).
  - Randomized sending delays (1–3 minute jitter) between bulk emails to protect domain sender reputation.
  - Hard budget caps on LLM spending with rolling accounting windows (`LLM_BUDGET_USD`).

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2, APScheduler, BeautifulSoup4, HTTPX |
| **Database** | PostgreSQL hosted on Supabase (using Session / Transaction Pooler on port 6543) |
| **AI / LLM** | OpenAI API (`gpt-4o`, `gpt-5-mini`) |
| **Email & Auth** | Google Gmail API (OAuth 2.0 Desktop Client), `google-auth-oauthlib`, `dnspython` |
| **Frontend** | React 19, Vite, Modern CSS, Oxlint |
| **Deployment** | Systemd daemon, AWS Lightsail / VPS, Cloudflare Tunnel |

---

## Project Structure

```
ColdEmailAgent/
├── backend/
│   ├── app/
│   │   ├── config.py           # Pydantic environment settings
│   │   ├── db.py               # SQLAlchemy database session & engine
│   │   ├── jobs.py             # APScheduler background tasks (reply polling, ghosting)
│   │   ├── main.py             # FastAPI entrypoint and lifespan scheduler
│   │   ├── models.py           # Database models (Company, Contact, Application, Drafts)
│   │   ├── schemas.py          # Pydantic schemas for request/response validation
│   │   ├── routers/            # API endpoints (dashboard, drafts, companies, gmail, jobs)
│   │   └── services/           # Core business logic (discovery, LLM, personalize, gmail)
│   ├── evals/                  # LLM reply classification benchmarks & test cases
│   ├── .env.example            # Environment configuration template
│   ├── requirements.txt        # Python backend dependencies
│   ├── auth_gmail.py           # Interactive Gmail OAuth token generator
│   └── test_gmail.py           # End-to-end Gmail connection & label verification script
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main dashboard, metrics funnel, and bulk send control
│   │   ├── DraftReview.jsx     # Inline draft editor, subject/body approval modal
│   │   ├── AddContact.jsx      # Manual contact insertion and discovery trigger
│   │   └── api.js              # Fetch client communicating with FastAPI
│   ├── package.json            # Node.js dependencies (React 19, Vite)
│   └── vite.config.js          # Vite build and proxy configuration
├── deploy/
│   ├── applier.service         # Systemd unit configuration
│   ├── provision.sh            # Server setup script (Python, swapfile, cloudflared)
│   ├── push.sh                 # Deployment rsync script
│   └── README.md               # Production deployment guide (AWS Lightsail + Cloudflare)
└── README.md
```

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** & `npm`
- **Supabase Account** (PostgreSQL database instance)
- **OpenAI API Key**
- **Google Cloud Console Project** with Gmail API enabled (OAuth 2.0 Desktop client credentials)
- *(Optional)* **Hunter.io API Key** for company lead discovery

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/shivam24-2000/ColdEmailAgent.git
cd ColdEmailAgent
```

---

### 2. Backend Setup

1. **Create and activate a virtual environment:**

   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**

   Copy the template and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   Key configuration parameters in `.env`:

   | Variable | Description |
   |---|---|
   | `DATABASE_URL` | Supabase PostgreSQL URI (e.g. `postgresql://postgres:<PASSWORD>@db.<PROJECT_REF>.supabase.co:6543/postgres`) |
   | `OPENAI_API_KEY` | OpenAI API Secret Key |
   | `OPENAI_MODEL` | Personalization model (default: `gpt-4o`) |
   | `OPENAI_DRAFT_MODEL` | High-efficiency draft model (default: `gpt-5-mini`) |
   | `CANDIDATE_NAME` | Your full name |
   | `CANDIDATE_EMAIL` | Your sender email address |
   | `CANDIDATE_PHONE` | Your contact telephone |
   | `CANDIDATE_LINKS` | Markdown links to GitHub, LinkedIn, Portfolio |
   | `CANDIDATE_SCHOOL` | University / Institution |
   | `CANDIDATE_YEAR` | Graduation year or current standing |
   | `CANDIDATE_PRIOR` | Summary of previous work experience |
   | `CANDIDATE_AVAILABILITY` | Target employment start dates / term |
   | `GMAIL_CREDENTIALS_FILE` | Path to OAuth client JSON (`credentials.json`) |
   | `DAILY_SEND_CAP` | Maximum emails to dispatch in 24 hours (e.g. `100`) |
   | `REPLY_POLL_MINUTES` | Frequency of inbox polling for candidate threads (e.g. `15`) |

---

### 3. Google Gmail OAuth 2.0 Authorization

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Gmail API**.
3. Configure the **OAuth Consent Screen**:
   - Set User Type to **External**.
   - Add scope: `https://www.googleapis.com/auth/gmail.modify`.
   - Add your Gmail address to **Test users**.
4. Create Credentials:
   - Select **Create Credentials** → **OAuth client ID**.
   - Choose Application Type: **Desktop app**.
   - Download the JSON file, rename it to `credentials.json`, and place it in the `backend/` directory.
5. Authorize and generate token:

   ```bash
   python test_gmail.py
   ```

   This will open your default browser to authorize the application. Once approved, `token.json` is automatically saved in `backend/` and validated against the Gmail API.

---

### 4. Database Initialization

ColdEmailAgent utilizes SQLAlchemy to automatically initialize the schema on your Supabase PostgreSQL database on application startup. You can test your connection with:

```bash
python -c "from app.db import engine; conn = engine.connect(); print('Connected to database successfully!'); conn.close()"
```

---

### 5. Running the Application

#### Start the FastAPI Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Interactive API documentation will be available at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

#### Start the React Frontend

In a separate terminal window:

```bash
cd frontend
npm install
npm run dev
```

The frontend dashboard will be available at: [http://localhost:5173](http://localhost:5173).

---

## Testing & Quality Assurance

- **Gmail Integration Test**:
  ```bash
  python backend/test_gmail.py
  ```
  Verifies OAuth tokens, mailbox profile retrieval, and Gmail label creation.

- **Reply Classifier Benchmark Suite**:
  ```bash
  python backend/evals/run_classifier_eval.py
  ```
  Runs evaluation cases against `backend/evals/reply_classifier_cases.json` to verify LLM accuracy across various recruiter reply scenarios.

---

## Production Deployment

ColdEmailAgent includes automated provisioning scripts for cloud environments (e.g. AWS Lightsail Ubuntu VPS) utilizing **Cloudflare Tunnel** and **systemd**:

1. Refer to [deploy/README.md](deploy/README.md) for full deployment instructions.
2. The background service is daemonized using `applier.service`:
   ```bash
   sudo systemctl status applier.service
   ```
3. Cloudflare Zero Trust (Access) can be layered in front of the dashboard to secure human-in-the-loop review operations.

---

## Security & Privacy Notice

- Never commit your `.env`, `credentials.json`, or `token.json` files. These are strictly excluded in `.gitignore`.
- ColdEmailAgent communicates with your Gmail account using official Google OAuth 2.0 with minimal required scopes (`gmail.modify`).
- Outbound emails are sent through an approval queue; automated staging never sends emails without your explicit authorization on the review dashboard.

---

## License

This project is open-source and available under the [MIT License](LICENSE).
