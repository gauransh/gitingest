import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from gitingest.utils import async_timeout

TIMEOUT: int = 20
HARDCODED_PAT_USERNAME = ""
HARDCODED_PAT = ""

@dataclass
class CloneConfig:
    url: str
    local_path: str
    commit: str | None = None
    branch: str | None = None
    git_username: str | None = None
    git_pat: str | None = None

async def _check_repo_exists(url: str, git_username: str | None = None, git_pat: str | None = None) -> bool:
    """
    Check if a Git repository exists using Git-specific curl commands.
    """
    
    parsed_url = urlparse(url)
    api_url = f"https://api.github.com/repos{parsed_url.path.replace('.git', '')}"
    
    curl_args = [
        "curl",
        "-I",
        "-L",
        "-H", "Accept: application/vnd.github.v3+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
    ]

    # Add authentication if credentials are provided
    if git_username and git_pat:
        curl_args.extend(["-u", f"{git_username}:{git_pat}"])
    elif git_pat:
        curl_args.extend(["-H", f"Authorization: Bearer {git_pat}"])
    elif HARDCODED_PAT_USERNAME and HARDCODED_PAT:
        curl_args.extend(["-u", f"{HARDCODED_PAT_USERNAME}:{HARDCODED_PAT}"])
    
    curl_args.append(api_url)

    proc = await asyncio.create_subprocess_exec(
        *curl_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    if proc.returncode != 0:
        return False

    response = stdout.decode()
    status_code = _get_status_code(response)
    
    if status_code in (200, 301, 303):
        return True
    elif status_code in (404, 401, 403):
        return False

    raise RuntimeError(f"Unexpected status code: {status_code}")

@async_timeout(TIMEOUT)
async def fetch_remote_branch_list(url: str) -> list[str]:
    """
    Fetch branch list using Git-specific curl commands.
    """
    parsed_url = urlparse(url)
    api_url = f"https://api.github.com/repos{parsed_url.path.replace('.git', '')}/branches"
    
    curl_args = [
        "curl",
        "-L",
        "-u", f"{HARDCODED_PAT_USERNAME}:{HARDCODED_PAT}",
        "-H", "Accept: application/vnd.github.v3+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        api_url
    ]

    proc = await asyncio.create_subprocess_exec(
        *curl_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    
    if proc.returncode != 0:
        return []

    import json
    try:
        branches = json.loads(stdout.decode())
        return [branch['name'] for branch in branches if isinstance(branch, dict)]
    except json.JSONDecodeError:
        return []

def _embed_pat_in_url(url: str, username: str, pat: str) -> str:
    """
    Embed PAT in URL with Git-specific formatting.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return url

    # Handle Git-specific URL patterns
    netloc = f"{username}:{pat}@{parsed.netloc}"
    updated = parsed._replace(netloc=netloc)
    return urlunparse(updated)

@async_timeout(TIMEOUT)
async def clone_repo(clone_config: CloneConfig) -> None:
    """Clone a Git repository."""    
    # Check if repository exists and is accessible
    repo_exists = await _check_repo_exists(
        clone_config.url,
        clone_config.git_username,
        clone_config.git_pat
    )
    
    if not repo_exists:
        raise ValueError("Repository not accessible - might be private or doesn't exist")
    
    # Construct clone URL with credentials if provided
    clone_url = clone_config.url
    if clone_config.git_username and clone_config.git_pat:
        parsed = urlparse(clone_url)
        clone_url = urlunparse(parsed._replace(
            netloc=f"{clone_config.git_username}:{clone_config.git_pat}@{parsed.netloc}"
        ))
    
    # Prepare git clone command
    git_args = ["git", "clone"]
    
    if clone_config.branch:
        git_args.extend(["-b", clone_config.branch])
    
    if clone_config.commit:
        git_args.extend(["--depth", "1"])
    
    git_args.extend([clone_url, str(clone_config.local_path)])
    
    # Execute git clone
    try:
        await _run_git_command(git_args)
        if clone_config.commit:
            await _run_git_command(
                ["git", "checkout", clone_config.commit],
                cwd=str(clone_config.local_path)
            )
    except Exception as e:
        raise RuntimeError(f"Failed to clone repository: {e}")

async def _run_git_command(args: list[str], cwd: str | None = None) -> tuple[bytes, bytes]:
    """Execute a git command and return its output."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_message = stderr.decode().strip()
        raise RuntimeError(f"Failed to clone repository: {error_message}")

    return stdout, stderr

def _get_status_code(response: str) -> int:
    status_line = response.splitlines()[0].strip()
    return int(status_line.split(" ", 2)[1])