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
    print("⚠️ Pillow kutubxonasi o'rnatilmagan.")

# Doimiy kurs
DOIMIY_KURS = 12050

# Muddat uchun koeffitsiyentlar
KOEFFITSIYENTLAR = {
    3: 16000,
    4: 17500,
    6: 18000
}

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

def load_fonts():
    """Fontlarni yuklash - SERVERGA MOSLASHTIRISH"""
    fonts = {}

    # DejaVu fontlar ro'yxati (Linux serverlar uchun)
    dejavu_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]

    # Arial fontlar ro'yxati (Windows uchun)
    arial_paths = [
        "arial.ttf",
        "arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf"
    ]

    try:
        # Mavjud fontni topish
        chosen_paths = None

        for path in dejavu_paths:
            if os.path.exists(path):
                chosen_paths = dejavu_paths
                logger.info(f"✅ DejaVu fontlar topildi: {path}")
                break

        if not chosen_paths:
            for path in arial_paths:
                if os.path.exists(path):
                    chosen_paths = arial_paths
                    logger.info(f"✅ Arial fontlar topildi: {path}")
                    break

        # Fontlarni o'rnatish
        if chosen_paths:
            fonts['title'] = ImageFont.truetype(chosen_paths[1], 72)
            fonts['header'] = ImageFont.truetype(chosen_paths[1], 48)
            fonts['medium'] = ImageFont.truetype(chosen_paths[1], 40)
            fonts['label'] = ImageFont.truetype(chosen_paths[0], 28)
            fonts['value'] = ImageFont.truetype(chosen_paths[1], 38)
            fonts['small'] = ImageFont.truetype(chosen_paths[0], 26)
            fonts['oylik'] = ImageFont.truetype(chosen_paths[1], 60)
            fonts['footer'] = ImageFont.truetype(chosen_paths[1], 32)
            fonts['footer_small'] = ImageFont.truetype(chosen_paths[0], 24)
            fonts['phone'] = ImageFont.truetype(chosen_paths[0], 26)
        else:
            raise Exception("Fontlar topilmadi")

    except Exception as e:
        logger.warning(f"⚠️ Fontlar yuklanmadi, default font ishlatiladi: {e}")
        default_font = ImageFont.load_default()
        fonts = {key: default_font for key in [
            'title', 'header', 'medium', 'label', 'value', 'small',
            'oylik', 'footer', 'footer_small', 'phone'
        ]}

    return fonts


