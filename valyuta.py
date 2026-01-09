import logging
import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler

# Log konfiguratsiyasi
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Valyuta ma'lumotlari (25+ ta asosiy valyuta)
CURRENCIES = {
    'USD': {'name': 'AQSh dollari', 'flag': '🇺🇸'},
    'EUR': {'name': 'Yevro', 'flag': '🇪🇺'},
    'RUB': {'name': 'Rossiya rubli', 'flag': '🇷🇺'},
    'CNY': {'name': 'Xitoy yuani', 'flag': '🇨🇳'},
    'AED': {'name': 'BAA dirhami', 'flag': '🇦🇪'},
    'KRW': {'name': 'Koreya voni', 'flag': '🇰🇷'},
    'TRY': {'name': 'Turk lirasi', 'flag': '🇹🇷'},
    'GBP': {'name': 'Britaniya funti', 'flag': '🇬🇧'},
    'JPY': {'name': 'Yaponiya yeni', 'flag': '🇯🇵'},
    'KZT': {'name': 'Qozogʻiston tengesi', 'flag': '🇰🇿'},
    'SGD': {'name': 'Singapur dollari', 'flag': '🇸🇬'},
    'CHF': {'name': 'Shveytsariya franki', 'flag': '🇨🇭'},
    'CAD': {'name': 'Kanada dollari', 'flag': '🇨🇦'},
    'UZS': {'name': 'Oʻzbek soʻmi', 'flag': '🇺🇿'},
    'UAH': {'name': 'Ukraina grivnasi', 'flag': '🇺🇦'},
    'PLN': {'name': 'Polsha zlotiyi', 'flag': '🇵🇱'},
    'INR': {'name': 'Hind rupiyasi', 'flag': '🇮🇳'},
    'BRL': {'name': 'Braziliya reali', 'flag': '🇧🇷'},
    'MYR': {'name': 'Malayziya ringgiti', 'flag': '🇲🇾'},
    'THB': {'name': 'Tailand bati', 'flag': '🇹🇭'},
    'SAR': {'name': 'Saudiya Arabistoni riyoli', 'flag': '🇸🇦'},
    'AZN': {'name': 'Ozarbayjon manati', 'flag': '🇦🇿'},
    'KGS': {'name': 'Qirgʻizistoni somi', 'flag': '🇰🇬'},
    'TJS': {'name': 'Tojikiston somonisi', 'flag': '🇹🇯'},
    'IRR': {'name': 'Eron riali', 'flag': '🇮🇷'}
}

# Valyuta kurslarini saqlash uchun global o'zgaruvchi
exchange_rates = {}
last_updated = None

