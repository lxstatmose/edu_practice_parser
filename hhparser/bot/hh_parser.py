import requests

# Функция для парсинга вакансий
def fetch_vacancies(vacancy_name, region, count=10, salary=None, experience=None, employment=None, schedule=None):
    url = "https://api.hh.ru/vacancies"
    vacancies = []
    page = 0
    per_page = 50  # Максимальное количество вакансий за один запрос

    # Преобразование параметров фильтра
    experience_map = {
        'Не имеет значения': None,
        'Без опыта': 'noExperience',
        'От 1 года до 3 лет': 'between1And3',
        'От 3 до 6 лет': 'between3And6',
        'Более 6 лет': 'moreThan6',
    }
    employment_map = {
        'Полная занятость': 'full',
        'Частичная занятость': 'part',
        'Стажировка': 'probation',
    }
    schedule_map = {
        'Полный день': 'fullDay',
        'Сменный график': 'shift',
        'Гибкий график': 'flexible',
        'Удаленная работа': 'remote',
    }

    while len(vacancies) < count:
        params = {
            'text': vacancy_name,
            'area': region,
            'per_page': per_page,
            'page': page
        }
        if salary:
            params['salary_from'], params['salary_to'] = salary
        if experience:
            params['experience'] = experience_map.get(experience)
        if employment:
            params['employment'] = employment_map.get(employment)
        if schedule:
            params['schedule'] = schedule_map.get(schedule)

        response = requests.get(url, params=params)
        if response.status_code != 200:
            break
        data = response.json()
        if not data['items']:
            break
        for item in data['items']:
            if vacancy_name.lower() in item['name'].lower():
                vacancy = {
                    'name': item['name'],
                    'area': item['area']['name'],
                    'salary': item.get('salary'),
                    'experience': item['experience']['name'],
                    'employment': item['employment']['name'],
                    'schedule': item['schedule']['name'] if 'schedule' in item else '',
                    'professional_roles': [role['name'] for role in item['professional_roles']],
                    'snippet': item['snippet']['responsibility'] if item['snippet'] else '',
                    'url': item['alternate_url'],
                    'employer': item['employer']['name'] if 'employer' in item else 'Не указано'
                }
                vacancies.append(vacancy)
                if len(vacancies) >= count:
                    break
        page += 1

    return vacancies[:count]
