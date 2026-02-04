// Menu.js - Client-side logic for menu and order management

let cart = [];
let menuData = {};
let socket = null;

// Initialize WebSocket connection
function initSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
    });
}

// Load menu on page load
document.addEventListener('DOMContentLoaded', async () => {
    initSocket();
    await loadMenu();
});

async function loadMenu() {
    try {
        const response = await fetch('/api/menu');
        const data = await response.json();
        
        menuData = data.menu;
        const specials = data.specials;
        
        // Display specials if available
        if (specials && specials.length > 0) {
            displaySpecials(specials);
        }
        
        // Display regular menu
        displayMenu(menuData);
    } catch (error) {
        console.error('Error loading menu:', error);
        alert('Errore nel caricamento del menu');
    }
}

function displaySpecials(specials) {
    const specialsSection = document.getElementById('specialsSection');
    const specialsContainer = document.getElementById('specialsContainer');
    
    specialsSection.style.display = 'block';
    specialsContainer.innerHTML = '';
    
    specials.forEach(special => {
        const itemElement = createMenuItem({
            id: `special_${special.id}`,
            nome: special.nome,
            prezzo: special.prezzo,
            descrizione: special.descrizione,
            categoria: 'Offerta del Giorno'
        });
        specialsContainer.appendChild(itemElement);
    });
}

function displayMenu(menu) {
    const container = document.getElementById('menuContainer');
    container.innerHTML = '';
    
    // Define category order
    const categoryOrder = [
        'Antipasti', 'Primi', 'Secondi', 'Contorni', 
        'Pizzeria', 'Vegetariani', 'Vegani', 
        'Dolci', 'Bevande', 'Caffetteria'
    ];
    
    categoryOrder.forEach(category => {
        if (menu[category]) {
            const section = document.createElement('div');
            section.className = 'menu-section';
            
            const title = document.createElement('h2');
            title.className = 'section-title';
            title.textContent = getCategoryIcon(category) + ' ' + category;
            section.appendChild(title);
            
            const subcategories = menu[category];
            
            Object.keys(subcategories).forEach(subcategory => {
                if (subcategory !== 'Generale' && Object.keys(subcategories).length > 1) {
                    const subtitle = document.createElement('h3');
                    subtitle.className = 'subsection-title';
                    subtitle.textContent = subcategory;
                    section.appendChild(subtitle);
                }
                
                const itemsContainer = document.createElement('div');
                itemsContainer.className = 'menu-items';
                
                subcategories[subcategory].forEach(item => {
                    const itemElement = createMenuItem({
                        ...item,
                        categoria: category
                    });
                    itemsContainer.appendChild(itemElement);
                });
                
                section.appendChild(itemsContainer);
            });
            
            container.appendChild(section);
        }
    });
}

function getCategoryIcon(category) {
    const icons = {
        'Antipasti': '🥗',
        'Primi': '🍝',
        'Secondi': '🥩',
        'Contorni': '🥦',
        'Pizzeria': '🍕',
        'Dolci': '🍰',
        'Bevande': '🥤',
        'Vegetariani': '🌱',
        'Vegani': '🌿',
        'Caffetteria': '☕'
    };
    return icons[category] || '🍽️';
}

function createMenuItem(item) {
    const div = document.createElement('div');
    div.className = 'menu-item';
    
    const info = document.createElement('div');
    info.className = 'menu-item-info';
    
    const name = document.createElement('div');
    name.className = 'menu-item-name';
    name.textContent = item.nome;
    info.appendChild(name);
    
    if (item.descrizione) {
        const desc = document.createElement('div');
        desc.className = 'menu-item-description';
        desc.textContent = item.descrizione;
        info.appendChild(desc);
    }
    
    const price = document.createElement('div');
    price.className = 'menu-item-price';
    price.textContent = `€${item.prezzo.toFixed(2)}`;
    info.appendChild(price);
    
    const actions = document.createElement('div');
    actions.className = 'menu-item-actions';
    
    const quantityInput = document.createElement('input');
    quantityInput.type = 'number';
    quantityInput.className = 'quantity-input';
    quantityInput.min = '1';
    quantityInput.value = '1';
    quantityInput.id = `qty_${item.id}`;
    
    const addButton = document.createElement('button');
    addButton.className = 'add-btn';
    addButton.textContent = '+';
    addButton.onclick = () => addToCart(item, quantityInput.value);
    
    actions.appendChild(quantityInput);
    actions.appendChild(addButton);
    
    div.appendChild(info);
    div.appendChild(actions);
    
    return div;
}

