"""Bounded Groq Chat Completions client using Python's standard library."""
import json
import os
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .domain import ServiceError


def http_error_message(exc, key):
    """Expose bounded provider diagnostics, never headers or raw HTML."""
    messages = {401: 'Неверный или отозванный API-ключ.', 403: 'Доступ запрещён.',
                404: 'Модель или ресурс недоступны.', 429: 'Лимит API исчерпан.'}
    message = f'HTTP {exc.code}: ' + messages.get(exc.code, 'Ошибка API.')
    try:
        raw = exc.read(8192).decode('utf-8', errors='replace')
        data = json.loads(raw)
        detail = data.get('error', {}).get('message')
        if isinstance(detail, str):
            detail = detail.replace(key, '[REDACTED]') if key else detail
            detail = re.sub(r'(?i)bearer\s+[^\s"<>]+', 'Bearer [REDACTED]', detail)
            detail = re.sub(r'gsk_[A-Za-z0-9_-]+', '[REDACTED]', detail)
            detail = ' '.join(detail.split())[:500]
            message += f' Groq: {detail}'
    except (ValueError, AttributeError, TypeError, OSError):
        message += ' Нет структурированного описания ошибки; возможен ответ сетевого фильтра.'
    return message


class Client:
    def __init__(self):
        self.key = os.environ.get('GROQ_API_KEY', '').strip()
        self.model = os.environ.get('GROQ_MODEL', '').strip()
        if not self.key or not self.model:
            raise ServiceError('Настройте GROQ_API_KEY и GROQ_MODEL в окружении.')
        try:
            self.timeout = float(os.environ.get('LLM_TIMEOUT_SECONDS', '45'))
            if not 1 <= self.timeout <= 120:
                raise ValueError()
        except ValueError as exc:
            raise ServiceError('LLM_TIMEOUT_SECONDS должен быть числом от 1 до 120.') from exc

    def generate(self, system, user):
        payload = {'model': self.model, 'max_completion_tokens': 4096,
                   'response_format': {'type': 'json_object'},
                   'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
        request = Request('https://api.groq.com/openai/v1/chat/completions',
                          data=json.dumps(payload).encode('utf-8'),
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                   'User-Agent': 'MVP-product-service/0.1.0',
                                   'Authorization': f'Bearer {self.key}'}, method='POST')
        for attempt in range(2):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read(1_000_001))
                choice = data['choices'][0]
                if choice.get('finish_reason') != 'stop':
                    raise ServiceError('LLM не завершила ответ штатно; результат отклонён.')
                content = choice['message']['content']
                if not isinstance(content, str) or not content.strip():
                    raise ServiceError('API вернул пустой текст.')
                return content
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504, 529) and attempt == 0:
                    time.sleep(1)
                    continue
                raise ServiceError(http_error_message(exc, self.key)) from None
            except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError):
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise ServiceError('API недоступен или истёк таймаут.') from None
            except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                raise ServiceError('Некорректная структура ответа API.') from None
