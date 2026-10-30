
import aiohttp
import asyncio
import html

from heroku import loader, utils


@loader.tds
class LyricsMod(loader.Module):
    """Lyrics | Developer: @alexsociety"""

    strings = {
        "name": "Lyrics | @alexsociety"
    }

    DEVELOPER = "@alexsociety"
    API = "https://lrclib.net/api/search"

    def __init__(self):
        self.results = []
        self.query = ""

    def esc(self, text):
        return html.escape(str(text or ""))

    async def search(self, query):
        headers = {
            "User-Agent": "Lyrics-Heroku-Module/2.0 (@alexsociety)"
        }

        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=timeout
        ) as session:
            async with session.get(
                self.API,
                params={"q": query}
            ) as response:

                if response.status != 200:
                    raise RuntimeError(
                        f"Ошибка API: {response.status}"
                    )

                data = await response.json(
                    content_type=None
                )

                return data if isinstance(data, list) else []

    def render(self, index):
        item = self.results[index]

        title = item.get("trackName") or "Unknown"
        artist = item.get("artistName") or "Unknown"
        album = item.get("albumName") or "Unknown"
        duration = item.get("duration")

        lyrics = (
            item.get("plainLyrics")
            or item.get("syncedLyrics")
            or ""
        )

        preview = " ".join(lyrics.split())[:90]

        if len(lyrics) > 90:
            preview += "..."

        if not preview:
            preview = "Текст недоступен."

        duration_text = ""
        if isinstance(duration, (int, float)):
            duration_text = (
                f"\n⏱ Длительность: "
                f"<code>{int(duration // 60):02d}:"
                f"{int(duration % 60):02d}</code>"
            )

        record_id = item.get("id")

        source = (
            f"https://lrclib.net/api/get/{record_id}"
            if isinstance(record_id, int)
            else "https://lrclib.net/"
        )

        return (
            "<b>🎵 LYRICS</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            f"🎧 <b>{self.esc(title)}</b>\n"
            f"👤 Исполнитель: {self.esc(artist)}\n"
            f"💿 Альбом: {self.esc(album)}"
            f"{duration_text}\n\n"
            f"📝 <b>Фрагмент текста:</b>\n"
            f"{self.esc(preview)}\n\n"
            f"🔗 <a href='{source}'>Открыть источник</a>\n\n"
            f"📄 Результат: {index + 1}/{len(self.results)}\n"
            "━━━━━━━━━━━━━━\n"
            f"👨‍💻 Разработчик: <b>{self.DEVELOPER}</b>"
        )

    def buttons(self, index):
        navigation = []

        if index > 0:
            navigation.append({
                "text": "⬅️ Назад",
                "callback": self.navigate,
                "args": [index - 1]
            })

        if index + 1 < len(self.results):
            navigation.append({
                "text": "Далее ➡️",
                "callback": self.navigate,
                "args": [index + 1]
            })

        result = []

        if navigation:
            result.append(navigation)

        result.append([
            {
                "text": "🔎 Новый поиск",
                "callback": self.new_search
            }
        ])

        result.append([
            {
                "text": "❌ Закрыть",
                "action": "close"
            }
        ])

        return result

    @loader.command()
    async def lyrics(self, message):
        """Поиск песни: .lyrics исполнитель - название"""

        query = utils.get_args_raw(message).strip()

        if not query:
            return await utils.answer(
                message,
                "<b>🎵 Lyrics</b>\n\n"
                "Использование:\n"
                "<code>.lyrics название</code>\n"
                "<code>.lyrics исполнитель - название</code>\n\n"
                f"👨‍💻 Разработчик: <b>{self.DEVELOPER}</b>"
            )

        try:
            self.results = await self.search(query)
            self.query = query

        except asyncio.TimeoutError:
            return await utils.answer(
                message,
                "⌛ Время ожидания поиска истекло."
            )

        except Exception as error:
            return await utils.answer(
                message,
                f"❌ Ошибка: {self.esc(error)}"
            )

        if not self.results:
            return await utils.answer(
                message,
                "😔 Ничего не найдено.\n"
                f"👨‍💻 Разработчик: {self.DEVELOPER}"
            )

        self.results = self.results[:20]

        await self.inline.form(
            message=message,
            text=self.render(0),
            reply_markup=self.buttons(0)
        )

    async def navigate(self, call, index):
        if not self.results:
            return await call.edit(
                "Результаты устарели. Выполни поиск заново."
            )

        index = max(
            0,
            min(index, len(self.results) - 1)
        )

        await call.edit(
            self.render(index),
            reply_markup=self.buttons(index),
            parse_mode="html"
        )

    async def new_search(self, call):
        await call.edit(
            "<b>🎵 LYRICS</b>\n\n"
            "Выполни команду:\n"
            "<code>.lyrics название песни</code>\n\n"
            f"👨‍💻 Разработчик: <b>{self.DEVELOPER}</b>",
            reply_markup=[
                [
                    {
                        "text": "❌ Закрыть",
                        "action": "close"
                    }
                ]
            ]
        )
