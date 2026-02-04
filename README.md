# GestOrd - Sistema di Gestione Ordini Ristorante

Sistema completo per la gestione degli ordini di un ristorante, composto da:
- **Applicazione Web per Camerieri** (compatibile mobile)
- **Consolle Desktop di Amministrazione**
- **Interfaccia per la Cucina**

## Caratteristiche

### Applicazione Web Cameriere
- Login sicuro con username e password
- Menu dinamico caricato da CSV con categorie e sottocategorie:
  - Antipasti, Primi (Carne/Pesce), Secondi (Carne/Pesce)
  - Contorni, Dolci, Pizzeria
  - Bevande (Bibite/Alcolici)
  - Vegetariani, Vegani, Caffetteria
- Gestione ordini con numero tavolo e persone
- Carrello con quantità e totale
- Aggiornamento stato ordini in tempo reale (WebSocket)
- Accesso tramite QR Code e ngrok (opzionale)
- Interfaccia responsive ottimizzata per mobile

### Consolle Amministrazione
- Visualizzazione ordini in tempo reale
- Tabella ordinata per timestamp decrescente
- Dettagli completi di ogni ordine (tavolo, persone, cameriere, portate)
- Modifica stato ordini (Inserito → In Lavorazione → Consegnato)
- Caricamento menu da CSV
- Gestione offerte del giorno
- Aggiunta nuovi camerieri
- Aggiornamento automatico ogni 5 secondi

### Interfaccia Cucina
- Visualizzazione ordini divisi per stato (colonne)
- Aggiornamento rapido stato lavorazione
- Layout ottimizzato per tablet/PC in cucina
- Colori distinti per stato (giallo, blu, verde)
- Aggiornamento automatico ogni 3 secondi

## Requisiti

- Python 3.8 o superiore
- Sistema operativo: Linux, macOS, Windows
- Connessione Internet (solo per ngrok - opzionale)

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

### Metodo 1: Script di Avvio Interattivo (Consigliato)
```bash
python start.py
```

Questo mostrerà un menu interattivo per lanciare i vari componenti.

### Metodo 2: Avvio Manuale dei Componenti

#### Avviare l'Applicazione Web
```bash
python webapp.py
```

Questo avvierà:
- Il server Flask sulla porta 5000
- Tentativo di connessione ngrok per l'accesso remoto (opzionale)
- Generazione QR code in `qr_code.txt` (se ngrok disponibile)

Accedi a: http://localhost:5000

**Credenziali default:**
- Username: `cameriere`
- Password: `password123`

#### Avviare la Consolle di Amministrazione
```bash
python admin_console.py
```

Aprirà una finestra PyQt5 con:
- Tab Ordini: visualizza e gestisci tutti gli ordini
- Tab Menu: gestione menu da CSV
- Tab Offerte: aggiungi offerte del giorno
- Tab Utenti: gestione camerieri

#### Avviare l'Interfaccia Cucina
```bash
python kitchen_display.py
```

Aprirà una finestra a schermo intero con tre colonne:
- 📋 Nuovi Ordini (giallo)
- 🔥 In Lavorazione (blu)
- ✅ Pronti (verde)

### Test del Sistema
```bash
python test_system.py
```

Verifica che tutti i componenti siano installati correttamente.

## Configurazione

### Menu
Il menu è configurato nel file `menu.csv` con la seguente struttura:

```csv
Categoria,Sottocategoria,Nome,Prezzo,Descrizione
Antipasti,,Bruschetta al Pomodoro,6.50,Pane tostato con pomodori freschi
Primi,Carne,Lasagne alla Bolognese,10.00,Lasagne fatte in casa
```

**Categorie supportate:**
- Antipasti
- Primi (sottocategorie: Carne, Pesce)
- Secondi (sottocategorie: Carne, Pesce)
- Contorni
- Pizzeria
- Dolci
- Bevande (sottocategorie: Bibite, Alcolici)
- Vegetariani
- Vegani
- Caffetteria

Per aggiornare il menu:
1. Modifica `menu.csv`
2. Dalla consolle amministrazione: clicca "Carica da CSV"
3. Oppure riavvia l'applicazione web

### Utenti
Gli utenti camerieri sono salvati nel database SQLite (`gestord.db`).

**Utente di default:**
- Username: `cameriere`
- Password: `password123`

