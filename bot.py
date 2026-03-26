import asyncio
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
VOICE_ID = os.getenv("VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # default: George

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(F.voice)
async def handle_voice(message: Message):
    await message.answer("Конвертирую...")

    # Скачиваем голосовуху с Telegram
    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)

    # Конвертируем ogg -> wav (PCM) через ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
        ogg_file.write(file_bytes.read())
        ogg_path = ogg_file.name

    wav_path = ogg_path.replace(".ogg", ".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "44100", "-ac", "1", wav_path],
        check=True, capture_output=True,
    )

    with open(wav_path, "rb") as wav_file:
        wav_data = wav_file.read()

    os.unlink(ogg_path)
    os.unlink(wav_path)

    # Отправляем в ElevenLabs Speech-to-Speech
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/speech-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            files={"audio": ("voice.wav", wav_data, "audio/wav")},
            data={
                "model_id": "eleven_multilingual_sts_v2",
                "language_code": "ru",
                "stability": 0.75,
                "similarity_boost": 0.6,
                "style": 0.0,
                "remove_background_noise": "true",
                "use_speaker_boost": "true",
            },
        )

    if response.status_code != 200:
        await message.answer(f"Ошибка ElevenLabs: {response.status_code}\n{response.text}")
        return

    # Отправляем обратно пользователю
    audio = BufferedInputFile(response.content, filename="voice.mp3")
    await message.answer_voice(audio)


@dp.message()
async def handle_other(message: Message):
    await message.answer("Отправь голосовое сообщение, и я изменю голос.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
