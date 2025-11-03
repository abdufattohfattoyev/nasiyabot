import os
import io
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import requests

from loader import dp, bot

try:
    from PIL import Image, ImageDraw, ImageFont

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("⚠️ Pillow kutubxonasi o'rnatilmagan. Rasm yaratish imkoniyati o'chirilgan.")

# Doimiy kurs
DOIMIY_KURS = 12050

# Muddat uchun koeffitsiyentlar (dollar uchun)
KOEFFITSIYENTLAR = {
    3: 16000,
    4: 17500,
    6: 18000
}

# Logo URL (GitHub yoki boshqa joydan)
LOGO_URL = "https://i.imgur.com/your-logo.png"  # Bu yerga logo URL kiriting

# =========================
# LOGGING SOZLASH
# =========================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =========================
# FSM HOLATLAR
# =========================

class NasiyaForm(StatesGroup):
    umumiy_narx = State()
    boshlangich_tolov = State()
    muddat = State()


# =========================
# YORDAMCHI FUNKSIYALAR
# =========================

def format_number(num):
    """Raqamlarni bo'sh joy bilan formatlash"""
    return "{:,.0f}".format(num).replace(',', ' ')


def calculate_nasiya(umumiy_narx, boshlangich_tolov, kurs, muddat):
    """Nasiya to'lovlarini hisoblash"""
    qoldiq_dollar = umumiy_narx - boshlangich_tolov
    qoldiq_som = qoldiq_dollar * kurs
    koeffitsiyent = KOEFFITSIYENTLAR[muddat]
    umumiy_tolov = qoldiq_dollar * koeffitsiyent
    qoshilgan_foyda = umumiy_tolov - qoldiq_som
    oylik_tolov = umumiy_tolov / muddat
    oyma_oy_foyda = qoshilgan_foyda / muddat
    oylik_asosiy = qoldiq_som / muddat

    return {
        'qoldiq_dollar': qoldiq_dollar,
        'qoldiq_som': qoldiq_som,
        'koeffitsiyent': koeffitsiyent,
        'umumiy_tolov': umumiy_tolov,
        'qoshilgan_foyda': qoshilgan_foyda,
        'oylik_tolov': oylik_tolov,
        'oyma_oy_foyda': oyma_oy_foyda,
        'oylik_asosiy': oylik_asosiy,
        'muddat': muddat
    }


# =========================
# KLAVIATURALAR
# =========================

def get_muddat_inline_keyboard():
    """Muddat tanlash inline klaviaturasi"""
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("3️⃣ 3 oy", callback_data="muddat_3"),
        InlineKeyboardButton("4️⃣ 4 oy", callback_data="muddat_4"),
        InlineKeyboardButton("6️⃣ 6 oy", callback_data="muddat_6")
    )
    return keyboard


