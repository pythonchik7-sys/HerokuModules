
# meta developer: @alexsoiety
# meta owner: @alexsoiety
# version: 2.0.0

import asyncio
import html
import json
import urllib.error
import urllib.request

from .. import loader, utils


@loader.tds
class GeminiAIMod(loader.Module):
    """Персональный ИИ от Google."""

    strings = {"name": "GeminiAI"}

    def __init__(self):
        self.api_key = ""
        self.model = "gemini-3.8-flash"
        self.system_prompt = (
            "Ты персональный ИИ-помощник пользователя Telegram. "
            "Отвечай на русском, если пользователь не просит другой язык. "
            "Будь точным, полезным и не выдумывай факты."
        )
        self.history = {}
        self.max_history = 12

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.api_key = self.get("api_key", "")
        self.model = self.get("model", "gemini-3.8-flash")
        self.system_prompt = self.get(
            "system_prompt", self.system_prompt
        )
        self.history = self.get("history", {})

    # ---------------- GEMINI API ----------------

    def _request(self, prompt, history=None):
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{self.model}:generateContent"
        )

        contents = []
        for item in (history or [])[-self.max_history:]:
            contents.append({
                "role": item["role"],
                "parts": [{"text": item["text"]}],
            })

        contents.append({
            "role": "user",
            "parts": [{"text": prompt}],
        })

        payload = {
            "systemInstruction": {
                "parts": [{"text": self.system_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))

        candidates = data.get("candidates", [])
        if not candidates:
            feedback = data.get("promptFeedback", {})
            raise RuntimeError(
                "Gemini не вернул ответ: "
                + json.dumps(feedback, ensure_ascii=False)[:500]
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        answer = "\n".join(
            part["text"] for part in parts if "text" in part
        ).strip()

        if not answer:
            raise RuntimeError("Ответ Gemini оказался пустым.")

        return answer

    async def _ask(self, prompt, chat_id):
        if not self.api_key:
            raise RuntimeError(
                "Сначала настрой API-ключ командой .gkey API_KEY"
            )

        key = str(chat_id)
        history = self.history.get(key, [])

        answer = await asyncio.to_thread(
            self._request, prompt, history
        )

        history.extend([
            {"role": "user", "text": prompt},
            {"role": "model", "text": answer},
        ])

        self.history[key] = history[-self.max_history:]
        self.set("history", self.history)

        return answer

    # ---------------- CHAT SUMMARY ----------------

    async def _summarize_chunk(self, text):
        prompt = (
            "Ты анализируешь фрагмент истории Telegram-переписки. "
            "Составь содержательное промежуточное резюме. Сохрани "
            "имена и роли участников, важные даты, факты, решения, "
            "обещания, вопросы и незакрытые темы. Различай мнение "
            "участника и подтверждённый факт. Не додумывай контекст.\n\n"
            + text
        )

        return await asyncio.to_thread(
            self._request, prompt, []
        )

    async def _get_chat_summary(self, entity, limit):
        chunks = []
        buffer = []
        buffer_size = 0
        fetched = 0

        # Telethon возвращает историю от новых сообщений к старым.
        async for msg in self._client.iter_messages(
            entity, limit=limit
        ):
            body = (getattr(msg, "message", None) or "").strip()

            if not body:
                continue

            sender_id = getattr(msg, "sender_id", None)
            date = getattr(msg, "date", None)
            date_text = (
                date.strftime("%Y-%m-%d %H:%M")
                if date else "дата неизвестна"
            )

            line = (
                f"[{date_text}] [ID отправителя: {sender_id}] "
                f"{body[:3000]}"
            )

            buffer.append(line)
            buffer_size += len(line)
            fetched += 1

            if buffer_size >= 12000:
                chunks.append("\n".join(reversed(buffer)))
                buffer = []
                buffer_size = 0

        if buffer:
            chunks.append("\n".join(reversed(buffer)))

        if not chunks:
            return (
                "В доступной истории не найдено текстовых сообщений.",
                0,
            )

        partials = []

        for index, chunk in enumerate(chunks, start=1):
            partial = await self._summarize_chunk(chunk)
            partials.append(
                f"Фрагмент {index}:\n{partial}"
            )

        # Иерархическое сжатие, чтобы не передавать слишком
        # большой текст одним запросом.
        while len("\n\n".join(partials)) > 24000 and len(partials) > 1:
            reduced = []

            for index in range(0, len(partials), 4):
                group = "\n\n".join(partials[index:index + 4])
                reduced.append(
                    await self._summarize_chunk(
                        "Объедини следующие резюме, сохранив "
                        "важные факты, даты и договорённости:\n\n"
                        + group
                    )
                )

            partials = reduced

        final_prompt = (
            "На основе резюме фрагментов истории составь итоговое "
            "саммари переписки на русском языке.\n\n"
            "Структура:\n"
            "1. Главные темы.\n"
            "2. Участники и сведения о них, подтверждённые сообщениями.\n"
            "3. Важные события и хронология.\n"
            "4. Договорённости и обещания.\n"
            "5. Открытые вопросы и следующие шаги.\n"
            "6. Краткий итог.\n\n"
            "Не выдумывай факты и не представляй предположения "
            "как достоверную информацию.\n\n"
            + "\n\n".join(partials)
        )

        result = await asyncio.to_thread(
            self._request, final_prompt, []
        )

        return result, fetched

    async def _send_long(self, message, text, reply_to=None):
        # HTML экранируется вызывающим кодом.
        parts = [
            text[index:index + 3500]
            for index in range(0, len(text), 3500)
        ]

        if not parts:
            parts = ["Пустой ответ."]

        await utils.answer(message, parts[0])

        for part in parts[1:]:
            await message.respond(part)

    # ---------------- COMMANDS ----------------

    @loader.command()
    async def gkey(self, message):
        """Установить ключ Gemini: .gkey API_KEY"""
        key = utils.get_args_raw(message).strip()

        if not key:
            await utils.answer(
                message, "Укажи API-ключ Gemini."
            )
            return

        self.api_key = key
        self.set("api_key", key)

        try:
            await message.delete()
        except Exception:
            pass

        await utils.answer(
            message,
            "🔐 API-ключ сохранён в настройках модуля. "
            "Не отправляй его в публичные чаты.",
        )

    @loader.command()
    async def ai(self, message):
        """Вопрос Gemini: .ai вопрос или ответом на сообщение .ai"""
        prompt = utils.get_args_raw(message).strip()

        if not prompt and message.is_reply:
            replied = await message.get_reply_message()
            prompt = (
                getattr(replied, "message", None) or ""
            ).strip()

        if not prompt:
            await utils.answer(
                message,
                "Пример: <code>.ai объясни, как работает Linux</code>",
            )
            return

        status = await utils.answer(message, "🤖 Gemini думает…")

        try:
            answer = await self._ask(prompt, message.chat_id)
            await self._send_long(
                status,
                "✨ <b>Gemini</b>\n\n" + html.escape(answer),
            )
        except urllib.error.HTTPError as e:
            detail = e.read().decode(
                "utf-8", "replace"
            )[:700]

            await utils.answer(
                status,
                f"❌ Ошибка Gemini API ({e.code}):\n"
                f"<code>{html.escape(detail)}</code>",
            )
        except Exception as e:
            await utils.answer(
                status,
                "❌ Ошибка: <code>"
                + html.escape(str(e)[:700])
                + "</code>",
            )

    @loader.command()
    async def aisummary(self, message):
        """Саммари истории: .aisummary [@username|ID] [количество]"""
        if not self.api_key:
            await utils.answer(
                message,
                "Сначала настрой ключ: <code>.gkey API_KEY</code>",
            )
            return

        args = utils.get_args_raw(message).strip().split()
        target = None
        limit = 200

        try:
            if len(args) == 1:
                if args[0].isdigit():
                    limit = int(args[0])
                else:
                    target = args[0]
            elif len(args) == 2:
                target = args[0]
                limit = int(args[1])
            elif len(args) > 2:
                await utils.answer(
                    message,
                    "Использование:\n"
                    "<code>.aisummary</code>\n"
                    "<code>.aisummary 500</code>\n"
                    "<code>.aisummary @username 300</code>",
                )
                return
        except ValueError:
            await utils.answer(
                message,
                "Количество сообщений должно быть числом.",
            )
            return

        if not 20 <= limit <= 2000:
            await utils.answer(
                message,
                "Укажи от 20 до 2000 сообщений.",
            )
            return

        status = await utils.answer(
            message, "🔎 Получаю историю и готовлю саммари…"
        )

        try:
            if target is None:
                entity = await self._client.get_entity(
                    message.chat_id
                )
            elif target.startswith("@"):
                entity = await self._client.get_entity(target)
            elif target.lstrip("-").isdigit():
                entity = await self._client.get_entity(
                    int(target)
                )
            else:
                await utils.answer(
                    status,
                    "Не удалось распознать цель. "
                    "Используй @username или числовой ID.",
                )
                return

            summary, fetched = await self._get_chat_summary(
                entity, limit
            )

            title = getattr(entity, "title", None)

            if not title:
                first = getattr(entity, "first_name", "") or ""
                last = getattr(entity, "last_name", "") or ""
                title = (
                    (first + " " + last).strip()
                    or getattr(entity, "username", None)
                    or str(getattr(entity, "id", "чат"))
                )

            output = (
                f"🧠 <b>Саммари: {html.escape(str(title))}</b>\n"
                f"Текстовых сообщений обработано: {fetched}\n\n"
                f"{html.escape(summary)}"
            )

            await self._send_long(status, output)

        except Exception as e:
            await utils.answer(
                status,
                "❌ Не удалось сделать саммари:\n<code>"
                + html.escape(str(e)[:700])
                + "</code>",
            )

    @loader.command()
    async def aiset(self, message):
        """Настроить стиль Gemini: .aiset инструкция"""
        prompt = utils.get_args_raw(message).strip()

        if not prompt:
            await utils.answer(
                message,
                "Пример: <code>.aiset Отвечай кратко и по делу</code>",
            )
            return

        self.system_prompt = prompt
        self.set("system_prompt", prompt)

        await utils.answer(message, "⚙️ Инструкция ИИ обновлена.")

    @loader.command()
    async def aimodel(self, message):
        """Выбрать модель: .aimodel MODEL_ID"""
        model = utils.get_args_raw(message).strip()

        if not model:
            await utils.answer(
                message,
                "Текущая модель: <code>"
                + html.escape(self.model)
                + "</code>",
            )
            return

        if not all(
            char.isalnum() or char in "-_." for char in model
        ):
            await utils.answer(message, "Некорректный ID модели.")
            return

        self.model = model
        self.set("model", model)

        await utils.answer(
            message,
            "Модель установлена: <code>"
            + html.escape(model)
            + "</code>",
        )

    @loader.command()
    async def aiclear(self, message):
        """Очистить историю ИИ текущего чата."""
        self.history.pop(str(message.chat_id), None)
        self.set("history", self.history)

        await utils.answer(
            message, "🧹 История ИИ текущего чата очищена."
        )

    @loader.command()
    async def aistatus(self, message):
        """Показать настройки Gemini."""
        await utils.answer(
            message,
            "🧠 <b>GeminiAI</b>\n"
            f"Модель: <code>{html.escape(self.model)}</code>\n"
            f"API-ключ: {'настроен' if self.api_key else 'не задан'}\n"
            f"Лимит контекста: {self.max_history} сообщений",
        )
