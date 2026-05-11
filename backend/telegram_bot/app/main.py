from __future__ import annotations

import asyncio
import html
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Document, Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from app.storage import DocumentStore

from app.config import settings
from app.core_api import CoreApiClient, CoreApiUnavailable, CoreApiValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BTN_UPLOAD = "📎 Загрузить документ"
BTN_MY_DOCS = "📚 Мои документы"
BTN_STATUS = "⚙️ Статус сервиса"
BTN_HELP = "❓ Помощь"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_MY_DOCS),
                KeyboardButton(text=BTN_UPLOAD),
            ],
            [
                KeyboardButton(text=BTN_STATUS),
                KeyboardButton(text=BTN_HELP),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите вопрос",
    )

router = Router()
core_api = CoreApiClient()
document_store = DocumentStore()


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def split_telegram_text(text: str, limit: int | None = None) -> list[str]:
    max_len = limit or settings.max_telegram_message_length

    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n"):
        candidate = f"{current}\n{paragraph}" if current else paragraph

        if len(candidate) <= max_len:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(paragraph) > max_len:
            chunks.append(paragraph[:max_len])
            paragraph = paragraph[max_len:]

        current = paragraph

    if current:
        chunks.append(current)

    return chunks


async def send_long_message(message: Message, text: str) -> None:
    for chunk in split_telegram_text(text):
        await message.answer(escape_html(chunk), parse_mode=ParseMode.HTML)


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "Привет! Я чат-бот для работы с базой знаний.\n\n"
        "Выберите действие на клавиатуре или просто напишите вопрос.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await show_help(message)


@router.message(F.text == BTN_HELP)
async def help_button(message: Message) -> None:
    await show_help(message)