def get_restart_inline_keyboard():
    """Qayta hisoblash inline klaviaturasi"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Qayta hisoblash", callback_data="restart"))
    return keyboard


# =========================
# RASM YARATISH
# =========================

def download_logo():
    """Logoni yuklab olish - bot papkasidan"""
    try:
        # Bot papkasidagi logo fayllarni tekshirish
        logo_paths = [
            'logo.png',
            'logo.jpg',
            'logo.jpeg',
            'assets/logo.png',
            'images/logo.png'
        ]

        for path in logo_paths:
            if os.path.exists(path):
                return Image.open(path)

        logger.warning("Logo fayli topilmadi. Logo faylni bot papkasiga joylashtiring (logo.png)")
    except Exception as e:
        logger.warning(f"Logo yuklab bo'lmadi: {e}")

    return None


def load_fonts():
    """Fontlarni yuklash - DejaVu asosiy, Arial zaxira"""
    fonts = {}

    # DejaVu fontlar ro'yxati (Linux serverlar uchun)
    dejavu_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]

    # Arial fontlar ro'yxati (Windows uchun)
    arial_paths = [
        "arial.ttf",
        "arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf"
    ]

    try:
        # Asosiy fontlarni yuklash - KATTAROQ O'LCHAMLAR
        try:
            fonts['title'] = ImageFont.truetype(dejavu_paths[0], 70)  # 64 -> 70
            fonts['header'] = ImageFont.truetype(dejavu_paths[0], 48)  # 42 -> 48
            fonts['medium'] = ImageFont.truetype(dejavu_paths[0], 40)  # 36 -> 40
            fonts['label'] = ImageFont.truetype(dejavu_paths[1], 28)  # 24 -> 28
            fonts['value'] = ImageFont.truetype(dejavu_paths[0], 38)  # 32 -> 38
            fonts['small'] = ImageFont.truetype(dejavu_paths[1], 26)  # 22 -> 26
            fonts['oylik'] = ImageFont.truetype(dejavu_paths[0], 62)  # 56 -> 62
            fonts['footer'] = ImageFont.truetype(dejavu_paths[0], 32)  # 28 -> 32
            fonts['footer_small'] = ImageFont.truetype(dejavu_paths[1], 24)  # 20 -> 24
            fonts['phone'] = ImageFont.truetype(dejavu_paths[1], 28)  # 24 -> 28
            logger.info("✅ DejaVu fontlar yuklandi (KATTA o'lchamlar)")
        except:
            # Arial orqali urinish
            fonts['title'] = ImageFont.truetype(arial_paths[1], 70)
            fonts['header'] = ImageFont.truetype(arial_paths[1], 48)
            fonts['medium'] = ImageFont.truetype(arial_paths[1], 40)
            fonts['label'] = ImageFont.truetype(arial_paths[0], 28)
            fonts['value'] = ImageFont.truetype(arial_paths[1], 38)
            fonts['small'] = ImageFont.truetype(arial_paths[0], 26)
            fonts['oylik'] = ImageFont.truetype(arial_paths[1], 62)
            fonts['footer'] = ImageFont.truetype(arial_paths[1], 32)
            fonts['footer_small'] = ImageFont.truetype(arial_paths[0], 24)
            fonts['phone'] = ImageFont.truetype(arial_paths[0], 28)
            logger.info("✅ Arial fontlar yuklandi (KATTA o'lchamlar)")
    except Exception as e:
        logger.warning(f"⚠️ Fontlar yuklanmadi, default font ishlatiladi: {e}")
        # Default fontlarni ishlatish
        default_font = ImageFont.load_default()
        fonts = {
            'title': default_font,
            'header': default_font,
            'medium': default_font,
            'label': default_font,
            'value': default_font,
            'small': default_font,
            'oylik': default_font,
            'footer': default_font,
            'footer_small': default_font,
            'phone': default_font
        }

    return fonts


def create_result_image(data, result):
    """Chiroyli va aniq natija rasmi yaratish"""
    if not PILLOW_AVAILABLE:
        return None

    try:
        width = 1200
        height = 1400

        # Ranglar - TO'LIQ OQ FON
        bg_color = (255, 255, 255)  # Oq
        header_color = (52, 52, 52)  # Qora-kulrang
        text_color = (33, 33, 33)  # To'q kulrang
        label_color = (120, 120, 120)  # Och kulrang
        accent_color = (0, 174, 239)  # Turkuaz ko'k
        light_bg = (255, 255, 255)  # Oq
        border_color = (230, 230, 230)  # Och kulrang
        success_color = (76, 175, 80)  # Yashil

        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Fontlarni yuklash
        fonts = load_fonts()

        y_position = 0

        # HEADER - TO'LIQ OQ FON
        draw.rectangle([(0, 0), (width, 180)], fill=(255, 255, 255))

        # Logo joylashtirish
        logo = download_logo()
        if logo:
            try:
                logo_width = 200
                logo_height = int(logo.height * (logo_width / logo.width))
                logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
                logo_x = (width - logo_width) // 2
                logo_y = (180 - logo_height) // 2

                if logo.mode == 'RGBA':
                    img.paste(logo, (logo_x, logo_y), logo)
                else:
                    img.paste(logo, (logo_x, logo_y))

                y_position = 180
            except Exception as e:
                logger.error(f"Logo joylashtirish xatosi: {e}")
                draw.text((width // 2, 90), "sebtech", fill=header_color,
                          font=fonts['title'], anchor="mm")
                y_position = 180
        else:
            draw.text((width // 2, 90), "sebtech", fill=header_color,
                      font=fonts['title'], anchor="mm")
            y_position = 180

        y_position += 50  # 40 -> 50

        # HISOB MA'LUMOTLARI - Sarlavha
        draw.text((width // 2, y_position), "HISOB MA'LUMOTLARI",
                  fill=text_color, font=fonts['header'], anchor="mm")

        y_position += 70  # 60 -> 70

        # Ma'lumotlar kartochkasi
        labels = ["Umumiy narx", "Boshlang'ich", "Qoldiq", "Kurs", "Muddat"]
        values = [
            f"${format_number(data['umumiy_narx'])}",
            f"${format_number(data['boshlangich_tolov'])}",
            f"${format_number(result['qoldiq_dollar'])}",
            f"{format_number(DOIMIY_KURS)} so'm",
            f"{result['muddat']} oy"
        ]

        card_top = y_position
        card_bottom = y_position + 130  # 120 -> 130
        draw.rectangle([(60, card_top), (width - 60, card_bottom)],
                       fill=light_bg, outline=border_color, width=4)

        col_width = (width - 120) // 5

        for i, (label, value) in enumerate(zip(labels, values)):
            x_pos = 60 + (i * col_width) + (col_width // 2)

            draw.text((x_pos, card_top + 32), label,  # 30 -> 32
                      fill=label_color, font=fonts['small'], anchor="mm")

            draw.text((x_pos, card_top + 80), value,  # 75 -> 80
                      fill=accent_color, font=fonts['value'], anchor="mm")

            if i < len(labels) - 1:
                line_x = 60 + ((i + 1) * col_width)
                draw.line([(line_x, card_top + 10), (line_x, card_bottom - 10)],
                          fill=border_color, width=3)

        y_position += 170  # 160 -> 170

        # HISOB NATIJALARI - Sarlavha
        draw.text((width // 2, y_position), "HISOB NATIJALARI",
                  fill=text_color, font=fonts['header'], anchor="mm")

        y_position += 70  # 60 -> 70

        # Natijalar kartochkasi
        result_labels = ["Qoldiq (asosiy)", "Qo'shilgan summa", "Umumiy to'lov"]
        result_values = [
            f"{format_number(result['qoldiq_som'])} so'm",
            f"{format_number(result['qoshilgan_foyda'])} so'm",
            f"{format_number(result['umumiy_tolov'])} so'm"
        ]

        card_top = y_position
        card_bottom = y_position + 130  # 120 -> 130
        draw.rectangle([(60, card_top), (width - 60, card_bottom)],
                       fill=light_bg, outline=border_color, width=4)

        col_width = (width - 120) // 3

        for i, (label, value) in enumerate(zip(result_labels, result_values)):
            x_pos = 60 + (i * col_width) + (col_width // 2)

            draw.text((x_pos, card_top + 32), label,  # 30 -> 32
                      fill=label_color, font=fonts['small'], anchor="mm")

            draw.text((x_pos, card_top + 80), value,  # 75 -> 80
                      fill=accent_color, font=fonts['value'], anchor="mm")

            if i < len(result_labels) - 1:
                line_x = 60 + ((i + 1) * col_width)
                draw.line([(line_x, card_top + 10), (line_x, card_bottom - 10)],
                          fill=border_color, width=3)

        y_position += 170  # 160 -> 170

        # OYLIK TO'LOV - Alohida katta kartochka
        card_top = y_position
        card_bottom = y_position + 150  # 140 -> 150
        draw.rectangle([(60, card_top), (width - 60, card_bottom)],
                       fill=success_color, outline=success_color, width=4)

        draw.text((width // 2, card_top + 42), "OYLIK TO'LOV",  # 40 -> 42
                  fill=(255, 255, 255), font=fonts['header'], anchor="mm")

        draw.text((width // 2, card_top + 100), f"{format_number(result['oylik_tolov'])} so'm",  # 95 -> 100
                  fill=(255, 255, 255), font=fonts['oylik'], anchor="mm")

        y_position += 190  # 180 -> 190

        # Bo'sh joy
        y_position += 60  # 60

        # FOOTER - Kontakt ma'lumotlar
        draw.text((width // 2, y_position), "Sebtech",
                  fill=header_color, font=fonts['footer'], anchor="mm")

        y_position += 40  # 38 -> 40
        draw.text((width // 2, y_position), "TRADE IN / NASIYA SAVDO",
                  fill=label_color, font=fonts['footer_small'], anchor="mm")

        y_position += 40  # 38 -> 40
        draw.text((width // 2, y_position), "+998 (77) 285-99-99",
                  fill=accent_color, font=fonts['phone'], anchor="mm")

        y_position += 38  # 35 -> 38
        draw.text((width // 2, y_position), "+998 (91) 285-99-99",
                  fill=accent_color, font=fonts['phone'], anchor="mm")

        # BytesIO ga saqlash
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG', quality=100, optimize=False)
        img_byte_arr.seek(0)

        return img_byte_arr

    except Exception as e:
        logger.error(f"Rasm yaratishda xatolik: {e}")
        return None


# =========================
# HANDLERLAR
# =========================

@dp.message_handler(CommandStart(), state='*')
async def bot_start(message: types.Message, state: FSMContext):
    """Bot boshlanganda"""
    await state.finish()

    user_name = message.from_user.full_name or "Foydalanuvchi"

    await message.answer(
        f"Assalomu alaykum, {user_name}! 👋\n\n"
        "Nasiya hisoblash botiga xush kelibsiz.\n"
        "Keling, sizning to'lovingizni hisoblaymiz.\n\n"
        "📝 Quyidagi ma'lumotlarni kiriting:"
    )

    await message.answer(
        "1️⃣ Mahsulotning umumiy narxini USD da kiriting:\n"
        "(Masalan: 1000)"
    )

    await NasiyaForm.umumiy_narx.set()


@dp.message_handler(state=NasiyaForm.umumiy_narx)
async def process_umumiy_narx(message: types.Message, state: FSMContext):
    """Umumiy narxni qabul qilish"""
    try:
        umumiy_narx = float(message.text.replace(' ', '').replace(',', '.'))

        if umumiy_narx <= 0:
            await message.answer(
                "❌ Iltimos, musbat son kiriting!\n\n"
                "1️⃣ Mahsulotning umumiy narxini USD da kiriting:\n(Masalan: 1000)"
            )
            return

        await state.update_data(umumiy_narx=umumiy_narx)

        await message.answer(
            f"✅ Umumiy narx: ${format_number(umumiy_narx)}\n\n"
            "2️⃣ Boshlang'ich to'lovni USD da kiriting:\n(Masalan: 500)"
        )

        await NasiyaForm.boshlangich_tolov.set()

    except ValueError:
        await message.answer(
            "❌ Noto'g'ri format! Iltimos, raqam kiriting.\n\n"
            "1️⃣ Mahsulotning umumiy narxini USD da kiriting:\n(Masalan: 1000)"
        )


@dp.message_handler(state=NasiyaForm.boshlangich_tolov)
async def process_boshlangich_tolov(message: types.Message, state: FSMContext):
    """Boshlang'ich to'lovni qabul qilish"""
    data = await state.get_data()
    umumiy_narx = data.get('umumiy_narx', 0)

    try:
        boshlangich_tolov = float(message.text.replace(' ', '').replace(',', '.'))

        if boshlangich_tolov < 0:
            await message.answer(
                f"✅ Umumiy narx: ${format_number(umumiy_narx)}\n\n"
                "❌ Boshlang'ich to'lov manfiy bo'lishi mumkin emas!\n\n"
                "2️⃣ Boshlang'ich to'lovni USD da kiriting:\n(Masalan: 500)"
            )
            return

        if boshlangich_tolov >= umumiy_narx:
            await message.answer(
                f"✅ Umumiy narx: ${format_number(umumiy_narx)}\n\n"
                "❌ Boshlang'ich to'lov umumiy narxdan kam bo'lishi kerak!\n\n"
                "2️⃣ Boshlang'ich to'lovni USD da kiriting:\n(Masalan: 500)"
            )
            return

        qoldiq = umumiy_narx - boshlangich_tolov
        await state.update_data(boshlangich_tolov=boshlangich_tolov)

        await message.answer(
            f"✅ Umumiy narx: ${format_number(umumiy_narx)}\n"
            f"✅ Boshlang'ich to'lov: ${format_number(boshlangich_tolov)}\n"
            f"📦 Qoldiq: ${format_number(qoldiq)}\n"
            f"💱 Kurs: {format_number(DOIMIY_KURS)} so'm\n\n"
            "3️⃣ Muddatni tanlang:",
            reply_markup=get_muddat_inline_keyboard()
        )

        await NasiyaForm.muddat.set()

    except ValueError:
        await message.answer(
            f"✅ Umumiy narx: ${format_number(umumiy_narx)}\n\n"
            "❌ Noto'g'ri format! Iltimos, raqam kiriting.\n\n"
            "2️⃣ Boshlang'ich to'lovni USD da kiriting:\n(Masalan: 500)"
        )


@dp.callback_query_handler(lambda c: c.data.startswith('muddat_'), state=NasiyaForm.muddat)
async def process_muddat_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Muddat tanlanganda"""
    await callback_query.answer()

    muddat = int(callback_query.data.split('_')[1])
    data = await state.get_data()

    # Hisoblash
    result = calculate_nasiya(
        data.get('umumiy_narx', 0),
        data.get('boshlangich_tolov', 0),
        DOIMIY_KURS,
        muddat
    )

    # Rasm yaratish
    img_byte_arr = create_result_image(data, result)

    # Natijani yuborish
    if img_byte_arr:
        try:
            await bot.send_photo(
                callback_query.message.chat.id,
                photo=img_byte_arr,
                caption="✅ Hisoblash yakunlandi!",
                reply_markup=get_restart_inline_keyboard()
            )
        except Exception as e:
            logger.error(f"Rasm yuborishda xatolik: {e}")
            img_byte_arr = None

    if not img_byte_arr:
        # Matn ko'rinishida yuborish
        natija = f"📊 <b>Nasiya hisoblash natijasi</b>\n\n"
        natija += f"🔹 Umumiy narx: ${format_number(data.get('umumiy_narx', 0))}\n"
        natija += f"🔹 Boshlang'ich to'lov: ${format_number(data.get('boshlangich_tolov', 0))}\n"
        natija += f"🔹 Qoldiq: ${format_number(result['qoldiq_dollar'])}\n"
        natija += f"🔹 Kurs: {format_number(DOIMIY_KURS)} so'm\n"
        natija += f"🔹 Muddat: {result['muddat']} oy\n"
        natija += f"🔹 Koeffitsiyent: {format_number(result['koeffitsiyent'])} so'm\n\n"

        natija += f"💵 <b>Qoldiq (asosiy):</b> {format_number(result['qoldiq_som'])} so'm\n"
        natija += f"➕ <b>Qo'shilgan summa:</b> {format_number(result['qoshilgan_foyda'])} so'm\n"
        natija += f"💰 <b>Umumiy to'lov:</b> {format_number(result['umumiy_tolov'])} so'm\n\n"

        natija += f"💸 <b>Oylik to'lov:</b> {format_number(result['oylik_tolov'])} so'm\n\n"

        natija += "🧾 <b>To'lovlar jadvali:</b>\n"
        for oy in range(1, muddat + 1):
            natija += f"{oy}-oy → <b>{format_number(result['oylik_tolov'])} so'm</b>\n"

        await bot.send_message(
            callback_query.message.chat.id,
            natija,
            parse_mode='HTML',
            reply_markup=get_restart_inline_keyboard()
        )

    await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'restart', state='*')
