"""Generate readable text and standalone HTML from the project's Markdown sources."""
from html import escape
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def render(markdown):
    parts, code, buffer, headings = [], False, [], []
    for line in markdown.splitlines():
        if line.startswith('```'):
            if code:
                parts.append('<pre><code>' + escape('\n'.join(buffer)) + '</code></pre>')
                buffer = []
            code = not code
        elif code:
            buffer.append(line)
        elif line.startswith('#'):
            level = min(len(line) - len(line.lstrip('#')), 6)
            title = escape(line.lstrip('#').strip())
            anchor = f'section-{len(headings)}'
            headings.append((anchor, title))
            parts.append(f'<h{level} id="{anchor}">' + title + f'</h{level}>')
        elif line.strip():
            safe = escape(line)
            safe = re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)', r'<a href="\2">\1</a>', safe)
            parts.append('<p>' + safe + '</p>')
    toc = '<nav aria-label="Оглавление"><strong>Оглавление</strong><ul>' + ''.join(
        f'<li><a href="#{anchor}">{title}</a></li>' for anchor, title in headings
    ) + '</ul></nav>'
    return toc + '\n'.join(parts)


def main():
    for filename, html in [('README.md', True), ('docs/PROMPTS_AND_DECISIONS.md', False),
                           ('docs/LIMITATIONS_AND_IMPROVEMENTS.md', True)]:
        path = ROOT / filename
        text = path.read_text(encoding='utf-8')
        if path.stem == 'PROMPTS_AND_DECISIONS':
            marker = '\n## Точная копия системного промпта\n'
            text = text.split(marker)[0] + marker + '\nАктивный промпт 2.0 (prompts/selection.txt):\n\n```text\n' + (ROOT / 'prompts/selection.txt').read_text(encoding='utf-8') + '```\n'
            path.write_text(text, encoding='utf-8')
        path.with_suffix('.txt').write_text(text, encoding='utf-8')
        if html:
            page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Документация MVP</title><style>body{font:17px/1.65 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#172b40;background:#f8fafc}h1,h2{line-height:1.25;color:#173b68}h2{margin-top:2em}p{overflow-wrap:anywhere}pre{background:#14263c;color:#edf5ff;padding:20px;border-radius:8px;overflow:auto;white-space:pre-wrap}a{color:#1454a0}header{border-bottom:2px solid #d8e3f0;padding-bottom:16px}</style><header>AI-помощник · Документация локального MVP</header><main>'''
            path.with_suffix('.html').write_text(page + render(text) + '</main></html>\n', encoding='utf-8')
    print('Документация экспортирована: README TXT/HTML; промпты TXT; ограничения TXT/HTML.')


if __name__ == '__main__':
    main()
