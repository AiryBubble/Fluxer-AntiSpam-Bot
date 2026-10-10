import asyncio
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import fluxer
import tomllib
from dotenv import load_dotenv
from safetext import SafeText

from url_checker import check_url_with_filter, ensure_filter_updated

load_dotenv()

TOKEN = os.getenv("FLUXER_BOT_TOKEN")
PREFIX = "nn."
BAN_THRESHOLD = 3
VIOLATION_RESET_TIME = 3600
BAN_MESSAGE_DELETE_DAYS = 1
RAID_JOIN_THRESHOLD = 5
RAID_JOIN_WINDOW_SECONDS = 10
RAID_NEW_ACCOUNT_MINUTES = 10
RAID_MODE_DURATION_MINUTES = 15

WHITELIST_FILE = "invite_whitelist.toml"
MODLOG_FILE = "mod_log.toml"
PROFANITY_DISABLED_FILE = "profanity_disabled.toml"
SHORTLINK_DOMAINS_FILE = "shortlink_domains.txt"
VERIFY_CONFIG_FILE = "verify_config.toml"

intents = fluxer.Intents.all()
bot = fluxer.Bot(command_prefix=PREFIX, intents=intents)
profanity_filters = (SafeText(language="ja"), SafeText(language="en"))
invite_whitelist_channels: dict[int, set[int]] = defaultdict(set)
profanity_disabled_guilds: set[int] = set()
violation_tracker: dict[int, dict[int, dict]] = defaultdict(dict)
recent_messages: dict[tuple[int, int], list[tuple[str, datetime]]] = defaultdict(list)
recent_message_times: dict[tuple[int, int], list[datetime]] = defaultdict(list)
recent_joins: dict[int, list[datetime]] = defaultdict(list)
raid_modes: dict[int, dict] = {}
verify_configs: dict[str, dict] = {}
channel_guild_cache: dict[int, int] = {}
shortlink_domains: set[str] = set()
state_lock = asyncio.Lock()
raid_lock = asyncio.Lock()

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{23,40}\.[A-Za-z0-9_-]{5,10}\.[A-Za-z0-9_-]{20,45}")
INVITE_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:fluxer\.gg|fluxer(?:app)?\.com/invite|fluxer\.io|fluxer\.me|fluxer\.li|dsc\.gg)/[A-Za-z0-9_-]+",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>]+|(?<![@\w])(?:[\w-]+\.)+[a-zA-Z]{2,}(?:/[^\s<>]*)?")
SHORTENER_PREFIXES = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "shorturl.at")

def _load_toml(path: str) -> dict:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "rb") as file:
            return tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"{path} の読み込みに失敗しました: {exc}")
        return {}

def _save_toml(path: str, data: dict) -> None:
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        def quote(value: str) -> str:
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

        def emit_table(table: dict, prefix: tuple[str, ...] = ()) -> None:
            if prefix:
                file.write("[" + ".".join(quote(part) for part in prefix) + "]\n")
            nested = []
            for key, value in table.items():
                if isinstance(value, dict):
                    nested.append((str(key), value))
                elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
                    encoded = ", ".join(quote(item) if isinstance(item, str) else str(item).lower() if isinstance(item, bool) else str(item) for item in value)
                    file.write(f"{quote(str(key))} = [{encoded}]\n")
                elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    encoded_items = []
                    for item in value:
                        fields = []
                        for item_key, item_value in item.items():
                            if isinstance(item_value, str):
                                rendered = quote(item_value)
                            elif isinstance(item_value, bool):
                                rendered = str(item_value).lower()
                            elif isinstance(item_value, (int, float)):
                                rendered = str(item_value)
                            else:
                                continue
                            fields.append(f"{quote(str(item_key))} = {rendered}")
                        encoded_items.append("{" + ", ".join(fields) + "}")
                    file.write(f"{quote(str(key))} = [{', '.join(encoded_items)}]\n")
                elif isinstance(value, str):
                    file.write(f"{quote(str(key))} = {quote(value)}\n")
                elif isinstance(value, (int, float, bool)):
                    file.write(f"{quote(str(key))} = {str(value).lower() if isinstance(value, bool) else value}\n")
            for key, value in nested:
                file.write("\n")
                emit_table(value, (*prefix, key))

        emit_table(data)
    os.replace(temporary, path)

