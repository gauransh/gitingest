""" This module contains functions to parse and validate input sources and patterns. """

import os
import re
import string
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from gitingest.config import MAX_FILE_SIZE, TMP_BASE_PATH
from gitingest.exceptions import InvalidPatternError
from gitingest.ignore_patterns import DEFAULT_IGNORE_PATTERNS
from gitingest.repository_clone import _check_repo_exists, fetch_remote_branch_list

HEX_DIGITS: set[str] = set(string.hexdigits)

KNOWN_GIT_HOSTS: list[str] = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "gitea.com",
    "codeberg.org",
    "gitingest.com",
]


@dataclass
class ParsedQuery:  # pylint: disable=too-many-instance-attributes
    """
    Dataclass to store the parsed details of the repository or file path.
    """

    user_name: str | None
    repo_name: str | None
    subpath: str
    local_path: Path
    url: str | None
    slug: str
    id: str
    type: str | None = None
    branch: str | None = None
    commit: str | None = None
    max_file_size: int = MAX_FILE_SIZE
    ignore_patterns: set[str] | None = None
    include_patterns: set[str] | None = None
    pattern_type: str | None = None
    git_username: str | None = None
    git_pat: str | None = None


async def parse_query(
    source: str,
    max_file_size: int,
    pattern_type: str = "exclude",
    pattern: str = "",
    git_username: str | None = None,
    git_pat: str | None = None,
    from_web: bool = False,
) -> ParsedQuery:
    """Parse a query for repository ingestion."""
    parsed_query = await _parse_repo_source(source)
    parsed_query.git_username = git_username
    parsed_query.git_pat = git_pat
    
    parsed_query = await _parse_repo_source(source)
    
    # Add credentials to parsed query
    parsed_query.git_username = git_username
    parsed_query.git_pat = git_pat

    # Combine default ignore patterns + custom patterns
    ignore_patterns_set = DEFAULT_IGNORE_PATTERNS.copy()
    if parsed_query.ignore_patterns:
        ignore_patterns_set.update(_parse_patterns(parsed_query.ignore_patterns))

    # Process include patterns and override ignore patterns accordingly
    if parsed_query.include_patterns:
        parsed_include = _parse_patterns(parsed_query.include_patterns)
        ignore_patterns_set = _override_ignore_patterns(ignore_patterns_set, include_patterns=parsed_include)
    else:
        parsed_include = None

    return ParsedQuery(
        user_name=parsed_query.user_name,
        repo_name=parsed_query.repo_name,
        url=parsed_query.url,
        subpath=parsed_query.subpath,
        local_path=parsed_query.local_path,
        slug=parsed_query.slug,
        id=parsed_query.id,
        type=parsed_query.type,
        branch=parsed_query.branch,
        commit=parsed_query.commit,
        max_file_size=max_file_size,
        ignore_patterns=ignore_patterns_set,
        include_patterns=parsed_include,
        pattern_type=pattern_type,
        git_username=parsed_query.git_username,
        git_pat=parsed_query.git_pat
    )


