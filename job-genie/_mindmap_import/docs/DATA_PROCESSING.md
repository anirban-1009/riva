# Data Processing Strategy: Intelligent Job Hunt

This document details the algorithms and logic used to process job data and match it against your experience.

## 1. Resume Parsing & Profile Analysis

### Input Processing
The system accepts a resume (PDF/Text) or LinkedIn profile export. 
- **Tool**: `pypdf` for PDFs, `beautifulsoup` for LinkedIn HTML exports.
- **Extraction**:
  - *Hard Skills*: Python, Docker, AWS, React, etc.
  - *Experience Level*: Years of experience based on job history dates.
  - *Role Titles*: Senior Backend Engineer, Tech Lead, etc.

### Profile Vectorization & Matching (Advanced)
Option to use:
- **Local LLMs**: (e.g., Ollama, Llama.cpp) for privacy-first semantic matching.
- **Gemini API (Free Tier)**: For high-quality reasoning and semantic matching without cost (within rate limits).
This allows for "soft skill" matching and understanding nuanced job requirements beyond simple keyword hits.

## 2. Job Listing Analysis

### Requirement Extraction
When a job description is fetched:
- **Keyword Extraction**: Identify key technologies and soft skills.
- **Role Classification**: Determine seniority (Junior, Mid, Senior, Lead) and domain (Backend, Frontend, Fullstack, DevOps).
- **Location Constraints**: Identify Remote, Hybrid, On-site requirements.

### Relevance Scoring
Calculate a `match_score` (0-100) for each job:
- **Keyword Overlap**: `(Matching Skills / Total Required Skills) * Weight`
- **Title Match**: Bonus points if current/past titles align with job title.
- **Experience Match**: Does the job require `5+ years` and you have `7`? (Pass/Fail or weighted score).
- **Network Boost**: Add points if you have 1st or 2nd-degree connections at the company.

## 3. LinkedIn Connection Intelligence

### Network Graph Building
- **Company Mapping**: Normalize company names from connections to match job listings (e.g., `Google Inc.` -> `Google`).
- **Role Relevance**: Identify connections in relevant roles (e.g., Engineers, Managers, Recruiters) vs. unrelated roles.
- **Connection Strength**: Prioritize people you've interacted with (if message history is available) or those with stronger ties.

## 4. Automation Workflow

1.  **Ingest Profile**: Run once to build the "User Model".
2.  **Search Loop**:
    - Query job boards for "Python Developer".
    - Filter results (Location, Date Posted).
    - Fetch full descriptions for top targets.
3.  **Score & Rank**: Apply the matching logic.
4.  **Visualize**: Output results to Obsidian, grouped by score.
    - *Top Matches* get prominent placement in `Dashboard.canvas`.
    - *Matches with Connections* get highlighted.
