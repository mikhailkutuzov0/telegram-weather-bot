import math
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext

from settings import bot_config
from api_requests import request
from database import orm


bot = Bot(token=bot_config.TELEGRAM_API_TOKEN)
# Запись происходит в оперативную память. (Не для реальных проектов.)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class ChoiceCityWeather(StatesGroup):
    waiting_city = State()


class SetUserCity(StatesGroup):
    waiting_user_city = State()


@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    orm.add_user(message.from_user.id)
    markup = await main_menu()
    text = f'Привет {message.from_user.first_name}, я бот,'\
        ' который подскажет тебе погоду на сегодня! 🌍'
    await message.answer(text, reply_markup=markup)


@dp.message_handler(regexp='Погода в моём городе')
async def get_user_city_weather(message: types.Message):
    city = orm.get_user_city(message.from_user.id)
    markup = create_menu_keyboard()

    if not city:
        text = 'Пожалуйста установите город проживания'
        btn_set_city = types.KeyboardButton('Установить свой город')
        markup = types.reply_keyboard.ReplyKeyboardMarkup(
            row_width=2,
            resize_keyboard=True
            )
        markup.add(btn_set_city)
        await message.answer(text, reply_markup=markup)
        return

    weather_data = await create_weather_report(message.from_user.id, city)
    text = await generate_weather_text(city, weather_data)
    await message.answer(text, reply_markup=markup)


@dp.message_handler(regexp='Меню')
async def main_menu_handler(message: types.Message):
    markup = await main_menu()
    text = f'Привет {message.from_user.first_name}, я бот,'\
        ' который подскажет тебе погоду на сегодня! 🌍'
    await message.answer(text, reply_markup=markup)


@dp.message_handler(regexp='Погода в другом месте')
async def city_start(message: types.Message):
    markup = create_menu_keyboard()
    text = 'Введите название города'
    await message.answer(text, reply_markup=markup)
    await ChoiceCityWeather.waiting_city.set()


@dp.message_handler(state=ChoiceCityWeather.waiting_city)
async def city_chosen(message: types.Message, state: FSMContext):
    city = message.text.capitalize()

    await state.update_data(waiting_city=city)
    markup = await main_menu()

    weather_data = await create_weather_report(message.from_user.id, city)
    text = await generate_weather_text(city, weather_data)

    await message.answer(text, reply_markup=markup)
    await state.finish()


@dp.message_handler(regexp='Установить свой город')
async def set_user_city_start(message: types.Message):
    markup = await main_menu()
    text = 'В каком городе проживаете?'
    await message.answer(text, reply_markup=markup)
    await SetUserCity.waiting_user_city.set()


@dp.message_handler(state=SetUserCity.waiting_user_city)
async def user_city_chosen(message: types.Message, state: FSMContext):
    city = message.text.capitalize()

    await state.update_data(waiting_user_city=city)
    user_data = await state.get_data()

    orm.set_user_city(message.from_user.id, user_data.get('waiting_user_city'))
    markup = await main_menu()

    text = f'Запомнил, {user_data.get("waiting_user_city")} ваш город'
    await message.answer(text, reply_markup=markup)
    await state.finish()


@dp.message_handler(regexp='История')
async def get_reports(message: types.Message):
    reports = orm.get_reports(message.from_user.id)
    await send_reports_history(message, reports)


