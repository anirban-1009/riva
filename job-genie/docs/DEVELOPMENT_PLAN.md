# Development Plan: Job Hunt Mind Mapper

## Phase 1: Foundation & Data Ingestion
**Goal:** Set up the project and get user data (Resume + Connections) into the system.

- [x] **Task 1.1**: Project Initialization
    - [x] Set up `pyproject.toml` with dependencies (`pypdf`, `pandas`, `pyyaml`, `playwright`, `google-generativeai`).
    - [x] Create `src/` directory structure (`ingest`, `core`, `generator`, `utils`).
    - [x] Create `Dockerfile` with system dependencies (Python, Playwright Browsers, TexLive for LaTeX).
    - [x] Define `config.yaml` structure for user inputs.
- [x] **Task 1.2**: Resume Parsing
    - [x] Implement `src/ingest/resume_parser.py`.
    - [x] Extract text from PDF using `pypdf`.
    - [x] Create a `ResumeParser` interface for extensibility.
    - [x] Write unit tests with sample PDFs.
    - [x] (Advanced) Use Gemini/LLM to structure the resume into a JSON profile.
- [x] **Task 1.3**: Network Ingestion
    - [x] Implement `src/ingest/linkedin_parser.py`.
    - [x] Parse LinkedIn Data Export (CSV) to get connections + companies.
    - [x] Clean and normalize company names.

## Phase 2: Job Discovery (The Scraper)
**Goal:** Automate fetching relevant job listings from LinkedIn (via Browser).

- [x] **Task 2.1**: Browser Automation Setup
    - [x] Set up Playwright with a `BrowserManager` class.
    - [x] Handle LinkedIn Login (manual first run to save cookies/state).
- [x] **Task 2.2**: Job Search Implementation
    - [x] Internal logic to construct search URLs based on config (location, keywords).
    - [x] Scrape search results (Title, Company, Link, ID).
- [x] **Task 2.3**: Job Details Extraction
    - [x] Visit individual job URLs.
    - [x] Extract full description, posted date, and metadata.
    - [x] Save raw job data to a temporary JSON/Cache (to avoid re-scraping).

## Phase 3: Intelligence & Matching
**Goal:** Use AI to score jobs and link them to your network.

- [x] **Task 3.1**: AI Engine Integration
    - [x] Implement `src/core/llm_client.py`.
    - [x] Support Google Gemini (Free Tier) and Ollama.
- [x] **Task 3.2**: Relevance Scorer
    - [x] Create prompt for "Resume vs Job Description" analysis.
    - [x] Output: Score (0-100), key matching skills, missing skills, reasoning.
- [x] **Task 3.3**: Network Graph Builder
    - [x] Logic to match specific job companies with user's connection companies.
    - [x] Logic to track "Last Contacted" and recent achievements.
- [x] **Task 3.4**: Gap Analysis (Feedback Loop)
    - [x] Logic to aggregate missing skills from High-Match jobs.
    - [x] Logic to track "Rejected" status and prompt (or deduce) improvement areas.

## Phase 4: Artifact Generation (Obsidian & Resume)
**Goal:** Generate the "Mind Map" vault and tailored application materials.

- [x] **Task 4.1**: Obsidian Template Implementation
    - [x] Create Jinja2 templates for `Job.md`, `Company.md`, `Person.md`.
- [x] **Task 4.2**: Vault/File Manager
    - Logic to create folders and update Markdown files.
- [x] **Task 4.3**: Canvas Dashboard
    - Generate `Dashboard.canvas` JSON.
- [x] **Task 4.4**: Resume Tailoring Engine
    - [x] Create a `.tex` master template.
    - [x] Implement logic to use Gemini to rewrite summary/skills for a specific job.
    - [x] Compile customized PDF using `pdflatex`.

## Phase 5: Notifications, Deployment & Polish
**Goal:** Make the tool robust, easy to run, and schedule.

- [x] **Task 5.1**: Email Notification System
    - [x] Implement `src/notification/email_service.py`.
    - [x] Generate HTML digest of new high-scoring jobs.
- [x] **Task 5.2**: Deployment Packaging
    - [x] Create `Dockerfile` for containerized execution.
    - [x] Write `scripts/run_daily.sh` for cron jobs.
    - [x] Add `setup.py` or `pyproject.toml` scripts for easy installation.
- [x] **Task 5.3**: Documentation & Instructions
    - Update `README.md` with "How to Run".
    - Add "First Run" guide (getting Cookie for LinkedIn, getting Gemini Key).
