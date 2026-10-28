__version__ = (3, 3, 0)
# meta banner: https://raw.githubusercontent.com/kamekuro/hikka-mods/main/banners/yamusic.png
# meta developer: @alexsociety
# scope: heroku_only
# scope: heroku_min 2.0.0
# requires: aiohttp pillow>=10.0.0 git+https://github.com/MarshalX/yandex-music-api

import aiohttp
import asyncio
import io
import json
import html
import logging
import random
import string
import typing
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import telethon
import yandex_music
import yandex_music.exceptions

from .. import loader, utils

logger = logging.getLogger(__name__)


class Banners:
    def __init__(
        self,
        title: str,
        artists: list[str],
        duration: int,
        progress: int,
        track_cover: bytes,
        fonts_data: list[bytes],
        album_title: str = "Сингл",
        meta_info: str = "Music",
        is_liked: bool = False,
        repeat_mode: str = "NONE",
        blur: int = 0,
    ):
        self.title = title
        self.artists = artists
        self.duration = max(0, int(duration or 0))
        self.progress = min(self.duration, max(0, int(progress or 0)))
        self.track_cover = track_cover
        self.fonts_data = fonts_data
        self.album_title = album_title
        self.meta_info = meta_info
        self.is_liked = is_liked
        self.repeat_mode = repeat_mode
        self.blur = min(50, max(0, int(blur or 0)))

    def ultra(self) -> io.BytesIO:
        WIDTH, HEIGHT = 2560, 1220

        def get_font(size):
            for font_bytes in self.fonts_data:
                try:
                    return ImageFont.truetype(io.BytesIO(font_bytes), size)
                except Exception:
                    continue
            return ImageFont.load_default()

        try:
            original_cover = Image.open(io.BytesIO(self.track_cover)).convert("RGBA")
        except Exception:
            original_cover = Image.new("RGBA", (1000, 1000), "black")

        dominant_color_img = original_cover.resize((1, 1), Image.Resampling.LANCZOS)
        dominant_color = dominant_color_img.getpixel((0, 0))

        r, g, b, a = dominant_color
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        if brightness < 60:
            r = min(255, r + 60)
            g = min(255, g + 60)
            b = min(255, b + 60)
            dominant_color = (r, g, b, 255)

        background = original_cover.copy()
        bg_w, bg_h = background.size

        target_ratio = WIDTH / HEIGHT
        current_ratio = bg_w / bg_h

        if current_ratio > target_ratio:
            new_w = int(bg_h * target_ratio)
            offset = (bg_w - new_w) // 2
            background = background.crop((offset, 0, offset + new_w, bg_h))
        else:
            new_h = int(bg_w / target_ratio)
            offset = (bg_h - new_h) // 2
            background = background.crop((0, offset, bg_w, offset + new_h))

        background = background.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

        if self.blur > 0:
            background = background.filter(ImageFilter.GaussianBlur(radius=self.blur))

        dark_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 180))
        background = Image.alpha_composite(background, dark_overlay)

        cover_size = 500
        cover_x = (WIDTH - cover_size) // 2
        cover_y = 160

        glow_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw_glow = ImageDraw.Draw(glow_layer)

        glow_rect_size = 620
        g_x = (WIDTH - glow_rect_size) // 2
        g_y = cover_y + (cover_size - glow_rect_size) // 2

        draw_glow.rounded_rectangle(
            (g_x, g_y, g_x + glow_rect_size, g_y + glow_rect_size),
            radius=50,
            fill=dominant_color,
        )

        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=60))
        glow_layer = ImageEnhance.Brightness(glow_layer).enhance(1.4)
        glow_layer = ImageEnhance.Color(glow_layer).enhance(1.2)

        background = Image.alpha_composite(background, glow_layer)

        cover_img = original_cover.resize(
            (cover_size, cover_size), Image.Resampling.LANCZOS
        )

        mask = Image.new("L", (cover_size, cover_size), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle((0, 0, cover_size, cover_size), radius=45, fill=255)

        background.paste(cover_img, (cover_x, cover_y), mask)

        draw = ImageDraw.Draw(background)
        center_x = WIDTH // 2
        current_y = cover_y + cover_size + 130

        def draw_text_shadow(text, pos, font, fill="white", anchor="ms"):
            x, y = pos
            draw.text(
                (x + 2, y + 2), text, font=font, fill=(0, 0, 0, 220), anchor=anchor
            )
            draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

        def fit_text(text, font, max_width):
            text = str(text or "").strip()
            if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
                return text
            suffix = "…"
            while text and draw.textbbox((0, 0), text + suffix, font=font)[2] > max_width:
                text = text[:-1]
            return text.rstrip() + suffix if text else suffix

        font_title = get_font(100)
        title_text = fit_text(self.title.upper(), font_title, WIDTH - 180)
        draw_text_shadow(title_text, (center_x, current_y), font_title)

        current_y += 85

        font_artist = get_font(65)
        artist_text = fit_text(", ".join(self.artists).upper(), font_artist, WIDTH - 220)
        draw_text_shadow(
            artist_text.upper(),
            (center_x, current_y),
            font_artist,
            fill=(255, 255, 255, 240),
        )

        current_y += 80

        bar_width = 800
        font_time = get_font(40)

        bar_start_x = center_x - (bar_width // 2)
        bar_end_x = center_x + (bar_width // 2)
        bar_y = current_y

        total_mins = self.duration // 1000 // 60
        total_secs = (self.duration // 1000) % 60

        total_time_str = f"{total_mins:02d}:{total_secs:02d}"

        cur_mins = self.progress // 1000 // 60
        cur_secs = (self.progress // 1000) % 60
        cur_time_str = f"{cur_mins:02d}:{cur_secs:02d}"

        draw_text_shadow(
            cur_time_str, (bar_start_x - 30, bar_y), font_time, anchor="rm"
        )
        draw_text_shadow(
            total_time_str, (bar_end_x + 30, bar_y), font_time, anchor="lm"
        )

        # A local RNG keeps the waveform deterministic without changing global state.
        rng = random.Random(f"{self.title}\0{self.duration}")

        num_bars = 65
        bar_spacing = bar_width / num_bars
        bar_w = max(4, int(bar_spacing * 0.5))
        max_h = 50
        min_h = 6

        if self.duration > 0:
            progress_ratio = min(1.0, max(0.0, self.progress / self.duration))
        else:
            progress_ratio = 0

        active_bars = int(num_bars * progress_ratio)

        for i in range(num_bars):
            base_h = rng.randint(min_h, max_h)
            edge_factor = 1.0 - abs((i - num_bars / 2) / (num_bars / 2))
            h = int(base_h * 0.4 + max_h * edge_factor * 0.6)
            h = max(min_h, h)

            x_center = bar_start_x + i * bar_spacing
            left = x_center - (bar_w / 2)
            right = x_center + (bar_w / 2)
            top = bar_y - (h / 2)
            bottom = bar_y + (h / 2)

            color = (255, 255, 255, 255) if i < active_bars else (80, 80, 80, 100)

            draw.rounded_rectangle(
                (left, top, right, bottom),
                radius=int(bar_w / 2),
                fill=color,
            )

        current_y += 80

        font_album = get_font(50)
        album_text = fit_text(self.album_title, font_album, WIDTH - 220)
        draw_text_shadow(
            album_text, (center_x, current_y), font_album, fill=(230, 230, 230)
        )
        current_y += 60

        font_meta = get_font(40)

        draw_text_shadow(
            self.meta_info, (center_x, current_y), font_meta, fill=(210, 210, 210)
        )

        icon_y_center = current_y - 15

        if self.repeat_mode != "NONE":
            rep_x = bar_start_x
            rep_size = 18

            draw.arc(
                [
                    rep_x - rep_size,
                    icon_y_center - rep_size,
                    rep_x + rep_size,
                    icon_y_center + rep_size,
                ],
                start=40,
                end=320,
                fill=(220, 220, 220, 255),
                width=3,
            )

            draw.polygon(
                [
                    (rep_x + rep_size - 2, icon_y_center - 8),
                    (rep_x + rep_size + 8, icon_y_center),
                    (rep_x + rep_size - 8, icon_y_center + 4),
                ],
                fill=(220, 220, 220, 255),
            )

            if self.repeat_mode == "ONE":
                font_one = get_font(20)
                draw.text(
                    (rep_x + rep_size + 12, icon_y_center),
                    "1",
                    font=font_one,
                    fill="white",
                    anchor="lm",
                )

        heart_x = bar_end_x
        heart_size = 20

        c_r = heart_size // 2 + 2

        c1_box = (
            heart_x - c_r * 2,
            icon_y_center - c_r - 2,
            heart_x,
            icon_y_center + c_r - 2,
        )
        c2_box = (
            heart_x,
            icon_y_center - c_r - 2,
            heart_x + c_r * 2,
            icon_y_center + c_r - 2,
        )
        tri_points = [
            (heart_x - c_r * 2 + 2, icon_y_center + 1),
            (heart_x + c_r * 2 - 2, icon_y_center + 1),
            (heart_x, icon_y_center + heart_size + 5),
        ]

        if self.is_liked:
            draw.ellipse(c1_box, fill=(255, 80, 120, 255))
            draw.ellipse(c2_box, fill=(255, 80, 120, 255))
            draw.polygon(tri_points, fill=(255, 80, 120, 255))
        else:
            draw.ellipse(c1_box, outline=(220, 220, 220, 255), width=3)
            draw.ellipse(c2_box, outline=(220, 220, 220, 255), width=3)
            draw.line(
                [tri_points[0], tri_points[2], tri_points[1]],
                fill=(220, 220, 220, 255),
                width=3,
            )

        by = io.BytesIO()
        background.save(by, format="PNG")
        by.seek(0)
        by.name = "banner.png"
        return by


@loader.tds
class YaMusicMod(loader.Module):
    """The module for Yandex.Music streaming service"""

    strings = {
        "name": "YaMusic",
        "_cfg_token": "Yandex.Music token",
        "_cfg_now_playing_text": "Now Playing message format",
        "_cfg_autobio_text": "Autobio message format",
        "_cfg_no_playing_bio_text": "Autobio text when nothing is playing",
        "_cfg_banner_version": "Banner version",
        "iguide": "<b>🎵 YaMusic</b>\n\nSet your Yandex.Music token in the module configuration.\nUse <code>.yg</code> to show this guide again.",
        "error_no_token_or_invalid": "❌ Yandex.Music token is missing or invalid.",
        "error_no_query": "❌ Enter a track name.",
        "error_not_found": "❌ Nothing found.",
        "error_no_playing": "❌ Nothing is playing right now.",
        "error_generic": "❌ An error occurred.",
        "search": "<b>🎵 {title}</b>\n👤 {performer}\n🆔 <code>{track_id}</code>",
        "downloading_track": "\n\n⏳ Downloading track...",
        "uploading_banner": "⏳ Generating banner...",
        "autobio_enabled": "✅ Autobio enabled.",
        "autobio_disabled": "❌ Autobio disabled.",
        "like_liked": "❤️ Liked: {track}",
        "like_unliked": "💔 Unliked: {track}",
        "like_disliked": "👎 Disliked: {track}",
        "lyrics": "<b>🎵 {track}</b>\n\n{text}\n\n✍️ Writers: {writers}",
        "no_lyrics": "❌ Lyrics for <b>{track}</b> were not found.",
        "_entity_types": "Playlist: {}",
        "_entity_playlist": "Playlist: {}",
        "_entity_album": "Album: {}",
        "_entity_artist": "Artist: {}",
        "_entity_various": "Various: {}",
        "download_error": "\n\n❌ Download failed: <code>{err}</code>",
    }

    duration_placeholder = {
        "start_duration": "<tg-emoji emoji-id=5262663495538742892>☀️</tg-emoji><tg-emoji emoji-id=5260381609479153468>☀️</tg-emoji>",
        "start_full_duration": "<tg-emoji emoji-id=5262663495538742892>☀️</tg-emoji><tg-emoji emoji-id=5260609582048254485>☀️</tg-emoji>",
        "closed_duration": "<tg-emoji emoji-id=5260467667738859177>☀️</tg-emoji>",
        "empty_mid": "<tg-emoji emoji-id=5260415715814448198>☀️</tg-emoji>",
        "empty_closed_duration_duration": "<tg-emoji emoji-id=5260239235608255208>☀️</tg-emoji>",
        "end_duration_full": "<tg-emoji emoji-id=5260467667738859177>☀️</tg-emoji>",
        "empty_closed_duration": "<tg-emoji emoji-id=5260239235608255208>☀️</tg-emoji>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                option="token",
                default=None,
                doc=lambda: self.strings("_cfg_token"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                option="now_playing_text",
                default=(
                    "<emoji document_id=5474304919651491706>🎧</emoji> <b>{performer} — {title}</b>\n\n"
                    "<emoji document_id=6039404727542747508>⌨️</emoji> <b>Now is listening on <code>"
                    "{device}</code> (<emoji document_id=6039454987250044861>🔊</emoji> {volume}%)</b>\n"
                    "<emoji document_id=6039630677182254664>🗂</emoji> <b>Playing from:</b> {playing_from}"
                    "\n\n<emoji document_id=5242574232688298747>🎵</emoji> <b>{link} | "
                    '<a href="https://song.link/ya/{track_id}">song.link</a></b>'
                ),
                doc=lambda: self.strings("_cfg_now_playing_text"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                option="autobio_text",
                default="{performer} — {title}",
                doc=lambda: self.strings("_cfg_autobio_text"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                option="no_playing_bio_text",
                default="I use Heroku with YaMusic mod btw",
                doc=lambda: self.strings("_cfg_no_playing_bio_text"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                option="banner_version",
                default="ultra",
                doc=lambda: self.strings("_cfg_banner_version"),
                validator=loader.validators.Choice(["ultra"]),
            ),
            loader.ConfigValue(
                option="blur",
                default=0,
            ),
        )

        self.ym_client = None
        self.device_id = "".join(random.choices(string.ascii_lowercase, k=16))

    async def client_ready(self, client, db):
        self._client: telethon.TelegramClient = client
        self._db = db
        self._last_bio = None

        utils.register_placeholder(
            "now_play", self._now_play_placeholder, "placeholder for nowplay music"
        )
        utils.register_placeholder("duration", self._duration_placeholder, "progress bar")

        if not self.get("guide_sent", False):
            await self.inline.bot.send_message(self._tg_id, self.strings("iguide"))
            self.set("guide_sent", True)
        me = await self._client.get_me()
        self._premium = me.premium if hasattr(me, "premium") else False
        if self.get("autobio", False):
            self.autobio.start()

    async def _now_play_placeholder(self):
        """Placeholder for {now_play}"""
        if not self.config["token"]:
            return "No Token"

        try:
            now = await self.__get_now_playing()
            if not now or now.get("paused"):
                return "Not playing"

            title = now["track"]["title"]
            artists = ", ".join(now["track"]["artist"])
            return f"{html.escape(str(title))} — {html.escape(str(artists))}"
        except Exception:
            return "Error"

    async def _get_ym_client(self):
        """Lazy initialization of Yandex Music Client to prevent spamming init"""
        token = (self.config["token"] or "").strip()
        if not token:
            self.ym_client = None
            return None

        if self.ym_client is not None:
            return self.ym_client

        try:
            self.ym_client = await yandex_music.ClientAsync(token).init()
            return self.ym_client
        except Exception:
            self.ym_client = None
            logger.exception("Failed to initialize Yandex Music client")
            return None

    @loader.loop(1800, autostart=True)
    async def premium_check(self):
        try:
            me = await self._client.get_me()
            self._premium = bool(getattr(me, "premium", False))
        except Exception:
            logger.debug("Could not refresh Telegram Premium status", exc_info=True)

    @loader.loop(30)
    async def autobio(self):
        if not self.config["token"]:
            self.autobio.stop()
            self.set("autobio", False)
            return
        try:
            now = await self.__get_now_playing()
            if now and not now.get("paused"):
                out = self.config["autobio_text"].format(
                    title=now["track"]["title"],
                    performer=", ".join(now["track"]["artist"]),
                )
            else:
                out = self.config["no_playing_bio_text"]

            out = out[: (140 if self._premium else 70)]
            if out == self._last_bio:
                return

            await self._client(
                telethon.functions.account.UpdateProfileRequest(about=out)
            )
            self._last_bio = out
        except telethon.errors.rpcerrorlist.FloodWaitError as e:
            wait_seconds = max(int(e.seconds), 60)
            logger.info("Autobio rate-limited; sleeping for %s seconds", wait_seconds)
            await asyncio.sleep(wait_seconds)
        except Exception:
            logger.exception("Autobio update failed")

    @loader.command(ru_doc="👉 Гайд по получению токена Яндекс.Музыки", alias="yg")
    async def yguidecmd(self, message: telethon.types.Message):
        """👉 Guide for obtaining a Yandex.Music token"""
        await utils.answer(message, self.strings("iguide"))

    @loader.command(ru_doc="👉 Включить/выключить автобио", alias="yb")
    async def ybiocmd(self, message: telethon.types.Message):
        """👉 Enable/disable autobio"""
        client = await self._get_ym_client()
        if not client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        bio = not self.get("autobio", False)
        self.set("autobio", bio)
        if bio:
            await self.autobio.func(self)
            self.autobio.start()
        else:
            self.autobio.stop()
            try:
                await self._client(
                    telethon.functions.account.UpdateProfileRequest(
                        about=self.config["no_playing_bio_text"][
                            : (140 if self._premium else 70)
                        ]
                    )
                )
            except Exception:
                pass

        bio = self.get("autobio", False)
        await utils.answer(
            message, self.strings("autobio_enabled" if bio else "autobio_disabled")
        )

    @loader.command(ru_doc="👉 Поиск треков в Яндекс.Музыке", alias="yq")
    async def ysearchcmd(self, message: telethon.types.Message):
        """👉 Searching tracks in Yandex.Music"""
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        query = utils.get_args_raw(message)
        if not query:
            return await utils.answer(message, self.strings("error_no_query"))

        try:
            search = await ym_client.search(query, type_="track")
        except Exception:
            logger.warning("Yandex Music search failed; reinitializing client", exc_info=True)
            self.ym_client = None
            ym_client = await self._get_ym_client()
            if not ym_client:
                return await utils.answer(message, self.strings("error_no_token_or_invalid"))
            try:
                search = await ym_client.search(query, type_="track")
            except Exception:
                logger.exception("Yandex Music search retry failed")
                return await utils.answer(message, self.strings("error_generic"))

        if not search.tracks or not search.tracks.results:
            return await utils.answer(message, self.strings("error_not_found"))

        track = search.tracks.results[0]
        out = self.strings("search").format(
            title=html.escape(str(track.title or "Unknown track")),
            performer=html.escape(", ".join(track.artists_name() or [])),
            track_id=track.track_id,
        )
        await utils.answer(message, out + self.strings("downloading_track"))

        try:
            audio = await self.__download_track(ym_client, track.id)
        except Exception as e:
            logger.error(f"Search download failed: {e}")
            return await utils.answer(
                message,
                out + self.strings("download_error").format(err=html.escape(str(e)[:250])),
            )

        await utils.answer(
            message=message,
            response=out,
            file=audio,
            attributes=(
                [
                    telethon.types.DocumentAttributeAudio(
                        duration=int(track.duration_ms / 1000),
                        title=track.title,
                        performer=", ".join([x.name for x in track.artists]),
                    )
                ]
            ),
        )

    async def _duration_placeholder(self):
        """Placeholder for {duration} with custom emoji bar"""
        if not self.config["token"]:
            return "No Token"

        try:
            now = await self.__get_now_playing()
            if not now or now.get("paused"):
                return "<code>Not Playing</code>"

            duration = now.get("duration_ms", 0)
            progress = now.get("progress_ms", 0)

            if duration == 0:
                return "0%"

            percent = (progress / duration) * 100
            fill_logic = int(percent // 16.66)

            bar = (
                self.duration_placeholder["start_full_duration"]
                if fill_logic >= 1
                else self.duration_placeholder["start_duration"]
            )
            for i in range(2, 6):
                if fill_logic >= i:
                    bar += self.duration_placeholder["closed_duration"]
                else:
                    bar += self.duration_placeholder["empty_mid"]
            if fill_logic >= 6:
                bar += self.duration_placeholder["end_duration_full"]
            else:
                bar += self.duration_placeholder["empty_closed_duration"]
            return bar
        except Exception:
            logger.debug("Duration placeholder failed", exc_info=True)
            return "<code>Unavailable</code>"

    async def _download_bytes(
        self, url: str, timeout: int = 10
    ) -> typing.Optional[bytes]:
        if not url or not url.startswith(("https://", "http://")):
            logger.warning("Refusing invalid download URL")
            return None

        max_bytes = 25 * 1024 * 1024
        client_timeout = aiohttp.ClientTimeout(total=max(1, int(timeout)))
        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 YaMusicMod/3.3"},
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        logger.warning("Download returned HTTP %s for %s", resp.status, url[:100])
                        return None
                    if resp.content_length and resp.content_length > max_bytes:
                        logger.warning("Refusing oversized download (%s bytes)", resp.content_length)
                        return None
                    data = await resp.content.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        logger.warning("Refusing oversized response body")
                        return None
                    return data
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            logger.warning("Download failed for %s", url[:100], exc_info=True)
        except Exception:
            logger.exception("Unexpected download failure for %s", url[:100])
        return None

    @loader.command(
        ru_doc="👉 Получить баннер трека, который играет сейчас", alias="yn"
    )
    async def ynowcmd(self, message: telethon.types.Message):
        """👉 Get the banner of the track playing right now"""

        await utils.answer(message, self.strings("uploading_banner"))
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        now = await self.__get_now_playing()

        if not now or now.get("paused"):
            return await utils.answer(message, self.strings("error_no_playing"))

        try:
            track_object = (await ym_client.tracks(now["playable_id"]))[0]
        except Exception:
            return await utils.answer(message, self.strings("error_generic"))

        try:
            match now["entity_type"]:
                case "PLAYLIST":
                    playlist = (await ym_client.playlists_list(now["entity_id"]))[0]
                    playlist_name = (
                        f'<b><a href ="https://music.yandex.ru/users/'
                        f"{playlist.owner.login}/playlists/{playlist.kind}"
                        f'">{html.escape(str(playlist.title))}</a></b>'
                    )
                case "ALBUM":
                    album = (await ym_client.albums(now["entity_id"]))[0]
                    playlist_name = (
                        f'<b><a href ="https://music.yandex.ru/album/'
                        f'{album.id}">{html.escape(str(album.title))}</a></b>'
                    )
                case "ARTIST":
                    artist = (await ym_client.artists(now["entity_id"]))[0]
                    playlist_name = (
                        f'<b><a href ="https://music.yandex.ru/artist/'
                        f'{artist.id}">{html.escape(str(artist.name))}</a></b>'
                    )
                case _:
                    playlist_name = "Unknown"
        except Exception:
            playlist_name = "Unknown"

        if now["entity_type"] not in {"PLAYLIST", "ALBUM", "ARTIST", "VARIOUS"}:
            now["entity_type"] = "VARIOUS"

        device, volume = "Unknown Device", "❔"
        if now["device"]:
            device = now["device"][0]["info"]["title"]
            volume = round(now["device"][0]["volume"] * 100, 2)
        out = self.config["now_playing_text"].format(
            performer=html.escape(", ".join(now["track"]["artist"])),
            title=html.escape(str(now["track"]["title"])),
            device=html.escape(str(device)),
            volume=volume,
            track_id=now["track"]["track_id"],
            album_id=now["track"]["album_id"],
            playing_from={
                "PLAYLIST": self.strings("_entity_playlist"),
                "ALBUM": self.strings("_entity_album"),
                "ARTIST": self.strings("_entity_artist"),
                "VARIOUS": self.strings("_entity_various"),
            }
            .get(now["entity_type"], self.strings("_entity_various"))
            .format(playlist_name),
            link=f"<a href=\"https://music.yandex.ru/track/{now['playable_id']}\">Яндекс.Музыка</a>",
        )

        album_obj = track_object.albums[0] if track_object.albums else None

        album_title = album_obj.title if album_obj else "Сингл"
        year = str(album_obj.year) if album_obj and album_obj.year else ""
        genre_raw = album_obj.genre if album_obj and album_obj.genre else "music"

        genre_map = {
            "rusrap": "Русский рэп",
            "pop": "Поп",
            "rock": "Рок",
            "alternative": "Альтернатива",
            "electronics": "Электроника",
            "hip-hop": "Хип-хоп",
            "rap": "Рэп",
            "rnb": "R&B",
            "metal": "Метал",
            "indie": "Инди",
            "folk": "Фолк",
            "soundtrack": "Саундтрек",
        }
        genre = genre_map.get(genre_raw, genre_raw.capitalize())
        meta_info = f"{year} • {genre}" if year else genre

        is_liked = False
        if hasattr(track_object, "users_likes") and track_object.users_likes:
            is_liked = True

        repeat_mode = now.get("repeat_mode", "NONE")

        cover_uri = getattr(track_object, "cover_uri", None)
        cover_url = (
            "https://" + cover_uri.replace("%%", "1000x1000")
            if cover_uri
            else None
        )
        cover_bytes = await self._download_bytes(cover_url) if cover_url else None
        if not cover_bytes:
            # Banners has a safe fallback cover for failed image downloads.
            cover_bytes = b""

        font_urls = [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Bold.ttf",
            "https://raw.githubusercontent.com/kamekuro/assets/master/fonts/Onest-Bold.ttf",
        ]
        fonts_data = []
        for f_url in font_urls:
            fb = await self._download_bytes(f_url)
            if fb:
                fonts_data.append(fb)

        banners = Banners(
            title=now["track"]["title"],
            artists=now["track"]["artist"],
            duration=now["duration_ms"],
            progress=now["progress_ms"],
            track_cover=cover_bytes,
            fonts_data=fonts_data,
            album_title=album_title,
            meta_info=meta_info,
            is_liked=is_liked,
            repeat_mode=repeat_mode,
            blur=self.config["blur"],
        )

        file = await utils.run_sync(
            getattr(banners, self.config["banner_version"], banners.ultra)
        )
        await utils.answer(message=message, response=out, file=file)

    @loader.command(ru_doc="👉 Получить трек, который играет сейчас", alias="ynt")
    async def ynowtcmd(self, message: telethon.types.Message):
        """👉 Get the track playing right now"""
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        await utils.answer(message, self.strings("downloading_track"))
        now = await self.__get_now_playing()

        if not now or now.get("paused"):
            return await utils.answer(message, self.strings("error_no_playing"))

        try:
            match now["entity_type"]:
                case "PLAYLIST":
                    playlist = (await ym_client.playlists_list(now["entity_id"]))[0]
                    playlist_name = (
                        f'<b><a href ="https://music.yandex.ru/users/'
                        f"{playlist.owner.login}/playlists/{playlist.kind}"
                        f'">{html.escape(str(playlist.title))}</a></b>'
                    )
                case "ALBUM":
                    album = (await ym_client.albums(now["entity_id"]))[0]
                    playlist_name = (
                        f'<b><a href ="https://music.yandex.ru/album/'
                        f'{album.id}">{html.escape(str(album.title))}</a></b>'
                    )
                case "ARTIST":
                    artist = (await ym_client.artists(now["entity_id"]))[0]
                    playlist_name = (
                        f'<b><a href ="https://music.yandex.ru/artist/'
                        f'{artist.id}">{html.escape(str(artist.name))}</a></b>'
                    )
                case _:
                    playlist_name = "Unknown"
        except Exception:
            playlist_name = "Unknown"

        if now["entity_type"] not in {"PLAYLIST", "ALBUM", "ARTIST", "VARIOUS"}:
            now["entity_type"] = "VARIOUS"

        device, volume = "Unknown Device", "❔"
        if now["device"]:
            device = now["device"][0]["info"]["title"]
            volume = round(now["device"][0]["volume"] * 100, 2)
        out = self.config["now_playing_text"].format(
            performer=html.escape(", ".join(now["track"]["artist"])),
            title=html.escape(str(now["track"]["title"])),
            device=html.escape(str(device)),
            volume=volume,
            track_id=now["track"]["track_id"],
            album_id=now["track"]["album_id"],
            playing_from={
                "PLAYLIST": self.strings("_entity_playlist"),
                "ALBUM": self.strings("_entity_album"),
                "ARTIST": self.strings("_entity_artist"),
                "VARIOUS": self.strings("_entity_various"),
            }
            .get(now["entity_type"], self.strings("_entity_various"))
            .format(playlist_name),
            link=f"<a href=\"https://music.yandex.ru/track/{now['playable_id']}\">Яндекс.Музыка</a>",
        )

        try:
            audio = await self.__download_track(
                ym_client, now["track"]["track_id"]
            )
        except Exception as e:
            logger.error(f"Now playing download failed: {e}")
            return await utils.answer(
                message,
                out + self.strings("download_error").format(err=html.escape(str(e)[:250])),
            )

        await utils.answer(
            message=message,
            response=out,
            file=audio,
            attributes=(
                [
                    telethon.types.DocumentAttributeAudio(
                        duration=int(now["duration_ms"] / 1000),
                        title=now["track"]["title"],
                        performer=", ".join(now["track"]["artist"]),
                    )
                ]
            ),
        )

    @loader.command(ru_doc="👉 Лайкнуть играющий сейчас трек")
    async def ylikecmd(self, message: telethon.types.Message):
        """👉 Like the track playing right now"""
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        now = await self.__get_now_playing()

        if not now or now.get("paused"):
            return await utils.answer(message, self.strings("error_no_playing"))

        await ym_client.users_likes_tracks_add(now["track"]["track_id"])
        await utils.answer(
            message,
            self.strings("like_liked").format(
                track_id=now["track"]["track_id"],
                track=html.escape(f"{', '.join(now['track']['artist'])} — {now['track']['title']}"),
            ),
        )

    @loader.command(ru_doc="👉 Снять лайк с играющего сейчас трека")
    async def yunlikecmd(self, message: telethon.types.Message):
        """👉 Unlike the track playing right now"""
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        now = await self.__get_now_playing()

        if not now or now.get("paused"):
            return await utils.answer(message, self.strings("error_no_playing"))

        await ym_client.users_likes_tracks_remove(now["track"]["track_id"])
        await utils.answer(
            message,
            self.strings("like_unliked").format(
                track_id=now["track"]["track_id"],
                track=html.escape(f"{', '.join(now['track']['artist'])} — {now['track']['title']}"),
            ),
        )

    @loader.command(ru_doc="👉 Дизлайкнуть играющий сейчас трек")
    async def ydislikecmd(self, message: telethon.types.Message):
        """👉 Dislike the track playing right now"""
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        now = await self.__get_now_playing()

        if not now or now.get("paused"):
            return await utils.answer(message, self.strings("error_no_playing"))

        await ym_client.users_dislikes_tracks_add(now["track"]["track_id"])
        await utils.answer(
            message,
            self.strings("like_disliked").format(
                track_id=now["track"]["track_id"],
                track=html.escape(f"{', '.join(now['track']['artist'])} — {now['track']['title']}"),
            ),
        )

    @loader.command(ru_doc="👉 Получить текст играющего сейчас трека")
    async def ylyricscmd(self, message: telethon.types.Message):
        """👉 Get the lyrics of the track playing right now"""
        ym_client = await self._get_ym_client()
        if not ym_client:
            return await utils.answer(
                message, self.strings("error_no_token_or_invalid")
            )

        now = await self.__get_now_playing()

        if not now or now.get("paused"):
            return await utils.answer(message, self.strings("error_no_playing"))

        try:
            lyrics = await ym_client.tracks_lyrics(now["track"]["track_id"])

            lyrics_text = "Error"
            download_url = lyrics.download_url
            if download_url:
                lyrics_bytes = await self._download_bytes(download_url)
                if lyrics_bytes:
                    lyrics_text = lyrics_bytes.decode("utf-8")

            await utils.answer(
                message,
                self.strings("lyrics").format(
                    track_id=now["track"]["track_id"],
                    track=html.escape(f"{', '.join(now['track']['artist'])} — {now['track']['title']}"),
                    text=html.escape(lyrics_text),
                    writers=html.escape(", ".join(lyrics.writers) if lyrics.writers else "Unknown"),
                ),
            )
        except yandex_music.exceptions.NotFoundError:
            await utils.answer(
                message,
                self.strings("no_lyrics").format(
                    track_id=now["track"]["track_id"],
                    track=html.escape(f"{', '.join(now['track']['artist'])} — {now['track']['title']}"),
                ),
            )
        except Exception:
            logger.exception("Could not retrieve track lyrics")
            await utils.answer(message, self.strings("error_generic"))

    async def __download_track(
        self,
        client: yandex_music.ClientAsync,
        track_id: typing.Union[int, str],
        link_only: bool = False,
    ):
        last_exception: typing.Optional[Exception] = None

        for attempt in range(5):
            try:
                info = await client.tracks_download_info(
                    track_id, get_direct_links=True
                )
                if not info:
                    raise Exception("Yandex API returned empty download_info")

                if link_only:
                    return info[0].direct_link

                direct_link = info[0].direct_link
                data: typing.Optional[bytes] = None

                try:
                    result = await info[0].download_bytes_async()
                    if isinstance(result, (bytes, bytearray)):
                        data = bytes(result)
                except TypeError:
                    try:
                        result = await info[0].download_bytes_async(client)
                        if isinstance(result, (bytes, bytearray)):
                            data = bytes(result)
                    except Exception as e:
                        logger.warning(f"download_bytes_async(client) failed: {e}")
                except Exception as e:
                    logger.warning(f"download_bytes_async failed: {e}")

                if not data and direct_link:
                    data = await self._download_bytes(direct_link, timeout=60)

                if not data:
                    raise Exception("Received empty audio data")

                by = io.BytesIO(data)
                by.name = "audio.mp3"
                return by

            except Exception as e:
                last_exception = e
                logger.error(
                    f"__download_track attempt {attempt + 1}/5 for {track_id} failed: {e}"
                )
                if attempt != 4:
                    await asyncio.sleep(2)

        raise last_exception or Exception("Unknown download error")

    async def __get_ynison(self):
        token = (self.config["token"] or "").strip()
        if not token:
            return {}

        timeout = aiohttp.ClientTimeout(total=15, connect=7, sock_read=10)
        ws_proto = {
            "Ynison-Device-Id": self.device_id,
            "Ynison-Device-Info": json.dumps({"app_name": "Chrome", "type": 1}),
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.ws_connect(
                    "wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison",
                    headers={
                        "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                        "Origin": "http://music.yandex.ru",
                        "Authorization": f"OAuth {token}",
                    },
                    heartbeat=20,
                ) as ws:
                    response = await asyncio.wait_for(ws.receive(), timeout=10)
                    if response.type != aiohttp.WSMsgType.TEXT:
                        logger.warning("Ynison redirect returned WebSocket type %s", response.type)
                        return {}
                    data = json.loads(response.data)

                host = data.get("host")
                redirect_ticket = data.get("redirect_ticket")
                if not host or not redirect_ticket:
                    logger.warning("Ynison redirect response is incomplete")
                    return {}

                ws_proto["Ynison-Redirect-Ticket"] = redirect_ticket
                payload = {
                    "update_full_state": {
                        "player_state": {
                            "player_queue": {
                                "current_playable_index": -1,
                                "entity_id": "",
                                "entity_type": "VARIOUS",
                                "playable_list": [],
                                "options": {"repeat_mode": "NONE"},
                                "entity_context": "BASED_ON_ENTITY_BY_DEFAULT",
                                "version": {"device_id": self.device_id, "version": 9021243204784341000, "timestamp_ms": 0},
                                "from_optional": "",
                            },
                            "status": {
                                "duration_ms": 0,
                                "paused": True,
                                "playback_speed": 1,
                                "progress_ms": 0,
                                "version": {"device_id": self.device_id, "version": 8321822175199937000, "timestamp_ms": 0},
                            },
                        },
                        "device": {
                            "capabilities": {"can_be_player": True, "can_be_remote_controller": False, "volume_granularity": 16},
                            "info": {"device_id": self.device_id, "type": "WEB", "title": "Chrome Browser", "app_name": "Chrome"},
                            "volume_info": {"volume": 0},
                            "is_shadow": True,
                        },
                        "is_currently_active": False,
                    },
                    "rid": f"{self.device_id}-{random.getrandbits(64):016x}",
                    "player_action_timestamp_ms": 0,
                    "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
                }

                async with session.ws_connect(
                    f"wss://{host}/ynison_state.YnisonStateService/PutYnisonState",
                    headers={
                        "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                        "Origin": "http://music.yandex.ru",
                        "Authorization": f"OAuth {token}",
                    },
                    heartbeat=20,
                ) as ws:
                    await ws.send_str(json.dumps(payload))
                    response = await asyncio.wait_for(ws.receive(), timeout=10)
                    if response.type != aiohttp.WSMsgType.TEXT:
                        logger.warning("Ynison state returned WebSocket type %s", response.type)
                        return {}
                    result = json.loads(response.data)
                    return result if isinstance(result, dict) else {}
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Ynison request failed", exc_info=True)
        except Exception:
            logger.exception("Unexpected Ynison error")
        return {}

    async def __get_now_playing(self):
        ym_client = await self._get_ym_client()
        if not ym_client:
            return {}

        ynison = await self.__get_ynison()
        if not ynison or (
            len(
                ynison.get("player_state", {})
                .get("player_queue", {})
                .get("playable_list", [])
            )
            == 0
        ):
            return {}

        try:
            player_state = ynison["player_state"]
            queue = player_state.get("player_queue", {})
            playable_list = queue.get("playable_list") or []
            index = int(queue.get("current_playable_index", -1))
            if index < 0 or index >= len(playable_list):
                return {}
            raw_track = playable_list[index]
            if raw_track.get("playable_type") == "LOCAL_TRACK":
                return {}

            tracks = await ym_client.tracks(raw_track["playable_id"])
            if not tracks:
                return {}
            track_object = tracks[0]

            status = player_state["status"]
            progress_ms = int(status["progress_ms"])
            duration_ms = int(status["duration_ms"])

            repeat_mode = (
                player_state.get("player_queue", {})
                .get("options", {})
                .get("repeat_mode", "NONE")
            )

            return (
                {
                    "track_object": track_object,
                    "paused": status["paused"],
                    "playable_id": raw_track["playable_id"],
                    "duration_ms": duration_ms,
                    "progress_ms": progress_ms,
                    "entity_id": queue.get("entity_id", ""),
                    "entity_type": queue.get("entity_type", "VARIOUS"),
                    "repeat_mode": repeat_mode,
                    "device": [
                        x
                        for x in ynison.get("devices", [])
                        if x["info"]["device_id"]
                        == ynison.get("active_device_id_optional", "")
                    ],
                    "track": {
                        "track_id": track_object.track_id,
                        "album_id": track_object.albums[0].id
                        if track_object.albums
                        else 0,
                        "title": track_object.title,
                        "artist": track_object.artists_name(),
                        "duration": track_object.duration_ms // 1000,
                        "minutes": round(track_object.duration_ms / 1000) // 60,
                        "seconds": round(track_object.duration_ms / 1000) % 60,
                    },
                }
            )
        except Exception as e:
            logger.error(f"Get Now Playing Error: {e}")
            return {}