def load_state() -> None:
    for guild_id, channel_ids in _load_toml(WHITELIST_FILE).items():
        invite_whitelist_channels[int(guild_id)] = {int(channel_id) for channel_id in channel_ids}
    disabled = _load_toml(PROFANITY_DISABLED_FILE).get("disabled_guilds", [])
    profanity_disabled_guilds.update(int(guild_id) for guild_id in disabled)
    verify_configs.update(_load_toml(VERIFY_CONFIG_FILE))
    for guild_id, users in _load_toml(MODLOG_FILE).items():
        for user_id, data in users.items():
            if data.get("status") != "banned":
                violation_tracker[int(guild_id)][int(user_id)] = data
    try:
        with open(SHORTLINK_DOMAINS_FILE, encoding="utf-8") as file:
            shortlink_domains.update(
                line.split("#", 1)[0].strip().lower().rstrip(".")
                for line in file if line.split("#", 1)[0].strip()
            )
    except OSError:
        pass

def save_whitelist() -> None:
    _save_toml(WHITELIST_FILE, {str(guild): sorted(channels) for guild, channels in invite_whitelist_channels.items()})

def save_profanity_settings() -> None:
    _save_toml(PROFANITY_DISABLED_FILE, {"disabled_guilds": sorted(profanity_disabled_guilds)})

def save_modlog() -> None:
    _save_toml(MODLOG_FILE, {
        str(guild_id): {str(user_id): info for user_id, info in users.items()}
        for guild_id, users in violation_tracker.items() if users
    })

async def member_is_admin(guild: fluxer.Guild, user_id: int) -> bool:

    if user_id == guild.owner_id:
        return True
    try:
        member = await guild.fetch_member(user_id)
        roles = await guild.fetch_roles()
    except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError) as exc:
        print(f"管理者ロール確認に失敗しました (guild={guild.id}, user={user_id}): {exc}")
        return False
    member_role_ids = {int(role_id) for role_id in member.roles}
    administrator = int(fluxer.Permissions.ADMINISTRATOR)
    return any(
        int(role.id) in member_role_ids and (int(role.permissions) & administrator) == administrator
        for role in roles
    )

async def require_admin(ctx) -> bool:
    try:
        guild = await cached_guild_for_message(ctx)
    except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError) as exc:
        print(f"コマンド実行サーバーの取得に失敗しました: {exc}")
        guild = None
    if guild is None:
        await ctx.reply("このコマンドはサーバー内でのみ使用できます。")
        return False
    if not await member_is_admin(guild, ctx.author.id):
        await ctx.reply("このコマンドには管理者権限が必要です。メンバー権限と各ロールの管理者権限を確認しましたが、許可されませんでした。")
        return False
    return True

async def can_moderate(guild: fluxer.Guild, user_id: int, permission_name: str) -> bool:
    try:
        member = await guild.fetch_member(user_id)
        roles = await guild.fetch_roles()
    except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError):
        return False
    role_map = {int(role.id): role for role in roles}
    permission = int(getattr(fluxer.Permissions, permission_name))
    if user_id == guild.owner_id:
        return True
    return any(
        (role := role_map.get(int(role_id))) is not None
        and (int(role.permissions) & int(fluxer.Permissions.ADMINISTRATOR)
             or int(role.permissions) & permission)
        for role_id in member.roles
    )