def create_result_image(data, result):
    """Chiroyli natija rasmi yaratish"""
    if not PILLOW_AVAILABLE:
        return None

    try:
        width = 1000
        height = 1200

        # Ranglar
        bg_color = (255, 255, 255)
        header_color = (52, 52, 52)
        text_color = (33, 33, 33)
        label_color = (120, 120, 120)
        accent_color = (0, 174, 239)
        border_color = (230, 230, 230)
        success_color = (76, 175, 80)

        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        fonts = load_fonts()

        y_position = 30

        # HEADER
        draw.text((width // 2, y_position), "Sebtech", fill=header_color,
                  font=fonts['title'], anchor="mm")
        y_position += 70

        # HISOB MA'LUMOTLARI SARLAVHA
        draw.text((width // 2, y_position), "HISOB MA'LUMOTLARI",
                  fill=text_color, font=fonts['header'], anchor="mm")
        y_position += 70

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
        card_bottom = y_position + 110
        draw.rectangle([(50, card_top), (width - 50, card_bottom)],
                       fill=(255, 255, 255), outline=border_color, width=2)

        col_width = (width - 100) // 5

        for i, (label, value) in enumerate(zip(labels, values)):
            x_pos = 50 + (i * col_width) + (col_width // 2)
            draw.text((x_pos, card_top + 25), label,
                      fill=label_color, font=fonts['small'], anchor="mm")
            draw.text((x_pos, card_top + 65), value,
                      fill=accent_color, font=fonts['value'], anchor="mm")

            if i < len(labels) - 1:
                line_x = 50 + ((i + 1) * col_width)
                draw.line([(line_x, card_top + 5), (line_x, card_bottom - 5)],
                          fill=border_color, width=1)

        y_position += 140

        # HISOB NATIJALARI SARLAVHA
        draw.text((width // 2, y_position), "HISOB NATIJALARI",
                  fill=text_color, font=fonts['header'], anchor="mm")
        y_position += 70

        # Natijalar kartochkasi
        result_labels = ["Qoldiq (asosiy)", "Qo'shilgan summa", "Umumiy to'lov"]
        result_values = [
            f"{format_number(result['qoldiq_som'])} so'm",
            f"{format_number(result['qoshilgan_foyda'])} so'm",
            f"{format_number(result['umumiy_tolov'])} so'm"
        ]

        card_top = y_position
        card_bottom = y_position + 110
        draw.rectangle([(50, card_top), (width - 50, card_bottom)],
                       fill=(255, 255, 255), outline=border_color, width=2)

        col_width = (width - 100) // 3

        for i, (label, value) in enumerate(zip(result_labels, result_values)):
            x_pos = 50 + (i * col_width) + (col_width // 2)
            draw.text((x_pos, card_top + 25), label,
                      fill=label_color, font=fonts['small'], anchor="mm")
            draw.text((x_pos, card_top + 65), value,
                      fill=accent_color, font=fonts['value'], anchor="mm")

            if i < len(result_labels) - 1:
                line_x = 50 + ((i + 1) * col_width)
                draw.line([(line_x, card_top + 5), (line_x, card_bottom - 5)],
                          fill=border_color, width=1)

        y_position += 140

        # OYLIK TO'LOV
        card_top = y_position
        card_bottom = y_position + 130
        draw.rectangle([(50, card_top), (width - 50, card_bottom)],
                       fill=success_color, outline=success_color, width=2)

        draw.text((width // 2, card_top + 30), "OYLIK TO'LOV",
                  fill=(255, 255, 255), font=fonts['header'], anchor="mm")
        draw.text((width // 2, card_top + 80), f"{format_number(result['oylik_tolov'])} so'm",
                  fill=(255, 255, 255), font=fonts['oylik'], anchor="mm")

        y_position += 160

        # FOOTER
        draw.text((width // 2, y_position), "Sebtech",
                  fill=header_color, font=fonts['footer'], anchor="mm")
        y_position += 40

        draw.text((width // 2, y_position), "TRADE IN / NASIYA SAVDO",
                  fill=label_color, font=fonts['footer_small'], anchor="mm")
        y_position += 35

        draw.text((width // 2, y_position), "+998 (77) 285-99-99",
                  fill=accent_color, font=fonts['phone'], anchor="mm")
        y_position += 35

        draw.text((width // 2, y_position), "+998 (91) 285-99-99",
                  fill=accent_color, font=fonts['phone'], anchor="mm")

        # BytesIO ga saqlash
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG', quality=85, optimize=True)
        img_byte_arr.seek(0)

        return img_byte_arr

    except Exception as e:
        logger.error(f"Rasm yaratishda xatolik: {e}", exc_info=True)
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
        "1️⃣ Mahsulotning umumiy narxini USD da kiriting:\n(Masalan: 1000)"
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
                "❌ Boshlang'ich to'lov manfiy bo'lishi mumkin emas!\n\n"
                "2️⃣ Boshlang'ich to'lovni USD da kiriting:\n(Masalan: 500)"
            )
            return

        if boshlangich_tolov >= umumiy_narx:
            await message.answer(
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
        natija += f"🔹 Muddat: {result['muddat']} oy\n\n"

        natija += f"💵 <b>Qoldiq (asosiy):</b> {format_number(result['qoldiq_som'])} so'm\n"
        natija += f"➕ <b>Qo'shilgan summa:</b> {format_number(result['qoshilgan_foyda'])} so'm\n"
        natija += f"💰 <b>Umumiy to'lov:</b> {format_number(result['umumiy_tolov'])} so'm\n\n"

        natija += f"💸 <b>Oylik to'lov:</b> {format_number(result['oylik_tolov'])} so'm\n"

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
        "1️⃣ Mahsulotning umumiy narxini USD da kiriting:\n(Masalan: 1000)"
    )

    await NasiyaForm.umumiy_narx.set()


@dp.message_handler(commands=['help'], state='*')
async def help_command(message: types.Message):
    """Yordam"""
    help_text = (
        "📚 <b>Yordam</b>\n\n"
        "Bu bot nasiya to'lovlarini hisoblash uchun yaratilgan.\n\n"
        "<b>Muddatlar va koeffitsiyentlar:</b>\n"
        "• 3 oy - 16,000\n"
        "• 4 oy - 17,500\n"
        "• 6 oy - 18,000\n\n"
        "<b>Doimiy kurs:</b> 12,050 so'm"
    )
    await message.answer(help_text, parse_mode='HTML')


@dp.message_handler(state='*')
async def unknown_message(message: types.Message):
    """Noma'lum xabar"""
    await message.answer(
        "❌ Noto'g'ri ma'lumot!\n\n"
        "Qayta boshlash uchun /start buyrug'ini yuboring."
    )