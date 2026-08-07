# goodlinks-publisher

Due job launchd: il publisher gira ogni ora, `archive.py` due volte al giorno (~07:30 e 21:30).
Log in `logs/` (`launchd.log` per il publisher, `launchd-archive.log` per l'archive).

## Anomalie note e accettate — non sono bug

Deciso il 2026-08-07. Non aprire task né proporre fix per questi due punti.

**Il job archive fallisce nella run del mattino ogni 3-4 giorni**, con `Connection reset by peer`
o `Connection refused` su `127.0.0.1:27124` (Local REST API di Obsidian): alle ~07:47 Obsidian non
è ancora avviato. La run delle 21:30 della stessa giornata va sempre a buon fine e recupera
l'archiviazione mancata, quindi il fix non paga il suo costo.
Riaprire il discorso solo se fallisce a orari in cui Obsidian è certamente aperto, o se inizia a
fallire anche la run serale.

**`BLOG_REPO` non è impostato di proposito**: l'output Hugo è implementato (PR #4) ma disattivato
per scelta editoriale. Il `WARNING - BLOG_REPO non impostato: output hugo disabilitato` a ogni
pubblicazione è atteso.

Diverso il caso di GoodLinks (`localhost:9428`): se è irraggiungibile scatta la notifica
"GoodLinks non raggiungibile" ed è un problema vero. Non è mai successo finora.