async def can_moderate_target(guild: fluxer.Guild, target_id: int) -> tuple[bool, str | None]:

    if target_id == guild.owner_id:
        return False, "サーバー所有者はBotでは処分できません。"
    try:
        bot_member, target_member, roles = await asyncio.gather(
            guild.fetch_member(int(bot.user.id)),
            guild.fetch_member(target_id),
            guild.fetch_roles(),
        )
    except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError) as exc:
        print(f"処分対象とBotのロール階層確認に失敗しました (guild={guild.id}, target={target_id}): {exc}")
        return False, "メンバーまたはロール情報を取得できませんでした。Botのメンバー閲覧権限を確認してください。"

    positions = {int(role.id): int(role.position) for role in roles}
    bot_top_position = max((positions.get(int(role_id), 0) for role_id in bot_member.roles), default=0)
    target_top_position = max((positions.get(int(role_id), 0) for role_id in target_member.roles), default=0)
    if bot_top_position <= target_top_position:
        return False, "対象者のロールがBotのロールと同じか上位です。Botのロールを対象者より上に移動してください。"
    return True, None

def extract_urls(content: str) -> list[str]:
    return URL_PATTERN.findall(content)

def violation_reason(message, guild_id: int) -> str | None:
    channel_id = int(message.channel_id)
    content = message.content or ""
    if len(URL_PATTERN.findall(content)) > 5:
        return "大量のURL送信が検出されました"
    if content.count("||") >= 10:
        return "スポイラー/Markdownスパムが検出されました"
    markdown_patterns = [r"#{1,6}\s", r"\*\*[^*\n]+\*\*", r"^>\s", r"^[-*]\s"]
    markdown_count = sum(
        len(re.findall(pattern, content, re.MULTILINE if pattern.startswith("^") else 0))
        for pattern in markdown_patterns
    )
    if channel_id not in invite_whitelist_channels.get(guild_id, set()) and markdown_count >= 8:
        return "マークダウンスパムが検出されました"
    emoji_count = len(re.findall(r"<a?:[a-zA-Z0-9_]+:\d+>|[\U0001F300-\U0001FAFF\u2600-\u27BF]", content))
    words = content.split()
    if emoji_count > 5 and emoji_count / max(len(words), 1) >= 0.8:
        return "絵文字スパムが検出されました"
    if TOKEN_PATTERN.search(content):
        return "トークンの送信が検出されました"
    if INVITE_PATTERN.search(content) and channel_id not in invite_whitelist_channels.get(guild_id, set()):
        return "許可されていないチャンネルでの招待リンク送信が検出されました"
    urls = extract_urls(content)
    if channel_id not in invite_whitelist_channels.get(guild_id, set()):
        for url in urls:
            domain = re.sub(r"^https?://|^www\.", "", url.lower()).split("/", 1)[0].split(":", 1)[0]
            if domain in shortlink_domains or any(domain == item or domain.endswith("." + item) for item in SHORTENER_PREFIXES):
                return "短縮リンクが検出されました"
    if guild_id not in profanity_disabled_guilds and any(item.check_profanity(content) for item in profanity_filters):
        return "不適切な言葉が検出されました"
    key = (guild_id, int(message.author.id))
    now = datetime.now(timezone.utc)
    recent = [(text, when) for text, when in recent_messages[key] if now - when < timedelta(seconds=10)]
    if sum(1 for text, _ in recent if text == content) >= 3:
        return "スパムが検出されました（同一メッセージの連投）"
    recent.append((content, now))
    recent_messages[key] = recent[-20:]
    times = [when for when in recent_message_times[key] if now - when < timedelta(seconds=5)]
    if len(times) >= 5:
        times.append(now)
        recent_message_times[key] = times[-20:]
        return "フラッドが検出されました（短時間での大量メッセージ）"
    times.append(now)
    recent_message_times[key] = times[-20:]
    if len(URL_PATTERN.findall(content)) > 5:
        return "大量のURL送信が検出されました"
    if re.search(r"(?:\|\|[^|]+\|\||```[^`]*```|`[^`]+`)", content) and content.count("||") + content.count("```") + content.count("**") >= 16:
        return "スポイラー/Markdownスパムが検出されました"
    emoji_count = len(re.findall(r"<a?:[a-zA-Z0-9_]+:\d+>|[\U0001F300-\U0001FAFF]", content))
    if emoji_count >= 15:
        return "絵文字スパムが検出されました"
    return None