async def show_help(message: Message) -> None:
    await message.answer(
        "Как пользоваться:\n\n"
        "📎 Загрузить документ — отправьте PDF, DOCX, TXT.\n"
        "📚 Мои документы — список документов, которые вы загрузили через этого бота.\n"
        "⚙️ Статус сервиса — проверить доступность Core API.\n\n"
        "История ответов хранится в Core API. Бот хранит только связь между вашим chat_id и загруженными document_id.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    await check_status(message)


@router.message(F.text == BTN_STATUS)
async def status_button(message: Message) -> None:
    await check_status(message)


async def check_status(message: Message) -> None:
    try:
        await core_api.send_message(chat_id=str(message.chat.id), text="ping")
    except CoreApiUnavailable:
        await message.answer("Core API недоступен.", reply_markup=main_keyboard())
        return
    except CoreApiValidationError as exc:
        await message.answer(
            f"Core API доступен, но вернул ошибку проверки: {exc}",
            reply_markup=main_keyboard(),
        )
        return

    await message.answer("Core API доступен.", reply_markup=main_keyboard())

@router.message(F.text == BTN_UPLOAD)
async def upload_button(message: Message) -> None:
    await message.answer(
        "Отправьте файл в формате PDF, DOCX, TXT",
        reply_markup=main_keyboard(),
    )

@router.message(F.text == BTN_MY_DOCS)
async def my_documents_button(message: Message) -> None:
    await show_my_documents(message)


async def show_my_documents(message: Message) -> None:
    chat_id = str(message.chat.id)
    docs = await document_store.list_documents(chat_id=chat_id)

    if not docs:
        await message.answer(
            "У вас пока нет загруженных документов.\n\n"
            "Нажмите «📎 Загрузить документ» и отправьте PDF, DOCX или TXT.",
            reply_markup=main_keyboard(),
        )
        return

    lines = ["📚 Ваши документы:\n"]

    for index, doc in enumerate(docs, start=1):
        document_id = doc["document_id"]
        filename = doc["filename"]
        local_status = doc["status"]

        status = local_status
        try:
            api_status = await core_api.get_document_status(document_id=document_id)
            status = str(api_status.get("status") or local_status)
            await document_store.update_status(
                chat_id=chat_id,
                document_id=document_id,
                status=status,
            )
        except CoreApiUnavailable:
            pass
        except CoreApiValidationError:
            status = "not_found"

        status_icon = {
            "pending": "⏳",
            "processing": "🔄",
            "indexed": "✅",
            "failed": "❌",
            "not_found": "⚠️",
        }.get(status, "ℹ️")

        short_id = document_id[:8]

        lines.append(
            f"{index}. {status_icon} {filename}\n"
            f"   Статус: {status}\n"
            f"   ID: {short_id}..."
        )

    await message.answer(
        "\n\n".join(lines),
        reply_markup=main_keyboard(),
    )


@router.message(F.document)
async def handle_document(message: Message, bot: Bot) -> None:
    document: Document | None = message.document
    if document is None or document.file_name is None:
        await message.answer("Не удалось прочитать файл.")
        return

    suffix = Path(document.file_name).suffix.lower()
    if suffix not in settings.supported_extensions:
        await message.answer("Поддерживаются только файлы PDF, DOCX и TXT.")
        return

    await message.answer("Файл получен. Загружаю в базу знаний...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = Path(tmp_dir) / document.file_name

        try:
            await bot.download(document, destination=local_path)
            upload_result = await core_api.upload_document(path=local_path)
        except CoreApiValidationError as exc:
            await message.answer(f"Файл не принят: {exc}")
            return
        except CoreApiUnavailable:
            await message.answer("Сервис временно недоступен, попробуйте позже.")
            return
        except Exception:
            logger.exception("Failed to process uploaded document")
            await message.answer("Не удалось обработать файл. Попробуйте позже.")
            return

    task_id = str(upload_result.get("task_id") or "")
    document_id = str(upload_result.get("document_id") or "")

    await document_store.add_document(
        chat_id=str(message.chat.id),
        document_id=document_id,
        filename=document.file_name,
        status=str(upload_result.get("status") or "pending"),
    )

    if not task_id:
        await message.answer("Файл загружен, но сервис не вернул task_id.")
        return

    await message.answer(
        f"Файл поставлен в очередь индексации.\n"
        f"document_id: {document_id}\n"
        f"task_id: {task_id}"
    )

    await poll_indexing_status(message, task_id=task_id, document_id=document_id)



async def poll_indexing_status(message: Message, *, task_id: str, document_id: str | None = None) -> None:
    final_statuses = {"indexed", "failed", "cancelled"}

    for _ in range(settings.upload_poll_attempts):
        await asyncio.sleep(settings.upload_poll_interval_seconds)

        try:
            status_result = await core_api.get_indexing_task_status(task_id=task_id)
        except CoreApiUnavailable:
            continue

        status = str(status_result.get("status") or "unknown")

        if document_id:
            await document_store.update_status(
                chat_id=str(message.chat.id),
                document_id=document_id,
                status=status,
            )

        if status in final_statuses:
            if status == "indexed":
                await message.answer("Файл успешно проиндексирован. Теперь по нему можно задавать вопросы.")
            elif status == "failed":
                error_message = status_result.get("error_message") or "неизвестная ошибка"
                await message.answer(f"Индексация завершилась ошибкой: {error_message}")
            else:
                await message.answer("Индексация была отменена.")
            return

    await message.answer(
        "Файл загружен, индексация ещё выполняется. "
        f"Проверить задачу можно в API по task_id: {task_id}"
    )


@router.message(F.text)
async def handle_text(message: Message) -> None:
    text = message.text or ""
    chat_id = str(message.chat.id)

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        answer = await core_api.send_message(chat_id=chat_id, text=text)
    except CoreApiValidationError as exc:
        await message.answer(f"Запрос не принят: попробуйте точнее задать вопрос")
        return
    except CoreApiUnavailable:
        await message.answer("Сервис временно недоступен, попробуйте позже.")
        return
    except Exception:
        logger.exception("Unexpected text handling error")
        await message.answer("Произошла ошибка. Попробуйте позже.")
        return

    await send_long_message(message, answer)


async def main() -> None:
    await document_store.init()

    while True:
        bot = Bot(token=settings.telegram_bot_token)
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(router)

        try:
            logger.info("Starting Telegram bot polling...")
            await dp.start_polling(bot)

        except Exception as exc:
            logger.exception("Telegram polling failed: %s", exc)
            await asyncio.sleep(10)

        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())