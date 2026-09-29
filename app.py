import hashlib
import logging
import os
import re
import secrets
from contextlib import closing

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from mysql.connector import Error as MySQLError
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Секретный ключ сессий — из окружения; если не задан, генерируем случайный
# (тогда сессии сбрасываются при перезапуске сервера).
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    app.secret_key = os.urandom(32)
    logger.warning("SECRET_KEY не задан: используется случайный ключ, задай его в .env")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", ""),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "database": os.environ.get("DB_NAME", ""),
    "user": os.environ.get("DB_USER", ""),
    "password": os.environ.get("DB_PASSWORD", ""),
    "connection_timeout": 5,
}
DB_MISSING = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.environ.get(k)]
if DB_MISSING:
    logger.warning("Не заданы переменные окружения: %s", ", ".join(DB_MISSING))

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 6

# Каталог нейросетей, которые продаём
PRODUCTS = [
    {
        "slug": "text",
        "name": "NeuroText",
        "icon": "✍️",
        "desc": "Генерация и обработка текста: чаты, статьи, суммаризация, перевод.",
        "price": 990,
    },
    {
        "slug": "vision",
        "name": "NeuroVision",
        "icon": "🎨",
        "desc": "Генерация изображений по описанию и редактирование картинок.",
        "price": 1490,
    },
    {
        "slug": "voice",
        "name": "NeuroVoice",
        "icon": "🎙️",
        "desc": "Синтез речи и распознавание аудио для голосовых приложений.",
        "price": 790,
    },
    {
        "slug": "embed",
        "name": "NeuroEmbed",
        "icon": "🔎",
        "desc": "Эмбеддинги для семантического поиска и рекомендаций.",
        "price": 490,
    },
]
PRODUCT_MAP = {p["slug"]: p for p in PRODUCTS}


def db_configured() -> bool:
    return not DB_MISSING