async def process_violation(message, guild: fluxer.Guild, reason: str) -> None:
    user_id = int(message.author.id)
    if not await can_moderate(guild, int(bot.user.id), "MANAGE_MESSAGES"):
        print(f"サーバー {guild.id}: メッセージ管理権限がないため違反メッセージを削除できません")
    else:
        try:
            await message.delete()
        except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException):
            pass

    if await member_is_admin(guild, user_id):
        return
    now = datetime.now(timezone.utc)
    async with state_lock:
        data = violation_tracker[int(guild.id)].setdefault(user_id, {"status": "active", "count": 0, "violations": []})
        previous = data.get("last_violation")
        if previous:
            try:
                if (now - datetime.fromisoformat(previous)).total_seconds() > VIOLATION_RESET_TIME:
                    data["count"], data["violations"] = 0, []
            except ValueError:
                pass
        data["count"] = int(data.get("count", 0)) + 1
        data["last_violation"] = now.isoformat()
        data.setdefault("violations", []).append({"reason": reason, "channel": str(message.channel_id), "time": now.isoformat()})
        count = data["count"]
        save_modlog()
    try:
        if count >= BAN_THRESHOLD:
            member = await guild.fetch_member(user_id)
            if not await can_moderate(guild, int(bot.user.id), "BAN_MEMBERS"):
                channel = await bot.fetch_channel(str(message.channel_id))
                await channel.send("BAN条件を満たしましたが、BotのロールにBAN権限がないためBANできませんでした。")
                return
            can_act, hierarchy_error = await can_moderate_target(guild, user_id)
            if not can_act:
                channel = await bot.fetch_channel(str(message.channel_id))
                await channel.send(f"BAN条件を満たしましたが、BANできませんでした。{hierarchy_error}")
                return
            await member.ban(delete_message_seconds=BAN_MESSAGE_DELETE_DAYS * 86400,
                            reason=f"累積違反 {count} 回: {reason}")
            channel = await bot.fetch_channel(str(message.channel_id))
            await channel.send(f"🔨 {message.author.mention} をBANしました。理由: {reason}（累積違反 {count} 回）")
            async with state_lock:
                violation_tracker[int(guild.id)].pop(user_id, None)
                save_modlog()
        else:
            channel = await bot.fetch_channel(str(message.channel_id))
            await channel.send(
                f"⚠️ {message.author.mention} に警告しました。理由: {reason}\n"
                f"違反回数: {count}/{BAN_THRESHOLD}（あと {BAN_THRESHOLD-count} 回でBAN）"
            )
    except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError) as exc:
        print(f"違反へのモデレーションに失敗しました: {exc}")
        try:
            channel = await bot.fetch_channel(str(message.channel_id))
            await channel.send(f"違反を検出しましたが、処分に失敗しました: {exc}")
        except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError) as notify_exc:
            print(f"処分失敗の通知にも失敗しました (guild={guild.id}): {notify_exc}")

async def check_raid_join(guild: fluxer.Guild, member) -> None:
    now = datetime.now(timezone.utc)
    joins = [when for when in recent_joins[int(guild.id)] if now - when < timedelta(seconds=RAID_JOIN_WINDOW_SECONDS)]
    joins.append(now)
    recent_joins[int(guild.id)] = joins
    joined_at = getattr(member, "joined_at", None)
    new_account = False
    if joined_at:
        try:
            new_account = now - datetime.fromisoformat(joined_at.replace("Z", "+00:00")) < timedelta(minutes=RAID_NEW_ACCOUNT_MINUTES)
        except ValueError:
            pass
    if len(joins) >= RAID_JOIN_THRESHOLD or (new_account and len(joins) >= 3):
        async with raid_lock:
            if int(guild.id) in raid_modes:
                return
            raid_modes[int(guild.id)] = {"started_at": now.isoformat(), "joins": len(joins)}
        print(f"Guild {guild.id}: raid mode activated after {len(joins)} joins")
        if new_account:
            member_id = int(member.get("user", {}).get("id", 0)) if isinstance(member, dict) else int(member.user.id)
            if member_id and await can_moderate(guild, int(bot.user.id), "KICK_MEMBERS"):
                try:
                    await guild.kick(member_id, reason="レイド対策: 作成直後アカウントの参加")
                except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException) as exc:
                    print(f"レイド参加者のキックに失敗しました: {exc}")