class CurrencyAPI:
    """Valyuta kurslarini olish uchun klass"""

    @staticmethod
    def get_cbu_rates():
        """O'zbekiston Markaziy Banki kurslarini olish"""
        try:
            url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                rates = {}

                for item in data:
                    code = item['Ccy']
                    if code in CURRENCIES:
                        rates[code] = {
                            'rate': Decimal(item['Rate']),
                            'name': CURRENCIES[code]['name'],
                            'flag': CURRENCIES[code]['flag'],
                            'date': item['Date'],
                            'source': 'Oʻzbekiston Markaziy Banki'
                        }

                # UZS (O'zbek so'mi) qo'shamiz
                rates['UZS'] = {
                    'rate': Decimal('1'),
                    'name': 'Oʻzbek soʻmi',
                    'flag': '🇺🇿',
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'Oʻzbekiston Markaziy Banki'
                }

                # Qo'shimcha valyutalar uchun taxminiy kurslar (haqiqiy API bo'lmasa)
                additional_currencies = {
                    'SGD': Decimal('12000'),
                    'CHF': Decimal('12500'),
                    'CAD': Decimal('9000'),
                    'PLN': Decimal('2500'),
                    'BRL': Decimal('2000'),
                    'MYR': Decimal('2400'),
                    'THB': Decimal('320'),
                    'SAR': Decimal('3000'),
                    'AZN': Decimal('6500'),
                    'KGS': Decimal('130'),
                    'TJS': Decimal('1100'),
                    'IRR': Decimal('0.027')
                }

                for code, rate in additional_currencies.items():
                    if code in CURRENCIES and code not in rates:
                        rates[code] = {
                            'rate': rate,
                            'name': CURRENCIES[code]['name'],
                            'flag': CURRENCIES[code]['flag'],
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'source': 'Taxminiy kurs'
                        }

                return rates
        except Exception as e:
            logger.error(f"CBU kurslarini olishda xatolik: {e}")
            # Agar internet bo'lmasa, taxminiy kurslar
            return CurrencyAPI.get_sample_rates()

    @staticmethod
    def get_sample_rates():
        """Internet bo'lmaganda taxminiy kurslar"""
        sample_rates = {
            'USD': {'rate': Decimal('12500'), 'name': 'AQSh dollari', 'flag': '🇺🇸'},
            'EUR': {'rate': Decimal('13500'), 'name': 'Yevro', 'flag': '🇪🇺'},
            'RUB': {'rate': Decimal('140'), 'name': 'Rossiya rubli', 'flag': '🇷🇺'},
            'CNY': {'rate': Decimal('1750'), 'name': 'Xitoy yuani', 'flag': '🇨🇳'},
            'AED': {'rate': Decimal('3400'), 'name': 'BAA dirhami', 'flag': '🇦🇪'},
            'KRW': {'rate': Decimal('9.5'), 'name': 'Koreya voni', 'flag': '🇰🇷'},
            'TRY': {'rate': Decimal('400'), 'name': 'Turk lirasi', 'flag': '🇹🇷'},
            'GBP': {'rate': Decimal('15800'), 'name': 'Britaniya funti', 'flag': '🇬🇧'},
            'JPY': {'rate': Decimal('85'), 'name': 'Yaponiya yeni', 'flag': '🇯🇵'},
            'KZT': {'rate': Decimal('27'), 'name': 'Qozogʻiston tengesi', 'flag': '🇰🇿'},
            'SGD': {'rate': Decimal('12000'), 'name': 'Singapur dollari', 'flag': '🇸🇬'},
            'CHF': {'rate': Decimal('12500'), 'name': 'Shveytsariya franki', 'flag': '🇨🇭'},
            'CAD': {'rate': Decimal('9000'), 'name': 'Kanada dollari', 'flag': '🇨🇦'},
            'UZS': {'rate': Decimal('1'), 'name': 'Oʻzbek soʻmi', 'flag': '🇺🇿'},
            'UAH': {'rate': Decimal('320'), 'name': 'Ukraina grivnasi', 'flag': '🇺🇦'},
            'PLN': {'rate': Decimal('2500'), 'name': 'Polsha zlotiyi', 'flag': '🇵🇱'},
            'INR': {'rate': Decimal('150'), 'name': 'Hind rupiyasi', 'flag': '🇮🇳'},
            'BRL': {'rate': Decimal('2000'), 'name': 'Braziliya reali', 'flag': '🇧🇷'},
            'MYR': {'rate': Decimal('2400'), 'name': 'Malayziya ringgiti', 'flag': '🇲🇾'},
            'THB': {'rate': Decimal('320'), 'name': 'Tailand bati', 'flag': '🇹🇭'},
            'SAR': {'rate': Decimal('3000'), 'name': 'Saudiya Arabistoni riyoli', 'flag': '🇸🇦'},
            'AZN': {'rate': Decimal('6500'), 'name': 'Ozarbayjon manati', 'flag': '🇦🇿'},
            'KGS': {'rate': Decimal('130'), 'name': 'Qirgʻizistoni somi', 'flag': '🇰🇬'},
            'TJS': {'rate': Decimal('1100'), 'name': 'Tojikiston somonisi', 'flag': '🇹🇯'},
            'IRR': {'rate': Decimal('0.027'), 'name': 'Eron riali', 'flag': '🇮🇷'}
        }

        rates = {}
        for code, info in sample_rates.items():
            rates[code] = {
                'rate': info['rate'],
                'name': info['name'],
                'flag': info['flag'],
                'date': datetime.now().strftime('%Y-%m-%d'),
                'source': 'Taxminiy kurs'
            }

        return rates

