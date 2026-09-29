// === NeuroAPI: логика форм и личного кабинета ===

document.addEventListener('DOMContentLoaded', () => {
    setupPasswordToggles();

    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleLogin(loginForm);
        });
    }

    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleRegister(registerForm);
        });
    }

    if (document.getElementById('keysList')) {
        setupDashboard();
    }
});

// ---- Утилиты ----

function setupPasswordToggles() {
    document.querySelectorAll('.toggle-pass').forEach((btn) => {
        btn.addEventListener('click', () => {
            const input = btn.parentElement.querySelector('input');
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.textContent = show ? '🙈' : '👁';
            btn.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
        });
    });
}

function errorBox(id) {
    return document.getElementById(id);
}

function showError(msg, id = 'error-msg') {
    const box = errorBox(id);
    if (!box) return;
    box.textContent = msg;
    box.classList.add('show');
}

function hideError(id = 'error-msg') {
    const box = errorBox(id);
    if (!box) return;
    box.textContent = '';
    box.classList.remove('show');
}

// JSON-запрос с блокировкой кнопки на время ожидания
async function postJson(btn, url, payload) {
    let originalText = null;
    if (btn) {
        originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Подожди…';
    }
    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {}),
        });
        let data = {};
        try {
            data = await res.json();
        } catch (e) { /* ответ не JSON */ }
        return { ok: res.ok, data };
    } catch (e) {
        return { ok: false, data: { error: 'Нет соединения с сервером' } };
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

// ---- Аутентификация ----

async function handleLogin(form) {
    hideError();
    const email = form.querySelector('#email').value.trim();
    const password = form.querySelector('#password').value;

    if (!email || !password) {
        showError('Заполни email и пароль');
        return;
    }

    const btn = form.querySelector('button[type="submit"]');
    const { ok, data } = await postJson(btn, '/api/login', { email, password });
    if (ok && data.redirect_url) {
        window.location.href = data.redirect_url;
    } else {
        showError(data.error || 'Ошибка входа, попробуй ещё раз');
    }
}

async function handleRegister(form) {
    hideError();
    const name = form.querySelector('#fullname').value.trim();
    const email = form.querySelector('#email').value.trim();
    const password = form.querySelector('#password').value;
    const confirm = form.querySelector('#confirm_password').value;

    if (!name || !email || !password) {
        showError('Заполни все поля');
        return;
    }
    if (password.length < 6) {
        showError('Пароль должен быть не короче 6 символов');
        return;
    }
    if (password !== confirm) {
        showError('Пароли не совпадают');
        return;
    }

    const btn = form.querySelector('button[type="submit"]');
    const { ok, data } = await postJson(btn, '/api/register', { name, email, password });
    if (ok && data.redirect_url) {
        window.location.href = data.redirect_url;
    } else {
        showError(data.error || 'Не получилось зарегистрироваться');
    }
}

// ---- Личный кабинет ----

function setupDashboard() {
    document.querySelectorAll('.topup-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            hideError('dashError');
            const { ok, data } = await postJson(btn, '/api/topup', { amount: Number(btn.dataset.amount) });
            if (ok) {
                updateBalance(data.balance);
            } else {
                showError(data.error || 'Не получилось пополнить баланс', 'dashError');
            }
        });
    });

    document.querySelectorAll('.buy-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            hideError('dashError');
            const { ok, data } = await postJson(btn, '/api/purchase', { product: btn.dataset.product });
            if (ok) {
                updateBalance(data.balance);
                showNewKey(data.product_name, data.api_key);
                await refreshKeys();
            } else {
                if (data.error && data.error.includes('пополни баланс')) {
                    document.getElementById('balanceAmount').scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                showError(data.error || 'Покупка не удалась', 'dashError');
            }
        });
    });

    document.getElementById('copyKeyBtn').addEventListener('click', copyNewKey);
}

function updateBalance(balance) {
    document.getElementById('balanceAmount').textContent = `${balance} ₽`;
}

function showNewKey(productName, apiKey) {
    const box = document.getElementById('newKeyBox');
    document.getElementById('newKeyProduct').textContent = productName;
    document.getElementById('newKeyValue').textContent = apiKey;
    box.hidden = false;
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function copyNewKey() {
    const btn = document.getElementById('copyKeyBtn');
    const value = document.getElementById('newKeyValue').textContent;
    try {
        await navigator.clipboard.writeText(value);
        btn.textContent = 'Скопировано ✓';
    } catch (e) {
        btn.textContent = 'Выдели вручную';
    }
    setTimeout(() => { btn.textContent = 'Копировать'; }, 2000);
}

// Перерисовывает список ключей по данным /api/me
async function refreshKeys() {
    const res = await fetch('/api/me');
    if (!res.ok) return;
    const data = await res.json();

    updateBalance(data.balance);
    document.getElementById('keysEmpty').hidden = data.keys.length > 0;

    const list = document.getElementById('keysList');
    list.innerHTML = '';
    for (const k of data.keys) {
        const item = document.createElement('div');
        item.className = 'key-item';

        const icon = document.createElement('span');
        icon.className = 'k-icon';
        icon.textContent = k.product_icon;

        const body = document.createElement('div');
        body.className = 'k-body';
        const prod = document.createElement('div');
        prod.className = 'k-product';
        prod.textContent = k.product_name;
        const key = document.createElement('div');
        key.className = 'k-key';
        key.textContent = k.api_key;
        body.append(prod, key);

        const date = document.createElement('span');
        date.className = 'k-date';
        date.textContent = k.created;

        item.append(icon, body, date);

        if (k.active) {
            const revoke = document.createElement('button');
            revoke.className = 'btn btn-sm btn-ghost';
            revoke.textContent = 'Отозвать';
            revoke.addEventListener('click', () => revokeKey(k.id, revoke));
            item.append(revoke);
        } else {
            const off = document.createElement('span');
            off.className = 'badge-off';
            off.textContent = 'отозван';
            item.append(off);
        }

        list.append(item);
    }
}

async function revokeKey(keyId, btn) {
    hideError('dashError');
    const { ok, data } = await postJson(btn, '/api/revoke_key', { key_id: keyId });
    if (ok) {
        await refreshKeys();
    } else {
        showError(data.error || 'Не получилось отозвать ключ', 'dashError');
    }
}
