import json
import time
from typing import Any

from django.conf import settings


def _extract_json_obj(text: str) -> dict[str, Any]:
    text = (text or '').strip()
    if not text:
        return {}
    return json.loads(text)


class OpenAIJsonAdapter:
    """CrewAI/OpenAI adapter with graceful fallback when provider packages are unavailable."""

    def __init__(self):
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4.1') or 'gpt-4.1'
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.max_retries = 2

    def run_json(self, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        if not self.api_key:
            raise RuntimeError('OPENAI_API_KEY not configured')

        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError(f'OpenAI SDK unavailable: {exc}') from exc

        client = OpenAI(api_key=self.api_key)
        last_error = None
        attempts = self.max_retries + 1
        response = None
        for attempt in range(1, attempts + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                    response_format={'type': 'json_object'},
                    temperature=0,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    raise RuntimeError(f'OpenAI request failed after {attempts} attempts: {exc}') from exc
                time.sleep(0.25 * attempt)

        if response is None and last_error is not None:
            raise RuntimeError(f'OpenAI request failed: {last_error}')

        content = ''
        if response.choices and response.choices[0].message:
            content = response.choices[0].message.content or ''

        payload = _extract_json_obj(content)
        token_usage = {}
        usage = getattr(response, 'usage', None)
        if usage is not None:
            token_usage = {
                'prompt_tokens': getattr(usage, 'prompt_tokens', None),
                'completion_tokens': getattr(usage, 'completion_tokens', None),
                'total_tokens': getattr(usage, 'total_tokens', None),
            }
        return payload, token_usage, self.model
