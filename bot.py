import asyncio
import os
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

    # Отправляем в ElevenLabs Speech-to-Speech
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/speech-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            files={"audio": ("voice.ogg", file_bytes.read(), "audio/ogg")},
            data={
                "model_id": "eleven_multilingual_sts_v2",
                "stability": 0.5,
                "similarity_boost": 0.85,
                "style": 0.0,
                "remove_background_noise": "false",
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
