import json
import logging
import os

import requests

logger = logging.getLogger("telegram")


class TelegramHelper:
    def __init__(self):
        self.token = os.environ["TELEGRAM_BOT_API_KEY"]
        self.chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_IDS"].split(",") if c.strip()]

        logger.debug("Telegram helper inizializzato!")

    def __send_telegram_message(
            self,
            message: str,
            chat_id: str,
    ):
        headers = {
            'Content-Type': 'application/json',
        }
        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        data_dict = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'MarkdownV2',
            'disable_notification': True
        }
        data = json.dumps(data_dict)
        response = requests.post(
            url,
            data=data,
            headers=headers,
        )

        if response.status_code != 200:
            raise Exception(f"Error sending message: {response.text}")

        return response

    def send(self, message):
        """Invia il messaggio a tutte le chat configurate.

        Un chat ID errato non blocca le altre chat: l'invio fallisce (raise)
        solo se falliscono TUTTE le chat.
        """
        # ponytail: un chat ID rotto viene solo loggato e non ritentato
        # (è un errore di configurazione, il retry non lo risolve)
        errors = []
        for chat_id in self.chat_ids:
            try:
                self.__send_telegram_message(message, chat_id)
            except Exception as e:
                logger.error(f"Invio fallito alla chat {chat_id}: {e}")
                errors.append(chat_id)

        if errors and len(errors) == len(self.chat_ids):
            raise Exception(f"Invio fallito a tutte le chat: {errors}")
