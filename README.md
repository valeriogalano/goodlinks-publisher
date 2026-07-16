# goodlinks-publisher

Pubblica automaticamente gli articoli taggati `pubblica` in [GoodLinks](https://goodlinks.app)
su Mastodon, Telegram e sul blog Hugo. Sostituisce la vecchia pipeline basata su
Readwise (`readwise-to-mastodon` + `readwise-to-telegram`).

## Come funziona

Lo script gira sul Mac ogni ora via `launchd`:

1. legge l'[API locale di GoodLinks](https://goodlinks.app/api/) (`localhost:9428`) filtrando per tag `pubblica`;
2. confronta gli articoli trovati con lo stato in `published_ids.json` (mappa `id articolo → output completati`);
3. per ogni articolo nuovo fa fan-out sui tre output:
   - **Mastodon** — post con template configurabile;
   - **Telegram** — messaggio MarkdownV2 su una o più chat;
   - **Hugo** — file `.md` in `content/links/` del repo del blog, con commit + push (build e deploy restano alla CI del blog);
4. aggiorna lo stato per output solo a pubblicazione riuscita: in caso di
   fallimento parziale, al giro successivo viene ritentato solo l'output
   mancante, senza duplicati.

Un output che fallisce non blocca gli altri. Exit code non-zero se almeno una
pubblicazione è fallita.

## Requisiti

- macOS con [GoodLinks](https://goodlinks.app) 3.2+ e API locale abilitata (Impostazioni → API)
- Python 3.11+
- Un bot Telegram (creabile tramite [@BotFather](https://t.me/botfather))
- Un access token Mastodon (Preferences → Development sulla propria istanza)
- Il repo Hugo del blog clonato in locale, con push configurato

## Installazione

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.env .env
# imposta i valori reali nel .env
```

## Configurazione

Vedi `config.example.env` per tutte le variabili:

| Variabile | Descrizione |
|---|---|
| `GOODLINKS_TOKEN` | Token dell'API locale di GoodLinks |
| `MASTODON_TOKEN` | Access token Mastodon |
| `MASTODON_MESSAGE_TEMPLATE` | Template del post Mastodon |
| `TELEGRAM_BOT_API_KEY` | Token del bot Telegram |
| `TELEGRAM_CHAT_IDS` | Chat ID separati da virgola |
| `TELEGRAM_MESSAGE_TEMPLATE` | Template del messaggio Telegram |
| `BLOG_REPO_PATH` | Percorso locale del repo Hugo del blog |

I template supportano i placeholder `{title}`, `{notes}`, `{link}`.

## Esecuzione automatica (launchd)

```bash
cp com.valeriogalano.goodlinks-publisher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.valeriogalano.goodlinks-publisher.plist
```

Lo script viene eseguito ogni ora. Log in `logs/goodlinks-publisher.log`
(con rotazione) e `logs/launchd.log`.

## Uso manuale

```bash
source .venv/bin/activate
python main.py
```

## Test

```bash
python -m pytest
```

## Troubleshooting

- **"Impossibile leggere l'API GoodLinks"** — l'app GoodLinks è chiusa o l'API
  locale è disabilitata. Aprire GoodLinks e verificare Impostazioni → API.
- **Errore Telegram su una sola chat** — un chat ID errato viene loggato ma non
  blocca l'invio alle altre chat; correggere `TELEGRAM_CHAT_IDS`.
- **Push sul blog fallito** — il commit resta locale nel repo del blog; al giro
  successivo viene ritentato solo il push, senza duplicare il post.
- **Articolo duplicato dopo modifica manuale dello stato** — `published_ids.json`
  è la fonte di verità: rimuovere un output dalla voce di un articolo ne causa
  la ripubblicazione su quell'output.
