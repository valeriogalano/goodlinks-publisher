import logging
import os

import requests

logger = logging.getLogger("goodlinks")


class GoodLinks:
    def __init__(self):
        self.token = os.environ["GOODLINKS_TOKEN"]
        self.api_url = "http://localhost:9428/api/v1"

        logger.debug("GoodLinks inizializzato!")

    def get_links_to_publish(self, tag="publish"):
        """Recupera i link con il tag specificato dall'API locale di GoodLinks.

        La risposta è paginata: {"data": [...], "hasMore": bool}.
        """
        url = f"{self.api_url}/links"
        headers = {"Authorization": f"Bearer {self.token}"}

        links = []
        offset = 0
        while True:
            response = requests.get(
                url, headers=headers, params={"tag": tag, "offset": offset})
            response.raise_for_status()

            payload = response.json()
            links.extend(payload["data"])
            if not payload.get("hasMore"):
                break
            offset = len(links)

        logger.debug(f"Link trovati con tag '{tag}': {len(links)}")
        return links