function addToCart(item, quantity) {
    quantity = parseInt(quantity);
    
    if (quantity < 1) {
        alert('Quantità non valida');
        return;
    }
    
    // Check if item already in cart
    const existingItem = cart.find(i => i.menu_item_id === item.id);
    
    if (existingItem) {
        existingItem.quantity += quantity;
    } else {
        cart.push({
            menu_item_id: item.id,
            nome: item.nome,
            prezzo: item.prezzo,
            quantity: quantity,
            categoria: item.categoria
        });
    }
    
    updateCartDisplay();
}

function updateCartDisplay() {
    const cartSummary = document.getElementById('cartSummary');
    const cartItems = document.getElementById('cartItems');
    const cartTotal = document.getElementById('cartTotal');
    
    if (cart.length === 0) {
        cartSummary.style.display = 'none';
        return;
    }
    
    cartSummary.style.display = 'block';
    cartItems.innerHTML = '';
    
    let total = 0;
    
    cart.forEach((item, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'cart-item';
        
        const nameDiv = document.createElement('div');
        nameDiv.innerHTML = `
            <div class="cart-item-name">${item.nome}</div>
            <div class="cart-item-quantity">${item.quantity}x €${item.prezzo.toFixed(2)}</div>
        `;
        
        const priceDiv = document.createElement('div');
        priceDiv.className = 'cart-item-price';
        const itemTotal = item.quantity * item.prezzo;
        priceDiv.textContent = `€${itemTotal.toFixed(2)}`;
        
        const removeBtn = document.createElement('button');
        removeBtn.textContent = '✕';
        removeBtn.className = 'btn btn-secondary btn-sm';
        removeBtn.onclick = () => removeFromCart(index);
        
        itemDiv.appendChild(nameDiv);
        itemDiv.appendChild(priceDiv);
        itemDiv.appendChild(removeBtn);
        
        cartItems.appendChild(itemDiv);
        
        total += itemTotal;
    });
    
    cartTotal.textContent = total.toFixed(2);
}

function removeFromCart(index) {
    cart.splice(index, 1);
    updateCartDisplay();
}

function clearCart() {
    if (confirm('Svuotare il carrello?')) {
        cart = [];
        updateCartDisplay();
    }
}

async function submitOrder() {
    const tableNumber = document.getElementById('tableNumber').value;
    const numPeople = document.getElementById('numPeople').value;
    const notes = document.getElementById('orderNotes').value;
    
    if (!tableNumber || !numPeople) {
        alert('Inserire numero tavolo e numero persone');
        return;
    }
    
    if (cart.length === 0) {
        alert('Il carrello è vuoto');
        return;
    }
    
    const orderData = {
        table_number: parseInt(tableNumber),
        num_people: parseInt(numPeople),
        items: cart,
        notes: notes
    };
    
    try {
        const response = await fetch('/api/orders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(orderData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`✅ Ordine #${result.order_id} inviato con successo!`);
            
            // Clear form
            cart = [];
            updateCartDisplay();
            document.getElementById('tableNumber').value = '';
            document.getElementById('numPeople').value = '';
            document.getElementById('orderNotes').value = '';
        } else {
            alert('❌ Errore nell\'invio dell\'ordine');
        }
    } catch (error) {
        console.error('Error submitting order:', error);
        alert('❌ Errore di connessione');
    }
}
