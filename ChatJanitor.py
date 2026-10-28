__version__ = (1, 0, 0)
# meta developer: @alexsoiety
# meta owner: @alexsoiety

import html
import time
from datetime import datetime

from telethon.tl.types import Channel

from .. import loader, utils


@loader.tds
class ChatJanitorMod(loader.Module):
    """Поиск заброшенных групп и каналов."""

    strings = {
        "name": "ChatJanitor",
    }

    async def client_ready(self, client, db):
        self._client = client
        if not isinstance(self.get("cj_candidates", None), list):
            self.set("cj_candidates", [])

    @loader.command()
    async def cjscan(self, message):
        """Найти неактивные группы и каналы: .cjscan 90"""
        args = utils.get_args_raw(message).strip()

        if not args.isdigit() or not 1 <= int(args) <= 3650:
            await utils.answer(
                message,
                "Укажи период в днях: <code>.cjscan 90</code>",
            )
            return

        days = int(args)
        cutoff = int(time.time()) - days * 86400
        candidates = []
        checked = 0
        skipped_owner = 0

        await utils.answer(message, "🔎 Сканирую группы и каналы...")

        async for dialog in self._client.iter_dialogs():
            entity = dialog.entity

            # Только группы и каналы, не личные переписки.
            if not isinstance(entity, Channel):
                continue

            # Никогда не предлагаем выйти из собственного канала/группы.
            if getattr(entity, "creator", False):
                skipped_owner += 1
                continue

            # Защита от некорректных или неизвестных дат.
            last_message = getattr(dialog, "date", None)
            if not last_message:
                continue

            try:
                last_ts = int(last_message.timestamp())
            except (AttributeError, TypeError, ValueError):
                continue

            if last_ts > cutoff:
                continue

            checked += 1

            title = getattr(entity, "title", "Без названия")
            unread = int(getattr(dialog, "unread_count", 0) or 0)

            # Сохраняем ID сущности для дальнейшего подтверждённого выхода.
            candidates.append({
                "id": len(candidates) + 1,
                "peer_id": int(entity.id),
                "title": str(title)[:200],
                "last_message": last_ts,
                "unread": unread,
                "megagroup": bool(getattr(entity, "megagroup", False)),
                "broadcast": bool(getattr(entity, "broadcast", False)),
            })

        self.set("cj_candidates", candidates)

        if not candidates:
            await utils.answer(
                message,
                f"✅ Старых групп и каналов за период {days} дней не найдено.\n"
                f"Собственные чаты пропущены: {skipped_owner}.",
            )
            return

        lines = [
            f"🧹 <b>CHATJANITOR · НАЙДЕНО {len(candidates)}</b>",
            f"Период без новых сообщений: {days} дней.",
            f"Собственные чаты пропущены: {skipped_owner}.",
            "",
        ]

        for item in candidates[:25]:
            last = datetime.fromtimestamp(
                item["last_message"]
            ).strftime("%d.%m.%Y")

            lines.append(
                f"<code>#{item['id']}</code> "
                f"<b>{html.escape(item['title'])}</b>\n"
                f"Последнее сообщение: {last} · "
                f"Непрочитанных: {item['unread']}"
            )

        if len(candidates) > 25:
            lines.append(
                f"\n...и ещё {len(candidates) - 25}. "
                "Они сохранены в общем списке."
            )

        lines.append(
            "\nПросмотр: <code>.cjlist</code>\n"
            "Выход из одного чата: <code>.cjleave ID</code>"
        )

        await utils.answer(message, "\n\n".join(lines))

    @loader.command()
    async def cjlist(self, message):
        """Показать список кандидатов."""
        candidates = self.get("cj_candidates", [])

        if not candidates:
            await utils.answer(
                message,
                "📭 Список пуст. Сначала выполни <code>.cjscan 90</code>.",
            )
            return

        lines = ["🧹 <b>CHATJANITOR · СПИСОК</b>"]

        for item in candidates[:50]:
            last = datetime.fromtimestamp(
                int(item["last_message"])
            ).strftime("%d.%m.%Y")

            lines.append(
                f"\n<code>#{item['id']}</code> "
                f"{html.escape(item['title'])}\n"
                f"Последнее сообщение: {last} · "
                f"Непрочитанных: {item['unread']}"
            )

        await utils.answer(message, "\n".join(lines))

    @loader.command()
    async def cjleave(self, message):
        """Выйти из одного чата по ID из списка: .cjleave 3"""
        args = utils.get_args_raw(message).strip()

        if not args.isdigit():
            await utils.answer(
                message,
                "Укажи ID из списка: <code>.cjleave 3</code>",
            )
            return

        item_id = int(args)
        candidates = self.get("cj_candidates", [])

        item = next(
            (x for x in candidates if int(x["id"]) == item_id),
            None,
        )

        if not item:
            await utils.answer(
                message,
                "⚠️ Кандидат не найден. Обнови список командой "
                "<code>.cjscan 90</code>.",
            )
            return

        try:
            # Повторно получаем сущность перед опасным действием.
            entity = await self._client.get_entity(
                await self._client.get_input_entity(item["peer_id"])
            )

            # Повторная защита от выхода из собственных каналов/групп.
            if not isinstance(entity, Channel):
                await utils.answer(
                    message,
                    "⚠️ Это больше не группа или канал. Действие отменено.",
                )
                return

            if getattr(entity, "creator", False):
                await utils.answer(
                    message,
                    "🛡 Это твой собственный канал/группа. Выход запрещён.",
                )
                return

            # Выйти из группы/канала, не удаляя сам чат у других участников.
            await self._client.delete_dialog(entity)

            self.set(
                "cj_candidates",
                [x for x in candidates if int(x["id"]) != item_id],
            )

            await utils.answer(
                message,
                f"✅ Выход выполнен: <b>{html.escape(item['title'])}</b>",
            )

        except Exception as e:
            await utils.answer(
                message,
                "❌ Не удалось выйти из чата.\n"
                f"<code>{html.escape(str(e)[:300])}</code>",
            )

    @loader.command()
    async def cjclear(self, message):
        """Очистить список кандидатов, не выходя из чатов."""
        self.set("cj_candidates", [])
        await utils.answer(
            message,
            "🗑 Список кандидатов очищен. Чаты не затронуты.",
        )
