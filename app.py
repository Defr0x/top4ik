import hashlib
import logging
import os
import re
import secrets
from contextlib import closing

import pymysql
pymysql.install_as_MySQLdb()
import mysql.connector
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from mysql.connector import Error as MySQLError
from werkzeug.security import check_password_hash, generate_password_hash

# --- Подключение нейросети ---
try:
    from llama_cpp import Llama
    llm = Llama.from_pretrained(
        repo_id="bartowski/Qwen2.5-0.5B-Instruct-GGUF",
        filename="Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
        n_ctx=2048,
        verbose=False
    )
    print("Модель успешно загружена.")
except Exception as e:
    llm = None
    print(f"Модель не загружена: {e}")

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "1581"

# --- Конфигурация БД ---
DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123",
    "connection_timeout": 5,
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 6

# Каталог нейросетей
PRODUCTS = [
    {"slug": "text", "name": "NeuroText", "icon": "✍️", "desc": "Генерация и обработка текста.", "price": 990},
    {"slug": "vision", "name": "NeuroVision", "icon": "🎨", "desc": "Генерация изображений.", "price": 1490},
    {"slug": "voice", "name": "NeuroVoice", "icon": "🎙️", "desc": "Синтез речи.", "price": 790},
]
PRODUCT_MAP = {p["slug"]: p for p in PRODUCTS}

def fmt_money(value) -> str:
    return f"{float(value or 0):.2f}"

def find_user_by_email(email: str):
    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute("SELECT `id`, `username`, `email`, `password_hash`, `balance` FROM `users` WHERE `email` = %s", (email,))
            return cur.fetchone()

def find_user_by_id(user_id: int):
    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute("SELECT `id`, `username`, `email`, `balance` FROM `users` WHERE `id` = %s", (user_id,))
            return cur.fetchone()

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        user = find_user_by_id(user_id)
    except MySQLError:
        return None
    if not user:
        session.clear()
    return user

def verify_password(stored_hash: str, password: str) -> bool:
    if not stored_hash:
        return False
    is_legacy_sha256 = len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash)
    if is_legacy_sha256:
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash
    try:
        return check_password_hash(stored_hash, password)
    except ValueError:
        return False

@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

# ============ Страницы ============

@app.route("/")
def landing():
    return render_template("landing.html", products=PRODUCTS, logged_in=bool(session.get("user_id")))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    user = find_user_by_id(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("login_page"))
    
    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute("SELECT * FROM `transactions` WHERE `user_id` = %s ORDER BY `created_at` DESC LIMIT 10", (user["id"],))
            transactions = cur.fetchall()

    return render_template(
        "dashboard.html",
        username=user["username"],
        balance=fmt_money(user["balance"]),
        products=PRODUCTS,
        transactions=transactions
    )

@app.route("/chat")
def chat_page():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("chat.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("registration.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

# ============ API ============

@app.route("/api/register", methods=["POST"])
def user_register():
    req = request.get_json(silent=True) or {}
    name = str(req.get("name", "")).strip()
    email = str(req.get("email", "")).strip().lower()
    password = str(req.get("password", ""))

    if not name or not email or not password:
        return jsonify({"error": "Заполните все поля"}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Некорректный email"}), 400

    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor()) as cur:
                cur.execute("INSERT INTO `users`(`username`, `email`, `password_hash`, `balance`) VALUES (%s, %s, %s, 0.00)",
                    (name, email, generate_password_hash(password)))
                cnx.commit()
                user_id = cur.lastrowid
    except mysql.connector.IntegrityError:
        return jsonify({"error": "Email уже занят"}), 409
    except MySQLError as e:
        return jsonify({"error": str(e)}), 500

    session["user_id"] = user_id
    session["username"] = name
    return jsonify({"success": True, "redirect_url": "/dashboard"}), 201

@app.route("/api/login", methods=["POST"])
def user_login():
    req = request.get_json(silent=True) or {}
    email = str(req.get("email", "")).strip().lower()
    password = str(req.get("password", ""))

    user = find_user_by_email(email)
    if not user or not verify_password(user["password_hash"], password):
        return jsonify({"error": "Неверный email или пароль"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"success": True, "redirect_url": "/dashboard"})

@app.route("/api/topup", methods=["POST"])
def topup():
    user = current_user()
    if not user:
        return jsonify({"error": "Требуется вход"}), 401

    req = request.get_json(silent=True) or {}
    amount = int(req.get("amount", 0))

    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute("UPDATE `users` SET `balance` = `balance` + %s WHERE `id` = %s", (amount, user["id"]))
            cur.execute("SELECT `balance` FROM `users` WHERE `id` = %s", (user["id"],))
            new_balance = cur.fetchone()["balance"]
            cur.execute("INSERT INTO `transactions`(`user_id`, `amount`, `type`, `description`, `balance_after`) VALUES (%s, %s, 'topup', 'Пополнение', %s)",
                (user["id"], amount, new_balance))
            cnx.commit()

    return jsonify({"success": True, "balance": fmt_money(new_balance)})

@app.route("/api/purchase", methods=["POST"])
def purchase():
    user = current_user()
    if not user:
        return jsonify({"error": "Требуется вход"}), 401

    req = request.get_json(silent=True) or {}
    product = PRODUCT_MAP.get(str(req.get("product", "")))
    if not product:
        return jsonify({"error": "Неизвестный продукт"}), 400

    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute(
                "UPDATE `users` SET `balance` = `balance` - %s WHERE `id` = %s AND `balance` >= %s",
                (product["price"], user["id"], product["price"]),
            )
            if cur.rowcount == 0:
                cnx.rollback()
                return jsonify({"error": f"Не хватает средств. Нужно {product['price']} ₽"}), 402
            
            cur.execute("SELECT `balance` FROM `users` WHERE `id` = %s", (user["id"],))
            new_balance = cur.fetchone()["balance"]
            
            cur.execute("INSERT INTO `transactions`(`user_id`, `amount`, `type`, `description`, `balance_after`) VALUES (%s, %s, 'purchase', %s, %s)",
                (user["id"], -product["price"], f"Покупка {product['name']}", new_balance))
            cnx.commit()

    return jsonify({"success": True, "balance": fmt_money(new_balance), "product_name": product["name"]})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "user_id" not in session:
        return jsonify({"error": "Не авторизован"}), 401
    
    if not llm:
        return jsonify({"reply": "Извини, нейросеть не загружена. Проверь логи."}), 500

    req = request.get_json()
    message = (req.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Пустое сообщение'}), 400

    prompt = f"<|im_start|>system\nТы полезный ассистент. Отвечай кратко и по-русски.<|im_end|>\n<|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n"
    output = llm(prompt, max_tokens=150, temperature=0.7, stop=["<|im_end|>"])
    reply = output['choices'][0]['text'].strip()
    return jsonify({'reply': reply})

def run():
    app.run(host="127.0.0.1", port=5002, debug=False)

if __name__ == "__main__":
    run()