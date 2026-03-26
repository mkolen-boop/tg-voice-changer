import asyncio
import json
import os
import subprocess
import tempfile
import httpx
from dotenv import load_dotenv

load_dotenv()
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile

BOT_TOKEN = os.getenv("BOT_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


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


@dp.message(F.voice)
async def handle_voice(message: Message):
    await message.answer("Конвертирую...")

    # Скачиваем голосовуху с Telegram
    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    wav_data = ogg_to_wav(file_bytes.read())

    async with httpx.AsyncClient(timeout=60) as client:
        # Шаг 1: STT — транскрипция с тегами эмоций
        stt_response = await client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            files={"file": ("voice.wav", wav_data, "audio/wav")},
            data={
                "model_id": "scribe_v2",
                "language_code": "ru",
                "tag_audio_events": "true",
            },
        )

        if stt_response.status_code != 200:
            await message.answer(f"Ошибка STT: {stt_response.status_code}\n{stt_response.text}")
            return

        text = stt_response.json().get("text", "")

        # Шаг 2: TTS v3 — синтез с голосом пользователя
        tts_response = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            json={
                "text": text,
                "model_id": "eleven_v3",
                "voice_settings": {
                    "stability": 0.5,
                },
            },
        )

        if tts_response.status_code != 200:
            await message.answer(f"Ошибка TTS: {tts_response.status_code}\n{tts_response.text}")
            return

    audio = BufferedInputFile(tts_response.content, filename="voice.mp3")
    await message.answer_voice(audio)


@dp.message()
async def handle_other(message: Message):
    await message.answer("Отправь голосовое сообщение, и я изменю голос.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
