# LA COMANDA - Quick Start Guide

## 🚀 Quick Setup (5 Minutes)

### 1. First Launch
```bash
python3 LAComanda.py
```

**What opens:** Only the Admin Console (main control center)

### 2. Add Your First Waiter
1. In Admin Console, click tab **"👔 Gestione Camerieri"**
2. Click **"➕ Aggiungi Cameriere"**
3. Fill in:
   - Username: `mario`
   - Password: `password123`
   - Nome Completo: `Mario Rossi`
4. Click **"Salva"**

### 3. Show Kitchen Display
1. Click tab **"🖥️ Finestre"**
2. Click **"Mostra Display Cucina"**
3. Kitchen Display window appears → **drag to second monitor**

### 4. Show QR Code (Optional)
1. In **"🖥️ Finestre"** tab
2. Click **"Mostra Finestra QR"**
3. Print or display QR for waiters to scan

### 5. Configure Business Hours
1. Click tab **"⚙️ Configurazione"**
2. Choose mode:
   - **Single Shift:** One service (e.g., 12:00-23:00)
   - **Double Shift:** Lunch & dinner (e.g., 12:00-14:30, 19:00-23:00)
3. Set times
4. Click **"Salva Configurazione"**

---

## 📱 Waiter Workflow

### Login
1. Scan QR code or go to: `http://[server]/lacomanda/cameriere`
2. Enter username/password
3. Main menu appears

### Taking Orders
1. **Select Table:** Choose table number
2. **Add Items:** 
   - Browse menu by category
   - Click items to add
   - Adjust quantities with +/-
3. **CI vs CD:**
   - 🔴 **CI (Immediate):** Beverages, coffee → Direct delivery
   - 🟢 **CD (Kitchen):** Food → Goes to kitchen first
4. **Send Order:** Click "Invia Ordine"

---

## 👨‍🍳 Kitchen Workflow

Kitchen Display shows **4 columns:**

### Column 1: INSERITO (New Orders)
- New CD orders appear here
- Click order → Change to "Preparato"

### Column 2: PREPARATO (Ready)
- Orders ready for delivery
- Waiter notified after 5 minutes

### Column 3: 🔥 REMINDER (Urgent)
- Orders taking too long
- Icons:
  - ⏱️ Normal (10-20 min)
  - ⚠️ Warning (20-25 min)
  - 🔥 Urgent (25+ min)

### Column 4: DA CONSEGNARE (To Deliver)
- All orders (CI + CD) ready for delivery
- Waiter marks as "Consegnato" when delivered

---

## 🎛️ Admin Operations

### View All Orders
- Tab **"📋 Ordini Attivi"**
- See all active orders in real-time
- Change status with buttons

### Order History
- Tab **"📚 Storico Ordini"**
- Filter by date, table, waiter
- View past orders
- Reprint receipts

### Manage Waiters
- Tab **"👔 Gestione Camerieri"**
- Add/Edit/Delete waiters
- Change passwords
- Enable/Disable accounts

### Configuration
- Tab **"⚙️ Configurazione"**
- Business hours
- Company info (for receipts)

### Window Controls
- Tab **"🖥️ Finestre"**
- Show/Hide Kitchen Display
- Show/Hide QR Window

---

## 🔄 Daily Routine

### Morning
1. Start system: `python3 LAComanda.py`
2. Verify business hours are correct
3. Show Kitchen Display (if hidden)
4. Ready to take orders!

### During Service
- **Waiters:** Take orders via web interface
- **Kitchen:** Monitor Kitchen Display, update statuses
- **Admin:** Monitor Admin Console, handle issues

### End of Day
- System automatically archives completed orders at closing time
- Or manually close all orders as "Pagato"
- Orders move to history database automatically

---

## ⚙️ Important Settings

### Remote Access (Optional)
For waiters to access from phones/tablets outside local network:

```bash
export NGROK_AUTH_TOKEN="your_token_here"
python3 LAComanda.py
```

Get token from: https://dashboard.ngrok.com/

### Menu Management
Edit `menu.csv` to update menu:
```csv
Categoria,Sottocategoria,Nome,Prezzo,Descrizione,Tipo
Primi,,Pasta al Pomodoro,7.00,Classic pasta,CD
Bevande,Bibite,Coca Cola,3.00,Soft drink,CI
```

**Tipo column:**
- `CD` = Kitchen preparation needed
- `CI` = Immediate service (no kitchen)

---

## 🆘 Common Issues

### "No module named flask"
```bash
pip install -r requirements.txt
```

### Kitchen Display not showing
1. Go to Admin Console
2. Tab **"🖥️ Finestre"**
3. Click **"Mostra Display Cucina"**

### QR code not working
Check URL in QR window:
- Should be: `http://[server]/lacomanda/cameriere`
- If localhost only, set NGROK_AUTH_TOKEN for remote access

### Orders not appearing in Kitchen
- Check order type (tipo_consegna)
- CD orders appear in Kitchen Display
- CI orders skip kitchen (immediate delivery)

---

## 📊 Order Statuses

| Status | Color | Meaning |
|--------|-------|---------|
| inserito | 🟠 Orange | New order, sent to kitchen |
| preparato | 🔵 Blue | Ready in kitchen |
| in_consegna | 🟣 Purple | Being delivered to table |
| consegnato | 🟢 Green | Delivered to customer |
| pagato | 🟢 Dark Green | Paid, complete |

---

## 🎯 Tips for Efficiency

1. **Use keyboard shortcuts** in admin console
2. **Multi-monitor setup:** Admin on one screen, Kitchen on another
3. **Tablet for waiters:** Better than phone for complex orders
4. **Regular backups:** lacomanda.db and lacomanda_history.db
5. **Check reminders:** Address 🔥 urgent orders first

---

## 📞 Support

For issues or questions:
- Check `lacomanda.log` for errors
- Review `IMPLEMENTATION_FINAL.md` for detailed docs
- Check `README_LaComanda.md` for CI/CD workflow details

---

**Version:** 3.0 (Complete)  
**Last Updated:** February 6, 2025  
**Status:** Production Ready ✅
