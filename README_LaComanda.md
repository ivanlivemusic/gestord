# La Comanda - Sistema Completo di Gestione Ordini Ristorante

**www.ivanlivemusic.com**

Sistema integrato per la gestione degli ordini di un ristorante con avvio automatico di tutti i componenti necessari.

## 🚀 Caratteristiche Principali

### Avvio Automatico Completo
All'avvio di `LAComanda.py` vengono automaticamente lanciati:
- ✅ Server Flask per web app cameriere (porta 5000)
- ✅ Ngrok per accesso remoto (con token preconfigurato)
- ✅ Consolle di Amministrazione (finestra Tkinter)
- ✅ Display Cucina (finestra Tkinter a schermo intero)
- ✅ Finestra QR Code (popup con link ngrok)

### Configurazione Persistente
Il sistema salva e ripristina automaticamente:
- Posizioni finestre (x, y)
- Dimensioni finestre (larghezza, altezza)
- Stato finestre (massimizzate/minimizzate)
- Configurazione salvata in `LaComanda.conf`

### Web App Cameriere
- 📱 Login con username/password
- 📋 Menu completo da CSV con categorie:
  - Antipasti, Primi (Carne/Pesce), Secondi (Carne/Pesce)
  - Contorni, Dolci, Pizzeria
  - Bevande (Bibite/Alcolici)
  - Vegetariani, Vegani, Caffetteria
- 🛒 Carrello con aggiunta multipla portate
- 👥 Gestione numero tavolo e persone
- 🔄 Aggiornamento tempo reale via WebSocket
- 📱 Interfaccia responsive ottimizzata per mobile

### Consolle Amministrazione
- 📊 Lista ordini in tempo reale (timestamp decrescente)
- 📝 Dettagli completi: tavolo, persone, cameriere, portate, stato
- 🔄 Modifica stato ordini (Inserito → In Lavorazione → Consegnato)
- 🍽️ Editor integrato menu (modifica CSV da interfaccia)
- 👥 Gestione camerieri (aggiungi, modifica, elimina)
- 🔄 Aggiornamento automatico ogni 5 secondi

### Display Cucina
- 🖥️ Finestra a schermo intero
- 📋 Ordini divisi per stato in 3 colonne:
  - 📋 NUOVI ORDINI (giallo)
  - 🔥 IN LAVORAZIONE (blu)
  - ✅ PRONTI (verde)
- 🔄 Aggiornamento automatico ogni 3 secondi
- 👆 Touch-friendly per tablet

### QR Code Window
- 📱 Popup con QR code per accesso rapido
- 🌐 URL pubblico ngrok
- 📋 Link copiabile
- 🎨 Design professionale con branding

## 📋 Requisiti

- Python 3.8 o superiore
- Sistema operativo: Windows, Linux, macOS
- Connessione Internet (per ngrok - opzionale)

## 🔧 Installazione

1. **Clona il repository:**
   ```bash
   git clone https://github.com/ivanlivemusic/gestord.git
   cd gestord
   ```

2. **Installa le dipendenze:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verifica la presenza dei file:**
   - `LAComanda.py` - File principale
   - `templates/lacomanda.html` - Template web
   - `LaComanda.conf` - Configurazione (creato automaticamente)
   - `menu.csv` - Menu del ristorante
   - `requirements.txt` - Dipendenze Python

## 🚀 Avvio del Sistema

### Metodo Semplice (Raccomandato)
```bash
python LAComanda.py
```

Questo comando avvia **automaticamente** tutti i componenti:
1. Server Flask + Ngrok
2. QR Code Window
3. Consolle Amministrazione
4. Display Cucina

**Nota:** Al primo avvio, attendi qualche secondo mentre ngrok si connette.

