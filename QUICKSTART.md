# 🚀 La Comanda - Guida Rapida

**Sistema Completo di Gestione Ordini Ristorante**
www.ivanlivemusic.com

## 📦 Installazione Rapida (5 minuti)

### 1. Clona il Repository
```bash
git clone https://github.com/ivanlivemusic/gestord.git
cd gestord
```

### 2. Installa le Dipendenze
```bash
pip install -r requirements.txt
```

### 3. Test del Sistema (Opzionale)
```bash
python test_lacomanda.py
```

### 4. Avvia La Comanda
```bash
python LAComanda.py
```

## ✅ Cosa Succede all'Avvio

Al lancio di `LAComanda.py`, il sistema avvia automaticamente:

1. **Server Flask** (porta 5000)
   - Web app per camerieri
   - API REST per ordini

2. **Ngrok** (tunnel pubblico)
   - URL pubblico tipo: `https://xxxx.ngrok-free.app`
   - Accesso da qualsiasi dispositivo

3. **Finestra QR Code** 
   - Popup con QR code da scansionare
   - Link diretto all'app web

4. **Consolle Amministrazione**
   - Gestione ordini in tempo reale
   - Editor menu integrato
   - Gestione camerieri

5. **Display Cucina**
   - Schermo intero con ordini
   - 3 colonne: Nuovi, In Lavorazione, Pronti
   - Aggiornamento automatico

## 🎯 Primo Utilizzo

### Per il Cameriere (Mobile/Tablet)
1. Scansiona il QR code con il tuo smartphone
2. Login con: `cameriere` / `password123`
3. Inserisci numero tavolo e persone
4. Aggiungi piatti dal menu
5. Premi "INVIA ORDINE"

### Per la Cucina (Tablet/PC)
1. Guarda la finestra "Display Cucina" (fullscreen)
2. I nuovi ordini appaiono nella colonna gialla
3. Click destro → "In Lavorazione" quando inizi
4. Click destro → "Consegnato" quando pronto
5. ESC per uscire da fullscreen

### Per l'Amministratore (PC)
1. Guarda la finestra "Consolle Amministrazione"
2. Tab "Ordini": monitora tutti gli ordini
3. Tab "Menu": modifica il menu
4. Tab "Camerieri": aggiungi nuovi camerieri

## 🔑 Credenziali Default

**Username:** cameriere  
**Password:** password123

⚠️ Cambia la password dopo il primo accesso!

## 📱 Accesso Remoto

### Da Smartphone/Tablet
- Scansiona il QR code nella finestra popup
- Oppure copia l'URL da console

### Da Computer sulla Stessa Rete
- Vai su `http://localhost:5000`

### Da Internet (ovunque)
- Usa l'URL ngrok visualizzato (es: `https://xxxx.ngrok-free.app`)

## ⚙️ File Importanti

| File | Descrizione |
|------|-------------|
| `LAComanda.py` | Applicazione principale (tutto in uno) |
| `templates/lacomanda.html` | Interfaccia web camerieri |
| `menu.csv` | Database menu ristorante |
| `lacomanda.db` | Database ordini (auto-creato) |
| `LaComanda.conf` | Configurazione finestre (auto-creato) |

## 🍽️ Modifica Menu

### Metodo 1: Da File CSV
1. Modifica `menu.csv` con Excel o editor di testo
2. Dalla consolle admin → Tab Menu → "Carica da CSV"

### Metodo 2: Da Interfaccia
1. Consolle admin → Tab Menu
2. Click "Nuovo Piatto"
3. Compila i campi e salva

## 🔧 Risoluzione Problemi

### Porta 5000 già in uso
```python
# Modifica in LAComanda.py:
PORT = 5001  # Cambia la porta
```

### Ngrok non si connette
- Verifica connessione internet
- Il sistema funziona anche senza ngrok (solo locale)

### Menu vuoto
```bash
# Verifica che menu.csv esista
ls menu.csv

# Ricarica da consolle admin
# Tab Menu → "Carica da CSV"
```

### Database corrotto
```bash
# Elimina e ricrea
rm lacomanda.db
python LAComanda.py  # Ricrea automaticamente
```

## 📊 Flusso di Lavoro Tipico

```
CAMERIERE                CUCINA                 ADMIN
   |                       |                      |
   |---Inserisce Ordine--->|                      |
   |                       |                      |
   |                       |<---Vede in "NUOVI"-->|
   |                       |                      |
   |                       |--Inizia Lavorazione->|
   |                       |                      |
   |                       |<--In "LAVORAZIONE"-->|
   |                       |                      |
   |                       |--Completa Ordine---->|
   |                       |                      |
   |                       |<----Vede "PRONTO"--->|
   |<--Notifica Pronto-----|                      |
   |                       |                      |
   |---Serve al Tavolo---->|                      |
```

## 💾 Backup

### Backup Database
```bash
cp lacomanda.db lacomanda_backup_$(date +%Y%m%d).db
```

### Backup Menu
```bash
cp menu.csv menu_backup_$(date +%Y%m%d).csv
```

## 📞 Supporto

**Documentazione completa:** `README_LaComanda.md`

**Problemi o domande:**
- Email: info@ivanlivemusic.com
- Sito: www.ivanlivemusic.com
- GitHub: https://github.com/ivanlivemusic/gestord/issues

## 🎨 Personalizzazione

### Cambia il Nome
Cerca nel codice `LAComanda.py` e `lacomanda.html`:
- "La Comanda" → "Il Tuo Nome"
- "www.ivanlivemusic.com" → "www.tuosito.com"

### Cambia i Colori
Modifica in `templates/lacomanda.html`:
```css
background: linear-gradient(135deg, #tuoColore1 0%, #tuoColore2 100%);
```

## 🏆 Caratteristiche Uniche

✅ **Tutto in un File** - LAComanda.py contiene tutto  
✅ **Avvio Automatico** - Un comando, tutti i componenti  
✅ **Configurazione Persistente** - Ricorda posizioni finestre  
✅ **QR Code Integrato** - Accesso immediato da mobile  
✅ **Tempo Reale** - WebSocket per aggiornamenti istantanei  
✅ **Zero Configurazione** - Funziona subito dopo l'installazione  

## 📝 Checklist Primo Avvio

- [ ] Dipendenze installate (`pip install -r requirements.txt`)
- [ ] Test superati (`python test_lacomanda.py`)
- [ ] Sistema avviato (`python LAComanda.py`)
- [ ] QR code visualizzato
- [ ] Login web app funzionante
- [ ] Menu caricato correttamente
- [ ] Ordine di test creato
- [ ] Ordine visibile in cucina
- [ ] Ordine visibile in admin
- [ ] Password default cambiata

---

**La Comanda** - La soluzione completa per il tuo ristorante.

*Made with ❤️ by www.ivanlivemusic.com*