async def restart_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Qayta hisoblash"""
    await callback_query.answer()
    await state.finish()

    await bot.send_message(
        callback_query.message.chat.id,
        "Assalomu alaykum! 👋\n\n"
        "Nasiya hisoblash botiga xush kelibsiz.\n"
        "Keling, sizning to'lovingizni hisoblaymiz.\n\n"
        "📝 Quyidagi ma'lumotlarni kiriting:"
    )

    await bot.send_message(
        callback_query.message.chat.id,
        "1️⃣ Mahsulotning umumiy narxini USD da kiriting:\n(Masalan: 1000)"
    )

    await NasiyaForm.umumiy_narx.set()


@dp.message_handler(commands=['help'], state='*')
async def help_command(message: types.Message):
    """Yordam"""
    help_text = (
        "📚 <b>Yordam</b>\n\n"
        "Bu bot nasiya to'lovlarini hisoblash uchun yaratilgan.\n\n"
        "<b>Qanday foydalanish:</b>\n"
        "1️⃣ /start - Botni boshlash\n"
        "2️⃣ Mahsulot narxini kiriting\n"
        "3️⃣ Boshlang'ich to'lovni kiriting\n"
        "4️⃣ Muddatni tanlang\n"
        "5️⃣ Natijani ko'ring\n\n"
        "<b>Muddatlar:</b>\n"
        "• 3 oy - koeffitsiyent 16,000\n"
        "• 4 oy - koeffitsiyent 17,500\n"
        "• 6 oy - koeffitsiyent 18,000\n\n"
        "<b>Doimiy kurs:</b> 12,050 so'm"
    )
    await message.answer(help_text, parse_mode='HTML')


@dp.message_handler(state='*')
async def unknown_message(message: types.Message):
    """Noma'lum xabar"""
    await message.answer(
        "❌ Noto'g'ri ma'lumot!\n\n"
        "Qayta boshlash uchun /start buyrug'ini yuboring.\n"
        "Yordam uchun /help buyrug'ini yuboring."
    )