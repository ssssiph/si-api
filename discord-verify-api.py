import os
import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from dotenv import load_dotenv
from db.db import execute_query
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["https://siph-industry.com"]}})
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = "https://siph-industry.com/verify-options"

def get_verification_settings(guild_id):
    """Получает role_id и username_format из базы"""
    result = execute_query(
        "SELECT role_id, username_format FROM verification_settings WHERE guild_id = %s",
        (guild_id,),
        fetch_one=True
    )
    return result

def calculate_account_age(join_date):
    """Вычисляет возраст аккаунта в днях"""
    try:
        join_date = datetime.strptime(join_date, "%Y-%m-%d")
        today = datetime.now()
        age = (today - join_date).days
        return str(age)
    except:
        return "0"

def update_discord_profile(guild_id, discord_id, roblox_username, display_name, roblox_id, roblox_join_date):
    """Выдает роль и меняет никнейм в Discord"""
    settings = get_verification_settings(guild_id)
    if not settings:
        return False

    role_id, username_format = settings
    try:
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        discord_response = requests.get(f"{DISCORD_API_BASE}/users/{discord_id}", headers=headers)
        discord_name = discord_response.json().get("username", "Unknown") if discord_response.ok else "Unknown"

        new_nickname = username_format
        new_nickname = new_nickname.replace("{smart-name}", f"{display_name} (@{roblox_username})")
        new_nickname = new_nickname.replace("{display-name}", display_name)
        new_nickname = new_nickname.replace("{user-id}", str(roblox_id))
        new_nickname = new_nickname.replace("{account-age}", calculate_account_age(roblox_join_date))
        new_nickname = new_nickname.replace("{player-name}", roblox_username)

        headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
        role_url = f"{DISCORD_API_BASE}/guilds/{guild_id}/members/{discord_id}/roles/{role_id}"
        nickname_url = f"{DISCORD_API_BASE}/guilds/{guild_id}/members/{discord_id}"

        response = requests.put(role_url, headers=headers)
        if not response.ok:
            print(f"Ошибка при выдачи роли: {response.status_code} {response.text}")
            return False
        print(f"Роль выдана: {discord_id} на сервере {guild_id}")

        response = requests.patch(nickname_url, headers=headers, json={"nick": new_nickname[:32]})
        if not response.ok:
            print(f"Ошибка при смене ника: {response.status_code} {response.text}")
            return False
        print(f"Ник изменён: {new_nickname} для пользователя {discord_id}")

        return True
    except Exception as e:
        print(f"Ошибка обновления профиля: {e}")
        return False

@app.route("/proxy/roblox/user/<user_id>", methods=["GET"])
def proxy_roblox_user(user_id):
    """Прокси для Roblox API: получение профиля пользователя"""
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
        resp = make_response(jsonify(response.json()), response.status_code)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp
    except Exception as e:
        resp = make_response(jsonify({"error": str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

@app.route("/api/oauth/callback", methods=["POST"])
def oauth_callback():
    """Обработка OAuth callback"""
    data = request.json
    code = data.get("code")
    if not code:
        resp = make_response(jsonify({"success": False, "error": "Код не предоставлен"}), 400)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

    try:
        token_response = requests.post(
            f"{DISCORD_API_BASE}/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        token_data = token_response.json()
        if not token_response.ok:
            resp = make_response(jsonify({"success": False, "error": token_data.get("error_description", "Ошибка авторизации")}), 400)
            resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
            return resp

        access_token = token_data["access_token"]
        user_response = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_data = user_response.json()
        if not user_response.ok:
            resp = make_response(jsonify({"success": False, "error": "Ошибка получения данных пользователя"}), 500)
            resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
            return resp

        resp = make_response(jsonify({
            "success": True,
            "access_token": access_token,
            "user_id": user_data["id"]
        }), 200)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp
    except Exception as e:
        resp = make_response(jsonify({"success": False, "error": str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

@app.route("/api/verify/code", methods=["POST"])
def generate_verify_code():
    """Генерирует код верификации"""
    data = request.json
    discord_id = data.get("discord_id")
    guild_id = data.get("guild_id")
    if not discord_id or not guild_id:
        resp = make_response(jsonify({"success": False, "error": "Недостаточно данных"}), 400)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

    import uuid
    code = str(uuid.uuid4())[:8]
    try:
        execute_query(
            "INSERT INTO verification_codes (discord_id, guild_id, code, created_at) VALUES (%s, %s, %s, NOW())",
            (discord_id, guild_id, code)
        )
        resp = make_response(jsonify({"success": True, "code": code}), 200)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp
    except Exception as e:
        resp = make_response(jsonify({"success": False, "error": str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

@app.route("/api/verify/check", methods=["POST"])
def check_verify_code():
    """Проверяет код в профиле Roblox"""
    data = request.json
    discord_id = data.get("discord_id")
    guild_id = data.get("guild_id")
    roblox_id = data.get("roblox_id")
    roblox_name = data.get("roblox_name")

    if not all([discord_id, guild_id, roblox_id, roblox_name]):
        resp = make_response(jsonify({"success": False, "error": "Недостаточно данных"}), 400)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

    try:
        code_result = execute_query(
            "SELECT code FROM verification_codes WHERE discord_id = %s AND guild_id = %s AND created_at > NOW() - INTERVAL 1 HOUR",
            (discord_id, guild_id),
            fetch_one=True
        )
        if not code_result:
            resp = make_response(jsonify({"success": False, "error": "Код не найден или истёк"}), 400)
            resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
            return resp

        code = code_result[0]
        roblox_response = requests.get(f"https://users.roblox.com/v1/users/{roblox_id}")
        if not roblox_response.ok:
            resp = make_response(jsonify({"success": False, "error": "Ошибка проверки Roblox"}), 500)
            resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
            return resp

        roblox_data = roblox_response.json()
        if code in roblox_data.get("description", ""):
            execute_query("""
                INSERT INTO verifications (discord_id, roblox_id, roblox_name, display_name, roblox_age, roblox_join_date, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    roblox_id = VALUES(roblox_id),
                    roblox_name = VALUES(roblox_name),
                    display_name = VALUES(display_name),
                    roblox_age = VALUES(roblox_age),
                    roblox_join_date = VALUES(roblox_join_date),
                    status = VALUES(status)
            """, (discord_id, roblox_id, roblox_name, roblox_data.get("displayName", roblox_name), roblox_data.get("age", 0), roblox_data.get("created", ""), "verified"))

            if update_discord_profile(guild_id, discord_id, roblox_name, roblox_data.get("displayName", roblox_name), roblox_id, roblox_data.get("created", "")):
                execute_query("DELETE FROM verification_codes WHERE discord_id = %s AND guild_id = %s", (discord_id, guild_id))
                resp = make_response(jsonify({"success": True, "message": "Верификация успешна"}), 200)
                resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
                return resp
            else:
                resp = make_response(jsonify({"success": False, "error": "Ошибка обновления профиля Discord"}), 500)
                resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
                return resp
        else:
            resp = make_response(jsonify({"success": False, "error": "Код не найден в профиле Roblox"}), 400)
            resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
            return resp
    except Exception as e:
        resp = make_response(jsonify({"success": False, "error": str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = 'https://siph-industry.com'
        return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
