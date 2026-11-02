"""Build an explicitly labelled editorial example using an existing API draft."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from service.domain import ServiceError, parse_product
from service.grounded import grounded_result
from service.__main__ import markdown


def main():
    parser = argparse.ArgumentParser(description='Сборка из исходных данных без нового API-запроса')
    parser.add_argument('input', type=Path)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        product, missing = parse_product(args.input.read_text(encoding='utf-8-sig'))
        candidate = json.loads(args.candidate.read_text(encoding='utf-8'))
        if candidate.get('product_name') != product['name'] or candidate.get('source_description') != (product['description'] or 'данных нет'):
            raise ServiceError('Черновик относится к другому входу.')
        expected = [{'name': k, 'value': v or 'данных нет', 'source': f'specs.{k}'} for k, v in product['specs'].items()]
        if candidate.get('characteristics') != expected or candidate.get('manufacturer') != (product['manufacturer'] or 'данных нет'):
            raise ServiceError('Характеристики черновика отличаются от входа.')
        if args.output.suffix != '.json':
            raise ServiceError('Выход должен быть .json.')
        targets = [args.output, args.output.with_suffix('.md')]
        if any(path.exists() for path in targets):
            raise ServiceError('Выход уже существует; выберите другое имя.')
        result = grounded_result(product, missing, candidate.get('metadata', {}).get('model', 'unknown'))
        result['metadata']['candidate_file'] = args.candidate.name
        result['metadata']['candidate_prompt_version'] = candidate.get('metadata', {}).get('prompt_version')
        result['metadata']['candidate_provider'] = candidate.get('metadata', {}).get('provider')
        result['metadata']['provider'] = 'local_source_template'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        for path, value in zip(targets, [json.dumps(result, ensure_ascii=False, indent=2) + '\n', markdown(result)]):
            with path.open('x', encoding='utf-8') as handle:
                handle.write(value)
        print(f'Сохранена шаблонная редакция: {args.output}; статус: {result["status"]}')
        return 3 if result['status'] == 'needs_revision' else 0
    except (ServiceError, OSError, ValueError, TypeError, AttributeError) as exc:
        print(str(exc) if isinstance(exc, ServiceError) else 'Не удалось прочитать данные или записать результат.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