async def _parse_repo_source(source: str) -> ParsedQuery:
    """
    Parse a repository URL into a structured query dictionary.

    If source is:
      - A fully qualified URL (https://gitlab.com/...), parse & verify that domain
      - A URL missing 'https://' (gitlab.com/...), add 'https://' and parse
      - A 'slug' (like 'pandas-dev/pandas'), attempt known domains until we find one that exists.

    Parameters
    ----------
    source : str
        The URL or domain-less slug to parse.

    Returns
    -------
    ParsedQuery
        A dictionary containing the parsed details of the repository.
    """
    source = unquote(source)

    # Attempt to parse
    parsed_url = urlparse(source)

    if parsed_url.scheme:
        _validate_scheme(parsed_url.scheme)
        _validate_host(parsed_url.netloc.lower())

    else:  # Will be of the form 'host/user/repo' or 'user/repo'
        tmp_host = source.split("/")[0].lower()
        if "." in tmp_host:
            _validate_host(tmp_host)
        else:
            # No scheme, no domain => user typed "user/repo", so we'll guess the domain.
            host = await try_domains_for_user_and_repo(*_get_user_and_repo_from_path(source))
            source = f"{host}/{source}"

        source = "https://" + source
        parsed_url = urlparse(source)

    host = parsed_url.netloc.lower()
    user_name, repo_name = _get_user_and_repo_from_path(parsed_url.path)

    _id = str(uuid.uuid4())
    slug = f"{user_name}-{repo_name}"
    local_path = TMP_BASE_PATH / _id / slug
    url = f"https://{host}/{user_name}/{repo_name}"

    parsed = ParsedQuery(
        user_name=user_name,
        repo_name=repo_name,
        url=url,
        subpath="/",
        local_path=local_path,
        slug=slug,
        id=_id,
        git_username=user_name,
        git_pat=None,
    )

    remaining_parts = parsed_url.path.strip("/").split("/")[2:]

    if not remaining_parts:
        return parsed

    possible_type = remaining_parts.pop(0)  # e.g. 'issues', 'pull', 'tree', 'blob'

    # If no extra path parts, just return
    if not remaining_parts:
        return parsed

    # If this is an issues page or pull requests, return early without processing subpath
    if remaining_parts and possible_type in ("issues", "pull"):
        return parsed

    parsed.type = possible_type

    # Commit or branch
    commit_or_branch = remaining_parts[0]
    if _is_valid_git_commit_hash(commit_or_branch):
        parsed.commit = commit_or_branch
        remaining_parts.pop(0)
    else:
        parsed.branch = await _configure_branch_and_subpath(remaining_parts, url)

    # Subpath if anything left
    if remaining_parts:
        parsed.subpath += "/".join(remaining_parts)

    return parsed


async def _configure_branch_and_subpath(remaining_parts: list[str], url: str) -> str | None:
    """
    Configure the branch and subpath based on the remaining parts of the URL.
    Parameters
    ----------
    remaining_parts : list[str]
        The remaining parts of the URL path.
    url : str
        The URL of the repository.
    Returns
    -------
    str | None
        The branch name if found, otherwise None.

    """
    try:
        # Fetch the list of branches from the remote repository
        branches: list[str] = await fetch_remote_branch_list(url)
    except RuntimeError as e:
        warnings.warn(f"Warning: Failed to fetch branch list: {e}", RuntimeWarning)
        return remaining_parts.pop(0)

    branch = []
    while remaining_parts:
        branch.append(remaining_parts.pop(0))
        branch_name = "/".join(branch)
        if branch_name in branches:
            return branch_name

    return None


def _is_valid_git_commit_hash(commit: str) -> bool:
    """
    Validate if the provided string is a valid Git commit hash.

    This function checks if the commit hash is a 40-character string consisting only
    of hexadecimal digits, which is the standard format for Git commit hashes.

    Parameters
    ----------
    commit : str
        The string to validate as a Git commit hash.

    Returns
    -------
    bool
        True if the string is a valid 40-character Git commit hash, otherwise False.
    """
    return len(commit) == 40 and all(c in HEX_DIGITS for c in commit)


def _normalize_pattern(pattern: str) -> str:
    """
    Normalize the given pattern by removing leading separators and appending a wildcard.

    This function processes the pattern string by stripping leading directory separators
    and appending a wildcard (`*`) if the pattern ends with a separator.

    Parameters
    ----------
    pattern : str
        The pattern to normalize.

    Returns
    -------
    str
        The normalized pattern.
    """
    pattern = pattern.lstrip(os.sep)
    if pattern.endswith(os.sep):
        pattern += "*"
    return pattern


def _parse_patterns(pattern: set[str] | str) -> set[str]:
    """
    Parse and validate file/directory patterns for inclusion or exclusion.

    Takes either a single pattern string or set of pattern strings and processes them into a normalized list.
    Patterns are split on commas and spaces, validated for allowed characters, and normalized.

    Parameters
    ----------
    pattern : set[str] | str
        Pattern(s) to parse - either a single string or set of strings

    Returns
    -------
    set[str]
        A set of normalized patterns.

    Raises
    ------
    InvalidPatternError
        If any pattern contains invalid characters. Only alphanumeric characters,
        dash (-), underscore (_), dot (.), forward slash (/), plus (+), and
        asterisk (*) are allowed.
    """
    patterns = pattern if isinstance(pattern, set) else {pattern}

    parsed_patterns: set[str] = set()
    for p in patterns:
        parsed_patterns = parsed_patterns.union(set(re.split(",| ", p)))

    # Remove empty string if present
    parsed_patterns = parsed_patterns - {""}

    # Validate and normalize each pattern
    for p in parsed_patterns:
        if not _is_valid_pattern(p):
            raise InvalidPatternError(p)

    return {_normalize_pattern(p) for p in parsed_patterns}


