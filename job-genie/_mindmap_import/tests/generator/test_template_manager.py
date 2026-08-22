from src.core.network_graph import Connection, ConnectionMetadata
from src.core.relevance_scorer import ScoringResult
from src.generator.template_manager import TemplateManager
from src.ingest.job_details_extractor import JobDetails


def test_render_job():
    job = JobDetails(
        id="123",
        title="Software Engineer",
        company="Tech Corp",
        location="Remote",
        description="Write code.",
        posted_date="2023-10-01",
        seniority_level="Senior",
        employment_type="Full-time",
        job_function="Engineering",
        industries="Technology",
        link="http://example.com",
    )
    score = ScoringResult(
        score=85,
        matching_skills=["Python", "AWS"],
        missing_skills=["Kubernetes"],
        reasoning="Good match",
    )

    manager = TemplateManager()
    output = manager.render_job(job, score)

    assert output.startswith("---\n")
    assert 'title: "Software Engineer"' in output
    assert 'company: "Tech Corp"' in output
    assert "score: 85" in output
    assert 'status: "ToApply"' in output
    assert 'location: "Remote"' in output
    assert "# Software Engineer @ [[Tech_Corp]]" in output
    assert "- Python" in output
    assert "- Kubernetes" in output
    assert "Write code." in output
    assert "## Job Description\n```\nWrite code.\n```" in output


def test_render_job_description_fence_escapes_embedded_backticks():
    job = JobDetails(
        id="123",
        title="Software Engineer",
        company="Tech Corp",
        location="Remote",
        description="Here is some code:\n```python\nprint(1)\n```\nEnjoy.",
        posted_date="2023-10-01",
        seniority_level="Senior",
        employment_type="Full-time",
        job_function="Engineering",
        industries="Technology",
        link="http://example.com",
    )
    score = ScoringResult(score=85, matching_skills=[], missing_skills=[], reasoning="Good match")

    manager = TemplateManager()
    output = manager.render_job(job, score)

    # A 3-backtick fence would be closed early by the ``` inside the description, so the
    # generator must use a longer fence (4 backticks here) to keep the whole block intact.
    assert "````\nHere is some code:\n```python\nprint(1)\n```\nEnjoy.\n````" in output


def test_render_job_applied_checkbox_and_poc():
    job = JobDetails(
        id="123",
        title="Software Engineer",
        company="Tech Corp",
        location="Remote",
        description="Write code.",
        posted_date="2023-10-01",
        seniority_level="Senior",
        employment_type="Full-time",
        job_function="Engineering",
        industries="Technology",
        link="http://example.com",
    )
    score = ScoringResult(score=85, matching_skills=[], missing_skills=[], reasoning="Good match")
    manager = TemplateManager()

    # Default (ToApply): unchecked, no applied_at, no POC.
    output = manager.render_job(job, score)
    assert "applied: false" in output
    assert "applied_at: null" in output
    assert "poc_name: null" in output
    assert "poc_link: null" in output
    assert "- None yet." in output

    # Applied status checks the box and stamps applied_at; POC renders as frontmatter + a link.
    output = manager.render_job(
        job,
        score,
        status="Applied",
        applied_at="2026-08-22 10:00:00",
        poc_name="Jane Doe",
        poc_link="https://linkedin.com/in/janedoe",
    )
    assert "applied: true" in output
    assert 'applied_at: "2026-08-22 10:00:00"' in output
    assert 'poc_name: "Jane Doe"' in output
    assert 'poc_link: "https://linkedin.com/in/janedoe"' in output
    assert "- [Jane Doe](https://linkedin.com/in/janedoe)" in output


def test_render_company():
    manager = TemplateManager()
    output = manager.render_company(
        name="Tech Corp",
        industry="Software",
        location="San Francisco",
        website="http://techcorp.com",
        jobs=[{"title": "DevOps", "filename": "Job_123", "status": "#ToApply"}],
        people=[{"name": "Alice", "filename": "Person_Alice", "title": "CTO"}],
    )

    assert output.startswith("---\n")
    assert 'name: "Tech Corp"' in output
    assert 'industry: "Software"' in output
    assert "# Tech Corp" in output
    assert "[[Job_123|DevOps]] (#ToApply)" in output
    assert "[[Person_Alice|Alice]] - CTO" in output


def test_render_person():
    meta = ConnectionMetadata(last_contacted="2023-01-01", notes="Nice person")
    person = Connection(
        first_name="Bob",
        last_name="Smith",
        company="Tech Corp",
        position="Developer",
        connected_on="2022-05-01",
        metadata=meta,
    )

    manager = TemplateManager()
    output = manager.render_person(person)

    assert output.startswith("---\n")
    assert 'name: "Bob Smith"' in output
    assert 'title: "Developer"' in output
    assert "# Bob Smith" in output
    assert "**Company:** [[Tech_Corp]]" in output
    assert "Nice person" in output
