import asyncio
import os
import subprocess
import tempfile
import httpx
from dotenv import load_dotenv

load_dotenv()
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

BOT_TOKEN = os.getenv("BOT_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

last_text: dict[int, str] = {}

REGEN_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔄 Перегенерувати", callback_data="regen")]
])

VOICE_SETTINGS = {
    "stability": 0.4,
    "similarity_boost": 0.83,
    "style": 0.5,
    "use_speaker_boost": False,
    "speed": 0.95,
}


def ogg_to_wav(ogg_bytes: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(ogg_bytes)
        ogg_path = f.name

    wav_path = ogg_path.replace(".ogg", ".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "44100", "-ac", "1", wav_path],
        check=True, capture_output=True,
    )

    with open(wav_path, "rb") as f:
        wav_data = f.read()

    os.unlink(ogg_path)
    os.unlink(wav_path)
    return wav_data


def apply_phone_effect(mp3_bytes: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        tts_path = f.name

    out_path = tts_path.replace(".mp3", "_phone.mp3")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", tts_path,
            "-filter_complex",
            "anoisesrc=c=white:a=0.0003[noise];[0:a][noise]amix=inputs=2:duration=first,"
            "highpass=f=150,lowpass=f=9000,equalizer=f=1000:width_type=o:width=2:g=-3",
            out_path,
        ],
        check=True, capture_output=True,
    )

    with open(out_path, "rb") as f:
        result = f.read()

    os.unlink(tts_path)
    os.unlink(out_path)
    return result


async def run_tts(text: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=60) as client:
        return await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "language_code": "ru",
                "voice_settings": VOICE_SETTINGS,
            },
        )


async def send_audio(message: Message, text: str):
    tts_response = await run_tts(text)

    if tts_response.status_code != 200:
        await message.answer(f"Ошибка TTS: {tts_response.status_code}\n{tts_response.text}")
        return

    last_text[message.from_user.id] = text
    audio = BufferedInputFile(apply_phone_effect(tts_response.content), filename="voice.mp3")
    await message.answer_voice(audio, reply_markup=REGEN_KB)


@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer(
        "Привет! Отправь голосовое или текстовое сообщение, и я изменю голос..\n\n"
        "Можешь записать голосовое — говори естественно, с эмоциями, смехом, вздохами.\n\n"
        "Или просто напиши текст, и я озвучу его. Можешь добавлять эмоции в скобках. \n\n"
        "Например (Саркастично) ну да да я так и поняла, окей супер.. (вздох)"
    )


@dp.message(F.voice)
async def handle_voice(message: Message):
    await message.answer("Конвертирую...")

    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    wav_data = ogg_to_wav(file_bytes.read())

    async with httpx.AsyncClient(timeout=60) as client:
        stt_response = await client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            files={"file": ("voice.wav", wav_data, "audio/wav")},
            data={
                "model_id": "scribe_v2",
                "language_code": "ru",
                "tag_audio_events": "false",
            },
        )

        if stt_response.status_code != 200:
            await message.answer(f"Ошибка STT: {stt_response.status_code}\n{stt_response.text}")
            return

        text = stt_response.json().get("text", "").replace("(", "[").replace(")", "]")

    await send_audio(message, text)


@dp.message(F.text)
async def handle_text(message: Message):
    await message.answer("Секундочку...")
    text = message.text.replace("(", "[").replace(")", "]")
    await send_audio(message, text)


@dp.callback_query(F.data == "regen")
async def handle_regen(callback: CallbackQuery):
    text = last_text.get(callback.from_user.id)
    if not text:
        await callback.answer("Нет текста для перегенерации", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer("Секундочку...")

    tts_response = await run_tts(text)

    if tts_response.status_code != 200:
        await callback.message.answer(f"Ошибка TTS: {tts_response.status_code}\n{tts_response.text}")
        return

    audio = BufferedInputFile(apply_phone_effect(tts_response.content), filename="voice.mp3")
    await callback.message.answer_voice(audio, reply_markup=REGEN_KB)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
