"""LLM selects only catalogue IDs; all rendered text stays under local control."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .domain import ServiceError
from .grounded import grounded_result

PROMPT_VERSION = '2.0'
SYSTEM = (Path(__file__).resolve().parent.parent / 'prompts/selection.txt').read_text(encoding='utf-8')


def catalogue(product):
    titles = {'t0': product['name'][:70]}
    with_brand = f'{product["name"]} — {product["manufacturer"]}'
    if product['manufacturer'] and len(with_brand) <= 70:
        titles['t1'] = with_brand
    options = [product['name']]
    if product['manufacturer']:
        options.append(f'{product["name"]} {product["manufacturer"]}')
    options += [f'{product["name"]} характеристики', f'{product["name"]} описание', f'{product["name"]} параметры']
    unique = list(dict.fromkeys(options))
    return {
        'titles': titles,
        'specs': {f's{i}': {'name': key, 'value': value or 'данных нет'} for i, (key, value) in enumerate(product['specs'].items())},
        'queries': {f'q{i}': text for i, text in enumerate(unique)},
        'source_description': product['description'] or 'данных нет',
    }


def validate_plan(plan, source):
    if not isinstance(plan, dict) or set(plan) != {'title_id', 'spec_order', 'query_ids'}:
        raise ServiceError('План должен содержать ровно title_id, spec_order, query_ids.')
    if not isinstance(plan['title_id'], str) or plan['title_id'] not in source['titles']:
        raise ServiceError('План содержит неизвестный title_id.')
    for field, allowed in [('spec_order', source['specs']), ('query_ids', source['queries'])]:
        values = plan[field]
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ServiceError(f'{field}: требуется список строковых идентификаторов.')
        if len(values) != len(set(values)) or any(v not in allowed for v in values):
            raise ServiceError(f'{field}: повторные или неизвестные идентификаторы.')
    if set(plan['spec_order']) != set(source['specs']):
        raise ServiceError('spec_order: нужно сохранить все исходные характеристики.')
    if not 3 <= len(plan['query_ids']) <= 5:
        raise ServiceError('query_ids: нужно выбрать 3–5 запросов.')


def generate(product, missing, client):
    source = catalogue(product)
    initial = 'Выбери структуру карточки по каталогу JSON:\n' + json.dumps(source, ensure_ascii=False)
    user = initial
    attempts = 0
    for attempt in range(2):
        attempts += 1
        raw = client.generate(SYSTEM, user)
        try:
            plan = json.loads(raw)
            validate_plan(plan, source)
        except (ValueError, RecursionError, ServiceError) as exc:
            # Never echo arbitrary model text into a repair prompt or final output.
            if attempt == 1:
                raise ServiceError('LLM дважды вернула недопустимый план; карточка не создана.') from None
            reason = str(exc) if isinstance(exc, ServiceError) else 'Ответ не является корректным JSON.'
            user = initial + '\nПредыдущий выбор отклонён: ' + reason + '\nВерни исправленный план только из идентификаторов каталога.'
            continue
        break
    keys = list(product['specs'])
    selected_keys = [keys[int(ref[1:])] for ref in plan['spec_order']]
    result = grounded_result(product, missing, client.model,
                             spec_order=selected_keys, title=source['titles'][plan['title_id']],
                             queries=[source['queries'][ref] for ref in plan['query_ids']])
    result['characteristics'] = [{'name': key, 'value': product['specs'][key] or 'данных нет', 'source': f'specs.{key}'} for key in selected_keys]
    result['warnings'][0] = 'LLM выбрала структуру из допустимых блоков. Текст собран локально без свободного добавления характеристик.'
    result['metadata'].update({
        'provider': 'groq', 'assembly_mode': 'llm_selection_source_template',
        'prompt_version': PROMPT_VERSION, 'selection_attempts': attempts,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_sha256': hashlib.sha256(json.dumps(product, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(),
    })
    result['selection_plan'] = plan
    return result