def _override_ignore_patterns(ignore_patterns: set[str], include_patterns: set[str]) -> set[str]:
    """
    Remove patterns from ignore_patterns that are present in include_patterns using set difference.

    Parameters
    ----------
    ignore_patterns : set[str]
        The set of ignore patterns to filter.
    include_patterns : set[str]
        The set of include patterns to remove from ignore_patterns.

    Returns
    -------
    set[str]
        The filtered set of ignore patterns.
    """
    return set(ignore_patterns) - set(include_patterns)


def _parse_path(path_str: str) -> ParsedQuery:
    """
    Parse the given file path into a structured query dictionary.

    Parameters
    ----------
    path_str : str
        The file path to parse.

    Returns
    -------
    ParsedQuery
        A dictionary containing the parsed details of the file path.
    """
    path_obj = Path(path_str).resolve()
    return ParsedQuery(
        user_name=None,
        repo_name=None,
        url=None,
        subpath="/",
        local_path=path_obj,
        slug=f"{path_obj.parent.name}/{path_obj.name}",
        id=str(uuid.uuid4()),
        git_username=None,
        git_pat=None,
    )


def _is_valid_pattern(pattern: str) -> bool:
    """
    Validate if the given pattern contains only valid characters.

    This function checks if the pattern contains only alphanumeric characters or one
    of the following allowed characters: dash (`-`), underscore (`_`), dot (`.`),
    forward slash (`/`), plus (`+`), or asterisk (`*`).

    Parameters
    ----------
    pattern : str
        The pattern to validate.

    Returns
    -------
    bool
        True if the pattern is valid, otherwise False.
    """
    return all(c.isalnum() or c in "-_./+*" for c in pattern)


async def try_domains_for_user_and_repo(user_name: str, repo_name: str) -> str:
    """
    Attempt to find a valid repository host for the given user_name and repo_name.

    Parameters
    ----------
    user_name : str
        The username or owner of the repository.
    repo_name : str
        The name of the repository.

    Returns
    -------
    str
        The domain of the valid repository host.

    Raises
    ------
    ValueError
        If no valid repository host is found for the given user_name and repo_name.
    """
    for domain in KNOWN_GIT_HOSTS:
        candidate = f"https://{domain}/{user_name}/{repo_name}"
        if await _check_repo_exists(candidate):
            return domain
    raise ValueError(f"Could not find a valid repository host for '{user_name}/{repo_name}'.")


def _get_user_and_repo_from_path(path: str) -> tuple[str, str]:
    """
    Extract the user and repository names from a given path.

    Parameters
    ----------
    path : str
        The path to extract the user and repository names from.

    Returns
    -------
    tuple[str, str]
        A tuple containing the user and repository names.

    Raises
    ------
    ValueError
        If the path does not contain at least two parts.
    """
    path_parts = path.lower().strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Invalid repository URL '{path}'")
    return path_parts[0], path_parts[1]


def _validate_host(host: str) -> None:
    """
    Validate the given host against the known Git hosts.

    Parameters
    ----------
    host : str
        The host to validate.

    Raises
    ------
    ValueError
        If the host is not a known Git host.
    """
    if host not in KNOWN_GIT_HOSTS:
        raise ValueError(f"Unknown domain '{host}' in URL")


def _validate_scheme(scheme: str) -> None:
    """
    Validate the given scheme against the known schemes.

    Parameters
    ----------
    scheme : str
        The scheme to validate.

    Raises
    ------
    ValueError
        If the scheme is not 'http' or 'https'.
    """
    if scheme not in ("https", "http"):
        raise ValueError(f"Invalid URL scheme '{scheme}' in URL")