Per aggiungere nuovi camerieri:
- Usa la consolle amministrazione → Tab "Gestione Utenti"
- Oppure usa la funzione `db.add_user()` nel codice

### Offerte del Giorno
Le offerte possono essere gestite dalla consolle di amministrazione senza modificare il CSV principale:
1. Tab "Offerte del Giorno"
2. Clicca "Aggiungi Offerta"
3. Compila i campi e salva

Le offerte sono valide per la data corrente e appaiono in alto nel menu web.

### Ngrok (Accesso Remoto)
Per abilitare l'accesso remoto tramite ngrok:

1. Registrati su https://ngrok.com
2. Ottieni il tuo auth token
3. Imposta la variabile d'ambiente:
```bash
export NGROK_AUTH_TOKEN="your_token_here"
```

L'applicazione web genererà automaticamente:
- URL pubblico accessibile da Internet
- QR Code salvato in `qr_code.txt`

**Nota:** Ngrok è opzionale. Senza, l'app funziona solo sulla rete locale.

## Struttura del Progetto

```
gestord/
├── webapp.py              # Applicazione web Flask
├── admin_console.py       # Consolle desktop amministrazione (PyQt5)
├── kitchen_display.py     # Interfaccia cucina (PyQt5)
├── database.py           # Gestione database SQLite
├── start.py              # Script avvio interattivo
├── test_system.py        # Test di sistema
├── menu.csv              # File menu del ristorante
├── requirements.txt      # Dipendenze Python
├── README.md            # Questa documentazione
├── .gitignore           # File da ignorare in Git
├── static/              # File statici web
│   ├── css/
│   │   └── style.css    # Stili CSS responsive
│   └── js/
│       └── menu.js      # Logica client-side
└── templates/           # Template HTML
    ├── login.html       # Pagina login
    └── menu.html        # Pagina menu/ordini
```

## Database

Il sistema usa SQLite con le seguenti tabelle:

- **users**: Camerieri con credenziali
- **menu_items**: Elementi del menu caricati da CSV
- **orders**: Ordini con informazioni base
- **order_items**: Dettagli portate per ogni ordine
- **daily_specials**: Offerte del giorno

Il database viene creato automaticamente al primo avvio in `gestord.db`.

## Flusso di Lavoro Tipico

1. **Cameriere** (Web App):
   - Login → Seleziona tavolo e numero persone
   - Aggiunge portate al carrello
   - Invia ordine
   - Stato: "Inserito"

2. **Cucina** (Kitchen Display):
   - Vede il nuovo ordine nella colonna "Nuovi Ordini"
   - Clicca "Inizia Lavorazione"
   - Stato: "In Lavorazione"
   - Quando pronto, clicca "Pronto per Servizio"
   - Stato: "Consegnato"

3. **Amministrazione** (Admin Console):
   - Monitora tutti gli ordini in tempo reale
   - Può modificare lo stato di qualsiasi ordine
   - Gestisce menu e offerte
   - Aggiunge nuovi camerieri

## Sincronizzazione Real-Time

Il sistema usa WebSocket (Socket.IO) per la sincronizzazione in tempo reale:
- Nuovo ordine → notifica immediata a tutti i client
- Cambio stato → aggiornamento automatico su tutte le interfacce
- Non serve ricaricare le pagine

## Risoluzione Problemi

### Port 5000 già in uso
```bash
# Cambia la porta in webapp.py (ultima riga)
socketio.run(app, host='0.0.0.0', port=5001, debug=False)
```

### Errore PyQt5
```bash
# Su Linux, potrebbe servire:
sudo apt-get install python3-pyqt5
# Su macOS:
brew install pyqt5
```

### Menu non carica
- Verifica che `menu.csv` esista
- Controlla il formato CSV (virgole come separatore)
- Usa la funzione "Carica da CSV" nella consolle admin

### Database corrotto
```bash
# Cancella e ricrea il database
rm gestord.db
python -c "import database; database.init_database()"
```

## Sicurezza

⚠️ **Nota di Sicurezza:**
- Cambia la `SECRET_KEY` in `webapp.py` per produzione
- Le password sono hashate con SHA256
- In produzione, usa HTTPS e password più forti
- Ngrok fornisce HTTPS automaticamente

## Licenza

MIT License

## Supporto

Per problemi o domande, apri un issue su GitHub:
https://github.com/ivanlivemusic/gestord/issues
