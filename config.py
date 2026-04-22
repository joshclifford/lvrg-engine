"""
LVRG Lead Magnet Engine — Config
"""

ANTHROPIC_API_KEY = "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"
INSTANTLY_API_KEY = "YmQ4NTJiMDAtNGViOS00ZWMyLWE2OGMtMTIzNGFlOGNkYWU3OmxaTk1CWmtrWHdNeg=="

# Sender identity
SENDER_NAME = "Josh"
SENDER_EMAIL = "adam@mobiloptimismrade.com"
SENDER_AGENCY = "LVRG Agency"
SENDER_WEBSITE = "lvrg.com"
SENDER_PHONE = "619.361.7484"
BOOKING_URL = "https://theresandiego.com/advertise/"

# GitHub Pages base URL for deployed previews
GITHUB_USER = "joshclifford"
GITHUB_REPO = "lvrg-previews"
PREVIEW_BASE_URL = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}"

# Output dirs
import os
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_DIR = os.path.join(ENGINE_DIR, "output", "sites")
EMAILS_DIR = os.path.join(ENGINE_DIR, "output", "emails")
INTEL_DIR = os.path.join(ENGINE_DIR, "output", "intel")

os.makedirs(SITES_DIR, exist_ok=True)
os.makedirs(EMAILS_DIR, exist_ok=True)
os.makedirs(INTEL_DIR, exist_ok=True)
FIRECRAWL_API_KEY = "fc-558ee853c9dd4d87b8e3213eaa69c808"
