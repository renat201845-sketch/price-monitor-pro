import json
import urllib.error
import urllib.request


def send_telegram_alert(bot_token: str, chat_id: str, message: str, timeout: int = 8) -> bool:
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def notify_deal(item_name: str, price: float, target_price: float, currency: str, tg_cfg: dict) -> None:
    alert_text = (
        f"[DEAL ALERT] {item_name}: {price:.2f} {currency} "
        f"(цель <= {target_price:.2f} {currency})"
    )
    print(alert_text)

    if tg_cfg.get("enabled"):
        sent = send_telegram_alert(
            bot_token=tg_cfg.get("bot_token", ""),
            chat_id=str(tg_cfg.get("chat_id", "")),
            message=alert_text,
        )
        if not sent:
            print("  -> Не удалось отправить уведомление в Telegram (проверь token/chat_id).")