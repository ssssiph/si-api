import os
import mysql.connector
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Создание соединения с базой данных"""
    url = urlparse(os.getenv("DATABASE_URL"))
    return mysql.connector.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port or 3306
    )

def init_db():
    """Создание таблиц для верификации"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица верификации Roblox
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verifications (
            discord_id BIGINT PRIMARY KEY,
            roblox_id BIGINT UNIQUE NOT NULL,
            roblox_name VARCHAR(255) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            roblox_age INT NOT NULL,
            roblox_join_date DATE NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # Таблица настроек верификации
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_settings (
            guild_id BIGINT PRIMARY KEY,
            role_id BIGINT DEFAULT NULL,
            username_format VARCHAR(255) DEFAULT NULL
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()

def execute_query(query, params=(), fetch_one=False, fetch_all=False):
    """Универсальное выполнение SQL-запросов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = None
    if fetch_one:
        result = cursor.fetchone()
    elif fetch_all:
        result = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()
    return result

init_db()
