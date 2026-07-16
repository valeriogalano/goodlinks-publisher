import base64
import logging
import os
import re
from datetime import datetime, timezone

import requests

logger = logging.getLogger("hugo")

# ponytail: GitHub API oggi, Forgejo API quando il blog migra su Codeberg
# (stesso endpoint contents, cambia solo base URL e auth header)
API_URL = "https://api.github.com"


def slugify(text: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug or 'senza-titolo'


class HugoHelper:
    """Crea il post come commit diretto sul repo remoto del blog via API.

    Il commit via API (con PAT) fa scattare la CI del blog, che builda e
    deploya. Nessuna dipendenza dallo stato del clone locale.
    """

    def __init__(self):
        self.repo = os.environ["BLOG_REPO"]  # es. valeriogalano/pensieriincodice-website
        self.token = os.environ["BLOG_REPO_TOKEN"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

        logger.debug("Hugo helper inizializzato!")

    def publish(self, title: str, link: str, notes: str):
        """Idempotente: se il file esiste già sul repo remoto, non fa nulla."""
        path = f"content/blog/{slugify(title)}.md"
        url = f"{API_URL}/repos/{self.repo}/contents/{path}"

        existing = requests.get(url, headers=self.headers)
        if existing.status_code == 200:
            logger.debug(f"Post già presente sul repo remoto: {path}")
            return

        date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        escaped_title = title.replace('"', '\\"')
        content = (
            "---\n"
            f'title: "{escaped_title}"\n'
            f"date: {date}\n"
            "tags:\n"
            "- Link condivisi\n"
            "categories:\n"
            "- News\n"
            "type: blog\n"
            "author: Valerio Galano\n"
            "---\n"
            "\n"
            f"{notes}\n"
            "\n"
            f"[Leggi l'articolo originale]({link})\n"
        )

        response = requests.put(url, headers=self.headers, json={
            "message": f"Add shared link: {title}",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        })
        if response.status_code not in (200, 201):
            raise Exception(f"Creazione post fallita: {response.status_code} {response.text[:200]}")

        logger.debug(f"Post creato sul repo remoto: {path}")
