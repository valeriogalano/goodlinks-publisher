import logging
import os

import requests

logger = logging.getLogger("goodlinks")


class GoodLinks:
    def __init__(self):
        self.token = os.environ["GOODLINKS_TOKEN"]
        self.api_url = "http://localhost:9428/api/v1"

        logger.debug("GoodLinks inizializzato!")

    def get_links_to_publish(self, tag="pubblica"):
        """Recupera i link con il tag specificato dall'API locale di GoodLinks."""
        url = f"{self.api_url}/links"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"tag": tag}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        links = response.json()
        logger.debug(f"Link trovati con tag '{tag}': {len(links)}")
        return links
