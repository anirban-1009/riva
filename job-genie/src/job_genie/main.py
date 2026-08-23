import click
from colorama import Fore, init

from job_genie.core.orchestrator import MindMapApp
from job_genie.utils.logger import setup_logging

init(autoreset=True)


@click.group()
def cli():
    """Job Hunt Mindmap CLI"""
    from dotenv import load_dotenv

    load_dotenv()
    setup_logging()


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
def check(config):
    """Validate configuration and environment."""
    MindMapApp(config).check_env()


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
def login(config):
    """Obtain LinkedIn session cookies manually."""
    MindMapApp(config).login()


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
@click.option("--headless", is_flag=True, default=False, help="Run in headless mode")
@click.option("--external-only", is_flag=True, default=False, help="Only run on external sites")
def search(config, headless, external_only):
    """Search for jobs based on configuration."""
    MindMapApp(config).search(headless, external_only=external_only)


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
@click.option("--headless", is_flag=True, default=True, help="Run in headless mode")
@click.option("--limit", default=None, type=int, help="Limit number of jobs")
@click.option("--force", is_flag=True, default=False, help="Force re-scrape")
@click.option("--min-fast-score", type=int, default=0, help="Minimum initial NLP score (0-100)")
@click.option("--score", is_flag=True, default=False, help="Perform LLM scoring after scraping")
@click.option("--external-only", is_flag=True, default=False, help="Only run on external sites (skip LinkedIn)")
@click.argument("job_id", required=False)
def scrape(config, headless, limit, force, min_fast_score, score, external_only, job_id):
    """Scrape details for found jobs (or a specific job ID)."""
    MindMapApp(config).scrape(headless, limit, force, min_fast_score, score, external_only, job_id)


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
@click.option("--headless", is_flag=True, default=False, help="Run in headless mode")
@click.option("--limit", default=None, type=int, help="Limit number of jobs")
@click.option("--score", is_flag=True, default=False, help="Perform LLM re-scoring after refresh")
@click.option(
    "--unknown-only", is_flag=True, default=False, help="Only refresh jobs with Unknown Title or Unknown Company"
)
def refresh(config, headless, limit, score, unknown_only):
    """Re-scrape details for existing jobs in database."""
    MindMapApp(config).refresh_existing_jobs(headless, limit, score, unknown_only)


@cli.command()
@click.option("--config", default="config.yaml")
@click.option("--all", "score_all", is_flag=True)
@click.argument("job_id", required=False)
def score(config, score_all, job_id):
    """Score jobs against resume."""
    MindMapApp(config).score_jobs(score_all, job_id)


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
@click.option("--min-score", default=0, type=int, help="Minimum score to include")
@click.option("--tag", default=None, help="Specific tag/specialization to analyze (e.g. AI_ML)")
def analyze_gaps(config, min_score, tag):
    """Analyze skill gaps and generate report."""
    MindMapApp(config).analyze_gaps(min_score, tag)


@cli.command()
@click.option("--config", default="config.yaml")
@click.option("--min-score", default=70)
def notify(config, min_score):
    """Send job digest email."""
    MindMapApp(config).notify(min_score)


@cli.command()
@click.option("--config", default="config.yaml")
@click.argument("job_id")
@click.option("--name", default=None)
@click.option("--max-chars", default=200, type=int, help="Maximum characters for the message")
def refer(config, job_id, name, max_chars):
    """Generate referral request for a job."""
    app = MindMapApp(config)
    res = app.referral(job_id, name, max_chars=max_chars)

    if res is None:
        name = click.prompt(Fore.CYAN + "Enter connection name manually", default="Hiring Manager")
        res = app.referral(job_id, name, max_chars=max_chars)

    if res:
        click.echo(Fore.WHITE + "\n" + "=" * 50)
        click.echo(Fore.GREEN + f"To: {res['to']} {Fore.CYAN}({len(res['message'])}/{max_chars} chars)")
        click.echo(Fore.WHITE + "-" * 50)
        click.echo(res["message"])
        click.echo(Fore.WHITE + "=" * 50 + "\n")


@cli.command()
@click.option("--config", default="config.yaml")
@click.argument("job_id")
def tailor(config, job_id):
    """Generate a tailored resume."""
    app = MindMapApp(config)
    path = app.tailor_resume(job_id)
    if path:
        click.echo(Fore.GREEN + f"Tailored resume saved to: {path}")


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
@click.option("--prompt", default="Say 'Mindmap AI Online'", help="Test prompt")
def test_ai(config, prompt):
    """Test AI provider connection."""
    MindMapApp(config).test_ai(prompt)


@cli.command()
@click.argument("job_id")
@click.option("--config", default="config.yaml", help="Path to config file")
def network(job_id, config):
    """Find connections for a job."""
    MindMapApp(config).find_network(job_id)


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
def network_all(config):
    """Find connections for all jobs."""
    MindMapApp(config).map_all_networks()


@cli.command()
@click.option("--config", default="config.yaml")
def sync(config):
    """Sync data to Obsidian."""
    MindMapApp(config).sync()


@cli.command()
@click.option("--config", default="config.yaml")
def sync_back(config):
    """Sync changes from Obsidian back to the database."""
    MindMapApp(config).sync_back()


@cli.command()
@click.option("--config", default="config.yaml")
def prune(config):
    """Delete Obsidian pages not present in the database."""
    MindMapApp(config).prune()


@cli.command()
@click.option("--config", default="config.yaml")
@click.argument("query")
@click.option("--semantic", is_flag=True, default=False, help="Use embedding-based semantic search")
@click.option("--limit", default=10, type=int, help="Maximum number of results")
@click.option("--reindex", is_flag=True, default=False, help="Reindex changed vault files before searching")
def find(config, query, semantic, limit, reindex):
    """Search the Obsidian vault (keyword by default, --semantic for embeddings)."""
    results = MindMapApp(config).find(query, semantic=semantic, limit=limit, reindex=reindex)

    if not results:
        click.echo(Fore.YELLOW + "No results found.")
        return

    for r in results:
        click.echo(Fore.WHITE + "-" * 50)
        click.echo(Fore.GREEN + f"{r.get('title') or r.get('path')} " + Fore.CYAN + f"[{r.get('category')}]")
        click.echo(Fore.WHITE + r.get("path", ""))
        if "snippet" in r:
            click.echo(r["snippet"])
        elif "distance" in r:
            click.echo(Fore.CYAN + f"distance: {r['distance']:.4f}")
    click.echo(Fore.WHITE + "-" * 50)


if __name__ == "__main__":
    cli()
