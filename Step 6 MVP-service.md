# Step 6 MVP-service

Дата: 02.11.2026. Статус: переход клиента на Groq реализован; локальная настройка ключа и реальная генерация ожидаются.

## Цель
Использовать аккаунт Groq, выбранный пользователем, вместо первоначально предложенного Anthropic.

## Выполнено
- Клиент переведён на https://api.groq.com/openai/v1/chat/completions и Bearer-авторизацию.
- Конфигурация: GROQ_API_KEY, GROQ_MODEL, LLM_TIMEOUT_SECONDS. Переменные Anthropic больше не используются.
- Системный и пользовательский промпты передаются отдельными messages. Используется JSON Object Mode, локальная проверка схемы сохранена.
- Разбирается choices[0].message.content; принимается только finish_reason=stop. Усечённые ответы отклоняются.
- Метаданные результата указывают provider=groq.
- Для первого прогона выбрана openai/gpt-oss-20b: модель присутствует в документации Groq и на скриншоте пользователя. Наличие карточки на скриншоте не доказывает права конкретного API-ключа.
- Обновлены README, .env.example, журнал решений и заметки о генерации.

## Проверка
Обновлены тесты HTTP-контракта: URL, Bearer, messages, JSON-режим, разбор ответа. Добавлены случаи пустого choices и завершения по лимиту токенов. Полный набор — 14 тестов, без обращения к сети. Все 14 тестов пройдены на Python 3.12.14; реальная интеграция с аккаунтом не проверялась.

## Действия пользователя для настройки
1. Открыть https://console.groq.com/keys и создать ключ с названием MVP-service (или использовать существующий подходящий ключ).
2. Открыть PowerShell в папке проекта.
3. Ввести ключ скрыто через окно учётных данных; никакой ключ не вставляется в исходный код или чат:

```powershell
$apiCredential = Get-Credential -UserName 'api' -Message 'Введите Groq API-ключ в поле пароля'
$env:GROQ_API_KEY = $apiCredential.GetNetworkCredential().Password
$env:GROQ_MODEL = 'openai/gpt-oss-20b'
$env:LLM_TIMEOUT_SECONDS = '45'
```

Переменные действуют в этом окне PowerShell и в запускаемых из него процессах. Они не передаются автоматически в уже работающий Codex. .env автоматически не загружается.

4. После настройки в том же окне можно выполнить реальный прогон:

```powershell
python -m service examples/inputs/product_01.json --output examples/outputs/product_01.json
python -m service examples/inputs/product_02.json --output examples/outputs/product_02.json
```

Если python отсутствует в PATH, использовать полный путь к установленному Python; доступный в текущем Codex интерпретатор указан в инструкции пользователю. Файлы результата не перезаписываются: при повторе выбрать новое имя.

## Источники
- https://console.groq.com/docs/openai
- https://console.groq.com/docs/text-chat
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/models

## Необходимый флаг
Ключ должен быть настроен локально. До получения фактических файлов вывода API-интеграция и примеры не объявляются проверенными. Следующий шаг 7 фиксирует реальные ответы, длины полей и сверку всех технических фактов.
