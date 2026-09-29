from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import mysql.connector
import hashlib

app = Flask(__name__)  
app.secret_key = 'super_secret_session_key_12345'

DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123"
}

# --- Главная страница (Личный кабинет с балансом) ---
@app.route("/")
def home():
    if 'email' not in session:
        return redirect(url_for('login_page'))

    # Получаем свежие данные (имя и баланс) из БД
    cnx = None
    cur = None
    balance = 0.0
    username = session.get('username', 'Пользователь')

    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cur = cnx.cursor(dictionary=True)
        # Получаем данные пользователя по email из сессии
        cur.execute("SELECT username, balance FROM `users` WHERE `email` = %s", (session['email'],))
        user = cur.fetchone()

        if user:
            username = user['username']
            # Если поле balance есть — берем его, если NULL — ставим 0.00
            balance = user.get('balance', 0.00) or 0.00
        else:
            session.clear()
            return redirect(url_for('login_page'))

    except mysql.connector.Error:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    return render_template('dashboard.html', username=username, balance=balance)

# --- Страницы интерфейса ---
@app.route("/login")
def login_page():
    if 'email' in session:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route("/register")
def register_page():
    if 'email' in session:
        return redirect(url_for('home'))
    return render_template('registration.html')

# --- API: Регистрация ---
@app.route('/user_register', methods=['POST'])
def user_register():
    req = request.get_json()
    if not req or 'name' not in req or 'email' not in req or 'password' not in req:
        return jsonify({"error": "Заполните все поля"}), 400

    name = req['name']
    login = req['email']
    password = req['password']

    password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()

    cnx = None
    cur = None
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cur = cnx.cursor()
        
        query = 'INSERT INTO `users`(`username`, `email`, `password_hash`, `balance`) VALUES (%s, %s, %s, 0.00)'
        cur.execute(query, (name, login, password_hash))
        cnx.commit()

        # Автоматический логин после регистрации
        session['username'] = name
        session['email'] = login

        return jsonify({"success": True, "redirect_url": "/"}), 201

    except mysql.connector.Error:
        return jsonify({"error": "Ошибка БД (возможно email уже занят)"}), 500
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

# --- API: Вход ---
@app.route('/user_login', methods=['POST'])
def user_login():
    req = request.get_json()
    if not req or 'email' not in req or 'password' not in req:
        return jsonify({"error": "Заполните все поля"}), 400

    email = req['email']
    password = req['password']

    cnx = None
    cur = None
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cur = cnx.cursor(dictionary=True, buffered=True)

        query = "SELECT * FROM `users` WHERE `email` = %s"
        cur.execute(query, (email,))

        if cur.rowcount == 0:
            return jsonify({"error": "Неверный email или пароль"}), 401

        user = cur.fetchone()
        stored_hash = user['password_hash']
        current_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()

        if current_hash == stored_hash:
            session['username'] = user['username']
            session['email'] = user['email']
            return jsonify({"success": True, "redirect_url": "/"})
        else:
            return jsonify({"error": "Неверный email или пароль"}), 401

    except mysql.connector.Error:
        return jsonify({"error": "Ошибка БД"}), 500
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

# --- Выход ---
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)