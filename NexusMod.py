__version__ = (1, 0, 0)
# scope: heroku_only
# meta developer: @alexsoiety
# meta owner: @alexsoiety
# meta description: Personal account workspace: notes, tasks, reminders, search and activity report.

import asyncio
import html
import logging
import re
import time
from datetime import datetime, timezone

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class NexusMod(loader.Module):
    """Nexus — персональный центр управления аккаунтом."""

    strings = {
        "name": "Nexus",
        "saved": "🧠 <b>Сохранено в Nexus</b> · заметка <code>#{}</code>",
        "empty_notes": "📭 Заметок пока нет. Ответь на сообщение командой <code>.nxsave</code>.",
        "empty_tasks": "✅ Активных задач нет.",
        "bad_id": "⚠️ Укажи корректный ID.",
        "not_found": "🔎 Ничего не найдено.",
        "reminder_added": "⏰ Напомню через <b>{}</b> мин. Сообщение придёт в Избранное.",
        "help": (
            "🪐 <b>NEXUS · ЛИЧНЫЙ ЦЕНТР</b>\n\n"
            "<b>Память</b>\n"
            "<code>.nxsave [текст]</code> — сохранить заметку или ответ на сообщение\n"
            "<code>.nxnotes</code> — последние заметки\n"
            "<code>.nxfind запрос</code> — поиск по заметкам и задачам\n"
            "<code>.nxdel ID</code> — удалить заметку\n\n"
            "<b>Задачи</b>\n"
            "<code>.nxtodo add текст</code> — создать задачу\n"
            "<code>.nxtodo list</code> — список задач\n"
            "<code>.nxtodo done ID</code> — отметить выполненной\n"
            "<code>.nxtodo del ID</code> — удалить задачу\n\n"
            "<b>Напоминания</b>\n"
            "<code>.nxremind минуты текст</code> — напомнить в Избранном\n"
            "<code>.nxreminders</code> — активные напоминания\n"
            "<code>.nxreminddel ID</code> — отменить напоминание\n\n"
            "<b>Общее</b>\n"
            "<code>.nx</code> — эта справка\n"
            "<code>.nxreport</code> — краткий отчёт Nexus\n\n"
            "👑 Владелец: <a href=\"https://t.me/alexsoiety\">@alexsoiety</a>"
        ),
    }

    def _get_list(self, key):
        value = self.get(key, [])
        return value if isinstance(value, list) else []

    def _put_list(self, key, value):
        self.set(key, value)

    async def client_ready(self, client, db):
        self._client = client
        # Initialize storage without overwriting existing data.
        for key in ("notes", "tasks", "reminders"):
            if not isinstance(self.get(key, None), list):
                self.set(key, [])

    @loader.command()
    async def nxcmd(self, message):
        """Nexus: показать справку."""
        await utils.answer(message, self.strings["help"])

    @loader.command()
    async def nxsavecmd(self, message):
        """Nexus: сохранить заметку или сообщение (ответом)."""
        args = utils.get_args_raw(message).strip()
        reply = await message.get_reply_message()
        if not args and not reply:
            await utils.answer(
                message,
                "Использование: <code>.nxsave текст</code> или ответь на сообщение командой <code>.nxsave</code>.",
            )
            return

        content = args
        source = "text"
        source_chat = None
        source_message = None
        if reply:
            source = "reply"
            source_chat = getattr(getattr(reply, "chat", None), "id", None)
            source_message = getattr(reply, "id", None)
            if not content:
                content = (getattr(reply, "raw_text", None) or "").strip()
            if not content and getattr(reply, "media", None):
                content = "[медиа/вложение]"
        if not content:
            await utils.answer(message, "⚠️ Не нашёл текста для сохранения.")
            return

        notes = self._get_list("notes")
        note_id = max([int(n.get("id", 0)) for n in notes if isinstance(n, dict)] or [0]) + 1
        notes.append({
            "id": note_id,
            "text": content[:12000],
            "created": int(time.time()),
            "source": source,
            "chat_id": source_chat,
            "message_id": source_message,
        })
        self._put_list("notes", notes[-1000:])
        await utils.answer(message, self.strings["saved"].format(note_id))

    @loader.command()
    async def nxnotescmd(self, message):
        """Nexus: показать последние заметки."""
        notes = self._get_list("notes")
        if not notes:
            await utils.answer(message, self.strings["empty_notes"])
            return
        lines = ["🧠 <b>NEXUS · ПОСЛЕДНИЕ ЗАМЕТКИ</b>"]
        for item in sorted(notes, key=lambda x: int(x.get("created", 0)), reverse=True)[:15]:
            snippet = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
            if len(snippet) > 180:
                snippet = snippet[:177] + "..."
            stamp = datetime.fromtimestamp(int(item.get("created", 0))).strftime("%d.%m %H:%M")
            lines.append(f"\n<code>#{item.get('id')}</code> · <i>{html.escape(stamp)}</i>\n{html.escape(snippet)}")
        await utils.answer(message, "\n".join(lines))

    @loader.command()
    async def nxfindcmd(self, message):
        """Nexus: поиск по заметкам и задачам."""
        query = utils.get_args_raw(message).strip().casefold()
        if not query:
            await utils.answer(message, "Использование: <code>.nxfind слово или фраза</code>")
            return
        results = []
        for item in self._get_list("notes"):
            text = str(item.get("text", ""))
            if query in text.casefold():
                results.append(("Заметка", item.get("id"), text))
        for item in self._get_list("tasks"):
            text = str(item.get("text", ""))
            if query in text.casefold():
                results.append(("Задача", item.get("id"), text))
        if not results:
            await utils.answer(message, self.strings["not_found"])
            return
        lines = [f"🔎 <b>Результаты: {len(results)}</b>"]
        for kind, item_id, text in results[:20]:
            snippet = re.sub(r"\s+", " ", text).strip()
            if len(snippet) > 220:
                snippet = snippet[:217] + "..."
            lines.append(f"\n<b>{kind} #{item_id}</b>\n{html.escape(snippet)}")
        await utils.answer(message, "\n".join(lines))

    @loader.command()
    async def nxdelcmd(self, message):
        """Nexus: удалить заметку по ID."""
        args = utils.get_args_raw(message).strip()
        if not args.isdigit():
            await utils.answer(message, "Использование: <code>.nxdel ID</code>")
            return
        note_id = int(args)
        notes = self._get_list("notes")
        updated = [n for n in notes if int(n.get("id", -1)) != note_id]
        if len(updated) == len(notes):
            await utils.answer(message, self.strings["not_found"])
            return
        self._put_list("notes", updated)
        await utils.answer(message, f"🗑 Заметка <code>#{note_id}</code> удалена.")

    @loader.command()
    async def nxtodocmd(self, message):
        """Nexus: управление задачами. add текст | list | done ID | del ID."""
        args = utils.get_args_raw(message).strip()
        if not args or args.lower() == "list":
            tasks = self._get_list("tasks")
            active = [t for t in tasks if not t.get("done")]
            if not active:
                await utils.answer(message, self.strings["empty_tasks"])
                return
            lines = ["📋 <b>NEXUS · ЗАДАЧИ</b>"]
            for task in sorted(active, key=lambda t: int(t.get("created", 0)))[:40]:
                lines.append(f"\n<code>#{task.get('id')}</code> ☐ {html.escape(str(task.get('text', '')))}")
            await utils.answer(message, "\n".join(lines))
            return

        action, _, value = args.partition(" ")
        action = action.lower()
        value = value.strip()
        tasks = self._get_list("tasks")

        if action == "add":
            if not value:
                await utils.answer(message, "Укажи текст: <code>.nxtodo add купить молоко</code>")
                return
            task_id = max([int(t.get("id", 0)) for t in tasks if isinstance(t, dict)] or [0]) + 1
            tasks.append({"id": task_id, "text": value[:1000], "created": int(time.time()), "done": False})
            self._put_list("tasks", tasks[-1000:])
            await utils.answer(message, f"➕ Задача <code>#{task_id}</code> добавлена.")
            return

        if action in ("done", "del") and value.isdigit():
            task_id = int(value)
            found = False
            updated = []
            for task in tasks:
                if int(task.get("id", -1)) == task_id:
                    found = True
                    if action == "done":
                        task["done"] = True
                        task["completed"] = int(time.time())
                        updated.append(task)
                    # del: deliberately do not append
                else:
                    updated.append(task)
            if not found:
                await utils.answer(message, self.strings["not_found"])
                return
            self._put_list("tasks", updated)
            verb = "выполнена" if action == "done" else "удалена"
            await utils.answer(message, f"✅ Задача <code>#{task_id}</code> {verb}.")
            return

        await utils.answer(
            message,
            "Команды:\n<code>.nxtodo add текст</code>\n<code>.nxtodo list</code>\n<code>.nxtodo done ID</code>\n<code>.nxtodo del ID</code>",
        )

    @loader.command()
    async def nxremindcmd(self, message):
        """Nexus: создать напоминание в Избранном. Формат: минуты текст."""
        args = utils.get_args_raw(message).strip()
        parts = args.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            await utils.answer(message, "Использование: <code>.nxremind 15 проверить сервер</code>")
            return
        minutes = int(parts[0])
        text = parts[1].strip()
        if not 1 <= minutes <= 43200:
            await utils.answer(message, "⚠️ Интервал должен быть от 1 минуты до 30 дней.")
            return
        reminders = self._get_list("reminders")
        reminder_id = max([int(r.get("id", 0)) for r in reminders if isinstance(r, dict)] or [0]) + 1
        due = int(time.time()) + minutes * 60
        reminders.append({"id": reminder_id, "text": text[:2000], "due": due, "created": int(time.time())})
        self._put_list("reminders", reminders[-500:])
        await utils.answer(message, self.strings["reminder_added"].format(minutes))

    @loader.command()
    async def nxreminderscmd(self, message):
        """Nexus: список активных напоминаний."""
        reminders = self._get_list("reminders")
        if not reminders:
            await utils.answer(message, "⏰ Активных напоминаний нет.")
            return
        lines = ["⏰ <b>NEXUS · НАПОМИНАНИЯ</b>"]
        for item in sorted(reminders, key=lambda r: int(r.get("due", 0)))[:30]:
            due = datetime.fromtimestamp(int(item.get("due", 0))).strftime("%d.%m %H:%M")
            lines.append(f"\n<code>#{item.get('id')}</code> · <b>{html.escape(due)}</b>\n{html.escape(str(item.get('text', '')))}")
        await utils.answer(message, "\n".join(lines))

    @loader.command()
    async def nxreminddelcmd(self, message):
        """Nexus: отменить напоминание по ID."""
        args = utils.get_args_raw(message).strip()
        if not args.isdigit():
            await utils.answer(message, "Использование: <code>.nxreminddel ID</code>")
            return
        reminder_id = int(args)
        reminders = self._get_list("reminders")
        updated = [r for r in reminders if int(r.get("id", -1)) != reminder_id]
        if len(updated) == len(reminders):
            await utils.answer(message, self.strings["not_found"])
            return
        self._put_list("reminders", updated)
        await utils.answer(message, f"🗑 Напоминание <code>#{reminder_id}</code> отменено.")

    @loader.loop(interval=20, autostart=True, wait_before=True)
    async def reminder_loop(self):
        """Deliver due reminders to Saved Messages."""
        reminders = self._get_list("reminders")
        if not reminders or not getattr(self, "_client", None):
            return
        now = int(time.time())
        due = [r for r in reminders if int(r.get("due", 0)) <= now]
        if not due:
            return
        due_ids = {int(r.get("id", -1)) for r in due}
        # Remove before sending to avoid duplicate delivery after a transient failure/restart.
        self._put_list("reminders", [r for r in reminders if int(r.get("id", -1)) not in due_ids])
        for reminder in due:
            try:
                when = datetime.fromtimestamp(int(reminder.get("due", now))).strftime("%d.%m.%Y %H:%M")
                await self._client.send_message(
                    "me",
                    f"⏰ <b>NEXUS · НАПОМИНАНИЕ</b>\n\n{html.escape(str(reminder.get('text', '')))}\n\n<i>Планировалось: {html.escape(when)}</i>",
                    parse_mode="html",
                )
            except Exception:
                logger.exception("Nexus: failed to deliver reminder #%s", reminder.get("id"))

    @loader.command()
    async def nxreportcmd(self, message):
        """Nexus: краткий отчёт о сохранённых данных."""
        notes = self._get_list("notes")
        tasks = self._get_list("tasks")
        reminders = self._get_list("reminders")
        active = sum(1 for task in tasks if not task.get("done"))
        done = sum(1 for task in tasks if task.get("done"))
        due = sum(1 for item in reminders if int(item.get("due", 0)) <= int(time.time()))
        await utils.answer(
            message,
            "🪐 <b>NEXUS · ОТЧЁТ</b>\n\n"
            f"🧠 Заметок: <b>{len(notes)}</b>\n"
            f"📋 Активных задач: <b>{active}</b>\n"
            f"✅ Выполненных задач: <b>{done}</b>\n"
            f"⏰ Напоминаний в очереди: <b>{len(reminders)}</b>\n"
            f"🔔 Просроченных напоминаний: <b>{due}</b>\n\n"
            "<i>Все данные хранятся в базе Heroku.</i>",
        )