@bot.event
async def on_ready():
    await asyncio.gather(*(refresh_channel_cache(guild) for guild in bot.guilds))
    print(f"Fluxerに接続しました: {bot.user.username}")

async def refresh_channel_cache(guild: fluxer.Guild) -> None:
    if not guild._http:
        return
    try:
        channels = await guild._http.get_guild_channels(guild.id)
        for channel in channels:
            channel_guild_cache[int(channel["id"])] = int(guild.id)
    except (fluxer.Forbidden, fluxer.HTTPException) as exc:
        print(f"サーバー {guild.id} のチャンネル一覧取得に失敗しました: {exc}")

async def cached_guild_for_message(message):
    channel_id = int(message.channel_id)
    guild_id = channel_guild_cache.get(channel_id)
    if guild_id is None and message._channel and message._channel.guild_id:
        guild_id = int(message._channel.guild_id)
        channel_guild_cache[channel_id] = guild_id
    if guild_id is None:
        channel = await bot.fetch_channel(str(channel_id))
        guild_id = channel.guild_id
        if guild_id:
            channel_guild_cache[channel_id] = int(guild_id)
    return bot.get_guild(int(guild_id)) if guild_id else None

@bot.event
async def on_guild_join(guild):
    await refresh_channel_cache(guild)

@bot.event
async def on_member_join(member):
    guild_id = int(member.get("guild_id", 0)) if isinstance(member, dict) else int(member.guild_id or 0)
    guild = bot.get_guild(guild_id)
    if guild:
        await check_raid_join(guild, member)

@bot.event
async def on_message(message):
    if getattr(message.author, "bot", False):
        return
    channel_id = int(message.channel_id)
    try:
        guild = await cached_guild_for_message(message)
    except (fluxer.NotFound, fluxer.Forbidden, fluxer.HTTPException) as exc:
        print(f"メッセージのギルド確認に失敗しました (channel={channel_id}): {exc}")
        return
    if guild is None:
        return
    if (message.content or "").strip().lower().startswith(PREFIX):
        return
    reason = violation_reason(message, int(guild.id))
    if reason:
        await process_violation(message, guild, reason)

@bot.command(name="help")
async def help_command(ctx):
    await ctx.reply(
        "**botname Fluxer コマンド**\n"
        "`nn.ping` / `nn.help`\n"
        "`nn.whitelist add/remove/list <channel_id>`\n"
        "`nn.profanity enable/disable`\n"
        "`nn.violation check/reset <user_id>`\n"
        "`nn.unban <user_id>` / `nn.antiraid status/disable`\n"
        "`nn.verify status/disable` / `nn.resetup_automod` / `nn.disable_external_apps`"
    )

@bot.command(name="ping")
async def ping_command(ctx):
    await ctx.reply("Pong!")

@bot.command(name="whitelist")
async def whitelist_command(ctx, action: str = "list", channel_id: str = ""):
    if not await require_admin(ctx):
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = int(guild.id)
    channels = invite_whitelist_channels[guild_id]
    if action == "list":
        await ctx.reply("許可チャンネル: " + (", ".join(f"`{item}`" for item in sorted(channels)) if channels else "なし"))
        return
    try:
        target = int(channel_id.strip("<#>"))
    except ValueError:
        await ctx.reply("使用方法: `nn.whitelist add <channel_id>` または `remove <channel_id>`")
        return
    if action == "add":
        channels.add(target)
    elif action == "remove":
        channels.discard(target)
    else:
        await ctx.reply("操作は `add`、`remove`、`list` のいずれかです")
        return
    save_whitelist()
    await ctx.reply(f"チャンネル `{target}` の招待リンク許可を更新しました")

