# GestOrd - Guida Rapida all'Uso

## 🚀 Avvio Rapido

### 1. Prima Installazione

```bash
# Clona il repository
git clone https://github.com/ivanlivemusic/gestord.git
cd gestord

# Installa le dipendenze
pip install -r requirements.txt

# (Opzionale) Crea dati di esempio
python create_demo_data.py
```

### 2. Avvio del Sistema

#### Metodo Semplice - Menu Interattivo
```bash
python start.py
```

Seleziona l'opzione desiderata dal menu:
1. Web App per Camerieri
2. Consolle Amministrazione
3. Display Cucina
4. Test di Sistema

#### Avvio Manuale
```bash
# Terminale 1 - Web App
python webapp.py

# Terminale 2 - Consolle Admin
python admin_console.py

# Terminale 3 - Display Cucina
python kitchen_display.py
```

## 📱 Uso dell'Applicazione Web (Camerieri)

### Login
1. Apri http://localhost:5000
2. Inserisci credenziali:
   - Username: `cameriere`
   - Password: `password123`
3. Clicca "Accedi"

### Prendere un Ordine

1. **Inserisci informazioni tavolo:**
   - Numero Tavolo: es. `5`
   - Numero Persone: es. `4`

2. **Seleziona portate dal menu:**
   - Scorri le categorie (Antipasti, Primi, Secondi, ecc.)
   - Imposta la quantità desiderata
   - Clicca il pulsante `+` per aggiungere al carrello

3. **Aggiungi note (opzionale):**
   - Es. "Cliente vegetariano", "Senza glutine", "Allergico ai crostacei"

4. **Verifica il riepilogo:**
   - Il carrello si apre automaticamente
   - Mostra tutte le portate e il totale

5. **Invia ordine:**
   - Clicca "Invia Ordine"
   - Riceverai conferma con numero ordine

### Navigazione Menu

Il menu è organizzato per categorie:
- 🥗 **Antipasti**: Bruschette, affettati, caprese
- 🍝 **Primi**: Pasta e risotti (divisi in Carne/Pesce)
- 🥩 **Secondi**: Carne e pesce (divisi per tipo)
- 🥦 **Contorni**: Verdure e patate
- 🍕 **Pizzeria**: Tutte le pizze
- 🍰 **Dolci**: Dessert
- 🥤 **Bevande**: Bibite e alcolici
- 🌱 **Vegetariani**: Piatti vegetariani
- 🌿 **Vegani**: Piatti vegani
- ☕ **Caffetteria**: Caffè e tè

### Offerte del Giorno
Se presenti, appaiono in alto con stella ⭐

## 💻 Uso della Consolle Amministrazione

### Tab Ordini

**Visualizzazione:**
- Tabella con tutti gli ordini ordinati per timestamp (più recenti in alto)
- Colonne: ID, Tavolo, Persone, Cameriere, Timestamp, Stato, Dettagli, Azioni

**Gestione Stati:**
- Usa il menu a tendina nella colonna "Azioni"
- Stati disponibili:
  - 🟡 **Inserito**: Ordine appena ricevuto
  - 🔵 **In Lavorazione**: Cucina sta preparando
  - 🟢 **Consegnato**: Ordine completato

**Aggiornamento:**
- Automatico ogni 5 secondi
- Manuale: clicca pulsante "🔄 Aggiorna"

### Tab Gestione Menu

**Caricamento Menu:**
1. Modifica il file `menu.csv`
2. Clicca "📂 Carica da CSV"
3. Seleziona il file aggiornato
4. Conferma caricamento

**Anteprima:**
- Visualizza il menu completo per categorie
- Mostra nome, prezzo e disponibilità

### Tab Offerte del Giorno

**Aggiungere un'offerta:**
1. Clicca "➕ Aggiungi Offerta"
2. Compila:
   - Nome piatto
   - Descrizione
   - Prezzo
   - Categoria
3. Clicca "Salva"

**Note:**
- Le offerte sono valide per la data corrente
- Appariranno automaticamente nel menu web
- Non modificano il CSV principale

### Tab Gestione Utenti

**Aggiungere un cameriere:**
1. Clicca "➕ Aggiungi Cameriere"
2. Compila:
   - Username (univoco)
   - Password
   - Nome Completo
3. Clicca "Salva"

**Credenziali:**
- Le password sono hashate nel database
- Ogni cameriere può accedere alla web app

## 👨‍🍳 Uso del Display Cucina

### Layout
Il display è diviso in 3 colonne:

1. **📋 Nuovi Ordini** (Giallo)
   - Ordini appena inseriti
   - Da prendere in carico

2. **🔥 In Lavorazione** (Blu)
   - Ordini in preparazione
   - Mostrano il progresso

3. **✅ Pronti** (Verde)
   - Ordini completati
   - Pronti per essere serviti

### Flusso di Lavoro

**Per ogni ordine:**
1. Appare in "Nuovi Ordini"
2. Clicca "▶️ Inizia Lavorazione"
   → Si sposta in "In Lavorazione"
