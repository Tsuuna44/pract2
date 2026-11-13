"""Этап 2. Сбор данных: прямые зависимости пакета Cargo (вариант 14).
"""
  
  
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
 
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse
 
 
MODE_REAL = "real"
"""Работа с реальным реестром Cargo."""

MODE_TEST = "test"
"""Работа с тестовым файлом-графом."""

MODES = (MODE_REAL, MODE_TEST)
"""Допустимые значения параметра --mode."""

URL_SCHEMES = ("http", "https")
"""Допустимые схемы URL."""

DEFAULT_INDEX_URL = "https://index.crates.io"
"""Реестр по умолчанию."""

CRATE_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
"""Регулярное выражение для имени пакета Cargo."""

TEST_NAME_RE = re.compile(r"[A-Z]+")
"""Регулярное выражение для имени в тесте (заглавные буквы)."""

EXIT_OK = 0
"""Код выхода при успехе."""

EXIT_ERROR = 2
"""Код выхода при ошибке."""

TIMEOUT_SECONDS = 20
"""Сколько секунд ждём ответа сервера."""

USER_AGENT = "depgraph-lab/1.0"
"""Строка User-Agent для HTTP-запросов."""

HTTP_NOT_FOUND = 404
"""Код HTTP 'файл не найден'."""

DEPENDENCY_KINDS = ("normal", "build")
"""Какие типы зависимостей учитываем."""

ONE_LETTER_DIRS = {1: "1", 2: "2"}
"""Каталоги для имён пакетов из 1-2 букв."""

THREE_LETTERS = 3
"""Количество букв, при котором имя лежит в 3/<первая буква>/."""

PREFIX_LEN = 2
"""Длина части имени в пути индекса."""

TREE_MIDDLE = "|-- "
"""Ветка, после которой есть ещё ветки."""

TREE_LAST = "`-- "
"""Последняя ветка уровня."""

INDENT_MIDDLE = "|   "
"""Отступ под средней веткой."""

INDENT_LAST = "    "
"""Отступ под последней веткой."""

MARK_REPEAT = " (*)"
"""Пометка: поддерево этого узла уже показано выше."""

MARK_CYCLE = " (цикл)"
"""Пометка: узел уже есть среди своих предков."""
 
 
class DepGraphError(Exception):
    """Базовая ошибка приложения: её текст видит пользователь."""
 
 
class ConfigError(DepGraphError):
    """Некорректные параметры командной строки."""
 
 
class RepoError(DepGraphError):
    """Не удалось получить данные из репозитория."""
 
 
@dataclass
class Config:
    """Все настраиваемые пользователем параметры."""
 
    package: str
    """Имя анализируемого пакета."""
    repo: str
    """URL реестра или путь к файлу."""
    mode: str
    """Режим работы: real или test."""
    tree: bool
    """Выводить ли ASCII-дерево."""
 
 
class ArgumentParser(argparse.ArgumentParser):
    """Разборщик, превращающий ошибки argparse в ConfigError."""
 
    def error(self, message):
        """Вместо печати usage и выхода бросает наше исключение."""
        raise ConfigError(message)
 
 
def _add_core_options(parser):
    """Добавляет четыре основные настраиваемые опции."""
    parser.add_argument(
        "-p", "--package", required=True,
        help="имя анализируемого пакета")
    parser.add_argument(
        "-r", "--repo",
        help="URL репозитория (real) или путь к файлу графа (test)")
    parser.add_argument(
        "-m", "--mode", choices=MODES, default=MODE_REAL,
        help="режим: real - реальный репозиторий, test - тестовый")
    parser.add_argument(
        "-t", "--tree", action="store_true",
        help="вывести зависимости в виде ASCII-дерева")
 
 
def build_parser():
    """Создаёт разборщик командной строки."""
    parser = ArgumentParser(
        prog="depgraph",
        description="Визуализация графа зависимостей пакетов Cargo")
    _add_core_options(parser)
    return parser
 
 
def validate_package(name, mode):
    """Проверяет имя пакета с учётом режима работы."""
    if not name.strip():
        raise ConfigError("имя пакета не может быть пустым")
    if mode == MODE_TEST:
        pattern, hint = TEST_NAME_RE, "заглавные латинские буквы"
    else:
        pattern, hint = CRATE_NAME_RE, "латиница, цифры, '-' и '_'"
    if not pattern.fullmatch(name):
        raise ConfigError(
            f"недопустимое имя пакета '{name}': ожидаются {hint}")
 
 
def _check_url(url):
    """Проверяет, что строка - корректный http(s)-адрес."""
    parts = urlparse(url)
    if parts.scheme not in URL_SCHEMES or not parts.netloc:
        raise ConfigError(
            f"'{url}' не похож на URL (нужен http:// или https://)")
 
 
def _check_file(path):
    """Проверяет, что файл тестового репозитория существует."""
    if not os.path.isfile(path):
        raise ConfigError(f"файл тестового репозитория не найден: {path}")
 
 
def validate_repo(repo, mode):
    """Проверяет значение репозитория согласно режиму."""
    if mode == MODE_TEST:
        _check_file(repo)
    else:
        _check_url(repo)
 
 
def validate_config(config):
    """Полная проверка всех параметров."""
    validate_package(config.package, config.mode)
    validate_repo(config.repo, config.mode)
 
 
def resolve_repo(repo, mode):
    """Подставляет репозиторий по умолчанию для режима real."""
    if repo is not None:
        return repo
    if mode == MODE_REAL:
        return DEFAULT_INDEX_URL
    raise ConfigError("в режиме test нужно указать --repo (файл графа)")
 
 
