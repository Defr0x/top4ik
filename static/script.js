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

    // Если мы на странице кабинета (есть кнопки покупки)
    if (document.querySelector('.buy-btn')) {
        setupDashboard();
    }
});

function setupPasswordToggles() {
    document.querySelectorAll('.toggle-pass').forEach((btn) => {
        btn.addEventListener('click', () => {
            const input = btn.parentElement.querySelector('input');
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.textContent = show ? '🙈' : '👁';
        });
    });
}

function showError(msg, id = 'error-msg') {
    const box = document.getElementById(id);
    if (!box) return;
    box.textContent = msg;
    box.classList.add('show');
}

function hideError(id = 'error-msg') {
    const box = document.getElementById(id);
    if (!box) return;
    box.textContent = '';
    box.classList.remove('show');
}

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
        try { data = await res.json(); } catch (e) {}
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

async function handleLogin(form) {
    hideError();
    const email = form.querySelector('#email').value.trim();
    const password = form.querySelector('#password').value;

    if (!email || !password) { showError('Заполни email и пароль'); return; }

    const btn = form.querySelector('button[type="submit"]');
    const { ok, data } = await postJson(btn, '/api/login', { email, password });
    if (ok && data.redirect_url) {
        window.location.href = data.redirect_url;
    } else {
        showError(data.error || 'Ошибка входа');
    }
}

async function handleRegister(form) {
    hideError();
    const name = form.querySelector('#fullname').value.trim();
    const email = form.querySelector('#email').value.trim();
    const password = form.querySelector('#password').value;
    const confirm = form.querySelector('#confirm_password').value;

    if (!name || !email || !password) { showError('Заполни все поля'); return; }
    if (password.length < 6) { showError('Пароль должен быть не короче 6 символов'); return; }
    if (password !== confirm) { showError('Пароли не совпадают'); return; }

    const btn = form.querySelector('button[type="submit"]');
    const { ok, data } = await postJson(btn, '/api/register', { name, email, password });
    if (ok && data.redirect_url) {
        window.location.href = data.redirect_url;
    } else {
        showError(data.error || 'Не получилось зарегистрироваться');
    }
}

function setupDashboard() {
    document.querySelectorAll('.topup-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            hideError('dashError');
            const { ok, data } = await postJson(btn, '/api/topup', { amount: Number(btn.dataset.amount) });
            if (ok) {
                // Перезагружаем страницу, чтобы обновить баланс и историю
                window.location.reload();
            } else {
                showError(data.error || 'Ошибка пополнения', 'dashError');
            }
        });
    });

    document.querySelectorAll('.buy-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            hideError('dashError');
            const { ok, data } = await postJson(btn, '/api/purchase', { product: btn.dataset.product });
            if (ok) {
                alert(`Успешно куплен ${data.product_name}!`);
                window.location.reload();
            } else {
                showError(data.error || 'Покупка не удалась', 'dashError');
            }
        });
    });
}