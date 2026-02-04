# GestOrd - Sistema di Gestione Ordini Ristorante

Sistema completo per la gestione degli ordini di un ristorante, composto da:
- **Applicazione Web per Camerieri** (compatibile mobile)
- **Consolle Desktop di Amministrazione**
- **Interfaccia per la Cucina**

## Caratteristiche

### Applicazione Web Cameriere
- Login sicuro con username e password
- Menu dinamico caricato da CSV
- Gestione ordini con numero tavolo e persone
- Aggiornamento stato ordini in tempo reale
- Accesso tramite QR Code e ngrok

### Consolle Amministrazione
- Visualizzazione ordini in tempo reale
- Ordinamento per timestamp
- Gestione stati ordini
- Caricamento menu da CSV
- Gestione offerte del giorno

### Interfaccia Cucina
- Visualizzazione ordini per stato
- Aggiornamento rapido stato lavorazione

## Requisiti

- Python 3.8 o superiore
- Connessione Internet (per ngrok)

## Installazione

1. Clona il repository:
```bash
git clone https://github.com/ivanlivemusic/gestord.git
cd gestord
```

2. Installa le dipendenze:
```bash
pip install -r requirements.txt
```

## Utilizzo

### Avviare l'Applicazione Web
```bash
python webapp.py
```

Questo avvierà:
- Il server Flask sulla porta 5000
- Ngrok per l'accesso remoto
- Genererà un QR code per l'accesso mobile

### Avviare la Consolle di Amministrazione
```bash
python admin_console.py
```

### Avviare l'Interfaccia Cucina
```bash
python kitchen_display.py
```

## Configurazione

### Menu
Modifica il file `menu.csv` per personalizzare il menu del ristorante.

### Utenti
Gli utenti camerieri sono configurati nel database SQLite (`gestord.db`).
Utente di default:
- Username: `cameriere`
- Password: `password123`

### Offerte del Giorno
Gestisci le offerte dalla consolle di amministrazione.

## Struttura del Progetto

```
gestord/
├── webapp.py              # Applicazione web Flask
├── admin_console.py       # Consolle desktop amministrazione
├── kitchen_display.py     # Interfaccia cucina
├── database.py           # Gestione database SQLite
├── menu.csv              # File menu del ristorante
├── requirements.txt      # Dipendenze Python
├── static/               # File statici web (CSS, JS)
├── templates/            # Template HTML
└── README.md            # Questo file
```

## Licenza

MIT License
