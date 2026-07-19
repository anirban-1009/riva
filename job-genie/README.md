# job-genie

## Purpose

The `job-genie` package is responsible for managing career development, job search assistance, resume optimization, application tracking, and interview preparation workflows.

## Responsibilities

- **Job Search & Scraping**: Querying job listings and extracting relevant details from job descriptions.
- **Resume & Cover Letter Optimization**: Customizing applications to match job descriptions.
- **Mock Interviews**: Interactive preparation and feedback loops for candidate practice.
- **Application Tracking**: Managing and updating the pipeline of submitted job applications.
- **Career Path Planning**: Recommending potential career tracks based on user profiles.

## Dependencies

- `common`

## Package Structure

```text
src/
└── job_genie/
    ├── __init__.py
    ├── models.py
    ├── services.py
    ├── tools.py
    ├── prompts.py
    └── plugin.py
```

## Running

```bash
uv run --package job-genie python -m job_genie
```

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