def init_db() -> None:
    """Создаёт таблицу API-ключей, если её ещё нет."""
    if not db_configured():
        return
    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor()) as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS `api_keys` (
                        `id` INT AUTO_INCREMENT PRIMARY KEY,
                        `user_id` INT NOT NULL,
                        `product` VARCHAR(50) NOT NULL,
                        `api_key` VARCHAR(80) NOT NULL UNIQUE,
                        `active` TINYINT(1) NOT NULL DEFAULT 1,
                        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX `idx_user` (`user_id`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cnx.commit()
    except MySQLError:
        logger.warning("Не удалось подключиться к БД при старте (таблица api_keys не проверена)")


def fmt_money(value) -> str:
    return f"{float(value or 0):.2f}"


def find_user_by_email(email: str):
    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute(
                "SELECT `id`, `username`, `email`, `password_hash`, `balance` FROM `users` WHERE `email` = %s",
                (email,),
            )
            return cur.fetchone()


def find_user_by_id(user_id: int):
    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute(
                "SELECT `id`, `username`, `email`, `balance` FROM `users` WHERE `id` = %s",
                (user_id,),
            )
            return cur.fetchone()


def get_user_keys(user_id: int):
    with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
        with closing(cnx.cursor(dictionary=True)) as cur:
            cur.execute(
                "SELECT `id`, `product`, `api_key`, `active`, `created_at` FROM `api_keys` "
                "WHERE `user_id` = %s ORDER BY `created_at` DESC, `id` DESC",
                (user_id,),
            )
            keys = cur.fetchall()
    for k in keys:
        created = k.get("created_at")
        if hasattr(created, "strftime"):
            k["created"] = created.strftime("%d.%m.%Y")
        else:
            # Некоторые драйверы (SQLite в демо) возвращают строку "ГГГГ-ММ-ДД ..."
            s = str(created or "")[:10]
            parts = s.split("-")
            k["created"] = ".".join(reversed(parts)) if len(parts) == 3 else s
        k["product_name"] = PRODUCT_MAP.get(k["product"], {}).get("name", k["product"])
        k["product_icon"] = PRODUCT_MAP.get(k["product"], {}).get("icon", "🧩")
    return keys


def current_user():
    """Пользователь из сессии с проверкой в БД. None — если не залогинен."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        user = find_user_by_id(user_id)
    except MySQLError:
        logger.exception("Ошибка БД при загрузке пользователя")
        return None
    if not user:
        session.clear()
    return user


def verify_password(stored_hash: str, password: str) -> bool:
    """Проверяет пароль. Старые хэши SHA-256 (64 hex-символа) тоже принимаются."""
    if not stored_hash:
        return False
    is_legacy_sha256 = len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash)
    if is_legacy_sha256:
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash
    try:
        return check_password_hash(stored_hash, password)
    except ValueError:
        return False


def migrate_legacy_hash(user_id: int, password: str) -> None:
    """Пересохраняет пароль современным хэшем после успешного входа со старым SHA-256."""
    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor()) as cur:
                cur.execute(
                    "UPDATE `users` SET `password_hash` = %s WHERE `id` = %s",
                    (generate_password_hash(password), user_id),
                )
                cnx.commit()
    except MySQLError:
        logger.exception("Не удалось обновить хэш пароля пользователя #%s", user_id)


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
    try:
        user = find_user_by_id(session["user_id"])
        if not user:
            session.clear()
            return redirect(url_for("login_page"))
        keys = get_user_keys(user["id"])
    except MySQLError:
        logger.exception("Ошибка БД при загрузке кабинета")
        return "Ошибка подключения к базе данных. Попробуйте позже.", 503
    return render_template(
        "dashboard.html",
        username=user["username"],
        balance=fmt_money(user["balance"]),
        keys=keys,
        products=PRODUCTS,
    )


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/register")
def register_page():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("registration.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ============ API: аутентификация ============

@app.route("/api/register", methods=["POST"])
@app.route("/user_register", methods=["POST"])  # совместимость со старой версией сайта
def user_register():
    req = request.get_json(silent=True) or {}

    name = str(req.get("name", "")).strip()
    email = str(req.get("email", "")).strip().lower()
    password = str(req.get("password", ""))

    if not name or not email or not password:
        return jsonify({"error": "Заполните все поля"}), 400
    if len(name) > 50:
        return jsonify({"error": "Имя слишком длинное"}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Некорректный email"}), 400
    if len(password) < MIN_PASSWORD_LEN:
        return jsonify({"error": f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов"}), 400

    if not db_configured():
        return jsonify({"error": "Сервер не настроен: нет конфигурации БД"}), 500

    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor()) as cur:
                cur.execute(
                    "INSERT INTO `users`(`username`, `email`, `password_hash`, `balance`) VALUES (%s, %s, %s, 0.00)",
                    (name, email, generate_password_hash(password)),
                )
                cnx.commit()
                user_id = cur.lastrowid
    except mysql.connector.IntegrityError:
        return jsonify({"error": "Такой email уже зарегистрирован"}), 409
    except MySQLError:
        logger.exception("Ошибка БД при регистрации")
        return jsonify({"error": "Ошибка базы данных, попробуйте позже"}), 500

    session["user_id"] = user_id
    session["username"] = name
    return jsonify({"success": True, "redirect_url": "/dashboard"}), 201


@app.route("/api/login", methods=["POST"])
@app.route("/user_login", methods=["POST"])  # совместимость со старой версией сайта
def user_login():
    req = request.get_json(silent=True) or {}

    email = str(req.get("email", "")).strip().lower()
    password = str(req.get("password", ""))

    if not email or not password:
        return jsonify({"error": "Заполните все поля"}), 400

    if not db_configured():
        return jsonify({"error": "Сервер не настроен: нет конфигурации БД"}), 500

    try:
        user = find_user_by_email(email)
    except MySQLError:
        logger.exception("Ошибка БД при входе")
        return jsonify({"error": "Ошибка базы данных, попробуйте позже"}), 500

    if not user or not verify_password(user["password_hash"], password):
        return jsonify({"error": "Неверный email или пароль"}), 401

    # Старый хэш SHA-256 → прозрачно обновляем на современный
    stored = user["password_hash"] or ""
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored):
        migrate_legacy_hash(user["id"], password)

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"success": True, "redirect_url": "/dashboard"})


# ============ API: баланс и ключи ============

@app.route("/api/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"error": "Требуется вход"}), 401
    try:
        keys = get_user_keys(user["id"])
    except MySQLError:
        return jsonify({"error": "Ошибка базы данных"}), 500
    return jsonify({
        "username": user["username"],
        "balance": fmt_money(user["balance"]),
        "keys": [
            {
                "id": k["id"],
                "product": k["product"],
                "product_name": k["product_name"],
                "product_icon": k["product_icon"],
                "api_key": k["api_key"],
                "active": bool(k["active"]),
                "created": k["created"],
            }
            for k in keys
        ],
    })


@app.route("/api/topup", methods=["POST"])
def topup():
    """Демо-пополнение баланса (без реальной оплаты)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Требуется вход"}), 401

    req = request.get_json(silent=True) or {}
    try:
        amount = int(req.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    if amount < 10 or amount > 50000:
        return jsonify({"error": "Сумма должна быть от 10 до 50 000 ₽"}), 400

    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor(dictionary=True)) as cur:
                cur.execute("UPDATE `users` SET `balance` = `balance` + %s WHERE `id` = %s", (amount, user["id"]))
                cnx.commit()
                cur.execute("SELECT `balance` FROM `users` WHERE `id` = %s", (user["id"],))
                balance = cur.fetchone()["balance"]
    except MySQLError:
        logger.exception("Ошибка БД при пополнении")
        return jsonify({"error": "Ошибка базы данных, попробуйте позже"}), 500

    return jsonify({"success": True, "balance": fmt_money(balance)})


@app.route("/api/purchase", methods=["POST"])
def purchase():
    """Покупка доступа к нейросети: списание с баланса и выдача API-ключа."""
    user = current_user()
    if not user:
        return jsonify({"error": "Требуется вход"}), 401

    req = request.get_json(silent=True) or {}
    product = PRODUCT_MAP.get(str(req.get("product", "")))
    if not product:
        return jsonify({"error": "Неизвестный продукт"}), 400

    api_key = "nk_" + secrets.token_urlsafe(24)
    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor(dictionary=True)) as cur:
                # Атомарно списываем, только если хватает средств
                cur.execute(
                    "UPDATE `users` SET `balance` = `balance` - %s WHERE `id` = %s AND `balance` >= %s",
                    (product["price"], user["id"], product["price"]),
                )
                if cur.rowcount == 0:
                    cnx.rollback()
                    return jsonify({"error": f"Не хватает средств. Нужно {product['price']} ₽ — пополни баланс"}), 402
                cur.execute(
                    "INSERT INTO `api_keys`(`user_id`, `product`, `api_key`) VALUES (%s, %s, %s)",
                    (user["id"], product["slug"], api_key),
                )
                cnx.commit()
                cur.execute("SELECT `balance` FROM `users` WHERE `id` = %s", (user["id"],))
                balance = cur.fetchone()["balance"]
    except MySQLError:
        logger.exception("Ошибка БД при покупке")
        return jsonify({"error": "Ошибка базы данных, попробуйте позже"}), 500

    return jsonify({
        "success": True,
        "api_key": api_key,
        "product_name": product["name"],
        "balance": fmt_money(balance),
    })


@app.route("/api/revoke_key", methods=["POST"])
def revoke_key():
    user = current_user()
    if not user:
        return jsonify({"error": "Требуется вход"}), 401

    req = request.get_json(silent=True) or {}
    try:
        key_id = int(req.get("key_id", 0))
    except (TypeError, ValueError):
        key_id = 0
    if not key_id:
        return jsonify({"error": "Не указан ключ"}), 400

    try:
        with closing(mysql.connector.connect(**DB_CONFIG)) as cnx:
            with closing(cnx.cursor()) as cur:
                cur.execute(
                    "UPDATE `api_keys` SET `active` = 0 WHERE `id` = %s AND `user_id` = %s",
                    (key_id, user["id"]),
                )
                cnx.commit()
                if cur.rowcount == 0:
                    return jsonify({"error": "Ключ не найден"}), 404
    except MySQLError:
        logger.exception("Ошибка БД при отзыве ключа")
        return jsonify({"error": "Ошибка базы данных, попробуйте позже"}), 500

    return jsonify({"success": True})


def run():
    init_db()
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )


if __name__ == "__main__":
    run()