async def update_exchange_rates():
    """Valyuta kurslarini yangilash"""
    global exchange_rates, last_updated

    rates = CurrencyAPI.get_cbu_rates()

    exchange_rates = rates
    last_updated = datetime.now()
    logger.info(f"Valyuta kurslari yangilandi: {len(exchange_rates)} ta valyuta")

def format_number(num):
    """Sonlarni chiroyli formatlash"""
    return f"{num:,.2f}".replace(",", " ").replace(".", ",")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botni ishga tushirish"""
    user = update.effective_user

    # Kurslarni yangilash
    await update_exchange_rates()

    # Foydalanuvchi ma'lumotlarini tozalash
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("💰 Valyuta kurslari", callback_data='rates')],
        [InlineKeyboardButton("🔄 Valyuta almashinuvi", callback_data='convert_main')],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Assalomu alaykum {user.first_name}!\n"
        f"📊 **Valyuta Kurslari va Konvertor Bot**ga xush kelibsiz!\n\n"
        f"Bot orqali:\n"
        f"• 25+ turdagi valyuta kurslarini ko'rishingiz mumkin\n"
        f"• Valyuta almashinuvlarini hisoblashingiz mumkin\n"
        f"• Inline rejimda har qanday chatda hisoblashingiz mumkin\n\n"
        f"Quyidagi tugmalardan birini tanlang:",
        reply_markup=reply_markup
    )

async def show_rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valyuta kurslarini ko'rsatish"""
    query = update.callback_query
    await query.answer()

    if not exchange_rates or datetime.now() - last_updated > timedelta(hours=1):
        await update_exchange_rates()

    if not exchange_rates:
        await query.edit_message_text(
            "❌ Valyuta kurslarini yuklashda xatolik yuz berdi. Iltimos, keyinroq urunib ko'ring."
        )
        return

    message = "📈 **VALYUTA KURSLARI**\n\n"
    message += f"⏳ Yangilangan: {last_updated.strftime('%Y-%m-%d %H:%M')}\n"
    message += f"📊 Manba: O'zbekiston Markaziy Banki\n\n"

    # 1-qism: Barcha valyutalarni so'mga nisbatan
    message += "**1️⃣ BARCHA VALYUTALAR (UZS ga nisbatan):**\n"

    # Valyutalarni tartiblash
    sorted_currencies = sorted(exchange_rates.items(), key=lambda x: CURRENCIES[x[0]]['name'])

    counter = 1
    for code, info in sorted_currencies:
        if code != 'UZS':
            rate = info['rate']
            flag = info.get('flag', '💰')
            name = info['name']

            if rate > Decimal('10'):  # Agar 1 valyuta > 10 so'm bo'lsa
                formatted_rate = format_number(rate)
                message += f"{counter}. {flag} 1 {code} ({name}) = {formatted_rate} UZS\n"
            else:  # Agar 1 valyuta < 10 so'm bo'lsa
                formatted_rate = format_number(Decimal('1') / rate)
                message += f"{counter}. {flag} 1 UZS = {formatted_rate} {code} ({name})\n"

            counter += 1

    message += "\n**2️⃣ CHET DAVLAT VALYUTALARI (USD ga nisbatan):**\n"

    # USD ga nisbatan kurslar
    if 'USD' in exchange_rates:
        usd_rate = exchange_rates['USD']['rate']

        # Asosiy valyutalar
        major_currencies = ['EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'CNY', 'RUB', 'TRY', 'INR']

        for code in major_currencies:
            if code in exchange_rates and code != 'USD':
                other_rate = exchange_rates[code]['rate']
                flag = exchange_rates[code].get('flag', '💰')
                name = exchange_rates[code]['name']

                # USD dan boshqa valyutaga
                if code in ['EUR', 'GBP', 'CHF', 'CAD', 'AUD']:
                    # Bu valyutalar odatda USD dan qimmat
                    rate_to_usd = other_rate / usd_rate
                    formatted_rate = format_number(rate_to_usd)
                    message += f"• {flag} 1 USD = {formatted_rate} {code} ({name})\n"
                else:
                    # USD dan arzon valyutalar
                    rate_from_usd = usd_rate / other_rate
                    formatted_rate = format_number(rate_from_usd)
                    message += f"• {flag} 1 {code} ({name}) = {formatted_rate} USD\n"

    keyboard = [
        [InlineKeyboardButton("🔄 Yangilash", callback_data='refresh_rates'),
         InlineKeyboardButton("🔙 Asosiy menyu", callback_data='back_to_main')]
    ]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def convert_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Konvertor asosiy menyusi"""
    query = update.callback_query
    await query.answer()

    # Foydalanuvchi ma'lumotlarini tozalash
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("🔄 Valyuta almashinuvi", callback_data='select_from')],
        [InlineKeyboardButton("🔙 Asosiy menyu", callback_data='back_to_main')]
    ]

    await query.edit_message_text(
        "🔄 **VALYUTA ALMASHINUVI**\n\n"
        "Bu bo'limda siz:\n"
        "1. Birinchi valyutani tanlaysiz\n"
        "2. Miqdorni kiritasiz\n"
        "3. Ikkinchi valyutani tanlaysiz\n"
        "4. Natijani olasiz\n\n"
        "Har qadamda xato qilsangiz, 'Orqaga' tugmasi orqali qaytishingiz mumkin.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_from_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Birinchi valyutani tanlash"""
    query = update.callback_query
    await query.answer()

    # Valyuta tugmalarini yaratish (5x5 grid)
    keyboard = []
    row = []

    sorted_currencies = sorted(CURRENCIES.keys())

    for i, code in enumerate(sorted_currencies):
        flag = CURRENCIES[code]['flag']
        row.append(InlineKeyboardButton(f"{flag} {code}", callback_data=f'from_{code}'))

        if len(row) == 5:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    # Orqaga tugmasi
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data='convert_main')])

    await query.edit_message_text(
        "💰 **1-QADAM: BIRINCHI VALYUTANI TANLANG**\n\n"
        "Qaysi valyutadan konvertatsiya qilmoqchisiz?\n"
        "Quyidagi valyutalardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_from_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Birinchi valyutani tanlaganidan keyin"""
    query = update.callback_query
    await query.answer()

    currency_code = query.data.split('_')[1]
    context.user_data['from_currency'] = currency_code
    context.user_data['step'] = 'enter_amount'

    flag = CURRENCIES[currency_code]['flag']
    name = CURRENCIES[currency_code]['name']

    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data='select_from')]]

    await query.edit_message_text(
        f"💰 **2-QADAM: MIQDORNI KIRITING**\n\n"
        f"Tanlangan valyuta: {flag} {currency_code} ({name})\n\n"
        f"Iltimos, konvertatsiya qilmoqchi bo'lgan miqdoringizni kiriting:\n"
        f"**Masalan:** 100, 1500.50, 25000\n\n"
        f"⚠️ **Diqqat:** Faqat raqam kiriting! Harf yoki belgi kiritmang.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Miqdorni qabul qilish va tekshirish"""
    if context.user_data.get('step') != 'enter_amount':
        return

    try:
        # Sonni tozalash
        text = update.message.text.strip()
        text = text.replace(',', '.').replace(' ', '')

        # Son ekanligini tekshirish
        amount = Decimal(text)

        # Manfiy son bo'lmasligi kerak
        if amount <= 0:
            await update.message.reply_text(
                "❌ **XATO:** Miqdor 0 dan katta bo'lishi kerak!\n"
                "Iltimos, qaytadan kiriting:"
            )
            return

        # Juda katta son bo'lmasligi kerak
        if amount > Decimal('1000000000'):  # 1 milliarddan oshmasligi kerak
            await update.message.reply_text(
                "❌ **XATO:** Miqdor juda katta!\n"
                "Iltimos, 1 milliarddan kichikroq son kiriting:"
            )
            return

        # Miqdorni saqlash
        context.user_data['amount'] = amount
        context.user_data['step'] = 'select_to'

        from_code = context.user_data['from_currency']
        from_flag = CURRENCIES[from_code]['flag']
        from_name = CURRENCIES[from_code]['name']
        formatted_amount = format_number(amount)

        await update.message.reply_text(
            f"✅ **MIQDOR QABUL QILINDI:** {formatted_amount} {from_code}\n\n"
            f"Endi ikkinchi valyutani tanlang:",
            reply_markup=get_currency_keyboard('to', from_code)
        )

    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ **XATO:** Noto'g'ri format!\n"
            "Iltimos, faqat raqam kiriting.\n"
            "**Masalan:** 100, 1500.50, 25000\n\n"
            "Qaytadan kiriting:"
        )
    except Exception as e:
        logger.error(f"Miqdorni qabul qilishda xatolik: {e}")
        await update.message.reply_text(
            "❌ **XATO:** Noma'lum xatolik yuz berdi.\n"
            "Iltimos, qaytadan kiriting:"
        )

