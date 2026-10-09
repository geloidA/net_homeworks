import re
import requests
from typing import Any

class UnknownInstructionError(Exception):
    ...

USER_TOKEN = '623b09e1ec6b957fd4ed6a3b9e84685a'

ACTIONS = [
    ("GET",     'GET-запрос'),
    ("GET",     'Перейдите по'),
    ("POST",    'POST-запрос'),
    ("UPLOAD",  'Загрузите файлы'),
]

TABLE_ROLES = [
    ("headers", 'заголовк'),
    ("cookies", "cookie"),
    ("form", "данные формы"),
    ("params", "параметры запроса"),
    ("files", "Загрузите файлы"),
]


def parse_table(table_html: str) -> dict:
    """Пары <code>key</code> → <code>value</code> из таблицы."""
    values = re.findall(r'<code>(.*?)</code>', table_html, flags=re.DOTALL)
    return dict(zip(values[0::2], values[1::2]))


def detect_action(html: str) -> str:
    for name, text_to_find in ACTIONS:
        if html.find(text_to_find) != -1:
            return name
    raise UnknownInstructionError(
        "Не удалось распознать действие. Поддерживаются: "
        "'GET-запрос', 'POST-запрос', 'Загрузите файлы', 'Перейдите по ссылке'."
    )


def detect_table_role(preceding_text: str) -> str:
    for role, text_to_find in TABLE_ROLES:
        if preceding_text.rfind(text_to_find) != -1:
            return role
    raise UnknownInstructionError(
        "Не удалось распознать назначение таблицы. "
        f"Текст перед таблицей: ...{preceding_text[-200:]!r}"
    )


def extract_url(html: str) -> str:
    """Извлекает URL из инструкции: либо <code>/...</code>, либо <a href="/...">."""
    # Вариант 1: "по адресу <code>/...</code>"
    m = re.search(r'по адресу <code>(.*?)</code>', html, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Вариант 2: "Перейдите по <a href="/...">ссылке</a>"
    m = re.search(r'<a href=["\'](.*)["\']', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    raise UnknownInstructionError(
        "Не найден URL в инструкции (ни 'по адресу <code>...</code>', ни '<a href=\"...\">'). "
        f"Начало страницы: {html[:200]!r}"
    )


def make_request(url: str,
                 action: str,
                 params: dict) -> requests.Response:
    if action == "GET":
        return requests.get(url, **params)
    if action == "POST":
        return requests.post(url, **params)
    if action == "UPLOAD":
        return requests.post(url, **params)

    raise UnknownInstructionError(f"Неизвестное действие: {action!r}")


def get_request_parameters(instruction: dict, action: str) -> dict:
    kwargs: dict = {"cookies": {"user": USER_TOKEN}}

    if "headers" in instruction:
        kwargs["headers"] = instruction["headers"]
    if "cookies" in instruction:
        for name, content in instruction["cookies"].items():
            kwargs["cookies"][name] = content
    if "params" in instruction:
        kwargs["params"] = instruction["params"]

    if action == "POST":
        kwargs["data"] = instruction.get("form", {})
    if action == "UPLOAD":
        kwargs["files"] = {
            name: (name, content.encode("utf-8"))
            for name, content in instruction.get("files", {}).items()
        }

    return kwargs


def execute(instruction: dict,
            base_url: str) -> requests.Response:
    action = instruction["action"]
    url = base_url.rstrip("/") + "/" + instruction["url"].lstrip("/")
    params = get_request_parameters(instruction, action)

    return make_request(url, action, params)


def parse_instruction(html: str) -> dict:
    action = detect_action(html)
    url = extract_url(html)

    instruction: dict[str, Any] = {"action": action, "url": url}

    # Разбиваем HTML вокруг таблиц; чётные куски — текст перед таблицами
    parts = re.split(r'(<table\b[^>]*>.*?</table>)', html, flags=re.DOTALL | re.IGNORECASE)
    for i in range(1, len(parts), 2):
        role = detect_table_role(parts[i - 1])
        instruction[role] = parse_table(parts[i])

    return instruction


def process_response(html: str,
                     base_url: str) -> str:
    try:
        instruction = parse_instruction(html)
    except UnknownInstructionError as e:
        raise UnknownInstructionError(
            f"Не удалось разобрать инструкцию: {e}\n"
            f"HTML (первые 500 символов): {html[:500]!r}"
        ) from e

    print(f"→ {instruction['action']}")

    response = execute(instruction, base_url)
    response.raise_for_status()
    return response.text


def has_action(html: str) -> bool:
    return any(html.find(p) != -1 for _, p in ACTIONS)


if __name__ == "__main__":
    base_url = 'http://hw1.alexbers.com/'
    private_token = 'Undefined'

    try:
        response = requests.get(base_url, cookies={"user": USER_TOKEN})
        response.raise_for_status()
        html = response.text

        for step in range(1000):
            if not has_action(html):
                print("=" * 60)
                print(html)
                break
            print(f"[шаг {step}] ", end='')
            html = process_response(html, base_url)

    except UnknownInstructionError as exc:
        print(f"ОШИБКА: {exc}")
