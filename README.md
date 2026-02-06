# LA COMANDA v3.0 - Sistema Professionale di Gestione Ordini Ristorante

**www.ivanlivemusic.com**

Sistema completo professionale per la gestione degli ordini di un ristorante, composto da:
- **Console Amministrazione** con gestione completa ordini, menu, camerieri e configurazione
- **Applicazione Web per Camerieri** con interfaccia mobile-friendly
- **Display Cucina** con workflow CI/CD e sistema reminder
- **Finestra QR Code** per accesso remoto via ngrok
- **Database Doppio** (ordini correnti + storico)
- **Sistema Reminder Automatico** con notifiche real-time
- **Gestione Modifiche** con workflow di approvazione
- **Fasce Orarie Flessibili** con supporto overnight

## 🚀 Quick Start

**Leggi prima:** [QUICKSTART_V3.md](QUICKSTART_V3.md) - Guida rapida di 5 minuti

```bash
# 1. Installa dipendenze
pip install -r requirements.txt

# 2. Avvia il sistema
python3 LAComanda.py

# 3. Login con credenziali default
# Username: cameriere
# Password: password
```

## ✨ Caratteristiche Principali

### 🔥 Novità v3.0

#### 1. **Dual Database System**
- `orders.db` - Ordini giornata corrente (alta performance)
- `orders_history.db` - Storico completo (analytics)
- Migrazione automatica a fine giornata

#### 2. **CI/CD Order Types**
- **CI** (Consegna Immediata): Bevande, piatti freddi
- **CD** (Consegna Differita): Piatti da cucinare
- Workflow separati e ottimizzati

#### 3. **Flexible Business Hours**
- Fascia singola o doppia (pranzo + cena)
- Supporto overnight (es. 17:00→04:00)
- Configurazione via UI
- Timer automatico fine giornata

#### 4. **Sistema Modifiche a Due Livelli**
- **Admin**: Modifica diretta con notifiche automatiche
- **Cameriere**: Richiesta + approvazione workflow
- Audit trail completo
- Notifiche real-time (Socket.IO)

#### 5. **Sistema Reminder Intelligente**
- CI: 10 min → notifica cameriere
- CD: 25 min → colonna REMINDER cucina
- CD preparato: 5 min → notifica ritiro
- Icone stato: ⏱️ ⚠️ 🔥
- Reset automatico su modifiche

#### 6. **Receipt Configuration**
- Dati azienda configurabili
- Template personalizzabili
- Supporto logo e QR code pagamento
- Anteprima in tempo reale

#### 7. **Order History & Analytics**
- Tab storico con filtri avanzati
- Export CSV/Excel
- Ristampa scontrini
- Delete con conferma

#### 8. **Waiter Management**
- CRUD completo camerieri
- Password hash sicuro (SHA-256)
- Active/Inactive toggle
- Audit accessi

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
- Accesso tramite QR Code e ngrok (token integrato)
- Interfaccia responsive ottimizzata per mobile

### Consolle Amministrazione
- Visualizzazione ordini in tempo reale
- Tabella ordinata per timestamp decrescente
- Dettagli completi di ogni ordine (tavolo, persone, cameriere, portate)
- Modifica stato ordini (Inserito → In Lavorazione → Consegnato)
- **Editor Menu Integrato (NUOVO!):**
  - Aggiungi, modifica, elimina piatti direttamente dall'interfaccia
  - Non serve più modificare il CSV manualmente
  - Gestione completa di categorie, sottocategorie, prezzi e descrizioni
- Caricamento menu da CSV (opzionale)
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

### Metodo 1: Launcher GUI (Consigliato per Windows/Desktop)
```bash
python main_gui.py
```

Questo aprirà un'interfaccia grafica con pulsanti per:
- Avviare/fermare l'applicazione web
- Avviare/fermare la consolle amministrazione
- Avviare/fermare il display cucina
- Visualizzare il QR Code per l'accesso remoto
- Monitorare i log di tutti i componenti

