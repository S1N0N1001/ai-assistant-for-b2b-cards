"""Input contracts and deterministic checks; no network access."""
import json
import re

PROMPT_VERSION = '1.3'


class ServiceError(Exception):
    """Safe, user-facing error."""


def parse_product(text):
    try:
        raw = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ServiceError('Некорректный входной JSON.') from exc
    if not isinstance(raw, dict):
        raise ServiceError('Корень JSON должен быть объектом.')
    product = {}
    missing = []
    for key in ('name', 'manufacturer', 'description'):
        value = raw.get(key)
        if value is None:
            value = ''
        if not isinstance(value, str):
            raise ServiceError(f'Поле {key} должно быть строкой.')
        product[key] = value.strip()
        if not product[key]:
            missing.append(key)
    specs = raw.get('specs')
    if specs is None:
        specs = {}
    if not isinstance(specs, dict):
        raise ServiceError('Поле specs должно быть объектом.')
    product['specs'] = {}
    for key, value in specs.items():
        if not key.strip() or (value is not None and not isinstance(value, str)):
            raise ServiceError('Характеристики: непустые имена и строковые значения либо null.')
        if key.strip() in product['specs']:
            raise ServiceError('Имена характеристик совпадают после удаления пробелов.')
        value = (value or '').strip()
        product['specs'][key.strip()] = value
        if not value:
            missing.append(f'specs.{key.strip()}')
    if not specs:
        missing.append('specs')
    if not product['name'] or not (any(product['specs'].values()) or product['description']):
        raise ServiceError('Нужны непустое name и хотя бы specs или description с техническими сведениями.')
    return product, missing


def numbers(text):
    return set(re.findall(r'\d+(?:[.,]\d+)?', text))


def check_draft(draft, product):
    if not isinstance(draft, dict):
        return ['Ответ должен быть JSON-объектом.']
    issues = []
    for field in ('seo_title', 'seo_description', 'commercial_block'):
        if not isinstance(draft.get(field), str) or not draft[field].strip():
            issues.append(f'{field}: требуется непустая строка.')
        else:
            draft[field] = draft[field].strip()
    title = draft.get('seo_title')
    description = draft.get('seo_description')
    if isinstance(title, str) and len(title) > 70:
        issues.append('seo_title: превышено 70 символов.')
    if isinstance(description, str) and not 800 <= len(description) <= 1200:
        issues.append(f'seo_description: сейчас {len(description)} символов, требуется 800–1200 символов. Целевой объём 900–1050; расширяйте только подтверждённые сведения, не выдумывайте свойства.')
    queries = draft.get('search_queries')
    if not isinstance(queries, list) or not 3 <= len(queries) <= 5 or any(not isinstance(q, str) or not q.strip() for q in queries):
        issues.append('search_queries: требуется 3–5 непустых строк.')
    elif len({q.strip().casefold() for q in queries}) != len(queries):
        issues.append('search_queries: запросы должны различаться.')
    for key in ('warnings', 'conflicts'):
        if not isinstance(draft.get(key), list) or any(not isinstance(v, str) for v in draft[key]):
            issues.append(f'{key}: требуется список строк.')
    allowed = numbers(json.dumps(product, ensure_ascii=False))
    generated = json.dumps({k: draft.get(k) for k in ('seo_title', 'seo_description', 'commercial_block', 'search_queries')}, ensure_ascii=False)
    if numbers(generated) - allowed:
        issues.append('В тексте найдены числовые значения, отсутствующие во входных данных.')
    source = json.dumps(product, ensure_ascii=False).casefold()
    # Regression guards for observed unsupported claims; not a full fact checker.
    claim_rules = [
        (r'компакт\w*', r'компакт\w*', 'компактность'),
        (r'стандартн\w*\s+трубопровод\w*', r'стандартн\w*\s+трубопровод\w*', 'стандартные трубопроводы'),
        (r'пыл\w*', r'пыл\w*', 'защита от пыли / расшифровка IP'),
        (r'отоплен\w*|водоснабжен\w*', r'отоплен\w*|водоснабжен\w*', 'отопление / водоснабжение'),
        (r'калибров\w*', r'калибров\w*', 'калибровка'),
        (r'цифров\w*|аналогов\w*', r'цифров\w*|аналогов\w*', 'тип индикации'),
        (r'част\w*\s+цикл\w*', r'част\w*\s+цикл\w*', 'ресурс циклов'),
        (r'прост\w*\s+монтаж\w*|л[её]гк\w*\s+установ\w*', r'прост\w*\s+монтаж\w*|л[её]гк\w*\s+установ\w*', 'простота монтажа'),
        (r'защит\w*\s+от\s+(?:\w+\s+){0,3}частиц\w*', r'защит\w*\s+от\s+(?:\w+\s+){0,3}частиц\w*', 'расшифровка защиты от частиц'),
        (r'без\s+дополнительн\w*\s+модификац\w*', r'без\s+дополнительн\w*\s+модификац\w*', 'работа без модификаций'),
    ]
    for claim, evidence, label in claim_rules:
        if re.search(claim, generated, re.IGNORECASE) and not re.search(evidence, source):
            issues.append(f'Неподтверждённая категория утверждений: {label}. Удалите её или уточните вход.')
    return issues


def assemble(product, missing, draft, issues, model):
    warnings = list(draft.get('warnings', [])) if isinstance(draft.get('warnings'), list) else []
    conflicts = draft.get('conflicts', [])
    if not isinstance(conflicts, list):
        conflicts = []
    warnings += issues
    warnings.append('Черновик: требуется ручная проверка всех технических утверждений.')
    if conflicts:
        warnings.append('Обнаружены возможные противоречия: требуется уточнение.')
    return {
        'status': 'needs_revision' if issues or conflicts else 'needs_review',
        'product_name': product['name'],
        'manufacturer': product['manufacturer'] or 'данных нет',
        **{k: draft.get(k) for k in ('seo_title', 'seo_description', 'search_queries', 'commercial_block')},
        'characteristics': [{'name': k, 'value': v or 'данных нет', 'source': f'specs.{k}'} for k, v in product['specs'].items()],
        'source_description': product['description'] or 'данных нет',
        'missing_fields': missing, 'conflicts': conflicts, 'warnings': warnings,
        'validation': {'automated_checks_passed': not issues, 'human_review_required': True},
        'metadata': {'provider': 'groq', 'model': model, 'prompt_version': PROMPT_VERSION},
    }