@bot.command(name="profanity")
async def profanity_command(ctx, action: str = ""):
    if not await require_admin(ctx):
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = int(guild.id)
    if action == "disable":
        profanity_disabled_guilds.add(guild_id)
    elif action == "enable":
        profanity_disabled_guilds.discard(guild_id)
    else:
        await ctx.reply("使用方法: `nn.profanity enable` または `disable`")
        return
    save_profanity_settings()
    await ctx.reply(f"不適切語フィルターを{'無効' if action == 'disable' else '有効'}にしました")

@bot.command(name="violation")
async def violation_command(ctx, action: str = "", user_id: str = ""):
    if not await require_admin(ctx):
        return
    try:
        target_id = int(user_id.strip("<@!>"))
    except ValueError:
        await ctx.reply("使用方法: `nn.violation check/reset <user_id>`")
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = int(guild.id)
    data = violation_tracker.get(guild_id, {}).get(target_id)
    if action == "check":
        if not data:
            await ctx.reply(f"`{target_id}` の違反履歴はありません")
            return
        recent = data.get("violations", [])[-5:]
        details = "\n".join(f"• {entry['reason']} ({entry['time']})" for entry in recent) or "なし"
        await ctx.reply(f"`{target_id}` の違反回数: {data.get('count', 0)}/{BAN_THRESHOLD}\n最近の違反:\n{details}")
    elif action == "reset":
        violation_tracker.get(guild_id, {}).pop(target_id, None)
        save_modlog()
        await ctx.reply(f"`{target_id}` の違反履歴をリセットしました（既に適用された処分は解除されません）")
    else:
        await ctx.reply("操作は `check` または `reset` です")

@bot.command(name="unban")
async def unban_command(ctx, user_id: str = ""):
    if not await require_admin(ctx):
        return
    guild = await cached_guild_for_message(ctx)
    if not await can_moderate(guild, int(ctx.author.id), "BAN_MEMBERS"):
        await ctx.reply("この操作にはBAN権限も必要です。メンバーのロール権限を確認してください")
        return
    if not await can_moderate(guild, int(bot.user.id), "BAN_MEMBERS"):
        await ctx.reply("BANを解除するにはBotのロールにもBAN権限が必要です")
        return
    try:
        target = int(user_id)
        await guild.unban(target, reason=f"{ctx.author.username} によるBAN解除")
    except ValueError:
        await ctx.reply("使用方法: `nn.unban <user_id>`")
        return
    except (fluxer.Forbidden, fluxer.NotFound, fluxer.HTTPException, RuntimeError) as exc:
        await ctx.reply(f"BAN解除に失敗しました: {exc}")
        return
    violation_tracker.get(int(guild.id), {}).pop(target, None)
    save_modlog()
    await ctx.reply(f"`{target}` のBANを解除し、違反履歴を削除しました")

@bot.command(name="antiraid")
async def antiraid_command(ctx, action: str = "status"):
    if not await require_admin(ctx):
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = int(guild.id)
    data = raid_modes.get(guild_id)
    if action == "status":
        if data:
            started = datetime.fromisoformat(data["started_at"])
            remaining = max(0, RAID_MODE_DURATION_MINUTES * 60 - (datetime.now(timezone.utc) - started).total_seconds())
            await ctx.reply(f"レイド対策モードは有効です。残り約{int(remaining // 60)}分{int(remaining % 60)}秒")
        else:
            await ctx.reply("レイド対策モードは無効です")
    elif action == "disable":
        raid_modes.pop(guild_id, None)
        await ctx.reply("レイド対策モードを解除しました")
    else:
        await ctx.reply("使用方法: `nn.antiraid status` または `disable`")

