import logging
import os
from urllib.parse import quote

import requests
import urllib3

# La Local REST API di Obsidian usa un certificato self-signed su 127.0.0.1:
# verify=False è corretto qui (solo localhost), silenziamo il warning relativo.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("obsidian")


class ObsidianVault:
    """Client minimo per la Local REST API del plugin Obsidian.

    Il vault è la fonte di verità per l'archiviazione: nessun file di stato.
    """

    def __init__(self):
        self.api_url = os.environ.get("OBSIDIAN_API_URL", "https://127.0.0.1:27124")
        self.token = os.environ["OBSIDIAN_API_KEY"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        logger.debug("Obsidian helper inizializzato!")

    def _url(self, path: str) -> str:
        # quote lascia '/' invariato (safe di default): i percorsi cartella restano tali.
        return f"{self.api_url}/vault/{quote(path)}"

    def list_folder(self, folder: str) -> list:
        """Nomi dei file nella cartella. Lista vuota se la cartella non esiste."""
        response = requests.get(self._url(folder + "/"), headers=self.headers, verify=False)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json().get("files", [])

    def read(self, path: str):
        """Contenuto markdown della nota, o None se non esiste."""
        response = requests.get(
            self._url(path),
            headers={**self.headers, "Accept": "text/markdown"},
            verify=False,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.text

    def write(self, path: str, content: str) -> None:
        response = requests.put(
            self._url(path),
            headers={**self.headers, "Content-Type": "text/markdown"},
            data=content.encode("utf-8"),
            verify=False,
        )
        if response.status_code not in (200, 201, 204):
            raise Exception(
                f"Scrittura vault fallita ({path}): {response.status_code} {response.text[:200]}")
