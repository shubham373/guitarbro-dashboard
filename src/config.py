"""
Configuration helper for GuitarBro Dashboard

Handles both local .env files and Streamlit Cloud secrets.
On Streamlit Cloud, secrets are configured in app settings.
Locally, they're read from .env file.
"""

import os
import streamlit as st
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()


def get_secret(key: str, default: str = None) -> str:
    """
    Get a secret value, checking Streamlit secrets first, then environment variables.

    Args:
        key: The secret key name
        default: Default value if not found

    Returns:
        The secret value or default
    """
    # Try Streamlit secrets first (for Streamlit Cloud deployment)
    try:
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    # Fall back to environment variable (for local development)
    return os.getenv(key, default)


# Export commonly used secrets as module-level variables
def get_facebook_page_id() -> str:
    return get_secret('FACEBOOK_PAGE_ID', '')


def get_facebook_page_token() -> str:
    return get_secret('FACEBOOK_PAGE_ACCESS_TOKEN', '')


def get_facebook_user_token() -> str:
    return get_secret('FACEBOOK_USER_ACCESS_TOKEN', '')


def get_facebook_ad_account_id() -> str:
    return get_secret('FACEBOOK_AD_ACCOUNT_ID', '')


def get_anthropic_api_key() -> str:
    return get_secret('ANTHROPIC_API_KEY', '')


def get_db_path() -> str:
    return get_secret('FB_COMMENTS_DB_PATH', 'data/fb_comments.db')
