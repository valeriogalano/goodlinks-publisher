import logging
import os

import requests

API_URL = 'https://mastodon.uno'

logger = logging.getLogger("mastodon")


class MastodonHelper:
    def __init__(self):
        self.token = os.environ["MASTODON_TOKEN"]

        logger.debug("Mastodon helper inizializzato!")

    def __send_mastodon_post(self, status: str):
        if len(status) > 500:
            status = status[:497] + "..."

        response = requests.post(
            f"{API_URL}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {self.token}"
            },
            json={
                'status': status,
                'visibility': 'public',
            }
        )

        if response.status_code != 201 and response.status_code != 200:
            raise Exception(f"Error sending status: {response.text}")

    def post(self, status):
        self.__send_mastodon_post(status)