3. Quando pronto, clicca "✅ Pronto per Servizio"
   → Si sposta in "Pronti"

**Informazioni visualizzate:**
- Numero ordine e tavolo
- Ora di inserimento
- Numero persone
- Nome cameriere
- Lista portate con quantità
- Note speciali (evidenziate in giallo)

**Aggiornamento:**
- Automatico ogni 3 secondi
- Manuale: clicca "🔄 Aggiorna"

## 🔄 Sincronizzazione Real-Time

Il sistema usa WebSocket per aggiornamenti istantanei:

- **Nuovo ordine** → Appare immediatamente su tutte le interfacce
- **Cambio stato** → Sincronizzazione automatica ovunque
- **Nessun refresh manuale** necessario

## 📊 Esempi di Workflow

### Scenario 1: Cena Standard

1. **Cameriere** (Web App):
   - Login
   - Tavolo 5, 4 persone
   - Aggiunge: 2 Antipasti, 4 Primi, 4 Secondi, 2 Contorni, 1 Vino
   - Invia ordine

2. **Cucina** (Display):
   - Vede nuovo ordine in colonna gialla
   - Clicca "Inizia Lavorazione"
   - Prepara i piatti
   - Clicca "Pronto per Servizio"

3. **Admin** (Consolle):
   - Monitora l'ordine nella tabella
   - Vede i cambi di stato in tempo reale

### Scenario 2: Offerta Speciale

1. **Admin** (Consolle):
   - Tab "Offerte del Giorno"
   - Aggiunge "Risotto al Tartufo - €18"

2. **Cameriere** (Web App):
   - Refresh automatico
   - Vede l'offerta in alto nel menu
   - La propone ai clienti

### Scenario 3: Aggiornamento Menu

1. **Admin**:
   - Modifica `menu.csv` sul PC
   - Aggiunge nuove pizze o piatti
   - Carica da consolle

2. **Sistema**:
   - Database aggiornato
   - Riavvio web app per applicare
   - Nuovo menu disponibile

## 🛠️ Manutenzione

### Backup Database
```bash
# Backup
cp gestord.db gestord_backup_$(date +%Y%m%d).db

# Ripristino
cp gestord_backup_YYYYMMDD.db gestord.db
```

### Pulizia Ordini Vecchi
```python
# Script personalizzato
import database as db
import sqlite3

conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM orders WHERE status = 'Consegnato' AND DATE(timestamp) < DATE('now', '-7 days')")
conn.commit()
conn.close()
```

### Reset Completo
```bash
rm gestord.db
python -c "import database; database.init_database()"
python create_demo_data.py  # Opzionale
```

## 🔐 Sicurezza

### Cambiare Secret Key (Produzione)
In `webapp.py`:
```python
app.config['SECRET_KEY'] = 'la-tua-chiave-segreta-molto-lunga-e-casuale'
```

### Cambiare Password Default
```python
import database as db
db.add_user('nuovo_cameriere', 'password_sicura_123!', 'Mario Rossi')
```

### Usare HTTPS
Ngrok fornisce HTTPS automaticamente:
```bash
export NGROK_AUTH_TOKEN="your_token"
python webapp.py
```

## 📱 Accesso Remoto con Ngrok

### Setup
1. Registrati su https://ngrok.com
2. Ottieni auth token
3. Imposta variabile d'ambiente:
```bash
export NGROK_AUTH_TOKEN="your_token_here"
```

### Uso
```bash
python webapp.py
```

Output mostrerà:
```
🌐 URL Pubblico: https://abc123.ngrok.io
📱 Scansiona il QR code per accedere da mobile
```

### QR Code
- Salvato in `qr_code.txt`
- Usalo per accesso rapido da smartphone
- Valido finché il server è attivo

## 💡 Suggerimenti

### Performance
- Usa SSD per il database
- Chiudi ordini vecchi periodicamente
- Limita dimensioni menu (max 200 piatti)

### Usabilità
- Tablet 10" minimo per cucina
- WiFi stabile e veloce
- Backup regolari del database

### Organizzazione
- Un tablet per cucina
- Uno o più per camerieri
- PC/tablet per amministrazione
- Stampante per scontrini (da integrare)

## 🐛 Debug

### Vedere i Log
```bash
# Web app
python webapp.py 2>&1 | tee webapp.log

# Vedere database
sqlite3 gestord.db
> SELECT * FROM orders;
> .quit
```

### Test Connessione WebSocket
Apri console browser (F12):
```javascript
// Dovrebbe mostrare: Connected to server
```

## 📞 Supporto

- GitHub Issues: https://github.com/ivanlivemusic/gestord/issues
- Wiki: https://github.com/ivanlivemusic/gestord/wiki
- Email: support@example.com (sostituisci con email reale)

## 🎯 Best Practices

1. **Backup giornalieri** del database
2. **Test settimanali** del sistema completo
3. **Aggiornamento menu** fuori orario servizio
4. **Formazione staff** su uso base
5. **Piano B** (carta e penna) sempre pronto
6. **Monitoraggio** ordini in tempo reale
7. **Chiusura ordini** a fine servizio