### Metodo 2: Script di Avvio Interattivo (Terminale)
```bash
python start.py
```

Questo mostrerà un menu interattivo in modalità testuale per lanciare i vari componenti.

### Metodo 3: Versione Single-File (Per facilità di distribuzione)
```bash
python gestord_all_in_one.py
```

Questa versione contiene tutto il sistema in un unico file. Opzioni disponibili:
```bash
python gestord_all_in_one.py --webapp      # Solo web app
python gestord_all_in_one.py --admin       # Solo consolle admin
python gestord_all_in_one.py --kitchen     # Solo display cucina
python gestord_all_in_one.py --init-db     # Inizializza database
```

### Metodo 4: Avvio Manuale dei Componenti

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
Il sistema include un token ngrok preconfigurato per l'accesso remoto immediato.

**Token integrato:** Il sistema usa automaticamente il token configurato, ma puoi sovrascriverlo con la variabile d'ambiente:
```bash
export NGROK_AUTH_TOKEN="your_token_here"
```

L'applicazione web genererà automaticamente:
- URL pubblico accessibile da Internet
- QR Code salvato in `qr_code.txt`
- QR Code visualizzabile dal Launcher GUI

**Nota:** Ngrok è opzionale. Senza, l'app funziona solo sulla rete locale.

## Struttura del Progetto

```
gestord/
├── main_gui.py           # Launcher GUI principale (NUOVO)
├── gestord_all_in_one.py # Versione single-file (NUOVO)
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

---

## 📚 Documentazione Completa

### Per Utenti
- **[QUICKSTART_V3.md](QUICKSTART_V3.md)** - Guida rapida di 5 minuti per iniziare
- **[README_LaComanda.md](README_LaComanda.md)** - Manuale utente completo
- **[GUIDA_USO.md](GUIDA_USO.md)** - Guida all'uso operativo

### Per Sviluppatori
- **[IMPLEMENTATION_FINAL.md](IMPLEMENTATION_FINAL.md)** - Riferimento tecnico completo (21KB)
- **[README_IMPLEMENTATION_V3.md](README_IMPLEMENTATION_V3.md)** - Panoramica implementazione
- **[IMPLEMENTATION_COMPLETE_FINAL.md](IMPLEMENTATION_COMPLETE_FINAL.md)** - Riepilogo finale

### Per Security Team
- **[SECURITY_FINAL.md](SECURITY_FINAL.md)** - Analisi sicurezza completa (12KB)

---

## 🎯 Workflow Operativo

### Cameriere (Web)
1. Login: `/lacomanda/login`
2. Prendi ordine: seleziona piatti, tavolo, numero persone
3. Conferma ordine → VA in database + notifica cucina (se CD)
4. Monitora stato: inserito → preparato → in_consegna → consegnato
5. Richiedi modifica (se necessario) → attendi approvazione admin

### Cucina (Display)
1. Vedi ordini CD in colonna INSERITO
2. Inizi preparazione → sposta in PREPARATO
3. Finisci → IN_CONSEGNA (notifica cameriere)
4. Se passa tempo → ordine in colonna 🔥 REMINDER

### Admin (Console)
1. Monitora tutti gli ordini in tempo reale
2. Approva/rifiuta richieste modifica camerieri
3. Modifica ordini direttamente (notifiche automatiche)
4. Gestisci camerieri, menu, configurazione
5. Vedi storico, export dati, ristampa scontrini
6. Marca consegnato → pagato (unico con permesso)

---

## 🔄 Stati Ordine

| Stato | Descrizione | Colore | Chi cambia |
|-------|-------------|--------|------------|
| `inserito` | Ordine ricevuto | 🟡 Giallo | Auto |
| `preparato` | Cucina finito | 🔵 Blu | Cucina |
| `in_consegna` | In consegna | 🟣 Viola | Cameriere |
| `consegnato` | Consegnato | 🟢 Verde | Cameriere |
| `pagato` | Pagato | 🟢 Verde Scuro | Solo Admin |

---

**LA COMANDA v3.0** - www.ivanlivemusic.com
