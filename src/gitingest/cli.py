""" Command-line interface for the Gitingest package. """

# pylint: disable=no-value-for-parameter

import asyncio

import click

from gitingest.config import MAX_FILE_SIZE, OUTPUT_FILE_PATH
from gitingest.repository_ingest import ingest


@click.command()
@click.argument("source", type=str, default=".")
@click.option("--output", "-o", default=None, help="Output file path (default: <repo_name>.txt in current directory)")
@click.option("--max-size", "-s", default=MAX_FILE_SIZE, help="Maximum file size to process in bytes")
@click.option("--exclude-pattern", "-e", multiple=True, help="Patterns to exclude")
@click.option("--include-pattern", "-i", multiple=True, help="Patterns to include")
@click.option("--branch", "-b", default=None, help="Branch to clone and ingest")
@click.option(
    "--git-username",
    envvar="GIT_USERNAME",
    help="Git username for authentication",
)
@click.option(
    "--git-pat",
    envvar="GIT_PAT",
    help="Git Personal Access Token for authentication",
)
def main(
    source: str,
    output: str | None,
    max_size: int,
    exclude_pattern: tuple[str, ...],
    include_pattern: tuple[str, ...],
    branch: str | None,
    git_username: str | None,
    git_pat: str | None,
):
    """
    Main entry point for the CLI. This function is called when the CLI is run as a script.

    It calls the async main function to run the command.

    Parameters
    ----------
    source : str
        The source directory or repository to analyze.
    output : str | None
        The path where the output file will be written. If not specified, the output will be written
        to a file named `<repo_name>.txt` in the current directory.
    max_size : int
        The maximum file size to process, in bytes. Files larger than this size will be ignored.
    exclude_pattern : tuple[str, ...]
        A tuple of patterns to exclude during the analysis. Files matching these patterns will be ignored.
    include_pattern : tuple[str, ...]
        A tuple of patterns to include during the analysis. Only files matching these patterns will be processed.
    branch : str | None
        The branch to clone (optional).
    git_username : str | None
        The Git username for authentication.
    git_pat : str | None
        The Git Personal Access Token for authentication.
    """
    # Main entry point for the CLI. This function is called when the CLI is run as a script.
    asyncio.run(_async_main(source, output, max_size, exclude_pattern, include_pattern, branch, git_username, git_pat))


async def _async_main(
    source: str,
    output: str | None,
    max_size: int,
    exclude_pattern: tuple[str, ...],
    include_pattern: tuple[str, ...],
    branch: str | None,
    git_username: str | None,
    git_pat: str | None,
) -> None:
    """
    Analyze a directory or repository and create a text dump of its contents.

    This command analyzes the contents of a specified source directory or repository, applies custom include and
    exclude patterns, and generates a text summary of the analysis which is then written to an output file.

    Parameters
    ----------
    source : str
        The source directory or repository to analyze.
    output : str | None
        The path where the output file will be written. If not specified, the output will be written
        to a file named `<repo_name>.txt` in the current directory.
    max_size : int
        The maximum file size to process, in bytes. Files larger than this size will be ignored.
    exclude_pattern : tuple[str, ...]
        A tuple of patterns to exclude during the analysis. Files matching these patterns will be ignored.
    include_pattern : tuple[str, ...]
        A tuple of patterns to include during the analysis. Only files matching these patterns will be processed.
    branch : str | None
        The branch to clone (optional).
    git_username : str | None
        The Git username for authentication.
    git_pat : str | None
        The Git Personal Access Token for authentication.

    Raises
    ------
    Abort
        If there is an error during the execution of the command, this exception is raised to abort the process.
    """
    try:
        # Combine default and custom ignore patterns
        exclude_patterns = set(exclude_pattern)
        include_patterns = set(include_pattern)

        if not output:
            output = OUTPUT_FILE_PATH
        summary, _, _ = await ingest(source, max_size, include_patterns, exclude_patterns, branch, output=output, git_username=git_username, git_pat=git_pat)

        click.echo(f"Analysis complete! Output written to: {output}")
        click.echo("\nSummary:")
        click.echo(summary)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    main()
