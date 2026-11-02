import argparse
import json
from pathlib import Path
import sys
from .client import Client
from .domain import ServiceError, parse_product
from .selection import generate


def markdown(result):
    lines = [f'# {result["product_name"]}', '', f'Статус: {result["status"]}', '',
             '## SEO-заголовок', str(result['seo_title']), '', '## SEO-описание', str(result['seo_description']),
             '', '## Характеристики']
    lines += [f'- {v["name"]}: {v["value"]} (источник: {v["source"]})' for v in result['characteristics']]
    lines += ['', '## Поисковые запросы'] + [f'- {q}' for q in (result['search_queries'] or [])]
    lines += ['', '## Commercial-блок', str(result['commercial_block']), '', '## Пропуски']
    lines += [f'- {v}' for v in result['missing_fields']]
    lines += ['', '## Противоречия'] + [f'- {v}' for v in result['conflicts']]
    lines += ['', '## Предупреждения'] + [f'- {v}' for v in result['warnings']]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description='Генерация черновика B2B-карточки')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('output/card.json'))
    parser.add_argument('--validate-only', action='store_true', help='Проверить вход без API')
    args = parser.parse_args()
    try:
        text = args.input.read_text(encoding='utf-8-sig')
        if len(text) > 100_000:
            raise ServiceError('Вход превышает лимит 100 000 символов.')
        product, missing = parse_product(text)
        if args.validate_only:
            print(json.dumps({'valid': True, 'missing_fields': missing}, ensure_ascii=False, indent=2))
            return 0
        targets = [args.output, args.output.with_suffix('.md')]
        if args.output.suffix.lower() != '.json':
            raise ServiceError('--output должен иметь расширение .json.')
        if any(p.resolve() == args.input.resolve() or p.exists() for p in targets):
            raise ServiceError('Выходной файл уже существует или совпадает с входом. Выберите новое имя.')
        result = generate(product, missing, Client())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        for path, content in zip(targets, [json.dumps(result, ensure_ascii=False, indent=2) + '\n', markdown(result)]):
            with path.open('x', encoding='utf-8') as handle:
                handle.write(content)
        print(f'Сохранено: {args.output} и {targets[1]}; статус: {result["status"]}')
        return 3 if result['status'] == 'needs_revision' else 0
    except (ServiceError, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, ServiceError) else 'Ошибка чтения или записи файла. Проверьте путь, права и UTF-8.'
        print(f'Ошибка: {message}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
