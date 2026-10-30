__version__ = (2, 0, 0)
# meta developer: @alexsoiety
# meta owner: @alexsoiety

import asyncio
import html
import time
from datetime import datetime

from telethon.tl.types import Channel
from .. import loader, utils


@loader.tds
class ChatJanitorMod(loader.Module):
    """Поиск, фильтрация и очистка заброшенных групп и каналов."""

    strings = {"name": "ChatJanitor"}
    PAGE_SIZE = 15

    async def client_ready(self, client, db):
        self._client = client
        self._scan_lock = asyncio.Lock()
        self._leave_lock = asyncio.Lock()
        for key, default in (
            ("cj_candidates", []), ("cj_selected", []),
            ("cj_leave_pending", {}), ("cj_last_scan", {}),
        ):
            if not isinstance(self.get(key, None), type(default)):
                self.set(key, default)

    def _items(self):
        value = self.get("cj_candidates", [])
        return value if isinstance(value, list) else []

    def _selected(self):
        return {int(x) for x in self.get("cj_selected", []) if str(x).isdigit()}

    def _save_selected(self, values):
        self.set("cj_selected", sorted(set(int(x) for x in values)))

    def _find(self, item_id):
        return next((x for x in self._items()
                     if isinstance(x, dict) and int(x.get("id", -1)) == item_id), None)

    @staticmethod
    def _title(item):
        return html.escape(str(item.get("title", "Без названия"))[:200])

    @staticmethod
    def _date(ts):
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y") if ts else "неизвестно"
        except (ValueError, TypeError, OSError):
            return "неизвестно"

    @staticmethod
    def _kind(item):
        return "канал" if item.get("broadcast") else (
            "супергруппа" if item.get("megagroup") else "группа"
        )

    async def _reply(self, message, text):
        await utils.answer(message, text)

    async def _resolve(self, item):
        entity = await self._client.get_entity(
            await self._client.get_input_entity(int(item["peer_id"]))
        )
        if not isinstance(entity, Channel):
            raise ValueError("Это больше не группа или канал")
        if getattr(entity, "creator", False):
            raise ValueError("Это ваш собственный чат — выход запрещён")
        return entity

    async def _leave_one(self, item):
        entity = await self._resolve(item)
        await self._client.delete_dialog(entity)

    @loader.command()
    async def cjscan(self, message):
        """Сканировать группы и каналы: .cjscan 90"""
        arg = utils.get_args_raw(message).strip()
        if not arg.isdigit() or not 1 <= int(arg) <= 3650:
            return await self._reply(message, "Период от 1 до 3650 дней: <code>.cjscan 90</code>")
        if self._scan_lock.locked():
            return await self._reply(message, "⏳ Сканирование уже выполняется.")

        days = int(arg)
        cutoff = int(time.time()) - days * 86400
        found, owners, unknown = [], 0, 0

        async with self._scan_lock:
            await self._reply(message, f"🔎 Сканирую группы и каналы за {days} дней…")
            async for dialog in self._client.iter_dialogs():
                entity = dialog.entity
                if not isinstance(entity, Channel):
                    continue
                if getattr(entity, "creator", False):
                    owners += 1
                    continue

                # Telethon отдаёт фактический unread_count из диалога Telegram.
                unread = max(0, int(getattr(dialog, "unread_count", 0) or 0))
                date = getattr(dialog, "date", None)
                try:
                    last_ts = int(date.timestamp()) if date else None
                except (AttributeError, TypeError, ValueError, OSError):
                    last_ts = None
                if last_ts is None:
                    unknown += 1
                    continue
                if last_ts > cutoff:
                    continue

                found.append({
                    "id": len(found) + 1,
                    "peer_id": int(entity.id),
                    "title": str(getattr(entity, "title", "Без названия"))[:200],
                    "last_message": last_ts,
                    "unread": unread,
                    "unread_mark": bool(getattr(dialog, "unread_mark", False)),
                    "megagroup": bool(getattr(entity, "megagroup", False)),
                    "broadcast": bool(getattr(entity, "broadcast", False)),
                })

        self.set("cj_candidates", found)
        self._save_selected([])
        self.set("cj_last_scan", {
            "days": days, "timestamp": int(time.time()),
            "owners_skipped": owners, "unknown_dates": unknown,
        })
        unread_total = sum(x["unread"] for x in found)
        await self._reply(
            message,
            "🧹 <b>Сканирование завершено</b>\n\n"
            f"Найдено: <b>{len(found)}</b>\n"
            f"Непрочитанных в найденных чатах: <b>{unread_total}</b>\n"
            f"Собственные чаты пропущены: {owners}\n"
            f"Неизвестная дата (пропущено): {unknown}\n\n"
            "Открой <code>.cjmenu</code> или <code>.cjlist</code>."
        )

    @loader.command()
    async def cjlist(self, message):
        """Список кандидатов: .cjlist [страница]"""
        arg = utils.get_args_raw(message).strip()
        page = max(1, int(arg)) if arg.isdigit() else 1
        items = self._items()
        if not items:
            return await self._reply(message, "📭 Список пуст. Выполни <code>.cjscan 90</code>.")
        pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = min(page, pages)
        subset = items[(page - 1) * self.PAGE_SIZE:page * self.PAGE_SIZE]
        lines = [f"🧹 <b>КАНДИДАТЫ · {len(items)} · {page}/{pages}</b>", ""]
        for x in subset:
            mark = " · 🔖 unread mark" if x.get("unread_mark") else ""
            lines.append(
                f"<code>#{x['id']}</code> <b>{self._title(x)}</b>\n"
                f"{self._kind(x)} · последнее сообщение: {self._date(x.get('last_message'))}\n"
                f"Непрочитанных: <b>{int(x.get('unread', 0) or 0)}</b>{mark}"
            )
        lines.append(f"\nСледующая страница: <code>.cjlist {min(page + 1, pages)}</code>")
        await self._reply(message, "\n\n".join(lines))

    @loader.command()
    async def cjfilter(self, message):
        """Фильтр: .cjfilter unread|read|all|unknown [поиск по названию]"""
        args = utils.get_args_raw(message).strip().split(maxsplit=1)
        mode = args[0].lower() if args else "all"
        query = args[1].lower() if len(args) > 1 else ""
        if mode not in ("all", "unread", "read", "unknown"):
            return await self._reply(message, "Фильтры: <code>all</code>, <code>unread</code>, <code>read</code>, <code>unknown</code>.")
        result = []
        for x in self._items():
            unread = int(x.get("unread", 0) or 0)
            if mode == "unread" and unread == 0:
                continue
            if mode == "read" and unread > 0:
                continue
            if mode == "unknown" and x.get("last_message"):
                continue
            if query and query not in str(x.get("title", "")).lower():
                continue
            result.append(x)
        if not result:
            return await self._reply(message, "📭 Ничего не найдено.")
        lines = [f"🔎 <b>{html.escape(mode)} · {len(result)} результатов</b>"]
        for x in result[:40]:
            lines.append(f"<code>#{x['id']}</code> {self._title(x)} — непрочитанных: {x.get('unread', 0)}")
        await self._reply(message, "\n".join(lines))

    @loader.command()
    async def cjselect(self, message):
        """Выбрать кандидата: .cjselect 3"""
        arg = utils.get_args_raw(message).strip()
        if not arg.isdigit() or not self._find(int(arg)):
            return await self._reply(message, "Укажи существующий ID из <code>.cjlist</code>.")
        selected = self._selected()
        selected.add(int(arg))
        self._save_selected(selected)
        await self._reply(message, f"☑️ Выбран чат #{arg}. Всего выбрано: {len(selected)}.")

    @loader.command()
    async def cjunselect(self, message):
        """Снять выбор: .cjunselect 3"""
        arg = utils.get_args_raw(message).strip()
        if not arg.isdigit():
            return await self._reply(message, "Использование: <code>.cjunselect 3</code>")
        selected = self._selected()
        selected.discard(int(arg))
        self._save_selected(selected)
        await self._reply(message, f"Выбор обновлён: {len(selected)}.")

    @loader.command()
    async def cjselectall(self, message):
        """Выбрать все найденные чаты."""
        self._save_selected(x["id"] for x in self._items())
        await self._reply(message, f"☑️ Выбрано: {len(self._items())}.")

    @loader.command()
    async def cjclearselect(self, message):
        """Снять весь выбор."""
        self._save_selected([])
        await self._reply(message, "Выбор очищен.")

    @loader.command()
    async def cjselected(self, message):
        """Показать выбранные чаты."""
        ids = self._selected()
        items = [x for x in self._items() if int(x.get("id", -1)) in ids]
        if not items:
            return await self._reply(message, "📭 Нет выбранных чатов.")
        lines = [f"☑️ <b>ВЫБРАНО: {len(items)}</b>"]
        lines += [f"<code>#{x['id']}</code> {self._title(x)}" for x in items[:50]]
        await self._reply(message, "\n".join(lines))

    @loader.command()
    async def cjleave(self, message):
        """Выйти из одного чата: .cjleave 3"""
        arg = utils.get_args_raw(message).strip()
        if not arg.isdigit():
            return await self._reply(message, "Использование: <code>.cjleave 3</code>")
        item_id = int(arg)
        item = self._find(item_id)
        if not item:
            return await self._reply(message, "Кандидат не найден. Сделай новое сканирование.")
        try:
            async with self._leave_lock:
                await self._leave_one(item)
            self.set("cj_candidates", [x for x in self._items() if int(x["id"]) != item_id])
            self._save_selected(self._selected() - {item_id})
            await self._reply(message, f"✅ Вышел: <b>{self._title(item)}</b>")
        except Exception as e:
            await self._reply(message, f"❌ Не удалось выйти: <code>{html.escape(str(e)[:250])}</code>")

    @loader.command()
    async def cjleaveall(self, message):
        """Массовый выход: .cjleaveall — предпросмотр; .cjleaveall confirm — запуск."""
        arg = utils.get_args_raw(message).strip().lower()
        if arg != "confirm":
            selected = self._selected()
            items = [x for x in self._items() if int(x["id"]) in selected] if selected else self._items()
            if not items:
                return await self._reply(message, "📭 Нет чатов для выхода.")
            self.set("cj_leave_pending", {
                "ids": [int(x["id"]) for x in items], "created": int(time.time())
            })
            preview = "\n".join("• " + self._title(x) for x in items[:20])
            if len(items) > 20:
                preview += f"\n…и ещё {len(items) - 20}"
            return await self._reply(
                message,
                f"⚠️ <b>ПРЕДПРОСМОТР МАССОВОГО ВЫХОДА</b>\n"
                f"Будет обработано: <b>{len(items)}</b>. "
                f"{'Выбранные чаты' if selected else 'Все кандидаты (ничего не выбрано)'}.\n\n"
                f"{preview}\n\n"
                "Подтверди в течение 10 минут: <code>.cjleaveall confirm</code>"
            )

        pending = self.get("cj_leave_pending", {})
        if not isinstance(pending, dict) or not pending.get("ids"):
            return await self._reply(message, "Нет активного подтверждения. Сначала .cjleaveall")
        if int(time.time()) - int(pending.get("created", 0)) > 600:
            self.set("cj_leave_pending", {})
            return await self._reply(message, "⌛ Подтверждение истекло. Запусти .cjleaveall заново.")
        if self._leave_lock.locked():
            return await self._reply(message, "⏳ Уже выполняется выход из чатов.")

        ids = list(pending["ids"])
        self.set("cj_leave_pending", {})
        success, failed = [], []
        async with self._leave_lock:
            await self._reply(message, f"🧹 Начинаю обработку {len(ids)} чатов…")
            for item_id in ids:
                item = self._find(int(item_id))
                if not item:
                    failed.append((item_id, "нет в текущем списке"))
                    continue
                try:
                    await self._leave_one(item)
                    success.append(int(item_id))
                    await asyncio.sleep(1.2)
                except Exception as e:
                    failed.append((item_id, str(e)[:120]))
                    await asyncio.sleep(2)

        completed = set(success)
        self.set("cj_candidates", [x for x in self._items() if int(x["id"]) not in completed])
        self._save_selected(self._selected() - completed)
        lines = [
            "🧹 <b>МАССОВЫЙ ВЫХОД ЗАВЕРШЁН</b>",
            f"Успешно: <b>{len(success)}</b>",
            f"Ошибок: <b>{len(failed)}</b>",
        ]
        for item_id, error in failed[:15]:
            item = self._find(int(item_id))
            title = item.get("title", f"#{item_id}") if item else f"#{item_id}"
            lines.append(f"• {self._title({'title': title})}: {html.escape(error)}")
        await self._reply(message, "\n".join(lines))

    @loader.command()
    async def cjmenu(self, message):
        """Панель команд ChatJanitor."""
        items = self._items()
        unread = sum(int(x.get("unread", 0) or 0) for x in items)
        await self._reply(
            message,
            "🧹 <b>CHATJANITOR 2.0</b>\n\n"
            f"Кандидатов: <b>{len(items)}</b> · Выбрано: <b>{len(self._selected())}</b>\n"
            f"Непрочитанных в кандидатах: <b>{unread}</b>\n\n"
            "<b>Сканирование</b>: <code>.cjscan 7|30|90|180|365</code>\n"
            "<b>Список</b>: <code>.cjlist [страница]</code>\n"
            "<b>Фильтр</b>: <code>.cjfilter unread|read|all|unknown [текст]</code>\n"
            "<b>Выбор</b>: <code>.cjselect ID</code>, <code>.cjunselect ID</code>, "
            "<code>.cjselectall</code>, <code>.cjclearselect</code>, <code>.cjselected</code>\n"
            "<b>Выход</b>: <code>.cjleave ID</code>, <code>.cjleaveall</code>\n"
            "Массовый выход требует отдельного подтверждения: "
            "<code>.cjleaveall confirm</code>.\n"
            "<code>.cjclear</code> — очистить список без выхода из чатов."
        )

    @loader.command()
    async def cjclear(self, message):
        """Очистить кандидатов и выбор без выхода из чатов."""
        self.set("cj_candidates", [])
        self._save_selected([])
        self.set("cj_leave_pending", {})
        await self._reply(message, "🗑 Список, выбор и ожидающее подтверждение очищены. Чаты не затронуты.")