@bot.command(name="verify")
async def verify_command(ctx, action: str = "status", *, arguments: str = ""):
    if not await require_admin(ctx):
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = str(guild.id)
    if action == "status":
        config = verify_configs.get(guild_id)
        if config:
            await ctx.reply(f"認証設定あり\n未認証ロール: `{config.get('unverified_role', '不明')}`\n認証済みロール: `{config.get('verified_role', '不明')}`\nチャンネル: `{config.get('channel', '不明')}`")
        else:
            await ctx.reply("認証システムは未設定です。セットアップは `nn.verify setup <未認証ロールID> <認証済みロールID> <チャンネルID>` で行えます。")
    elif action == "disable":
        if verify_configs.pop(guild_id, None) is not None:
            _save_toml(VERIFY_CONFIG_FILE, verify_configs)
            await ctx.reply("認証システムの設定を削除しました。既存ロールは変更していません。")
        else:
            await ctx.reply("認証システムは設定されていません。")
    elif action == "setup":
        try:
            unverified_id, verified_id, channel_id = (int(value) for value in arguments.split())
        except (TypeError, ValueError):
            await ctx.reply("使用方法: `nn.verify setup <未認証ロールID> <認証済みロールID> <チャンネルID>`")
            return
        if unverified_id == verified_id:
            await ctx.reply("未認証ロールと認証済みロールには異なるロールを指定してください")
            return
        await ctx.reply("Fluxer SDKではユーザー操作用ボタン/モーダルとチャンネル参照のAPIが確認できないため、設定は保存できません。")
    elif action == "panel":
        await ctx.reply("ボタン/モーダルの認証パネルはFluxer SDKに対応APIがないため設置できません。")
    else:
        await ctx.reply("使用方法: `nn.verify status/disable/setup/panel`")

@bot.command(name="resetup_automod")
async def resetup_automod_command(ctx):
    if not await require_admin(ctx):
        return
    await ctx.reply("FluxerのAutoModルールAPIは現在未実装のため、自動ルールは作成できません。メッセージ監視によるトークン検知は有効です。")

@bot.command(name="disable_external_apps")
async def disable_external_apps_command(ctx):
    if not await require_admin(ctx):
        return
    await ctx.reply("外部アプリ権限を一括変更する機能はFluxer APIで確認できないため、変更していません。")

@bot.command(name="uninstall")
async def uninstall_command(ctx, confirmation: str = ""):
    if not await require_admin(ctx):
        return
    if confirmation.lower() != "confirm":
        await ctx.reply("サーバー設定を削除するには `nn.uninstall confirm` を実行してください。")
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = int(guild.id)
    invite_whitelist_channels.pop(guild_id, None)
    profanity_disabled_guilds.discard(guild_id)
    violation_tracker.pop(guild_id, None)
    raid_modes.pop(guild_id, None)
    save_whitelist()
    save_profanity_settings()
    save_modlog()
    await ctx.reply("サーバーに保存されたbotname設定と違反履歴を削除しました。Botの退出はFluxer SDKで未確認です。")

@bot.command(name="status")
async def status_command(ctx):
    if not await require_admin(ctx):
        return
    guild = await cached_guild_for_message(ctx)
    guild_id = int(guild.id)
    await ctx.reply(
        f"レイド対策: {'有効' if guild_id in raid_modes else '無効'}\n"
        f"不適切語フィルター: {'無効' if guild_id in profanity_disabled_guilds else '有効'}\n"
        f"招待リンク許可チャンネル: {len(invite_whitelist_channels.get(guild_id, set()))}件"
    )

@bot.event
async def on_command_error(ctx, error):
    print(f"コマンドエラー: {error}")
    try:
        await ctx.reply(f"コマンドを実行できませんでした: {error}")
    except (fluxer.Forbidden, fluxer.HTTPException):
        pass

async def main():
    if not TOKEN or TOKEN == "your_fluxer_bot_token_here":
        raise RuntimeError(".env に FLUXER_BOT_TOKEN を設定してください")
    load_state()
    try:
        available = await asyncio.to_thread(ensure_filter_updated)
        if not available:
            print("マルウェアフィルターを取得できませんでした。短縮リンクと他のフィルターは継続します")
    except Exception as exc:
        print(f"マルウェアフィルター初期化エラー: {exc}")
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