### Output atteso:
```
============================================================
La Comanda - Sistema di Gestione Ordini Ristorante
www.ivanlivemusic.com
============================================================

[1/5] Avvio server Flask...
[2/5] Creazione interfaccia Tkinter...
[3/5] Generazione QR Code...
✓ Ngrok URL: https://xxxx-xx-xx-xxx-xx.ngrok-free.app
[4/5] Avvio Consolle Amministrazione...
[5/5] Avvio Display Cucina...

✓ Tutti i componenti avviati con successo!
✓ Web App: http://localhost:5000
✓ URL Pubblico: https://xxxx-xx-xx-xxx-xx.ngrok-free.app

============================================================
```

## 📱 Accesso all'Applicazione

### Da Computer Locale
Apri il browser e vai su: `http://localhost:5000`

### Da Dispositivo Mobile/Remoto
1. Scansiona il QR Code mostrato nella finestra popup
2. Oppure usa l'URL pubblico ngrok visualizzato nella console

### Credenziali di Default
- **Username:** `cameriere`
- **Password:** `password123`

## 🎯 Utilizzo del Sistema

### 1. Cameriere (Web App)
1. Effettua login con le credenziali
2. Inserisci numero tavolo e persone
3. Seleziona i piatti dal menu (clicca o usa +/-)
4. Verifica il carrello in basso
5. Premi "INVIA ORDINE"
6. Lo stato iniziale è "Inserito"

### 2. Cucina (Display Cucina)
1. Visualizza i nuovi ordini nella colonna "NUOVI ORDINI"
2. Clicca con il tasto destro per cambiare stato
3. Sposta in "IN LAVORAZIONE" quando inizi a preparare
4. Sposta in "PRONTI" quando pronto per il servizio
5. Usa ESC per uscire dalla modalità fullscreen

### 3. Amministrazione (Consolle)
1. Monitora tutti gli ordini in tempo reale
2. Doppio click su un ordine per vedere i dettagli
3. Tasto destro per cambiare lo stato
4. Tab "Menu": gestisci il menu (aggiungi/modifica piatti)
5. Tab "Camerieri": aggiungi nuovi camerieri

## 📄 File del Sistema

### File Principali
- **`LAComanda.py`** - Applicazione principale (tutto in un file)
- **`templates/lacomanda.html`** - Template HTML per web app
- **`LaComanda.conf`** - Configurazione persistente (auto-generato)
- **`menu.csv`** - Menu del ristorante
- **`lacomanda.db`** - Database SQLite (auto-creato)

### Struttura Database
Il sistema crea automaticamente un database SQLite con le seguenti tabelle:
- `users` - Camerieri con credenziali
- `menu_items` - Piatti del menu
- `orders` - Ordini
- `order_items` - Dettagli portate per ogni ordine
- `daily_specials` - Offerte del giorno

## 🍽️ Gestione Menu

### Caricamento da CSV
Il file `menu.csv` deve avere questa struttura:
```csv
Categoria,Sottocategoria,Nome,Prezzo,Descrizione
Antipasti,,Bruschetta al Pomodoro,6.50,Pane tostato con pomodori freschi
Primi,Carne,Lasagne alla Bolognese,10.00,Lasagne fatte in casa
Primi,Pesce,Spaghetti alle Vongole,12.00,Spaghetti con vongole fresche
```

### Categorie Supportate
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

### Modifica Menu
1. Dalla consolle amministrazione → Tab "Menu"
2. Clicca "➕ Nuovo Piatto" per aggiungere
3. Oppure modifica direttamente il file `menu.csv`
4. Clicca "📁 Carica da CSV" per aggiornare

## 👥 Gestione Camerieri

### Aggiungere un Nuovo Cameriere
1. Consolle amministrazione → Tab "Camerieri"
2. Clicca "➕ Aggiungi Cameriere"
3. Inserisci: username, password, nome completo
4. Salva

### Cameriere di Default
Il sistema crea automaticamente un utente:
- Username: `cameriere`
- Password: `password123`
- Nome: `Cameriere Default`

## ⚙️ Configurazione

