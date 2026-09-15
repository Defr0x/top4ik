from flask import Flask, render_template, request, jsonify
import mysql.connector
import hashlib

app = Flask(__name__)  

DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123"
}

@app.route('/user_register', methods=['POST'])
def user_register():
    req = request.get_json()
    if not req or 'name' not in req or 'email' not in req or 'password' not in req:
        return jsonify({"error": "Missing data"}), 400

    name = req['name']
    login = req['email']
    password = req['password']

    password_bytes = password.encode('utf-8')
    sha256_hash_obj = hashlib.sha256(password_bytes)
    password_hash = sha256_hash_obj.hexdigest()

    cnx = None
    cur = None
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cur = cnx.cursor()
        
        query = 'INSERT INTO `users`(`username`, `email`, `password_hash`) VALUES (%s, %s, %s)'
        user_data = (name, login, password_hash)
        
        cur.execute(query, user_data)
        cnx.commit()

        return jsonify({"success": "User registered successfully"}), 201

    except mysql.connector.Error as err:
        return jsonify({"error": "Database error"}), 500
    finally:
        if cur:
            cur.close()
        if cnx and cnx.is_connected():
            cnx.close()

@app.route('/user_login', methods=['POST'])
def user_login():
    req = request.get_json()
    if not req or 'email' not in req or 'password' not in req:
        return jsonify({"error": "Missing data"}), 400

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
            return jsonify({"error": "Invalid email or password"}), 401

        user = cur.fetchone()
        stored_hash = user['password_hash']

        password_bytes = password.encode('utf-8')
        sha256_hash_obj = hashlib.sha256(password_bytes)
        current_hash = sha256_hash_obj.hexdigest()

        if current_hash == stored_hash:
            return jsonify({"success": f"Welcome, {user['username']}!"})
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    except mysql.connector.Error as err:
        return jsonify({"error": "Database error"}), 500
    finally:
        if cur:
            cur.close()
        if cnx and cnx.is_connected():
            cnx.close()

@app.route("/")
def registration():
    return render_template('registration.html')

@app.route("/login")
def login_page():
    return render_template('login.html')

if __name__ == '__main__':
    app.run(debug=True)