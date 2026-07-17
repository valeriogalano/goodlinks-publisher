"""Archiviazione degli articoli GoodLinks nel vault Obsidian.

Job separato dalla pubblicazione (main.py): replica la funzione che il plugin
`readwise-official` faceva su Readwise. Per ogni link con almeno un highlight
crea/aggiorna due note:

- `3.Risorse/Articoli/<titolo>.md`                 → metadata + highlights
- `3.Risorse/Full Document Contents/Articoli/...`  → testo integrale (trafilatura)

Nessun file di stato: il vault è la fonte di verità (match per URL). Best-effort:
gli errori per-articolo vengono loggati e non fermano il giro.
"""
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

from goodlinks import GoodLinks
from main import notify_failure, setup_logging
from obsidian_helper import ObsidianVault

BASE_DIR = Path(__file__).parent
ARTICLES_DIR = "3.Risorse/Articoli"
FULLDOC_DIR = "3.Risorse/Full Document Contents/Articoli"
GOODLINKS_HEADING = "## Highlights (GoodLinks)"

# Parametri di tracking da rimuovere prima di confrontare gli URL: due link con
# utm diversi puntano allo stesso articolo e non vanno duplicati.
TRACKING_PARAMS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src",
    "spm", "yclid", "_hsenc", "_hsmi", "cmpid", "smid",
}

URL_RE = re.compile(r'^- URL:\s*(\S.*)$', re.MULTILINE)

logger = logging.getLogger("archive")


def normalize_url(url: str) -> str:
    """Chiave di confronto stabile: minuscole host, niente www/fragment/tracking."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    if not parts.scheme:  # es. mailto senza netloc gestito comunque da urlsplit
        return url.strip()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = f"{host}:{parts.port}" if parts.port else host
    query = urlencode([
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ])
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), query, ""))


def vault_filename(title: str) -> str:
    """Nome file dalla titolatura, senza i caratteri illegali su filesystem."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', '', title or "").strip()
    name = re.sub(r'\s+', ' ', name)
    return name or "Senza titolo"


def extract_url(content: str):
    match = URL_RE.search(content or "")
    return match.group(1).strip() if match else None


def highlight_text(h: dict) -> str:
    return (h.get("markdownContent") or h.get("content") or "").strip()


def render_highlights(highlights: list) -> str:
    lines = []
    for h in highlights:
        content = highlight_text(h)
        if not content:
            continue
        lines.append(f"- {content}")
        note = (h.get("note") or "").strip()
        if note:
            lines.append(f"    - Note: {note}")
    return "\n".join(lines)


def new_highlights(highlights: list, existing_content: str) -> list:
    """Highlight non ancora presenti nella nota (match per testo)."""
    return [h for h in highlights
            if highlight_text(h) and highlight_text(h) not in (existing_content or "")]


def append_section(content: str, heading: str, body: str) -> str:
    """Aggiunge body in coda al file, creando `heading` se assente.

    ponytail: append in coda al file, non strettamente sotto il heading se
    seguissero altre sezioni; per la sezione GoodLinks (che teniamo in fondo)
    è corretto. Basta un patch mirato via document map se cambia.
    """
    content = (content or "").rstrip()
    if heading in content:
        return f"{content}\n{body}\n"
    return f"{content}\n\n{heading}\n{body}\n"


def build_highlights_note(link: dict, highlights: list, fulldoc_wikilink: str) -> str:
    title = link.get("title") or link.get("url") or "Senza titolo"
    parts = [f"# {title}", "", "#GoodLinks", "", "## Metadata"]
    if link.get("author"):
        parts.append(f"- Author: [[{link['author']}]]")
    parts.append(f"- Full Title: {title}")
    parts.append("- Category: #articles")
    if link.get("tags"):
        parts.append("- Document Tags: " + " ".join(f"#{t}" for t in link["tags"]))
    if link.get("summary"):
        parts.append(f"- Summary: {link['summary']}")
    parts.append(f"- URL: {link.get('url', '')}")
    parts += ["", "## Full Document",
              f"[[{fulldoc_wikilink}|See full document content →]]",
              "", "## Highlights", render_highlights(highlights), ""]
    return "\n".join(parts)


def build_fulldoc_note(link: dict, full_text: str) -> str:
    title = link.get("title") or link.get("url") or "Senza titolo"
    parts = [f"# {title}", "", "#GoodLinks", "", "## Metadata"]
    if link.get("author"):
        parts.append(f"- Author: [[{link['author']}]]")
    parts.append(f"- Full Title: {title}")
    parts.append("- Category: #articles")
    if link.get("summary"):
        parts.append(f"- Summary: {link['summary']}")
    parts.append(f"- URL: {link.get('url', '')}")
    parts += ["", "## Full Document", full_text, ""]
    return "\n".join(parts)


