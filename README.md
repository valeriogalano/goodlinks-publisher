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
   A fine esecuzione, se lo stato è cambiato, viene **committato e pushato
   automaticamente** su Codeberg (backup versionato, direttamente su `main`:
   è un dato operativo, non codice). Richiede la passphrase della chiave SSH
   nel keychain (`UseKeychain yes` in `~/.ssh/config`), perché launchd non ha
   ssh-agent.
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
| `OBSIDIAN_API_KEY` | API key della Local REST API di Obsidian (per `archive.py`) |
| `OBSIDIAN_API_URL` | URL della Local REST API (opzionale, default `https://127.0.0.1:27124`) |

I template supportano i placeholder `{title}`, `{notes}`, `{link}`. `{notes}`
è la **prima nota** (l'highlight più vecchio) presa sull'articolo in GoodLinks —
non la descrizione, che l'anteprima del link mostra già. Articolo senza
highlight → `{notes}` vuoto, e le righe vuote residue vengono ripulite.

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

## Archiviazione nel vault Obsidian

`archive.py` è un job **separato** dalla pubblicazione: replica la funzione che
il plugin `readwise-official` faceva su Readwise, ovvero salvare gli articoli
con annotazioni nel vault Obsidian. È indipendente dagli output Mastodon/Telegram/Hugo.

Per ogni link GoodLinks con **almeno un highlight** crea/aggiorna due note:

- `3.Risorse/Articoli/<titolo>.md` — metadata + highlights (con eventuali note);
- `3.Risorse/Full Document Contents/Articoli/<titolo>.md` — testo integrale
  estratto con [trafilatura](https://trafilatura.readthedocs.io/) (locale, niente cloud).

Caratteristiche:

1. **Nessun file di stato**: il vault è la fonte di verità. L'idempotenza si
   basa sul match per **URL normalizzato** (strip di `utm_*` e altri parametri
   di tracking) letto dal blocco `## Metadata` delle note esistenti.
2. **Skip + append** sulle collisioni con le ~400 note storiche di Readwise: se
   l'URL è già presente, la nota non viene ricreata; i nuovi highlight GoodLinks
   vengono appesi in una sezione `## Highlights (GoodLinks)`. Il full content
   viene creato solo se non esiste già.
3. **Best-effort**: gli errori per-articolo sono loggati e non fermano il giro
   (exit 0). Se trafilatura fallisce (paywall, JS-heavy) il full content viene
   saltato ma la nota highlights è creata comunque. Se GoodLinks non è
   raggiungibile: exit 1 con notifica macOS, nessuna scrittura sul vault.

Richiede il plugin **Local REST API** di Obsidian abilitato e la sua API key in
`OBSIDIAN_API_KEY` (vedi `config.example.env`). Obsidian deve essere aperto.

Prova a secco (legge tutto, non scrive nulla):

```bash
python archive.py --dry-run
```

Schedulazione launchd, **2 volte al giorno** (7:30 e 21:30):

```bash
cp com.valeriogalano.goodlinks-publisher-archive.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.valeriogalano.goodlinks-publisher-archive.plist
```

Log in `logs/goodlinks-publisher.log` e `logs/launchd-archive.log`.

## Uso manuale

```bash
source .venv/bin/activate
python main.py       # pubblicazione (Mastodon/Telegram/Hugo)
python archive.py    # archiviazione nel vault Obsidian
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
