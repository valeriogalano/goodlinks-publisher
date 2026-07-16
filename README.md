# goodlinks-publisher

Pubblica automaticamente gli articoli taggati `publish` in [GoodLinks](https://goodlinks.app)
su Mastodon, Telegram e sul blog Hugo. Sostituisce la vecchia pipeline basata su
Readwise (`readwise-to-mastodon` + `readwise-to-telegram`).

## Come funziona

Lo script gira sul Mac via `launchd` ogni ora nelle ore diurne (8:20–20:20):

1. legge l'[API locale di GoodLinks](https://goodlinks.app/api/) (`localhost:9428`) filtrando per tag `publish`;
2. tiene solo gli articoli modificati negli ultimi 7 giorni (il tagging aggiorna
   `modifiedAt`): i vecchi articoli non vengono mai ripubblicati, anche con lo
   stato corrotto;
3. confronta gli articoli trovati con lo stato in `published_ids.json` (mappa `id articolo → output completati`);
4. per ogni articolo nuovo fa fan-out sui tre output:
   - **Mastodon** — post con template configurabile;
   - **Telegram** — messaggio MarkdownV2 su una o più chat;
   - **Hugo** — post `.md` in `content/blog/` (tag `Link condivisi`) creato come
     commit **direttamente sul repo remoto via API GitHub**: il commit fa
     scattare la CI del blog che builda e deploya. Per mettere in pausa questo
     output basta commentare `BLOG_REPO` nel `.env`;
5. aggiorna lo stato per output solo a pubblicazione riuscita: in caso di
   fallimento parziale, al giro successivo viene ritentato solo l'output
   mancante, senza duplicati.

Un output che fallisce non blocca gli altri. Exit code non-zero se almeno una
pubblicazione è fallita.

## Prevenzione dei duplicati

Vengono pubblicati **solo gli articoli nuovi**, mai il backlog storico, grazie
a due protezioni indipendenti:

1. **Stato per-output** — `published_ids.json` mappa ogni id articolo sugli
   output già completati; un articolo presente con tutti gli output viene
   sempre saltato. Al primo avvio lo stato è stato seedato con l'intero
   backlog (223 articoli già pubblicati dalla vecchia pipeline Readwise).
2. **Finestra di 7 giorni** — come i vecchi script `readwise-to-*`
   (`updatedAfter`): vengono considerati solo gli articoli con `modifiedAt`
   (o `addedAt`) negli ultimi 7 giorni. Anche con stato corrotto, vuoto o
   cancellato, gli articoli vecchi non vengono mai ripubblicati.

Taggare `publish` un articolo aggiorna il suo `modifiedAt`, quindi anche un
articolo salvato mesi fa rientra nella finestra nel momento in cui viene
taggato: è questo il gesto che lo manda in pubblicazione.

## Requisiti

- macOS con [GoodLinks](https://goodlinks.app) 3.2+ e API locale abilitata (Impostazioni → API)
- Python 3.11+
- Un bot Telegram (creabile tramite [@BotFather](https://t.me/botfather))
- Un access token Mastodon (Preferences → Development sulla propria istanza)
- Un PAT GitHub con permesso di scrittura sul repo del blog

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
| `BLOG_REPO` | Repo del blog su GitHub (`owner/repo`); commentarla mette in pausa l'output Hugo |
| `BLOG_REPO_TOKEN` | PAT GitHub con scrittura sul repo del blog |

I template supportano i placeholder `{title}`, `{notes}`, `{link}`. Su Mastodon
e Telegram `{notes}` è sconsigliato: l'anteprima del link mostra già la
descrizione dell'articolo.

## Esecuzione automatica (launchd)

```bash
cp com.valeriogalano.goodlinks-publisher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.valeriogalano.goodlinks-publisher.plist
```

La **schedulazione è configurata nel plist** (`StartCalendarInterval`): ogni
ora al minuto 20, solo nelle ore diurne (8:20–20:20). Per cambiare gli orari,
modificare il plist nel repo e reinstallarlo:

```bash
launchctl unload ~/Library/LaunchAgents/com.valeriogalano.goodlinks-publisher.plist
cp com.valeriogalano.goodlinks-publisher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.valeriogalano.goodlinks-publisher.plist
```

Log in `logs/goodlinks-publisher.log` (con rotazione) e `logs/launchd.log`.

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
- **Creazione post sul blog fallita** — errore API GitHub loggato (token scaduto
  o permessi mancanti); al giro successivo viene ritentato solo l'output hugo.
  Se il file esiste già sul repo remoto, il retry non crea duplicati.
- **Articolo duplicato dopo modifica manuale dello stato** — `published_ids.json`
  è la fonte di verità: rimuovere un output dalla voce di un articolo ne causa
  la ripubblicazione su quell'output.
