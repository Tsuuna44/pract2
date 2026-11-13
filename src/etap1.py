"""Этап 1. Минимальный прототип с конфигурацией (вариант 14). 
""" 
 
 
import argparse
import os
import re
import sys
 
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
 
 
class DepGraphError(Exception):
    """Базовая ошибка приложения: её текст видит пользователь."""
 
 
class ConfigError(DepGraphError):
    """Некорректные параметры командной строки."""
 
 
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
 
 
def config_items(config):
    """Параметры в виде пар (ключ, значение) для вывода на экран."""
    return [
        ("package", config.package),
        ("repo", config.repo),
        ("mode", config.mode),
        ("tree", config.tree),
    ]
 
 
def run(config):
    """Печатает все настраиваемые параметры (только для этапа 1)."""
    for key, value in config_items(config):
        print(f"{key}: {value}")
 
 
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