def get_currency_keyboard(prefix, exclude_code=None):
    """Valyuta tugmalarini yaratish"""
    keyboard = []
    row = []

    sorted_currencies = sorted(CURRENCIES.keys())

    for i, code in enumerate(sorted_currencies):
        if code == exclude_code:
            continue

        flag = CURRENCIES[code]['flag']
        row.append(InlineKeyboardButton(f"{flag} {code}", callback_data=f'{prefix}_{code}'))

        if len(row) == 5:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    # Orqaga tugmasi
    if prefix == 'to':
        keyboard.append([InlineKeyboardButton("🔙 Miqdorni o'zgartirish", callback_data='back_to_amount')])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f'back_to_{prefix}')])

    return InlineKeyboardMarkup(keyboard)

async def handle_to_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ikkinchi valyutani tanlash"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == 'back_to_amount':
        # Miqdorni qayta kiritish
        context.user_data['step'] = 'enter_amount'
        from_code = context.user_data['from_currency']
        from_flag = CURRENCIES[from_code]['flag']
        from_name = CURRENCIES[from_code]['name']

        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data='select_from')]]

        await query.edit_message_text(
            f"💰 **MIQDORNI QAYTA KIRITING**\n\n"
            f"Tanlangan valyuta: {from_flag} {from_code} ({from_name})\n\n"
            f"Iltimos, konvertatsiya qilmoqchi bo'lgan miqdoringizni kiriting:\n"
            f"**Masalan:** 100, 1500.50, 25000",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    to_currency = data.split('_')[1]

    # Ma'lumotlarni saqlash
    context.user_data['to_currency'] = to_currency
    context.user_data['step'] = 'show_result'

    # Konvertatsiyani hisoblash
    await calculate_and_show_result(query, context)

async def calculate_and_show_result(query, context):
    """Konvertatsiyani hisoblash va natijani ko'rsatish"""
    from_code = context.user_data['from_currency']
    to_code = context.user_data['to_currency']
    amount = context.user_data['amount']

    # Kurslarni yangilash
    if not exchange_rates or datetime.now() - last_updated > timedelta(hours=1):
        await update_exchange_rates()

    # Konvertatsiyani hisoblash
    result = convert_currency(amount, from_code, to_code)

    if result is None:
        await query.edit_message_text(
            "❌ **XATO:** Ushbu valyuta juftligi uchun kurs ma'lumotlari mavjud emas.\n\n"
            "Iltimos, boshqa valyutalarni tanlang yoki keyinroq urunib ko'ring.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Qaytadan hisoblash", callback_data='convert_main')],
                [InlineKeyboardButton("🔙 Asosiy menyu", callback_data='back_to_main')]
            ])
        )
        return

    converted_amount, rate = result

    from_flag = CURRENCIES[from_code]['flag']
    from_name = CURRENCIES[from_code]['name']
    to_flag = CURRENCIES[to_code]['flag']
    to_name = CURRENCIES[to_code]['name']

    formatted_amount = format_number(amount)
    formatted_result = format_number(converted_amount)
    formatted_rate = format_number(rate)

    # Manba ma'lumoti
    source = exchange_rates.get(from_code, {}).get('source', 'Noma\'lum manba')
    if from_code == 'UZS' or to_code == 'UZS':
        source = "O'zbekiston Markaziy Banki"

    message = (
        f"💱 **KONVERTATSIYA NATIJASI**\n\n"
        f"📥 **KIRUVCHI:** {formatted_amount} {from_flag} {from_code} ({from_name})\n"
        f"📤 **CHIQUVCHI:** {formatted_result} {to_flag} {to_code} ({to_name})\n\n"
        f"📊 **KURS:** 1 {from_code} = {formatted_rate} {to_code}\n"
        f"⏳ **YANGILANGAN:** {last_updated.strftime('%Y-%m-%d %H:%M')}\n"
        f"📝 **MANBA:** {source}\n\n"
        f"✅ **Hisoblash muvaffaqiyatli yakunlandi!**"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Yangi hisoblash", callback_data='convert_main'),
         InlineKeyboardButton("💰 Kurslarni ko'rish", callback_data='rates')],
        [InlineKeyboardButton("🔙 Asosiy menyu", callback_data='back_to_main')]
    ]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def convert_currency(amount: Decimal, from_currency: str, to_currency: str):
    """Valyuta konvertatsiyasini amalga oshirish"""
    try:
        # Agar ikkala valyuta ham UZS bo'lmasa
        if from_currency != 'UZS' and to_currency != 'UZS':
            # UZS orqali konvertatsiya qilamiz
            from_rate = exchange_rates.get(from_currency, {}).get('rate')
            to_rate = exchange_rates.get(to_currency, {}).get('rate')

            if from_rate and to_rate:
                # from_currency → UZS → to_currency
                in_uzs = amount * from_rate
                result = in_uzs / to_rate
                rate = from_rate / to_rate
                return result.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), rate

        # Agar UZS dan konvertatsiya qilinsa
        elif from_currency == 'UZS':
            to_rate = exchange_rates.get(to_currency, {}).get('rate')
            if to_rate:
                result = amount / to_rate
                rate = Decimal('1') / to_rate
                return result.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), rate

        # Agar UZS ga konvertatsiya qilinsa
        elif to_currency == 'UZS':
            from_rate = exchange_rates.get(from_currency, {}).get('rate')
            if from_rate:
                result = amount * from_rate
                rate = from_rate
                return result.quantize(Decimal('1'), rounding=ROUND_HALF_UP), rate

        return None
    except Exception as e:
        logger.error(f"Konvertatsiya xatosi: {e}")
        return None

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalarni boshqarish"""
    query = update.callback_query
    data = query.data

    if data == 'rates':
        await show_rates(update, context)
    elif data == 'refresh_rates':
        await update_exchange_rates()
        await show_rates(update, context)
    elif data == 'convert_main':
        await convert_main(update, context)
    elif data == 'select_from':
        await select_from_currency(update, context)
    elif data.startswith('from_'):
        await handle_from_currency(update, context)
    elif data.startswith('to_'):
        await handle_to_currency(update, context)
    elif data == 'help':
        await help_command(update, context)
    elif data == 'back_to_main':
        await start_callback(update, context)
    elif data == 'back_to_amount':
        context.user_data['step'] = 'enter_amount'
        from_code = context.user_data['from_currency']
        from_flag = CURRENCIES[from_code]['flag']
        from_name = CURRENCIES[from_code]['name']

        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data='select_from')]]

        await query.edit_message_text(
            f"💰 **MIQDORNI QAYTA KIRITING**\n\n"
            f"Tanlangan valyuta: {from_flag} {from_code} ({from_name})\n\n"
            f"Iltimos, konvertatsiya qilmoqchi bo'lgan miqdoringizni kiriting:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Orqaga asosiy menyuga qaytish"""
    query = update.callback_query
    await query.answer()

    # Foydalanuvchi ma'lumotlarini tozalash
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("💰 Valyuta kurslari", callback_data='rates')],
        [InlineKeyboardButton("🔄 Valyuta almashinuvi", callback_data='convert_main')],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data='help')]
    ]

    await query.edit_message_text(
        "📊 **Valyuta Kurslari va Konvertor Bot**\n\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam ma'lumotlarini ko'rsatish"""
    query = update.callback_query

    if query:
        await query.answer()
        message_target = query.edit_message_text
    else:
        message_target = update.message.reply_text

    help_text = (
        "🆘 **BOTDAN FOYDALANISH BO'YICHA KO'RSATMA**\n\n"

        "📊 **Valyuta Kurslari:**\n"
        "• 'Valyuta kurslari' tugmasi orqali 25+ turdagi valyuta kurslarini ko'ring\n"
        "• 1-qism: Barcha valyutalar so'mga nisbatan\n"
        "• 2-qism: Chet davlat valyutalari USD ga nisbatan\n\n"

        "🔄 **Valyuta Almashinuvi:**\n"
        "1. 'Valyuta almashinuvi' tugmasini bosing\n"
        "2. Birinchi valyutani tanlang\n"
        "3. Miqdorni kiriting (faqat raqam)\n"
        "4. Ikkinchi valyutani tanlang\n"
        "5. Natijani ko'ring\n\n"

        "⚠️ **DIQQAT:**\n"
        "• Har qadamda xato qilsangiz, 'Orqaga' tugmasi bilan qaytishingiz mumkin\n"
        "• Miqdorni kirgazishda faqat raqam ishlating\n"
        "• Kurslar har soatda yangilanadi\n\n"

        "📱 **Inline rejim:**\n"
        "• Har qanday chatda @Valyuta_Kurs_1bot nomini yozing\n"
        "• Masalan: `100 USD to UZS` yoki `50000 UZS to USD`\n\n"

        "⚙️ **Buyruqlar:**\n"
        "/start - Botni ishga tushirish\n"
        "/help - Yordam ko'rsatish\n"
        "/convert - Konvertorni ochish\n"
        "/rates - Valyuta kurslari\n\n"

        "📞 **Qo'llab-quvvatlash:**\n"
        "Muammo bo'lsa @I_admin1_bot ga murojaat qiling"
    )

    keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data='back_to_main')]]

    await message_target(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline so'rovlarni qayta ishlash"""
    query = update.inline_query.query.strip()

    if not query:
        return

    try:
        # Format: "100 USD to UZS" yoki "100 USD UZS"
        parts = query.upper().split()

        if len(parts) >= 3:
            amount = Decimal(parts[0].replace(',', '.'))
            from_currency = parts[1]
            to_currency = parts[-1] if parts[2].lower() == 'to' else parts[2]

            # Valyuta kodlarini tekshirish
            if from_currency in CURRENCIES and to_currency in CURRENCIES:
                # Konvertatsiyani hisoblash
                result = convert_currency(amount, from_currency, to_currency)

                if result:
                    converted_amount, rate = result

                    from_flag = CURRENCIES[from_currency]['flag']
                    to_flag = CURRENCIES[to_currency]['flag']

                    title = f"{format_number(amount)} {from_currency} = {format_number(converted_amount)} {to_currency}"
                    description = f"1 {from_currency} = {format_number(rate)} {to_currency}"

                    message_text = (
                        f"💱 **Konvertatsiya natijasi:**\n\n"
                        f"{from_flag} {format_number(amount)} {from_currency} = {to_flag} {format_number(converted_amount)} {to_currency}\n\n"
                        f"📊 **Kurs:** 1 {from_currency} = {format_number(rate)} {to_currency}\n"
                        f"⏳ {last_updated.strftime('%Y-%m-%d %H:%M')}"
                    )

                    result_obj = InlineQueryResultArticle(
                        id='1',
                        title=title,
                        description=description,
                        input_message_content=InputTextMessageContent(
                            message_text=message_text
                        )
                    )

                    await update.inline_query.answer([result_obj], cache_time=1)
    except Exception as e:
        logger.error(f"Inline so'rovda xatolik: {e}")

def main():
    """Asosiy dastur"""
    # Bot tokenini o'rnating
    TOKEN = "7933047653:AAGfqaVK1VY1VgqfzIRqeAHaRTtZlY-b9sk"  # Bu yerni o'z bot tokenizingiz bilan almashtiring

    # Botni yaratish
    application = Application.builder().token(TOKEN).build()

    # Komandalarni qo'shish
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("convert", convert_main))
    application.add_handler(CommandHandler("rates", show_rates))

    # Tugmalarni qo'shish
    application.add_handler(CallbackQueryHandler(button_handler))

    # Xabarlarni qo'shish (miqdorni qabul qilish)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount))

    # Inline so'rovlarni qo'shish
    application.add_handler(InlineQueryHandler(inline_query))

    # Botni ishga tushirish
    print("✅ Bot ishga tushdi...")
    print("📱 Bot username: @username (BotFather dan olingan)")
    print("💰 Valyutalar: 25+ tur")
    print("🔄 Kurs manbasi: O'zbekiston Markaziy Banki")
    application.run_polling()

if __name__ == '__main__':
    main()
