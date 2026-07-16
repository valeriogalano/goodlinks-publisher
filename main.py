import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "published_ids.json"
LOG_FILE = BASE_DIR / "logs" / "goodlinks-publisher.log"

OUTPUTS = ("mastodon", "telegram", "hugo")

logger = logging.getLogger("main")


def setup_logging():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5),
            logging.StreamHandler(),
        ],
    )


def load_state() -> dict:
    """Mappa id articolo -> lista output completati."""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("published_ids.json mancante o non valido, uso stato vuoto.")
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def escape_markdown(text_to_escape):
    """Escaping per Telegram MarkdownV2."""
    translate_table = str.maketrans({
        '_': r'\_',
        '*': r'\*',
        '[': r'\[',
        ']': r'\]',
        '(': r'\(',
        ')': r'\)',
        '~': r'\~',
        '`': r'\`',
        '>': r'\>',
        '#': r'\#',
        '+': r'\+',
        '-': r'\-',
        '=': r'\=',
        '|': r'\|',
        '{': r'\{',
        '}': r'\}',
        '.': r'\.',
        '!': r'\!'
    })

    return text_to_escape.translate(translate_table)


def build_publishers() -> dict:
    """Costruisce le funzioni di pubblicazione per ogni output.

    Import e istanze lazy: un output non configurato (env mancante) fallisce
    al momento della pubblicazione senza bloccare gli altri.
    """
    from mastodon_helper import MastodonHelper
    from telegram_helper import TelegramHelper
    from hugo_helper import HugoHelper

    def publish_mastodon(title, link, notes):
        message = os.environ["MASTODON_MESSAGE_TEMPLATE"].format(
            title=title, link=link, notes=notes)
        MastodonHelper().post(message)

    def publish_telegram(title, link, notes):
        message = os.environ["TELEGRAM_MESSAGE_TEMPLATE"].format(
            title=escape_markdown(title), link=link, notes=escape_markdown(notes))
        TelegramHelper().send(message)

    def publish_hugo(title, link, notes):
        HugoHelper().publish(title, link, notes)

    return {
        "mastodon": publish_mastodon,
        "telegram": publish_telegram,
        "hugo": publish_hugo,
    }


def process_links(links, state, publishers) -> int:
    """Fan-out: pubblica ogni articolo su ogni output mancante.

    Aggiorna e salva lo stato dopo ogni output riuscito. Ritorna il numero
    di pubblicazioni fallite.
    """
    failures = 0
    for article in links:
        article_id = str(article["id"])
        title = article.get("title") or ""
        link = article.get("url") or ""
        notes = article.get("summary") or ""

        done = state.setdefault(article_id, [])
        pending = [name for name in publishers if name not in done]
        if not pending:
            continue

        logger.info(f"Pubblicazione articolo '{title}' su: {', '.join(pending)}")
        for name in pending:
            try:
                publishers[name](title, link, notes)
                done.append(name)
                save_state(state)
                logger.info(f"[{name}] pubblicato: {title}")
            except Exception as e:
                failures += 1
                logger.error(f"[{name}] pubblicazione fallita per '{title}': {e}")

    return failures


def main():
    load_dotenv(BASE_DIR / ".env")
    setup_logging()

    from goodlinks import GoodLinks

    try:
        links = GoodLinks().get_links_to_publish()
    except Exception as e:
        # GoodLinks non raggiungibile (app chiusa o API disabilitata):
        # errore loggato, exit senza toccare lo stato.
        logger.error(f"Impossibile leggere l'API GoodLinks: {e}")
        sys.exit(1)

    if not links:
        logger.debug("Nessun articolo con tag 'publish' trovato.")
        return

    state = load_state()
    failures = process_links(links, state, build_publishers())

    if failures:
        logger.error(f"Esecuzione terminata con {failures} pubblicazioni fallite.")
        sys.exit(1)

    logger.debug("Bye!")


if __name__ == "__main__":
    main()
