"""
LVRG Lead Magnet Engine — GitHub Pages Deployer
Auto-pushes generated sites to joshclifford/lvrg-previews
"""

import subprocess
import shutil
import os
from config import GITHUB_USER, GITHUB_REPO, PREVIEW_BASE_URL, SITES_DIR

REPO_PATH = f"/home/user/workspace/lvrg-pages"


def deploy_site(prospect_id: str, site_dir: str) -> str:
    """Copy site to GitHub repo and push. Returns public URL."""
    
    print(f"  [deploy] Deploying {prospect_id} to GitHub Pages...")
    
    # Copy site files to repo
    dest = os.path.join(REPO_PATH, prospect_id)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(site_dir, dest)
    
    # Git add, commit, push
    cmds = [
        f"cd {REPO_PATH} && git add {prospect_id}/",
        f'cd {REPO_PATH} && git commit -m "Add preview: {prospect_id}"',
        f"cd {REPO_PATH} && git push origin main",
    ]
    
    for cmd in cmds:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            print(f"  [deploy] Git warning: {result.stderr[:200]}")
    
    public_url = f"{PREVIEW_BASE_URL}/{prospect_id}/index.html"
    print(f"  [deploy] Live at: {public_url}")
    return public_url
