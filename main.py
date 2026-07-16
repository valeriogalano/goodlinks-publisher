import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "published_ids.json"
LOG_FILE = BASE_DIR / "logs" / "goodlinks-publisher.log"

OUTPUTS = ("mastodon", "telegram", "hugo")

# Come i vecchi script readwise-to-*: considera solo gli articoli toccati di
# recente. Difesa in profondità oltre allo stato: anche con published_ids.json
# corrotto o vuoto, i vecchi articoli non vengono mai ripubblicati.
RECENT_WINDOW_DAYS = 7

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


def filter_recent(links: list) -> list:
    """Tiene solo i link modificati negli ultimi RECENT_WINDOW_DAYS giorni.

    Il tagging aggiorna modifiedAt, quindi un articolo vecchio taggato oggi
    rientra. Link senza timestamp vengono scartati (scelta conservativa).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS)
    recent = []
    for link in links:
        timestamp = link.get("modifiedAt") or link.get("addedAt")
        if not timestamp:
            logger.warning(f"Link senza timestamp, scartato: {link.get('id')}")
            continue
        if datetime.fromisoformat(timestamp) >= cutoff:
            recent.append(link)
    return recent


def render_template(template: str, **placeholders) -> str:
    """Applica il template e ripulisce le righe vuote lasciate dai campi vuoti."""
    return re.sub(r'\n{3,}', '\n\n', template.format(**placeholders)).strip()


def build_publishers() -> dict:
    """Costruisce le funzioni di pubblicazione per ogni output.

    Import e istanze lazy: un output non configurato (env mancante) fallisce
    al momento della pubblicazione senza bloccare gli altri.
    """
    from mastodon_helper import MastodonHelper
    from telegram_helper import TelegramHelper
    from hugo_helper import HugoHelper

    def publish_mastodon(title, link, notes):
        message = render_template(os.environ["MASTODON_MESSAGE_TEMPLATE"],
                                  title=title, link=link, notes=notes)
        MastodonHelper().post(message)

    def publish_telegram(title, link, notes):
        message = render_template(os.environ["TELEGRAM_MESSAGE_TEMPLATE"],
                                  title=escape_markdown(title), link=link,
                                  notes=escape_markdown(notes))
        TelegramHelper().send(message)

    def publish_hugo(title, link, notes):
        HugoHelper().publish(title, link, notes)

    publishers = {
        "mastodon": publish_mastodon,
        "telegram": publish_telegram,
        "hugo": publish_hugo,
    }

    # Output Hugo in pausa: senza BLOG_REPO nel .env viene saltato del tutto
    # (gli articoli restano pendenti su hugo e verranno recuperati alla
    # riattivazione, se ancora dentro la finestra dei 7 giorni).
    if not os.environ.get("BLOG_REPO"):
        logger.warning("BLOG_REPO non impostato: output hugo disabilitato.")
        del publishers["hugo"]

    return publishers


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
        # {notes} = prima nota presa in GoodLinks, iniettata in main()
        # (NON il summary: quello lo mostra già l'anteprima del link)
        notes = article.get("notes") or ""

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

    gl = GoodLinks()
    try:
        links = filter_recent(gl.get_links_to_publish())
        # {notes} = prima nota presa sull'articolo in GoodLinks
        for article in links:
            article["notes"] = gl.get_first_note(str(article["id"]))
    except Exception as e:
        # GoodLinks non raggiungibile (app chiusa o API disabilitata):
        # errore loggato, exit senza toccare lo stato.
        logger.error(f"Impossibile leggere l'API GoodLinks: {e}")
        sys.exit(1)

    if not links:
        logger.debug("Nessun articolo recente con tag 'publish' trovato.")
        return

    state = load_state()
    failures = process_links(links, state, build_publishers())

    if failures:
        logger.error(f"Esecuzione terminata con {failures} pubblicazioni fallite.")
        sys.exit(1)

    logger.debug("Bye!")


if __name__ == "__main__":
    main()