@dp.callback_query_handler(lambda call: 'users' not in call.data)
async def callback_query(call, state: FSMContext):
    query_type = call.data.split('_')[0]
    if query_type == 'delete' and call.data.split('_')[1] == 'report':
        report_id = int(call.data.split('_')[2])
        current_page = 1
        orm.delete_user_report(report_id)
        reports = orm.get_reports(call.from_user.id)
        total_pages = math.ceil(len(reports) / 4)
        inline_markup = types.InlineKeyboardMarkup()
        for report in reports[:current_page*4]:
            inline_markup.add(types.InlineKeyboardButton(
                text=generate_report_button_text,
                callback_data=f'report_{report.id}'
                ))
        current_page += 1
        inline_markup.row(
            types.InlineKeyboardButton(
                text=f'{current_page-1}/{total_pages}',
                callback_data='None'
                ),
            types.InlineKeyboardButton(
                text='Вперёд',
                callback_data=f'next_{current_page}'
                )
        )
        await call.message.edit_text(
            text='История запросов:', reply_markup=inline_markup
            )
        return
    async with state.proxy() as data:
        data['current_page'] = int(call.data.split('_')[1])
        await state.update_data(current_page=data['current_page'])
        if query_type == 'next':
            reports = orm.get_reports(call.from_user.id)
            total_pages = math.ceil(len(reports) / 4)
            inline_markup = types.InlineKeyboardMarkup()
            if data['current_page']*4 >= len(reports):
                for report in reports[
                    data['current_page']*4-4:len(reports) + 1
                     ]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=generate_report_button_text(),
                        callback_data=f'report_{report.id}'
                        ))
                data['current_page'] -= 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text='Назад',
                        callback_data=f'prev_{data["current_page"]}'
                        ),
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"]+1}/{total_pages}',
                        callback_data='None'
                        )
                )
                await call.message.edit_text(
                    text="История запросов:", reply_markup=inline_markup
                    )
                return
            for report in reports[
                data['current_page']*4-4:data['current_page']*4
                              ]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=generate_report_button_text(report),
                    callback_data=f'report_{report.id}'
                ))
            data['current_page'] += 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_{data["current_page"]-2}'
                    ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"]-1}/{total_pages}',
                    callback_data='None'
                    ),
                types.InlineKeyboardButton(
                    text='Вперёд', callback_data=f'next_{data["current_page"]}'
                    )
            )
            await call.message.edit_text(
                text="История запросов:",
                reply_markup=inline_markup
                )
        if query_type == 'prev':
            reports = orm.get_reports(call.from_user.id)
            total_pages = math.ceil(len(reports) / 4)
            inline_markup = types.InlineKeyboardMarkup()
            if data['current_page'] == 1:
                for report in reports[0:data['current_page']*4]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=generate_report_button_text(report),
                        callback_data=f'report_{report.id}'
                        ))
                data['current_page'] += 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"]-1}/{total_pages}',
                        callback_data='None'
                        ),
                    types.InlineKeyboardButton(
                        text='Вперёд',
                        callback_data=f'next_{data["current_page"]}'
                        )
                )
                await call.message.edit_text(
                    text="История запросов:", reply_markup=inline_markup
                    )
                return
            for report in reports[
                data['current_page']*4-4:data['current_page']*4
                 ]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=generate_report_button_text(report),
                    callback_data=f'report_{report.id}'
                    ))
            data['current_page'] -= 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_{data["current_page"]}'
                    ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"]+1}/{total_pages}',
                    callback_data='None'
                    ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_{data["current_page"]}'
                    ),
            )
            await call.message.edit_text(
                text="История запросов:", reply_markup=inline_markup
                )
        if query_type == 'report':
            reports = orm.get_reports(call.from_user.id)
            report_id = call.data.split('_')[1]
            inline_markup = types.InlineKeyboardMarkup()
            for report in reports:
                if report.id == int(report_id):
                    inline_markup.add(
                        types.InlineKeyboardButton(
                            text='Назад',
                            callback_data=f'reports_{data["current_page"]}'
                            ),
                        types.InlineKeyboardButton(
                            text='Удалить зарос',
                            callback_data=f'delete_report_{report_id}'
                            )
                    )
                    await call.message.edit_text(
                        text=f'Данные по запросу\n'
                        f'Город:{report.city}\n'
                        f'Температура: {report.temp} C\n'
                        f'Ощущается как: {report.feels_like} C\n'
                        f'Скорость ветра: {report.wind_speed} м/с\n'
                        f'Давление: {report.pressure_mm} мм',
                        reply_markup=inline_markup
                    )
                    break
        if query_type == 'reports':
            reports = orm.get_reports(call.from_user.id)
            total_pages = math.ceil(len(reports) / 4)
            inline_markup = types.InlineKeyboardMarkup()
            data['current_page'] = 1
            for report in reports[:data['current_page']*4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=generate_report_button_text(report),
                    callback_data=f'report_{report.id}'
                ))
            data['current_page'] += 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text=f'{data["current_page"]-1}/{total_pages}',
                    callback_data='None'
                    ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_{data["current_page"]}'
                    )
            )
            await call.message.edit_text(
                text='История запросов:',
                reply_markup=inline_markup
                )


@dp.message_handler(
    lambda message: message.from_user.id in bot_config.TELEGRAM_ADMIN_ID and
    message.text == 'Администратор'
)
async def admin_panel(message: types.Message):
    markup = types.reply_keyboard.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Список пользователей')
    markup.add(btn1)
    adm = 'Админ-панель'
    text = f'{adm}'
    await message.answer(text, reply_markup=markup)


@dp.message_handler(
        lambda message: message.from_user.id in bot_config.TELEGRAM_ADMIN_ID
        and message.text == 'Список пользователей'
)
async def get_all_users(message: types.Message):
    current_page = 1
    users = orm.get_all_users()
    total_pages = math.ceil(len(users) / 4)
    text = 'Все мои пользователи:'
    inline_markup = types.InlineKeyboardMarkup()
    for user in users[:current_page*4]:
        inline_markup.add(types.InlineKeyboardButton(
            text=format_user_text(user),
            callback_data=f'{"None"}'
        ))
    current_page += 1
    inline_markup.row(
        types.InlineKeyboardButton(
            text=f'{current_page-1}/{total_pages}',
            callback_data='None'
            ),
        types.InlineKeyboardButton(
            text='Вперёд',
            callback_data=f'next_users_{current_page}'
            )
    )
    await message.answer(text, reply_markup=inline_markup)