def fetch_full_text(url: str):
    """Testo integrale via trafilatura (locale). None se non estraibile."""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        return trafilatura.extract(downloaded, output_format="markdown", include_links=True)
    except Exception as e:
        logger.warning(f"trafilatura fallita per {url}: {e}")
        return None


def index_by_url(obsidian, folder: str) -> dict:
    """Mappa URL normalizzato -> nome file, leggendo le note esistenti."""
    index = {}
    for filename in obsidian.list_folder(folder):
        if not filename.endswith(".md"):
            continue
        url = extract_url(obsidian.read(f"{folder}/{filename}"))
        if url:
            index[normalize_url(url)] = filename
    return index


def _write(obsidian, path, content, dry_run):
    if dry_run:
        logger.info(f"[dry-run] scriverei {path} ({len(content)} char)")
        return
    obsidian.write(path, content)
    logger.info(f"Scritto {path}")


def _process_link(link, highlights, obsidian, articoli_index, fulldoc_index,
                  fetch, dry_run) -> int:
    url = link.get("url") or ""
    norm = normalize_url(url)
    filename = vault_filename(link.get("title") or str(link.get("id")))
    fulldoc_wikilink = f"Full Document Contents/Articoli/{filename}.md"
    writes = 0

    existing = articoli_index.get(norm)
    if existing is None:
        note = build_highlights_note(link, highlights, fulldoc_wikilink)
        _write(obsidian, f"{ARTICLES_DIR}/{filename}.md", note, dry_run)
        articoli_index[norm] = f"{filename}.md"
        writes += 1
    else:
        existing_path = f"{ARTICLES_DIR}/{existing}"
        content = obsidian.read(existing_path) or ""
        fresh = new_highlights(highlights, content)
        if fresh:
            updated = append_section(content, GOODLINKS_HEADING, render_highlights(fresh))
            _write(obsidian, existing_path, updated, dry_run)
            writes += 1

    if norm not in fulldoc_index:
        text = fetch(url)
        if text:
            note = build_fulldoc_note(link, text)
            _write(obsidian, f"{FULLDOC_DIR}/{filename}.md", note, dry_run)
            fulldoc_index[norm] = f"{filename}.md"
            writes += 1
        else:
            logger.warning(f"Full content non estratto, salto: {url}")

    return writes


def archive(goodlinks, obsidian, links, fetch=fetch_full_text, dry_run=False) -> int:
    """Ritorna il numero di note scritte. Best-effort per-articolo."""
    articoli_index = index_by_url(obsidian, ARTICLES_DIR)
    fulldoc_index = index_by_url(obsidian, FULLDOC_DIR)

    writes = 0
    for link in links:
        if not link.get("highlighted"):
            continue  # niente highlight: la finestra "1 highlight o 1 nota" non si applica
        try:
            highlights = goodlinks.get_highlights(link["id"])
            if not highlights:
                continue
            writes += _process_link(link, highlights, obsidian, articoli_index,
                                    fulldoc_index, fetch, dry_run)
        except Exception as e:
            logger.error(f"Archiviazione fallita per '{link.get('title')}': {e}")

    return writes


def main():
    load_dotenv(BASE_DIR / ".env")
    setup_logging()
    # setup_logging mette il root a DEBUG: l'archiviazione fa centinaia di
    # chiamate HTTP (vault + trafilatura), le librerie a DEBUG allagano il log.
    for noisy in ("urllib3", "trafilatura", "htmldate", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    dry_run = "--dry-run" in sys.argv

    gl = GoodLinks()
    try:
        links = gl.get_all_links()  # fail-fast: GoodLinks prima di toccare il vault
    except Exception as e:
        logger.error(f"Impossibile leggere l'API GoodLinks: {e}")
        notify_failure("GoodLinks non raggiungibile: app chiusa o API disabilitata?")
        sys.exit(1)

    try:
        writes = archive(gl, ObsidianVault(), links, dry_run=dry_run)
    except Exception as e:
        logger.error(f"Archiviazione fallita: {e}")
        notify_failure(f"Archiviazione Obsidian fallita: {e}")
        sys.exit(1)

    suffix = " (dry-run)" if dry_run else ""
    logger.info(f"Archiviazione completata: {writes} note scritte{suffix}.")


if __name__ == "__main__":
    main()
