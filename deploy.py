"""
LVRG Lead Magnet Engine — GitHub Pages Deployer
Uses GitHub Contents API to push files directly (no git clone needed).
"""

import os
import base64
import json
import urllib.request
import urllib.error
from config import GITHUB_USER, GITHUB_REPO, PREVIEW_BASE_URL


def _github_request(method: str, path: str, body: dict = None) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "lvrg-engine")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"GitHub API {method} {path} → {e.code}: {body}")


def _get_file_sha(path: str) -> str | None:
    """Get existing file SHA (needed for updates). Returns None if file doesn't exist."""
    try:
        result = _github_request("GET", path)
        return result.get("sha")
    except RuntimeError:
        return None


def deploy_site(prospect_id: str, site_dir: str) -> str:
    """Push site files to GitHub Pages via API. Returns public URL."""

    print(f"  [deploy] Pushing {prospect_id} via GitHub API...")

    # Read the generated index.html
    index_path = os.path.join(site_dir, "index.html")
    with open(index_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    github_path = f"{prospect_id}/index.html"

    # Check if file already exists (need SHA to update)
    sha = _get_file_sha(github_path)

    body = {
        "message": f"Add preview: {prospect_id}",
        "content": content,
        "branch": "main",
    }
    if sha:
        body["sha"] = sha
        body["message"] = f"Update preview: {prospect_id}"

    _github_request("PUT", github_path, body)

    public_url = f"{PREVIEW_BASE_URL}/{prospect_id}/index.html"
    print(f"  [deploy] Live at: {public_url}")
    return public_url
