# -*- coding: utf-8 -*-
# Broadcast Manager for coddrago/Heroku
# Developer: @alexsociety
# Safe utility: parses a replied-to report, manages a local candidate list,
# blacklist, templates, settings, export and history. It does not mass-DM
# people discovered in third-party reports.

import re
import html
import time

from heroku import loader, utils


@loader.tds
class BroadcastManager(loader.Module):
    """Парсер и менеджер списка Telegram-аккаунтов."""

    strings = {
        "name": "BroadcastManager",
        "developer": "@alexsociety"
    }

    PAGE_SIZE = 8

    def _get(self, key, default=None):
        value = self.get(key, default)
        return value if value is not None else default

    def _set(self, key, value):
        self.set(key, value)

    def _candidates(self):
        return self._get("candidates", {})

    def _blacklist(self):
        return set(str(x) for x in self._get("blacklist", []))

    def _templates(self):
        return self._get("templates", [])

    def _history(self):
        return self._get("history", [])

    def _save_history(self, action, details):
        history = self._history()
        history.insert(0, {
            "time": int(time.time()),
            "action": action,
            "details": str(details)[:300],
        })
        self._set("history", history[:30])

    @staticmethod
    def _esc(value):
        return html.escape(str(value))

    async def _show(self, call, text, buttons):
        await call.edit(text, reply_markup=buttons, parse_mode="html")

    def _main_markup(self):
        return [
            [
                {"text": "🔎 Разобрать реплай", "callback": self._parse_from_menu},
                {"text": "👥 Кандидаты", "callback": self._candidate_page},
            ],
            [
                {"text": "🚫 Чёрный список", "callback": self._blacklist_page},
                {"text": "📝 Шаблоны", "callback": self._templates_page},
            ],
            [
                {"text": "📤 Экспорт", "callback": self._export},
                {"text": "📊 Статистика", "callback": self._stats},
            ],
            [{"text": "🕘 История", "callback": self._history_page}],
        ]

    @loader.command()
    async def bmenu(self, message):
        """Открыть Broadcast Manager."""
        await self.inline.form(
            message=message,
            text=self._dashboard_text(),
            reply_markup=self._main_markup(),
        )

    def _dashboard_text(self):
        candidates = self._candidates()
        blocked = self._blacklist()
        visible = [k for k in candidates if k not in blocked]
        return (
            "<b>📣 Broadcast Manager</b>\n\n"
            f"👤 Найдено аккаунтов: <code>{len(candidates)}</code>\n"
            f"🚫 В чёрном списке: <code>{len(blocked)}</code>\n"
            f"📋 В активном списке: <code>{len(visible)}</code>\n"
            f"📝 Шаблонов: <code>{len(self._templates())}</code>\n\n"
            "<i>Модуль анализирует отчёты и помогает управлять "
            "списком. Автоматическая массовая отправка личных "
            "сообщений найденным незнакомым людям не выполняется.</i>"
        )

    async def _parse_from_menu(self, call):
        await self._show(
            call,
            "<b>🔎 Парсер реплая</b>\n\n"
            "Закрой это меню, ответь командой <code>.bparse</code> "
            "на сообщение с отчётом.\n\n"
            "Будут распознаны @username и ссылки t.me. "
            "Сущности проверяются по типу: User сохраняется, "
            "группы, каналы и боты пропускаются.\n"
            "Числовые ID без разрешаемой сущности будут показаны "
            "как нераспознанные.",
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    async def _back(self, call):
        await self._show(call, self._dashboard_text(), self._main_markup())

    @loader.command()
    async def bparse(self, message):
        """Разобрать реплай: .bparse"""
        reply = await message.get_reply_message()
        if not reply:
            return await utils.answer(message, "Ответь командой .bparse на сообщение с отчётом.")

        source = reply.raw_text or ""
        usernames = set(re.findall(
            r"(?<![\w])@([A-Za-z][A-Za-z0-9_]{4,31})", source
        ))
        usernames.update(re.findall(
            r"(?:https?://)?t\.me/([A-Za-z][A-Za-z0-9_]{4,31})(?![\w])",
            source,
            re.I,
        ))

        # Numeric IDs are collected for the report only. An ID alone does not
        # reliably identify a resolvable Telegram peer.
        numeric_ids = set(re.findall(r"`(\d{5,15})`", source))
        added, skipped, unresolved = 0, 0, 0
        candidates = self._candidates()

        for username in sorted(usernames):
            try:
                entity = await self.client.get_entity("@" + username)
            except Exception:
                unresolved += 1
                continue

            entity_type = entity.__class__.__name__
            if entity_type != "User" or bool(getattr(entity, "bot", False)):
                skipped += 1
                continue

            uid = str(entity.id)
            candidates[uid] = {
                "id": int(entity.id),
                "username": getattr(entity, "username", None) or username,
                "first_name": getattr(entity, "first_name", "") or "",
                "last_name": getattr(entity, "last_name", "") or "",
                "source": "reply-parser",
                "added_at": int(time.time()),
            }
            added += 1

        self._set("candidates", candidates)
        self._save_history("parse", f"added={added}; skipped={skipped}")

        text = (
            "<b>🔎 Результат разбора</b>\n\n"
            f"👤 Добавлено/обновлено пользователей: <code>{added}</code>\n"
            f"⏭ Пропущено групп, каналов и ботов: <code>{skipped}</code>\n"
            f"❔ Не удалось разрешить username: <code>{unresolved}</code>\n"
            f"🔢 Числовых ID найдено в тексте: <code>{len(numeric_ids)}</code>\n\n"
            "Числовые ID не добавлялись автоматически: без доступной "
            "сущности нельзя надёжно отличить пользователя от другого peer."
        )
        await utils.answer(
            message,
            text,
            reply_markup=[[{"text": "📊 Открыть панель", "callback": self._open_menu}]],
        )

    async def _open_menu(self, call):
        await self._show(call, self._dashboard_text(), self._main_markup())

    async def _candidate_page(self, call, page=0):
        items = sorted(
            self._candidates().items(),
            key=lambda item: (item[1].get("username") or str(item[0])).lower()
        )
        blocked = self._blacklist()
        total_pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(int(page), total_pages - 1))
        chunk = items[page * self.PAGE_SIZE:(page + 1) * self.PAGE_SIZE]

        lines = ["<b>👥 Кандидаты</b>\n"]
        if not chunk:
            lines.append("Список пока пуст.")
        for uid, item in chunk:
            username = item.get("username")
            label = "@" + username if username else "без username"
            status = "🚫" if uid in blocked else "•"
            lines.append(f"{status} {self._esc(label)} — <code>{uid}</code>")

        buttons = []
        nav = []
        if page > 0:
            nav.append({"text": "⬅️", "callback": self._candidate_page, "args": [page - 1]})
        nav.append({"text": f"{page + 1}/{total_pages}", "action": "answer"})
        if page + 1 < total_pages:
            nav.append({"text": "➡️", "callback": self._candidate_page, "args": [page + 1]})
        buttons.append(nav)
        buttons.append([
            {"text": "🚫 Добавить ID в ЧС", "callback": self._blacklist_help},
            {"text": "🧹 Очистить список", "callback": self._confirm_clear},
        ])
        buttons.append([{"text": "🔙 В меню", "callback": self._back}])
        await self._show(call, "\n".join(lines), buttons)

    async def _blacklist_help(self, call):
        await self._show(
            call,
            "Чтобы добавить пользователя в чёрный список:\n"
            "<code>.bblock 123456789</code>\n\n"
            "Чтобы убрать:\n<code>.bunblock 123456789</code>",
            [[{"text": "🔙 К кандидатам", "callback": self._candidate_page, "args": [0]}]],
        )

    @loader.command()
    async def bblock(self, message):
        """Добавить ID в чёрный список: .bblock ID"""
        args = utils.get_args_raw(message).strip()
        if not args.isdigit():
            return await utils.answer(message, "Укажи числовой Telegram ID.")
        blocked = self._blacklist()
        blocked.add(args)
        self._set("blacklist", sorted(blocked))
        self._save_history("blacklist-add", args)
        await utils.answer(message, f"🚫 ID <code>{args}</code> добавлен в чёрный список.")

    @loader.command()
    async def bunblock(self, message):
        """Убрать ID из чёрного списка: .bunblock ID"""
        args = utils.get_args_raw(message).strip()
        blocked = self._blacklist()
        blocked.discard(args)
        self._set("blacklist", sorted(blocked))
        self._save_history("blacklist-remove", args)
        await utils.answer(message, f"✅ ID <code>{self._esc(args)}</code> удалён из чёрного списка.")

    async def _blacklist_page(self, call):
        blocked = sorted(self._blacklist())
        body = "\n".join(f"• <code>{self._esc(uid)}</code>" for uid in blocked[:50])
        if not body:
            body = "Чёрный список пуст."
        await self._show(
            call,
            "<b>🚫 Чёрный список</b>\n\n" + body +
            ("\n\n<i>Показаны первые 50 записей.</i>" if len(blocked) > 50 else ""),
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    async def _confirm_clear(self, call):
        await self._show(
            call,
            "<b>⚠️ Очистить весь список кандидатов?</b>",
            [[
                {"text": "Да, очистить", "callback": self._clear_candidates},
                {"text": "Отмена", "callback": self._candidate_page, "args": [0]},
            ]],
        )

    async def _clear_candidates(self, call):
        self._set("candidates", {})
        self._save_history("clear-candidates", "all")
        await self._show(
            call,
            "🧹 Список кандидатов очищен.",
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    async def _export(self, call):
        candidates = self._candidates()
        blocked = self._blacklist()
        rows = []
        for uid, item in sorted(candidates.items()):
            rows.append(
                f"{uid}\t@{item.get('username') or ''}\t"
                f"{'blocked' if uid in blocked else 'candidate'}"
            )
        payload = "\n".join(["id\tusername\tstatus"] + rows)
        await self._show(
            call,
            "<b>📤 Экспорт базы</b>\n\n"
            f"Записей: <code>{len(rows)}</code>\n"
            "Формат: TSV. Нажми кнопку, чтобы получить текст.",
            [[{"text": "Показать экспорт", "callback": self._show_export, "args": [payload]}],
             [{"text": "🔙 В меню", "callback": self._back}]],
        )

    async def _show_export(self, call, payload):
        # Telegram message length guard; export is shown in manageable chunks.
        payload = str(payload)
        await self._show(
            call,
            "<b>📄 Экспорт (TSV)</b>\n<pre>" +
            self._esc(payload[:3500]) +
            "</pre>",
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    async def _stats(self, call):
        candidates = self._candidates()
        blocked = self._blacklist()
        users = len(candidates)
        active = sum(1 for uid in candidates if uid not in blocked)
        await self._show(
            call,
            "<b>📊 Статистика</b>\n\n"
            f"Всего записей: <code>{users}</code>\n"
            f"В чёрном списке: <code>{len(blocked)}</code>\n"
            f"Не заблокировано: <code>{active}</code>\n"
            f"Шаблонов: <code>{len(self._templates())}</code>\n"
            f"Записей истории: <code>{len(self._history())}</code>",
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    async def _templates_page(self, call):
        templates = self._templates()
        lines = ["<b>📝 Шаблоны сообщений</b>\n"]
        if not templates:
            lines.append("Шаблонов пока нет.")
        else:
            for i, item in enumerate(templates[:10], 1):
                lines.append(f"{i}. <b>{self._esc(item.get('name', 'Без названия'))}</b>")
                lines.append(f"<i>{self._esc(item.get('text', '')[:100])}</i>")
        lines.append("\nДобавить: <code>.btemplate Название | Текст</code>")
        lines.append("Удалить: <code>.btemplatedel Номер</code>")
        await self._show(
            call,
            "\n".join(lines),
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    @loader.command()
    async def btemplate(self, message):
        """Сохранить шаблон: .btemplate Название | Текст"""
        raw = utils.get_args_raw(message)
        if "|" not in raw:
            return await utils.answer(message, "Формат: .btemplate Название | Текст")
        name, text = [part.strip() for part in raw.split("|", 1)]
        if not name or not text:
            return await utils.answer(message, "Название и текст не должны быть пустыми.")
        templates = self._templates()
        templates.append({"name": name[:60], "text": text[:3500]})
        self._set("templates", templates[-30:])
        self._save_history("template-add", name)
        await utils.answer(message, "✅ Шаблон сохранён.")

    @loader.command()
    async def btemplatedel(self, message):
        """Удалить шаблон по номеру: .btemplatedel 1"""
        raw = utils.get_args_raw(message).strip()
        if not raw.isdigit():
            return await utils.answer(message, "Укажи номер шаблона.")
        templates = self._templates()
        index = int(raw) - 1
        if index < 0 or index >= len(templates):
            return await utils.answer(message, "Шаблон с таким номером не найден.")
        removed = templates.pop(index)
        self._set("templates", templates)
        self._save_history("template-delete", removed.get("name", ""))
        await utils.answer(message, "🗑 Шаблон удалён.")

    async def _history_page(self, call):
        history = self._history()[:15]
        lines = ["<b>🕘 Последние действия</b>\n"]
        if not history:
            lines.append("История пока пуста.")
        for item in history:
            stamp = time.strftime("%d.%m %H:%M", time.localtime(item.get("time", 0)))
            lines.append(
                f"• <code>{self._esc(stamp)}</code> "
                f"<b>{self._esc(item.get('action', ''))}</b> — "
                f"{self._esc(item.get('details', ''))}"
            )
        await self._show(
            call,
            "\n".join(lines),
            [[{"text": "🔙 В меню", "callback": self._back}]],
        )

    @loader.command()
    async def bstats(self, message):
        """Краткая статистика менеджера."""
        candidates = self._candidates()
        blocked = self._blacklist()
        await utils.answer(
            message,
            "<b>📊 Broadcast Manager</b>\n"
            f"Аккаунтов: <code>{len(candidates)}</code>\n"
            f"Чёрный список: <code>{len(blocked)}</code>\n"
            f"Шаблонов: <code>{len(self._templates())}</code>",
        )