@dp.callback_query_handler(lambda call: 'users' in call.data)
async def callback_query1(call, state: FSMContext):
    query_type = call.data.split('_')[0]
    async with state.proxy() as data:
        data['current_page'] = int(call.data.split('_')[2])
        await state.update_data(current_page=data['current_page'])
        if query_type == 'next':
            users = orm.get_all_users()
            total_pages = math.ceil(len(users) / 4)
            inline_markup = types.InlineKeyboardMarkup()
            if data['current_page']*4 >= len(users):
                for user in users[data['current_page']*4-4:len(users) + 1]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=format_user_text(user),
                        callback_data=f'{"None"}'
                    ))
                data['current_page'] -= 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text='Назад',
                        callback_data=f'prev_users_{data["current_page"]}'
                        ),
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"]+1}/{total_pages}',
                        callback_data='None'
                        )
                )
                await call.message.edit_text(
                    text='Все мои пользователи:',
                    reply_markup=inline_markup
                    )
                return
            for user in users[data['current_page']*4-4:data['current_page']*4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=format_user_text(user),
                    allback_data=f'{"None"}'
                ))
            data['current_page'] += 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_users_{data["current_page"]-2}'
                    ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"]-1}/{total_pages}',
                    callback_data='None'
                    ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_users_{data["current_page"]}'
                    )
            )
            await call.message.edit_text(
                text='Все мои пользователи:', reply_markup=inline_markup
                )
        if query_type == 'prev':
            users = orm.get_all_users()
            total_pages = math.ceil(len(users) / 4)
            inline_markup = types.InlineKeyboardMarkup()
            if data['current_page'] == 1:
                for user in users[0:data['current_page']*4]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=format_user_text(user),
                        callback_data=f'{"None"}'
                        ))
                data['current_page'] += 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"]-1}/{total_pages}',
                        callback_data='None'
                        ),
                    types.InlineKeyboardButton(
                        text='Вперёд',
                        callback_data=f'next_users_{data["current_page"]}'
                        )
                )
                await call.message.edit_text(
                    text='Все мои пользователи:', reply_markup=inline_markup
                    )
                return
            for user in users[data['current_page']*4-4:data['current_page']*4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=format_user_text(user),
                    callback_data=f'{"None"}'
                    ))
            data['current_page'] -= 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_users_{data["current_page"]}'
                    ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"]+1}/{total_pages}',
                    callback_data='None'
                    ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_users_{data["current_page"]}'
                    ),
            )
            await call.message.edit_text(
                text='Все мои пользователи:', reply_markup=inline_markup
                )


async def main_menu():
    markup = types.reply_keyboard.ReplyKeyboardMarkup(row_width=1)
    button_1 = types.KeyboardButton('Погода в моём городе 🏙')
    button_2 = types.KeyboardButton('Погода в другом месте 🌉')
    button_3 = types.KeyboardButton('История 📜')
    button_4 = types.KeyboardButton('Установить свой город 🏠')
    markup.add(button_1, button_2, button_3, button_4)
    return markup


def create_menu_keyboard():
    markup = types.reply_keyboard.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Меню 📄')
    markup.add(btn1)
    return markup


async def create_weather_report(user_id: int, city: str):
    data = request.get_weather(city)
    orm.create_report(
        user_id, data["temp"],
        data["feels_like"],
        data["wind_speed"],
        data["pressure_mm"],
        city
        )
    return data


async def generate_weather_text(city: str, weather_data: dict) -> str:
    return f'''Погода в {city}
🔵Температура: {weather_data["temp"]} C
🔵Ощущается как: {weather_data["feels_like"]} C
🔵Скорость ветра: {weather_data["wind_speed"]}м/с
🔵Давление: {weather_data["pressure_mm"]}мм'''


async def send_reports_history(message, reports):
    current_page = 1
    total_pages = math.ceil(len(reports) / 4)
    text = 'История запросов 🧾:'
    inline_markup = await generate_reports_keyboard(
        reports,
        current_page,
        total_pages
        )
    await message.answer(text, reply_markup=inline_markup)


async def generate_reports_keyboard(reports, current_page, total_pages):
    inline_markup = types.InlineKeyboardMarkup()
    for report in reports[current_page*4-4:current_page*4]:
        inline_markup.add(types.InlineKeyboardButton(
            text=f'{report.city} '
            f'{report.date.day}.{report.date.month}.{report.date.year}',
            callback_data=f'report_{report.id}'
        ))
    inline_markup.row(
        types.InlineKeyboardButton(
            text=f'{current_page}/{total_pages}',
            callback_data='None'
            ),
        types.InlineKeyboardButton(
            text='Вперёд ➡️',
            callback_data=f'next_{current_page}'
            )
    )
    return inline_markup


def generate_report_button_text(report):
    return f'''{report.city}
{report.date.day}.{report.date.month}.{report.date.year}'''


def format_user_text(user):
    return f'''{user.id}) id: {user.tg_id}
Отчётов: {len(user.reports)}'''


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
