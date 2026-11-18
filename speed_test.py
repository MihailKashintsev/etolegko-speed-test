"""Measure sequential HTTP download throughput using only the standard library."""

import argparse
import math
import os
import sys
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024


def styled(text, color="36", stream=None):
    stream = stream if stream is not None else sys.stdout
    if stream.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb":
        return f"\033[{color}m{text}\033[0m"
    return text


def http_url(value):
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname
        parsed.port  # Validate malformed ports before making a request.
    except ValueError as error:
        raise argparse.ArgumentTypeError("Некорректный HTTP(S)-адрес") from error
    if not valid or parsed.username is not None or parsed.password is not None:
        raise argparse.ArgumentTypeError("Нужен HTTP(S)-адрес без логина и пароля")
    return value


def positive_seconds(value):
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Тайм-аут должен быть положительным числом") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("Тайм-аут должен быть конечным числом больше нуля")
    return seconds


def download(url, timeout):
    request = Request(url, headers={
        "User-Agent": "ETOLegko-SpeedTest/1.0",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
    })
    size = 0
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        while chunk := response.read(CHUNK_SIZE):
            size += len(chunk)
        expected = response.headers.get("Content-Length")
        if expected is not None and size != int(expected):
            raise OSError("Ответ оборвался: полученный объём отличается от Content-Length")
    return size, time.perf_counter() - started


def measure(url, timeout=30.0):
    total_bytes = 0
    total_seconds = 0.0
    for index in range(1, REQUEST_COUNT + 1):
        size, seconds = download(url, timeout)
        total_bytes += size
        total_seconds += seconds
        bar = styled("█" * index + "░" * (REQUEST_COUNT - index))
        print(f"  {bar}  {index:02d}/{REQUEST_COUNT}  {size:>12,} байт  {seconds:8.3f} с", flush=True)
    return total_bytes, total_seconds


def main(argv=None):
    parser = argparse.ArgumentParser(description="10 последовательных HTTP-загрузок и их средняя скорость")
    parser.add_argument("url", type=http_url, help="Прямой HTTP(S)-адрес файла; заключите в кавычки")
    parser.add_argument("--timeout", type=positive_seconds, default=30.0,
                        help="Тайм-аут сетевой операции в секундах (по умолчанию 30)")
    args = parser.parse_args(argv)
    print(styled("\n  HTTP DOWNLOAD · SPEED TEST", "1;36"))
    print("  10 последовательных запросов · Python stdlib")
    print(styled("  " + "─" * 58, "90"))
    print("  ПРОГРЕСС     ЗАПРОС           ОБЪЁМ      ВРЕМЯ\n", flush=True)
    try:
        size, seconds = measure(args.url, args.timeout)
    except (URLError, OSError, ValueError) as error:
        print(styled(f"\n  ОШИБКА · {error}", "1;31", sys.stderr), file=sys.stderr)
        print("  Замер не завершён; итоговая скорость не рассчитана.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nЗамер отменён.", file=sys.stderr)
        return 130
    print(styled("\n  " + "─" * 58, "90"))
    print(styled("  ЗАМЕР ЗАВЕРШЁН", "1;32"))
    print(f"  Запросов:             {REQUEST_COUNT}/{REQUEST_COUNT}")
    print(f"  Среднее время:        {seconds / REQUEST_COUNT:.3f} с")
    print(f"  Всего скачано:        {size:,} байт ({size / 1024**2:.3f} МиБ)")
    print(f"  Общее время запросов: {seconds:.3f} с")
    if seconds > 0:
        print(styled(f"  Скорость скачивания:  {size / seconds / 1024**2:.3f} МиБ/с", "1;36"))
        print(f"                        {size * 8 / seconds / 1_000_000:.3f} Мбит/с")
        print("\n  Скорость до выбранного сервера, не всего интернет-канала.\n")
    else:
        print("Скорость не рассчитана: длительность ниже разрешения таймера.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
