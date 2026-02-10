"""Shared OpenAI client utilities for the job search platform."""

import openai
from django.conf import settings

_sync_client = None
_async_client = None


def get_model_name():
    """Return the configured OpenAI model name."""
    return getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')


def is_gpt_scoring_enabled():
    """Check if GPT job scoring is enabled and API key is configured."""
    enabled = getattr(settings, 'GPT_JOB_SCORING_ENABLED', False)
    has_key = bool(getattr(settings, 'OPENAI_API_KEY', ''))
    return enabled and has_key


def get_sync_openai_client():
    """Return a singleton synchronous OpenAI client for Celery workers."""
    global _sync_client
    if _sync_client is None:
        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if not api_key:
            return None
        _sync_client = openai.OpenAI(api_key=api_key)
    return _sync_client


def get_async_openai_client():
    """Return a singleton async OpenAI client for async views."""
    global _async_client
    if _async_client is None:
        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if not api_key:
            return None
        _async_client = openai.AsyncOpenAI(api_key=api_key)
    return _async_client
