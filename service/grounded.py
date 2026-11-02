"""Conservative editorial assembly. Product facts are copied, never inferred."""
from .domain import assemble, check_draft


def grounded_result(product, missing, model, *, spec_order=None, title=None, queries=None):
    name = product['name']
    manufacturer = product['manufacturer'] or 'данных нет'
    spec_keys = list(product['specs']) if spec_order is None else spec_order
    specs = '; '.join(f'{key}: {product["specs"][key] or "данных нет"}' for key in spec_keys) or 'данных нет'
    description = product['description'] or 'данных нет'
    text = (
        f'{name}. Производитель: {manufacturer}. '
        f'Назначение и условия применения по предоставленному описанию: {description}\n\n'
        f'Основные параметры из исходной спецификации: {specs}.\n\n'
        'При выборе сопоставьте перечисленные параметры и условия применения с требованиями вашей задачи. '
        'Указанные значения следует рассматривать совместно: совпадение одного параметра не подтверждает '
        'соответствие прибора всем требованиям. Обозначения и единицы приведены в исходном виде. '
        'Сведения, отсутствующие в предоставленном описании и спецификации, необходимо уточнить перед заказом. '
        'Этот текст подготовлен по переданным данным и не заменяет полный технический паспорт изделия.'
    )
    queries = queries if queries is not None else [name, f'{name} {manufacturer}' if product['manufacturer'] else f'{name} описание', f'{name} характеристики']
    draft = {
        'seo_title': title if title is not None else (name if len(name) <= 70 else name[:70]),
        'seo_description': text,
        'search_queries': queries,
        'commercial_block': f'Для задач, соответствующих следующему назначению и условиям: {description}',
        'warnings': ['Текст собран по фиксированному шаблону из входных данных; свободный ответ LLM не используется как готовая карточка.'],
        'conflicts': [],
    }
    issues = check_draft(draft, product)
    result = assemble(product, missing, draft, issues, model)
    result['metadata'].update({'assembly_mode': 'source_template', 'template_version': '1.0',
                               'prompt_version': None})
    return result
