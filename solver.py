import re
from typing import Any

import requests

class UnknownInstructionError(Exception):
    ...

USER_TOKEN = '623b09e1ec6b957fd4ed6a3b9e84685a'

ACTIONS = [
    ("GET",    re.compile(r'\bGET[- ]?запрос',      re.IGNORECASE)),
    ("GET",    re.compile(r'Перейдите по', re.IGNORECASE)),
    ("POST",   re.compile(r'\bPOST[- ]?запрос',     re.IGNORECASE)),
    ("UPLOAD", re.compile(r'Загрузите\s+файлы',     re.IGNORECASE)),
]

TABLE_ROLES = [
    (re.compile(r'заголовк',                 re.IGNORECASE), "headers"),
    (re.compile(r'cookie',                   re.IGNORECASE), "cookies"),
    (re.compile(r'данны[ех]\s+формы',        re.IGNORECASE), "form"),
    (re.compile(r'параметр[а-я]*\s+запроса', re.IGNORECASE), "params"),
    (re.compile(r'содержимым',               re.IGNORECASE), "files"),
]

def extract_tables(html: str) -> list[str]:
    """Возвращает список HTML-фрагментов <table>...</table>."""
    return re.findall(r'<table\b[^>]*>.*?</table>', html, re.DOTALL | re.IGNORECASE)


def parse_table(table_html: str) -> dict:
    """Пары <code>key</code> → <code>value</code> из таблицы."""
    values = re.findall(r'<code>(.*?)</code>', table_html, flags=re.DOTALL)
    return dict(zip(values[0::2], values[1::2]))


def detect_action(html: str) -> str:
    for name, pattern in ACTIONS:
        if pattern.search(html):
            return name
    raise UnknownInstructionError(
        "Не удалось распознать действие. Поддерживаются: "
        "'GET-запрос', 'POST-запрос', 'Загрузите файлы', 'Перейдите по ссылке'."
    )


def has_action(html: str) -> bool:
    return any(p.search(html) for _, p in ACTIONS)


def detect_table_role(preceding_text: str) -> str:
    for pattern, role in TABLE_ROLES:
        if pattern.search(preceding_text):
            return role
    raise UnknownInstructionError(
        "Не удалось распознать назначение таблицы. "
        f"Текст перед таблицей: ...{preceding_text[-200:]!r}"
    )


def extract_url(html: str) -> str:
    """Извлекает URL из инструкции: либо <code>/...</code>, либо <a href="/...">."""
    # Вариант 1: "по адресу <code>/...</code>"
    m = re.search(r'по\s+адресу\s*<code>(.*?)</code>', html, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Вариант 2: "Перейдите по <a href="/...">ссылке</a>"
    m = re.search(r'<a\s+[^>]*href\s*=\s*["\']?([^"\'>\s]+)["\']?', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    raise UnknownInstructionError(
        "Не найден URL в инструкции (ни 'по адресу <code>...</code>', ни '<a href=\"...\">'). "
        f"Начало страницы: {html[:200]!r}"
    )


def execute(instruction: dict,
            session: requests.Session,
            base_url: str) -> requests.Response:
    action = instruction["action"]
    url = base_url.rstrip("/") + "/" + instruction["url"].lstrip("/")

    kwargs: dict = { "cookies": {"user": USER_TOKEN} }

    if "headers" in instruction:
        kwargs["headers"] = instruction["headers"]
    if "cookies" in instruction:
        for name, content in instruction["cookies"].items():
            kwargs["cookies"][name] = content
    if "params" in instruction:
        kwargs["params"] = instruction["params"]

    if action == "GET":
        return session.get(url, **kwargs)

    if action == "POST":
        kwargs["data"] = instruction.get("form", {})
        return session.post(url, **kwargs)

    if action == "UPLOAD":
        kwargs["files"] = {
            name: (name, content.encode("utf-8"))
            for name, content in instruction.get("files", {}).items()
        }
        return session.post(url, **kwargs)

    raise UnknownInstructionError(f"Неизвестное действие: {action!r}")


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
                     session: requests.Session,
                     base_url: str) -> str:
    try:
        instruction = parse_instruction(html)
    except UnknownInstructionError as e:
        raise UnknownInstructionError(
            f"Не удалось разобрать инструкцию: {e}\n"
            f"HTML (первые 500 символов): {html[:500]!r}"
        ) from e

    print(f"→ {instruction['action']} {instruction['url']}")

    response = execute(instruction, session, base_url)
    response.raise_for_status()
    return response.text


if __name__ == "__main__":
    base_url = 'http://hw1.alexbers.com/'
    private_token = 'Undefined'

    try:
        session = requests.Session()

        response = session.get(base_url, cookies={"user": USER_TOKEN})
        response.raise_for_status()
        html = response.text

        for step in range(1000):
            if not has_action(html):
                print("=" * 60)
                print(html)

            print(f"[шаг {step}] ", end='')
            html = process_response(html, session, base_url)

    except UnknownInstructionError as exc:
        print(f"ОШИБКА: {exc}")