### Token Ngrok
Il token ngrok è preconfigurato nel codice:
```python
NGROK_TOKEN = "33QsRShp08GVLeGoBmh5Usdwvjw_7DZg6nr29UTfnHMrfnzyX"
```

Per usare un token diverso, modifica la variabile nel file `LAComanda.py`.

### Porta Web Server
Default: 5000

Per cambiarla, modifica la variabile nel file `LAComanda.py`:
```python
PORT = 5001  # Cambia qui
```

### Configurazione Finestre
Le posizioni e dimensioni delle finestre sono salvate automaticamente in `LaComanda.conf` quando chiudi le finestre.

Per ripristinare i valori di default, elimina il file:
```bash
rm LaComanda.conf
```

## 🔒 Sicurezza

⚠️ **Nota di Sicurezza:**
- Cambia la `SECRET_KEY` in produzione
- Le password sono hashate con SHA256
- In produzione, usa password più forti
- Ngrok fornisce automaticamente HTTPS
- Cambia le credenziali di default

## 🐛 Risoluzione Problemi

### Porta 5000 già in uso
```bash
# Modifica PORT in LAComanda.py
PORT = 5001
```

### Errore Tkinter su Linux
```bash
sudo apt-get install python3-tk
```

### Ngrok non si connette
- Verifica la connessione Internet
- Il sistema funziona anche senza ngrok (solo locale)
- Controlla che il token sia valido

### Database corrotto
```bash
# Elimina e ricrea il database
rm lacomanda.db
python LAComanda.py  # Il database viene ricreato automaticamente
```

### Menu non carica
- Verifica che `menu.csv` esista
- Controlla il formato CSV (virgole come separatore)
- Usa "Carica da CSV" dalla consolle admin

## 🎨 Personalizzazione

### Modificare i Colori
Modifica i colori nel file `templates/lacomanda.html`:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Modificare il Branding
Cerca nel codice le stringhe:
- "La Comanda"
- "www.ivanlivemusic.com"

E sostituiscile con il tuo brand.

## 📊 Stati Ordine

Il sistema gestisce 3 stati principali:
1. **Inserito** - Ordine appena creato dal cameriere
2. **In Lavorazione** - Ordine in preparazione in cucina
3. **Consegnato** - Ordine pronto/servito

Gli stati possono essere modificati da:
- Consolle Amministrazione
- Display Cucina
- Web App (solo visualizzazione)

## 🔄 Aggiornamenti in Tempo Reale

Il sistema usa WebSocket (Socket.IO) per:
- Notificare nuovi ordini a tutti i client
- Aggiornare lo stato degli ordini in tempo reale
- Sincronizzare cucina, admin e camerieri
- Nessun bisogno di ricaricare le pagine

## 📝 File Generati Automaticamente

Al primo avvio, il sistema crea:
- `lacomanda.db` - Database SQLite
- `LaComanda.conf` - Configurazione finestre (se non esiste)
- Log nella console di sistema

## 💡 Suggerimenti

1. **Tablet in Cucina:** Usa un tablet con il Display Cucina in modalità fullscreen
2. **Mobile per Camerieri:** I camerieri possono usare smartphone/tablet via ngrok
3. **Backup Database:** Fai backup periodici di `lacomanda.db`
4. **Menu CSV:** Mantieni una copia di backup di `menu.csv`
5. **Configurazione:** Salva una copia di `LaComanda.conf` personalizzato

## 📞 Supporto

Per problemi o domande:
- Email: info@ivanlivemusic.com
- Sito: www.ivanlivemusic.com
- GitHub Issues: https://github.com/ivanlivemusic/gestord/issues

## 📄 Licenza

MIT License

Copyright (c) 2024 Ivan Live Music

## 🙏 Ringraziamenti

Sviluppato per semplificare la gestione degli ordini nei ristoranti.

**La Comanda** - Gestione ordini semplice e professionale.

---

*www.ivanlivemusic.com*
