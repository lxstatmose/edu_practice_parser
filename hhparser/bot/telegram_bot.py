import os
import logging
import csv
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler
from hh_parser import fetch_vacancies
from database import create_table, insert_vacancies, fetch_all_vacancies, clear_table

# Загрузка перменных окружения из .env файла
load_dotenv()

# Логи
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Форматирование зарплаты в читаемый вид
def format_salary(salary):
    if salary is None:
        return "Не указана"
    elif isinstance(salary, dict):
        if salary['from'] and salary['to']:
            return f"{salary['from']} - {salary['to']} {salary['currency']}"
        elif salary['from']:
            return f"от {salary['from']} {salary['currency']}"
        elif salary['to']:
            return f"до {salary['to']} {salary['currency']}"
    return "Не указана"

# Состояния
SEARCH, REGION, COUNT, FILTERS, SALARY, EXPERIENCE, EMPLOYMENT, SCHEDULE = range(8)

# Команда старт
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [['/start', '/search', '/save', '/export', '/clear']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text(
        'Привет! Этот бот умеет парсить вакансии с hh.ru.\nВыберите команду:',
        reply_markup=reply_markup
    )

# Команда поиска
async def search_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Введите название вакансии, которую вы хотите найти:')
    return SEARCH

# Запрос региона
async def search_vacancy(update: Update, context: CallbackContext) -> int:
    context.user_data['vacancy'] = update.message.text
    await update.message.reply_text('Введите регион для поиска вакансий:')
    return REGION

# Запрос количества вакансий
async def search_region(update: Update, context: CallbackContext) -> int:
    context.user_data['region'] = update.message.text
    await update.message.reply_text('Введите количество вакансий, которое вы хотите получить (от 1 до 50):')
    return COUNT

# Защита от дурака)
async def search_count(update: Update, context: CallbackContext) -> int:
    try:
        count = int(update.message.text)
        if count <= 0:
            await update.message.reply_text('Пожалуйста, введите положительное числовое значение.')
            return COUNT
    except ValueError:
        await update.message.reply_text('Пожалуйста, введите числовое значение.')
        return COUNT

    context.user_data['count'] = count
    return await filter_menu(update, context)

# Показ меню с фильтрами
async def filter_menu(update: Update, context: CallbackContext) -> int:
    keyboard = [
        [InlineKeyboardButton("Зарплата", callback_data='salary')],
        [InlineKeyboardButton("Опыт работы", callback_data='experience')],
        [InlineKeyboardButton("Тип занятости", callback_data='employment')],
        [InlineKeyboardButton("График работы", callback_data='schedule')],
        [InlineKeyboardButton("Начать поиск", callback_data='start_search')],
        [InlineKeyboardButton("Сбросить фильтры", callback_data='reset_filters')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text('Выберите фильтр:', reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text('Выберите фильтр:', reply_markup=reply_markup)
    return FILTERS

# Обработчик фильтров
async def filter_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'salary':
        await query.edit_message_text('Введите диапазон зарплаты в формате "от-до":')
        return SALARY
    elif query.data == 'experience':
        keyboard = [
            [InlineKeyboardButton("Не имеет значения", callback_data='no_matter')],
            [InlineKeyboardButton("Без опыта", callback_data='no_experience')],
            [InlineKeyboardButton("От 1 года до 3 лет", callback_data='1-3')],
            [InlineKeyboardButton("От 3 до 6 лет", callback_data='3-6')],
            [InlineKeyboardButton("Более 6 лет", callback_data='6+')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите опыт работы:', reply_markup=reply_markup)
        return EXPERIENCE
    elif query.data == 'employment':
        keyboard = [
            [InlineKeyboardButton("Полная занятость", callback_data='full')],
            [InlineKeyboardButton("Частичная занятость", callback_data='part')],
            [InlineKeyboardButton("Стажировка", callback_data='internship')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите тип занятости:', reply_markup=reply_markup)
        return EMPLOYMENT
    elif query.data == 'schedule':
        keyboard = [
            [InlineKeyboardButton("Полный день", callback_data='full_day')],
            [InlineKeyboardButton("Сменный график", callback_data='shift')],
            [InlineKeyboardButton("Гибкий график", callback_data='flexible')],
            [InlineKeyboardButton("Удаленная работа", callback_data='remote')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите график работы:', reply_markup=reply_markup)
        return SCHEDULE
    elif query.data == 'reset_filters':
        context.user_data.pop('salary', None)
        context.user_data.pop('experience', None)
        context.user_data.pop('employment', None)
        context.user_data.pop('schedule', None)
        await query.edit_message_text('Фильтры сброшены.')
        return await filter_menu(update, context)
    elif query.data == 'start_search':
        return await perform_search(update, context)

# Защита от дурака для
async def salary_input(update: Update, context: CallbackContext) -> int:
    salary_range = update.message.text.split('-')
    if len(salary_range) != 2:
        await update.message.reply_text('Пожалуйста, введите диапазон зарплаты в правильном формате "от-до".')
        return SALARY

    try:
        salary_from = int(salary_range[0])
        salary_to = int(salary_range[1])
    except ValueError:
        await update.message.reply_text('Пожалуйста, введите числовые значения.')
        return SALARY

    context.user_data['salary'] = (salary_from, salary_to)
    return await filter_menu(update, context)

# Выбор опыта работы
async def experience_input(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    experience_map = {
        'no_matter': 'Не имеет значения',
        'no_experience': 'Без опыта',
        '1-3': 'От 1 года до 3 лет',
        '3-6': 'От 3 до 6 лет',
        '6+': 'Более 6 лет',
    }
    context.user_data['experience'] = experience_map.get(query.data, 'Не имеет значения')
    return await filter_menu(update, context)

# Выбор занятости
async def employment_input(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    employment_map = {
        'full': 'Полная занятость',
        'part': 'Частичная занятость',
        'internship': 'Стажировка',
    }
    context.user_data['employment'] = employment_map.get(query.data, 'Полная занятость')
    return await filter_menu(update, context)

# Выбор графика
async def schedule_input(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    schedule_map = {
        'full_day': 'Полный день',
        'shift': 'Сменный график',
        'flexible': 'Гибкий график',
        'remote': 'Удаленная работа',
    }
    context.user_data['schedule'] = schedule_map.get(query.data, 'Полный день')
    return await filter_menu(update, context)

# Функция для управления поиском
async def perform_search(update: Update, context: CallbackContext) -> int:
    vacancy = context.user_data.get('vacancy')
    region = context.user_data.get('region')
    count = context.user_data.get('count')
    salary = context.user_data.get('salary')
    experience = context.user_data.get('experience')
    employment = context.user_data.get('employment')
    schedule = context.user_data.get('schedule')

    vacancies = fetch_vacancies(vacancy, region, count, salary, experience, employment, schedule)
    context.user_data['vacancies'] = vacancies

    if vacancies:
        for v in vacancies:
            formatted_salary = format_salary(v['salary'])
            message = (
                f"Название: {v['name']}\n"
                f"Регион: {v['area']}\n"
                f"Зарплата: {formatted_salary}\n"
                f"Опыт: {v['experience']}\n"
                f"Тип занятости: {v['employment']}\n"
                f"График работы: {v['schedule']}\n"
                f"Роли: {', '.join(v['professional_roles'])}\n"
                f"Описание: {v['snippet']}\n"
                f"Компания: {v['employer']}\n"
                f"Ссылка: {v['url']}\n"
                "------------------------------"
            )
            if update.callback_query:
                await update.callback_query.message.reply_text(message.strip())
            else:
                await update.message.reply_text(message.strip())
    else:
        if update.callback_query:
            await update.callback_query.message.reply_text('Вакансии не найдены.')
        else:
            await update.message.reply_text('Вакансии не найдены.')

    return ConversationHandler.END

# Команда сохранения
async def save(update: Update, context: CallbackContext) -> None:
    create_table()
    vacancies = context.user_data.get('vacancies', [])
    if vacancies:
        insert_vacancies(vacancies)
        await update.message.reply_text('Вакансии сохранены в базе данных.')
        context.user_data.pop('vacancies', None)
        return ConversationHandler.END
    else:
        await update.message.reply_text('Нет вакансий для сохранения.')

# Команда экспорта
async def export_start(update: Update, context: CallbackContext) -> None:
    vacancies = fetch_all_vacancies()
    if not vacancies:
        if update.message:
            await update.message.reply_text('Нет данных для экспорта.')
        else:
            await update.callback_query.message.reply_text('Нет данных для экспорта.')
        return

    keyboard = [
        [InlineKeyboardButton("Экспорт в CSV", callback_data='export_csv')],
        [InlineKeyboardButton("Экспорт в чат", callback_data='export_chat')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text('Выберите вариант экспорта:', reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text('Выберите вариант экспорта:', reply_markup=reply_markup)

# Обработчик для команды экспорта
async def export_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'export_csv':
        await export_to_csv(update, context)
    elif query.data == 'export_chat':
        await export_to_chat(update, context)

# Функция для экспорта в CSV
async def export_to_csv(update: Update, context: CallbackContext):
    vacancies = fetch_all_vacancies()
    if not vacancies:
        await update.callback_query.answer('Нет данных для экспорта.', show_alert=True)
        return

    file_path = '/tmp/vacancies.csv'
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Название', 'Регион', 'Зарплата', 'Опыт', 'Тип занятости', 'График работы', 'Роли', 'Описание', 'Компания', 'Ссылка'])

        for v in vacancies:
            name, area, salary, experience, employment, schedule, roles, snippet, employer, url = v
            formatted_salary = format_salary(salary)
            writer.writerow([name, area, formatted_salary, experience, employment, schedule, ', '.join(roles), snippet, employer, url])

    with open(file_path, 'rb') as file:
        await update.callback_query.message.reply_document(file)

    os.remove(file_path)

# Функция для экспорта в чат
async def export_to_chat(update: Update, context: CallbackContext):
    vacancies = fetch_all_vacancies()
    if not vacancies:
        await update.callback_query.answer('Нет данных для экспорта.', show_alert=True)
        return

    for v in vacancies:
        name, area, salary, experience, employment, schedule, roles, snippet, employer, url = v
        formatted_salary = format_salary(salary)
        message = (
            f"Название: {name}\n"
            f"Регион: {area}\n"
            f"Зарплата: {formatted_salary}\n"
            f"Опыт: {experience}\n"
            f"Тип занятости: {employment}\n"
            f"График работы: {schedule}\n"
            f"Роли: {', '.join(roles)}\n"
            f"Описание: {snippet}\n"
            f"Компания: {employer}\n"
            f"Ссылка: {url}\n"
            "------------------------------"
        )
        await update.callback_query.message.reply_text(message.strip())

# Команда очистки
async def clear(update: Update, context: CallbackContext) -> None:
    clear_table()
    await update.message.reply_text('Все сохраненные вакансии были удалены.')

def main() -> None:
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search_start)],
        states={
            SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_vacancy)],
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_region)],
            COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_count)],
            FILTERS: [CallbackQueryHandler(filter_handler)],
            SALARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, salary_input)],
            EXPERIENCE: [CallbackQueryHandler(experience_input)],
            EMPLOYMENT: [CallbackQueryHandler(employment_input)],
            SCHEDULE: [CallbackQueryHandler(schedule_input)],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('save', save))
    application.add_handler(CommandHandler('export', export_start))
    application.add_handler(CommandHandler('clear', clear))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(export_handler, pattern='^export_(csv|chat)$'))
    application.run_polling()

if __name__ == '__main__':
    main()

