import pathlib

import click
from colorama import Fore, init

from src.ingest.linkedin_parser import LinkedInParser
from src.ingest.resume_parser import PDFResumeParser

init(autoreset=True)


@click.command()
@click.option("--resume", type=click.Path(exists=True, path_type=pathlib.Path), help="Path to PDF Resume")
@click.option(
    "--linkedin", type=click.Path(exists=True, path_type=pathlib.Path), help="Path to LinkedIn Connections CSV"
)
def verify(resume, linkedin):
    """Verify ingestion components manually."""

    if not resume and not linkedin:
        click.echo(Fore.YELLOW + "Please provide --resume and/or --linkedin file paths to verify.")
        click.echo("Usage example: uv run python scripts/verify_ingestion.py --resume data/resume.pdf")
        return

    if resume:
        click.echo(Fore.CYAN + f"\n=== Verifying Resume Parser: {resume.name} ===")
        try:
            parser = PDFResumeParser()
            data = parser.parse(resume)
            click.echo(Fore.GREEN + f"Successfully parsed {resume.name}!")
            click.echo(f"Format: {data['format']}")
            text_preview = data["text"][:500].replace("\n", " ")
            click.echo(f"Text Preview: {text_preview}...")
        except Exception as e:
            click.echo(Fore.RED + f"Error parsing resume: {e}")

    if linkedin:
        click.echo(Fore.CYAN + f"\n=== Verifying LinkedIn Parser: {linkedin.name} ===")
        try:
            parser = LinkedInParser(linkedin)
            connections = parser.parse_connections()
            click.echo(Fore.GREEN + f"Successfully parsed {len(connections)} connections!")

            if connections:
                click.echo(f"First connection: {connections[0]}")

            companies = parser.get_companies()
            click.echo(f"Found {len(companies)} unique companies.")
            click.echo(f"Example Companies: {companies[:5]}")

        except Exception as e:
            click.echo(Fore.RED + f"Error parsing LinkedIn data: {e}")


if __name__ == "__main__":
    verify()
