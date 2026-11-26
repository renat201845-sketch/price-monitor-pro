import argparse
import json
import logging
from pathlib import Path

from db import add_price_record, get_all_stats, get_item_history, init_db, upsert_item
from fetcher import get_item_price
from notifier import notify_deal

logger = logging.getLogger("price_monitor")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Не найден конфигурационный файл: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_check(config: dict, base_dir: Path) -> None:
    db_path = base_dir / config.get("db_file", "prices.db")
    init_db(db_path)

    timeout = int(config.get("request_timeout", 10))
    tg_cfg = config.get("telegram", {})
    items = config.get("items", [])

    if not items:
        print("Список товаров (items) в config.json пуст.")
        return

    print(f"\n=== Проверка цен ({len(items)} товаров) ===")
    for entry in items:
        name = entry["name"]
        url = entry["url"]
        selector = entry.get("selector")
        currency = entry.get("currency", "PLN")
        target_price = entry.get("target_price")
        fallback_price = entry.get("fallback_price")

        item_id = upsert_item(
            db_path=db_path,
            name=name,
            url=url,
            target_price=float(target_price) if target_price is not None else None,
            currency=currency,
        )

        price, source = get_item_price(
            url=url,
            timeout=timeout,
            fallback_price=fallback_price,
            selector=selector,
        )
        if price is None:
            print(f"[SKIP] {name}: не удалось получить цену.")
            continue

        add_price_record(db_path=db_path, item_id=item_id, price=price, source=source)
        print(f"[OK]   {name}: {price:.2f} {currency} ({source})")

        if target_price is not None and price <= float(target_price):
            notify_deal(name, price, float(target_price), currency, tg_cfg)


def cmd_stats(config: dict, base_dir: Path) -> None:
    db_path = base_dir / config.get("db_file", "prices.db")
    init_db(db_path)
    rows = get_all_stats(db_path)

    if not rows:
        print("В базе пока нет товаров. Сначала запусти: python main.py check")
        return

    print("\n=== Статистика по товарам (SQLite) ===")
    print("-" * 82)
    print(f"{'Товар':<30} {'Посл.':>9} {'Мин.':>9} {'Макс.':>9} {'Средн.':>9} {'Цель':>9}")
    print("-" * 82)
    for r in rows:
        last_str = f"{r['last_price']:.2f}" if r["last_price"] is not None else "-"
        min_str = f"{r['min_price']:.2f}" if r["min_price"] is not None else "-"
        max_str = f"{r['max_price']:.2f}" if r["max_price"] is not None else "-"
        avg_str = f"{r['avg_price']:.2f}" if r["avg_price"] is not None else "-"
        target_str = f"{r['target_price']:.2f}" if r["target_price"] is not None else "-"
        print(
            f"{r['name'][:30]:<30} {last_str:>9} {min_str:>9} "
            f"{max_str:>9} {avg_str:>9} {target_str:>9}"
        )
    print("-" * 82)


def cmd_history(config: dict, base_dir: Path, item_name: str, limit: int) -> None:
    db_path = base_dir / config.get("db_file", "prices.db")
    init_db(db_path)
    rows = get_item_history(db_path, item_name, limit=limit)

    if not rows:
        print(f"История для товара '{item_name}' не найдена.")
        return

    print(f"\n=== История цен: {item_name} (последние {len(rows)}) ===")
    for r in rows:
        print(f"  {r['checked_at']} | {r['price']:.2f} {r['currency']} | {r['source']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Price Monitor Pro with SQLite history and alerts")
    parser.add_argument("-v", "--verbose", action="store_true", help="Показать подробные логи")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Проверить цены и записать историю в SQLite")
    subparsers.add_parser("stats", help="Показать сводную статистику по всем товарам")

    history_parser = subparsers.add_parser("history", help="Показать историю цен по конкретному товару")
    history_parser.add_argument("name", help="Название товара из config.json")
    history_parser.add_argument("--limit", type=int, default=10, help="Сколько записей показать")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    base_dir = Path(__file__).resolve().parent
    config = load_config(base_dir / "config.json")

    if args.command == "check":
        cmd_check(config, base_dir)
    elif args.command == "stats":
        cmd_stats(config, base_dir)
    elif args.command == "history":
        cmd_history(config, base_dir, args.name, args.limit)


if __name__ == "__main__":
    main()