def parse_args(argv: Optional[List[str]] = None):
    """Разбирает аргументы и возвращает проверенный Config."""
    args = build_parser().parse_args(argv)
    config = Config(
        package=args.package,
        repo=resolve_repo(args.repo, args.mode),
        mode=args.mode,
        tree=args.tree)
    validate_config(config)
    return config
 
 
def index_path(name):
    """Путь файла пакета в индексе: 1/a, 2/ab, 3/a/abc, ab/cd/abcd."""
    lower = name.lower()
    short = ONE_LETTER_DIRS.get(len(lower))
    if short:
        return f"{short}/{lower}"
    if len(lower) == THREE_LETTERS:
        return f"3/{lower[0]}/{lower}"
    first = lower[:PREFIX_LEN]
    second = lower[PREFIX_LEN:PREFIX_LEN * 2]
    return f"{first}/{second}/{lower}"
 
 
def index_url(base_url, name):
    """Полный URL файла пакета в индексе."""
    return base_url.rstrip("/") + "/" + index_path(name)
 
 
def fetch_text(url):
    """Скачивает текст по URL, ошибки сети превращает в RepoError."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            raise RepoError(f"пакет не найден в репозитории: {url}")
        raise RepoError(f"HTTP-ошибка {error.code} для {url}")
    except (urllib.error.URLError, OSError, UnicodeError) as error:
        raise RepoError(f"не удалось получить {url}: {error}")
 
 
def parse_records(text):
    """Разбирает файл индекса: одна JSON-запись на строку."""
    records = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            raise RepoError("файл индекса повреждён (не JSON)")
    return records
 
 
def version_key(version):
    """Ключ сортировки версии: релизы выше пререлизов, затем числа."""
    main_part = version.split("+")[0]
    is_stable = "-" not in main_part
    core = main_part.split("-")[0]
    numbers = tuple(
        int(part) if part.isdigit() else 0 for part in core.split("."))
    return (is_stable, numbers)
 
 
def pick_latest(records, package):
    """Выбирает последнюю не отозванную (yanked) версию пакета."""
    alive = [rec for rec in records if not rec.get("yanked")]
    pool = alive or records
    if not pool:
        raise RepoError(f"у пакета '{package}' нет версий")
    return max(pool, key=lambda rec: version_key(rec["vers"]))
 
 
def direct_dependencies(record):
    """Имена прямых зависимостей версии (normal и build, не optional)."""
    names = set()
    for dep in record.get("deps", []):
        kind = dep.get("kind") or "normal"
        if dep.get("optional") or kind not in DEPENDENCY_KINDS:
            continue
        names.add(dep.get("package") or dep["name"])
    return sorted(names)
 
 
def get_package_info(base_url, package):
    """Возвращает (версия, список прямых зависимостей) пакета."""
    text = fetch_text(index_url(base_url, package))
    latest = pick_latest(parse_records(text), package)
    return latest["vers"], direct_dependencies(latest)
 
 
def make_cargo_fetcher(base_url):
    """Возвращает функцию имя -> прямые зависимости для build_graph."""
    def fetch(name):
        """Прямые зависимости пакета из реального репозитория."""
        return get_package_info(base_url, name)[1]
    return fetch
 
 
def _child_items(children, prefix, depth):
    """Дети узла в виде элементов стека обхода дерева."""
    last_index = len(children) - 1
    return [(child, prefix, index == last_index, depth)
            for index, child in enumerate(children)]
 
 
def _mark(node, path, seen, adjacency):
    """Пометка узла: цикл, повтор раскрытого поддерева или ничего."""
    if node in path:
        return MARK_CYCLE
    if node in seen and adjacency.get(node):
        return MARK_REPEAT
    return ""
 
 
def ascii_tree(root, adjacency):
    """Строит ASCII-дерево зависимостей итеративно (без рекурсии).
 
    path - предки текущего узла (поиск циклов), seen - уже раскрытые
    узлы: их повторы помечаются (*) и повторно не раскрываются.
    """
    lines = [root]
    seen = {root}
    path = [root]
    stack = list(reversed(_child_items(adjacency.get(root, []), "", 1)))
    while stack:
        node, prefix, is_last, depth = stack.pop()
        del path[depth:]
        mark = _mark(node, path, seen, adjacency)
        connector = TREE_LAST if is_last else TREE_MIDDLE
        lines.append(prefix + connector + node + mark)
        if mark:
            continue
        seen.add(node)
        path.append(node)
        indent = INDENT_LAST if is_last else INDENT_MIDDLE
        items = _child_items(
            adjacency.get(node, []), prefix + indent, depth + 1)
        stack.extend(reversed(items))
    return "\n".join(lines)
 
 
def run(config):
    """Печатает прямые зависимости пакета (только для этапа 2)."""
    if config.mode == MODE_TEST:
        raise ConfigError("режим test будет реализован на этапе 3")
    version, deps = get_package_info(config.repo, config.package)
    print(f"Прямые зависимости {config.package} {version}:")
    if config.tree:
        print(ascii_tree(config.package, {config.package: deps}))
        return
    for name in deps:
        print(f"  {name}")
    if not deps:
        print("  (нет)")
 
 
def main(argv=None):
    """Главная функция: возвращает код выхода процесса."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        run(parse_args(argv))
    except DepGraphError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK
 
 
if __name__ == "__main__":
    sys.exit(main())
