"""
LVRG Lead Magnet Engine — GitHub Pages Deployer
Clones lvrg-previews at runtime (Railway has no local workspace),
copies the generated site, and pushes back.
"""

import subprocess
import shutil
import os
import tempfile
from config import GITHUB_USER, GITHUB_REPO, PREVIEW_BASE_URL


def _run(cmd: str, cwd: str = None) -> tuple[int, str, str]:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def deploy_site(prospect_id: str, site_dir: str) -> str:
    """Clone previews repo, copy site, push. Returns public URL."""

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        raise ValueError("GITHUB_TOKEN env var not set — cannot deploy to GitHub Pages")

    print(f"  [deploy] Deploying {prospect_id} to GitHub Pages...")

    # Clone into a temp directory
    tmp = tempfile.mkdtemp()
    repo_url = f"https://{github_token}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    code, out, err = _run(f"git clone --depth 1 {repo_url} repo", cwd=tmp)
    if code != 0:
        raise RuntimeError(f"git clone failed: {err}")

    repo_path = os.path.join(tmp, "repo")

    # Configure git identity
    _run('git config user.email "engine@lvrg.com"', cwd=repo_path)
    _run('git config user.name "LVRG Engine"', cwd=repo_path)

    # Copy site files
    dest = os.path.join(repo_path, prospect_id)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(site_dir, dest)

    # Commit and push
    _run(f"git add {prospect_id}/", cwd=repo_path)
    code, out, err = _run(f'git commit -m "Add preview: {prospect_id}"', cwd=repo_path)
    if code != 0 and "nothing to commit" not in out and "nothing to commit" not in err:
        print(f"  [deploy] Commit note: {err or out}")

    code, out, err = _run("git push origin main", cwd=repo_path)
    if code != 0:
        raise RuntimeError(f"git push failed: {err}")

    # Cleanup
    shutil.rmtree(tmp, ignore_errors=True)

    public_url = f"{PREVIEW_BASE_URL}/{prospect_id}/index.html"
    print(f"  [deploy] Live at: {public_url}")
    return public_url
