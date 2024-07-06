import psycopg2
import psycopg2.extras
import json

DB_HOST = "database"
DB_PORT = "5432"
DB_NAME = "vacancies"
DB_USER = "postgres"
DB_PASSWORD = "postgres"

# Подключение к базе данных
def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Создание таблицы
def create_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vacancies (
            id SERIAL PRIMARY KEY,
            name TEXT,
            area TEXT,
            salary JSONB,
            experience TEXT,
            employment TEXT,
            schedule TEXT,
            professional_roles TEXT[],
            snippet TEXT,
            employer TEXT,
            url TEXT
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

# Вставка вакансий
def insert_vacancies(vacancies):
    conn = get_connection()
    cur = conn.cursor()
    psycopg2.extras.execute_values(cur, '''
        INSERT INTO vacancies (name, area, salary, experience, employment, schedule, professional_roles, snippet, employer, url) VALUES %s
    ''', [(v['name'], v['area'], json.dumps(v['salary']), v['experience'], v['employment'], v['schedule'], v['professional_roles'], v['snippet'], v['employer'], v['url']) for v in vacancies])
    conn.commit()
    cur.close()
    conn.close()

# Функция для вытаскивания вакансий
def fetch_all_vacancies():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT name, area, salary, experience, employment, schedule, professional_roles, snippet, employer, url FROM vacancies')
    vacancies = cur.fetchall()
    cur.close()
    conn.close()
    return vacancies

# Очистка таблицы
def clear_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('TRUNCATE TABLE vacancies')
    conn.commit()
    cur.close()
    conn.close()
