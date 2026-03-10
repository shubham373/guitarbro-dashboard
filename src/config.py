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
    # First try environment variable (works for both local and cloud)
    env_value = os.getenv(key)
    if env_value:
        return env_value

    # Try Streamlit secrets (for Streamlit Cloud deployment)
    try:
        return st.secrets[key]
    except:
        # No secrets file or key not found - this is fine for local development
        pass

    return default


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


# Shopify API Configuration
def get_shopify_store_url() -> str:
    """Get Shopify store URL (e.g., 'playguitarbro.myshopify.com')"""
    return get_secret('SHOPIFY_STORE_URL', '')


def get_shopify_access_token() -> str:
    """Get Shopify Admin API access token"""
    return get_secret('SHOPIFY_ACCESS_TOKEN', '')


# Prozo/Proship API Configuration
def get_prozo_email() -> str:
    """Get Prozo login email"""
    return get_secret('PROZO_EMAIL', '')


def get_prozo_password() -> str:
    """Get Prozo login password"""
    return get_secret('PROZO_PASSWORD', '')
