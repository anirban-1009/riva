# Obsidian Vault Structure: The Job Hunt Mind Map

This document outlines the specific file structure and linking strategy to create a powerful, interconnected "mind map" of your job search within Obsidian.

## Core Entities & Relationships

The power of the mind map comes from the links between these three core entities:

1.  **Jobs** (`Jobs/`)
    -   *Links to*: `[[Company Name]]`, `[[Skill]]`
    -   *Tags*: `#job`, `#status/to_apply`, `#remote`, `#high_priority`
    -   *Properties*: `Salary`, `Applied Date`, `Source URL`

2.  **Companies** (`Companies/`)
    -   *Links to*: `[[Industry]]`, `[[Location]]`
    -   *Backlinks from*: Jobs at this company, People working here.
    -   *Tags*: `#company`, `#target_company`

-   *Links to*: `[[Current Company]]`, `[[Target Role]]` (if they are in a similar role)
-   *Tags*: `#connection`, `#network/strong`, `#recruiter`
-   *Properties*: `Last_Contacted`, `Latest_Update`

## Folder Hierarchy

```
MindMap_Vault/
├── 00_Dashboard.canvas      # Visual overview of top opportunities
├── Jobs/                    # Individual job postings
│   ├── Senior Python Dev at Spotify.md
│   └── ML Engineer at Netflix.md
├── Companies/               # Company profiles
│   ├── Spotify.md
│   └── Netflix.md
├── People/                  # Your network
│   ├── Jane Doe.md          # Works at Spotify
│   └── Recruiter Mike.md    # Recruiter at Netflix
├── Assets/                  # Resume versions, cover letters
│   └── Resume_2024.pdf
├── Analysis/                # Skill gaps & Retrospectives
│   ├── Missing_Skills.md
│   └── Rejected_Applications.md
└── Templates/               # Templates for new notes
    ├── Job_Template.md
    └── Meeting_Note.md
```

## Graph Visualization Strategy

### 1. The "Opportunity Cluster"
When filtering the graph for `#job` and `#status/to_apply`, you will see clusters around specific companies.
-   **Visual**: A large node for `[[Spotify]]` connected to 3 job nodes and 2 person nodes (`[[Jane Doe]]`).
-   **Insight**: "I have 2 connections at Spotify where there are 3 open roles. This is a high-priority target."

### 2. The "Skill Gap" Analysis
Create notes for skills (`Skills/Python.md`, `Skills/React.md`).
-   Link jobs to required skills.
-   **Visual**: See which skill nodes have the most connections to high-value jobs.
-   **Insight**: "React is required by 80% of the jobs I'm interested in, but I don't have it on my resume."

## Automated Canvas Generation
The tool can generate `.canvas` files for specific views:
-   **"Warm Leads" Canvas**: Automatically places `[[Company]]` cards in the center, surrounded by `[[Job]]` cards on one side and `[[Person]]` cards on the other, for companies where you have connections.
-   **"Application Pipeline" Canvas**: Columns for `To Apply`, `Applied`, `Interviewing`, `Offer`—moving job cards between columns updates their status property.

## Note Templates

### Job Note Template
```markdown
---
tags:
  - job
  - status/to_apply
company: "[[Spotify]]"
location: "Remote"
salary: "$150k - $180k"
posted_date: 2023-10-27
url: "https://..."
match_score: 85
---

# Senior Python Developer at [[Spotify]]

**Connections at Company:**
- [[Jane Doe]] (Engineering Manager)
- [[John Smith]] (Alumni)

## Description
...

## My Fit
- ✅ Python API Development
- ❌ GraphQL experience (Need to brush up)

## Action Items
- [ ] Message [[Jane Doe]] about the role
- [ ] Tailor resume
- [ ] Apply
```
