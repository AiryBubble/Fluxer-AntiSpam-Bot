import fluxer
from fluxer import Client, Intents
import os
import re
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import better_profanity
from dotenv import load_dotenv
from url_checker import check_url_with_filter, download_filter_list
import json

load_dotenv()

TOKEN = os.getenv('FLUXER_TOKEN')

intents = Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = Client(intents=intents)

WHITELIST_FILE = 'invite_whitelist.json'
BANLOG_FILE = 'ban_log.json'

invite_whitelist_channels = defaultdict(set)
user_message_counts = defaultdict(list)
user_message_times = defaultdict(list)
violation_tracker = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'last_violation': None, 'violations': []}))

ADMIN_USER_IDS = [
    admin uid here,
]

def load_banlog():
    global violation_tracker
    try:
        if os.path.exists(BANLOG_FILE):
            with open(BANLOG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for guild_id, users in data.items():
                    for user_id, info in users.items():
                        violation_tracker[int(guild_id)][int(user_id)] = {
                            'count': info['count'],
                            'last_violation': info['last_violation'],
                            'violations': info['violations']
                        }
            print(f"BAN履歴を読み込みました")
    except Exception as e:
        print(f"BAN履歴読み込みエラー: {e}")

def save_banlog():
    try:
        data = {}
        for guild_id, users in violation_tracker.items():
            data[str(guild_id)] = {}
            for user_id, info in users.items():
                data[str(guild_id)][str(user_id)] = {
                    'count': info['count'],
                    'last_violation': info['last_violation'],
                    'violations': info['violations']
                }
        with open(BANLOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"BAN履歴保存エラー: {e}")

def load_whitelist():
    global invite_whitelist_channels
    try:
        if os.path.exists(WHITELIST_FILE):
            with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                invite_whitelist_channels = defaultdict(set)
                for guild_id, channels in data.items():
                    invite_whitelist_channels[int(guild_id)] = set(channels)
            print(f"ホワイトリストを読み込みました: {len(invite_whitelist_channels)} サーバー")
    except Exception as e:
        print(f"ホワイトリスト読み込みエラー: {e}")

def save_whitelist():
    try:
        data = {str(guild_id): list(channels) for guild_id, channels in invite_whitelist_channels.items()}
        with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"ホワイトリスト保存エラー: {e}")

from better_profanity import profanity
profanity.load_censor_words()

SHORTLINK_DOMAINS = [
    'adf.ly',
    'bit.ly',
    'buff.ly',
    'clk.sh',
    'cutt.ly',
    'goo.gl',
    'is.gd',
    'linklyhq.com',
    'linktr.ee',
    'linkvertise.net',
    'ow.ly',
    'rb.gy',
    'rebrand.ly',
    'short.io',
    'short.link',
    'shorte.st',
    'shortlink.com',
    'shortlink.io',
    'shortlink.me',
    'shorturl.at',
    'snip.ly',
    'soo.gd',
    't.co',
    'tiny.cc',
    'tinyurl.com',
    'trib.al',
    'x.gd',
    'piyolog.hatenadiary.jp',
    'pc.watch.impress.co.jp',
    'develop.tools',
    'gg.gg',
    's.id',
    't.ly',
    'surl.li',
    '00m.in',
    'tgr.jp',
    '9lick.me',
    'kuku.lu',
    'your.ls',
    'youtu.be',
    'youtube.com',
    'meta.wikimedia.org',
    'w.wiki',
    '0.gp',
    '2.gp',
    '2.ly',
    '3.ly',
    '3.sv',
    '4.gp',
    '4.ly',
    '5.gp',
    '6.gp',
    '6.ly',
    '7.ly',
    '8.ly',
    'c.je',
    'e.vg',
    'f.ht',
    'g.vu',
    'i.gg',
    'r.sv',
    'u.to',
    'v.af',
    'v.gd',
    '0x.co',
    '1s.pt',
    '2d.al',
    '2h.ae',
    '2m.is',
    '2s.gg',
    '3n.si',
    '3u.gs',
    '4e.fi',
    '4z.no',
    '52.nu',
    '73.nu',
    '7i.se',
    '7x.qa',
    '7z.si',
    '9m.no',
    'click.ly',
    'cl.gy',
    'da.gd',
    'ee.sb',
    'ft.ax',
    'g5.vc',
    'hq.ax',
    'i8.ae',
    'if.fm',
    'in.mt',
    'is.am',
    'ko.fm',
    'lc.cx',
    'ly.my',
    'md.ly',
    'mq.gy',
    'n9.cl',
    'ov.cm',
    'ss.ly',
    'tg.pe',
    'to.lk',
    'tr.ee',
    'tt.vg',
    'v.vin',
    'v0.nu',
    'we.pe',
    'ws.tc',
    'wz.my',
    'xx.nz',
    'ye.pe',
    'zo.cm',
    'zz.sd',
    '000.fo',
    'u.artspin.jp',
    '0e0.pw',
    '0rz.tw',
    '110.vg',
    '128.pl',
    '2cm.es',
    '2no.co',
    'arai-shinsuke.com',
    '2rs.me',
    '302.jp',
    '302.to',
    '5ne.co',
    '7c.tel',
    '985.so',
    'a.info',
    'a38.fr',
    'aic.la',
    'biy.us',
    'bly.to',
    'bom.so',
    'cfg.me',
    'cia.sh',
    'cut.tw',
    'dlj.li',
    'dub.sh',
    'flu.yt',
    'g.asia',
    'g60.jp',
    'goo.cm',
    'goo.su',
    'goo.vc',
    'heh.st',
    'iii.im',
    'iil.la',
    'inx.mail.ee',
    'inx.lv',
    'iwe.re',
    'j2l.de',
    'jii.li',
    'jli.cl',
    'kik.to',
    'lel.st',
    'lhs.cx',
    'ln.run',
    'myu.pw',
    'o0o.jp',
    'oyn.at',
    'p.asia',
    'plu.sh',
    'pnt.to',
    'qqq.yt',
    'qr1.jp',
    'r5f.jp',
    'shorten.ly',
    'rid.ee',
    'sht.ac',
    'sor.bz',
    'srt.rw',
    'su2.me',
    'suo.yt',
    'syu.to',
    't-p.bz',
    'tin.al',
    'to2.pw',
    'tri.im',
    'tto.jp',
    'u5a.cn',
    'u6e.cn',
    'ur0.cc',
    'ur0.jp',
    'ur3.us',
    'ur7.cc',
    'ure.my',
    'url.rw',
    'url.sa',
    'use.my',
    'vvd.bz',
    'wal.ee',
    'ww9.jp',
    'xy2.eu',
    'z2.ink',
    'fileseek.jp',
    'zip.lu',
    'zws.im',
    'zzb.bz',
    'xn--s7y.xn--tckwe',
    '1sl.pw',
    'i188.eu.org',
    'ip1.cc',
    'zhp.jp',
    'bitly.cx',
    'bitly.lc',
    'bitly.pk',
    'tinyurl.mobi',
    'tinyurl.one',
    'tinyurl.ph',
    'tinyurl.se',
    'tinyurl.top',
    'tinyurl.ws',
    'tinyurls.tech',
    'etinyurl.com',
    'url.ba',
    'url.beauty',
    'url-s.xyz',
    'url2.fun',
    'urlc.net',
    'urls.cat',
    'urls.fr',
    'urls.my.id',
    'urls.wtf',
    'urlshortener.biz',
    'urlsmall.com',
    'urlsrt.io',
    'grabify.org',
    'urlto.me',
    'urlty.co',
    'urly.it',
    'urlz.fr',
    'short.af',
    'short.bg',
    'short.pw',
    'short-link.me',
    'shorten.ws',
    'shortenerlink.xyz',
    'shorter.me',
    'shortifyme.co',
    'shorturl.asia',
    'shorturl.click',
    'shorturl.gg',
    'shorturl.is',
    'shorturl.ma',
    'shorturl.me',
    'shorturl.re',
    'shorturl.sbs',
    'shorturl.tokyo',
    'mini-url.net',
    'miniurl.be',
    'miniurl.cl',
    'miniurl.com',
    'miniurl.pro',
    'miniurl.top',
    'minurls.com',
    'tiny.ee',
    'tiny.pl',
    'tiny.re',
    'tinylink.at',
    'tinylink.cz',
    'tinylink.in',
    'tinylink.net',
    'tinylink.onl',
    'tinylinks.cc',
    '069.biz',
    'tensouya.com',
    '1-0x.com',
    '125.back.jp',
    'hayao0819.com',
    '1lil.li',
    '1ly.red',
    '301.link',
    '33-4.me',
    '34vv.net',
    '443.cyou',
    'amz.run',
    'shorturl.com',
    'alturl.com',
    'archive.today',
    'beautylinks.net',
    'clickmoe.link',
    'clickurl.link',
    'cut.onl',
    'cxy.jp',
    'd99.biz',
    'directmeto.site',
    'doturl.link',
    'dym.icu',
    'u.egg-p.net',
    'tools.emboma.jp',
    'ggle.in',
    'redirect-project.glitch.me',
    'grabify.link',
    'megalodon.jp',
    'gyo.tc',
    'h-ref.com',
    'hakanaurl.link',
    'su.ima24.net',
    'iplogger.org',
    'iplog.co',
    'kawaii.st',
    'u.kawaii.su',
    'koaku.ma',
    'kutt.uk',
    'linkify.me',
    'links.tube',
    'lnk.farm',
    'llili.li',
    'microurl.org',
    'mixi.bz',
    'mixi.jp',
    'nolog.link',
    'nullrefer.me',
    'pro-url.com',
    'quick2.link',
    'redir.lat',
    'redirect.bio',
    'rssfeed.news',
    'ryaku.jp',
    'sdigo.app',
    'c.shogo82148.com',
    'shortpals.online',
    'sht.moe',
    'smallurl.co',
    'ssurl.at',
    'surlz.com',
    'switas.com',
    'swit.as',
    'tinu.be',
    'tobeto.be',
    'tantan-link.com',
    'u301.co',
    'app.udcxx.me',
    'upto.site',
    'webinfo.link',
    'x-short.plus',
    'yoro.cc',
    'ytub.ee',
    'zizi.ly',
    'rinu.jp'
]

@bot.on("ready")
async def on_ready():
    print(f'{bot.user.username} としてログインしました')
    print('------')
    
    load_whitelist()
    load_banlog()
    
    print("フィルターを初期化中...")
    download_filter_list()

@bot.on("guild_join")
async def on_guild_join(guild):
    print(f'新しいサーバーに参加: {guild.name} (ID: {guild.id})')

@bot.on("message")
async def on_message(message):
    if message.author.bot:
        return
    
    is_admin = message.author.id in ADMIN_USER_IDS
    
    if not is_admin and message.guild:
        try:
            member = await message.guild.fetch_member(message.author.id)
            if member:
                if hasattr(member, 'permissions'):
                    perms = member.permissions
                    if hasattr(perms, 'administrator'):
                        is_admin = perms.administrator
                    elif hasattr(perms, 'value'):
                        is_admin = (perms.value & 0x8) == 0x8
        except Exception as e:
            print(f"権限チェックエラー: {e}")
    
    if message.content.startswith('!'):
        args = message.content[1:].split()
        cmd = args[0].lower()
        
        if cmd == 'unban' and len(args) > 1:
            if not is_admin:
                await message.channel.send('権限がありません (管理者権限が必要です)')
                return
            
            try:
                user_id = int(args[1])
                
                await message.guild.unban(user_id, reason=f"{message.author} によるBAN解除")
                
                if message.guild.id in violation_tracker and user_id in violation_tracker[message.guild.id]:
                    del violation_tracker[message.guild.id][user_id]
                    save_banlog()
                
                await message.channel.send(f'ユーザーID `{user_id}` のBANを解除しました')
                    
            except ValueError:
                await message.channel.send('無効なユーザーIDです。数字のみで指定してください')
            except Exception as e:
                error_msg = str(e).lower()
                if "unknown ban" in error_msg or "not banned" in error_msg or "not found" in error_msg:
                    await message.channel.send(f'ユーザーID `{user_id}` はBANされていません')
                elif "forbidden" in error_msg or "permission" in error_msg:
                    await message.channel.send('BAN解除の権限がありません')
                else:
                    await message.channel.send(f'エラーが発生しました: {e}')
            return
        
        elif cmd == 'help':
            help_text = """**利用可能なコマンド:**
!unban <ユーザーID> - BANを解除します
!help - このヘルプを表示

**注意:** unban コマンドは管理者権限が必要です"""
            await message.channel.send(help_text)
            return
    
    checks = [
        check_token_send(message),
        check_invite_links(message),
        check_shortlinks(message),
        check_malware_links(message),
        check_profanity(message),
        check_spam(message),
        check_flood(message),
        check_emoji_spam(message),
        check_spoiler_spam(message),
        check_markdown_spam(message)
    ]
    
    for check in checks:
        if check:
            await message.delete()
            if is_admin:
                return
            else:
                result = await handle_violation(message, check)
                return

BAN_THRESHOLD = 3
VIOLATION_RESET_TIME = 3600
BAN_MESSAGE_DELETE_DAYS = 1

async def handle_violation(message, reason):
    guild_id = message.guild.id
    user_id = message.author.id
    current_time = datetime.now().isoformat()
    
    user_data = violation_tracker[guild_id][user_id]
    if user_data['last_violation']:
        last_time = datetime.fromisoformat(user_data['last_violation'])
        if (datetime.now() - last_time).total_seconds() > VIOLATION_RESET_TIME:
            user_data['count'] = 0
            user_data['violations'] = []
    
    user_data['count'] += 1
    user_data['last_violation'] = current_time
    user_data['violations'].append({
        'reason': reason,
        'channel': message.channel.id,
        'time': current_time
    })
    save_banlog()
    
    violation_count = user_data['count']
    
    try:
        member = await message.guild.fetch_member(user_id)
    except:
        member = message.author
    
    if violation_count >= BAN_THRESHOLD:
        try:
            await member.ban(
                reason=f"累積違反 {violation_count} 回: {reason}",
                delete_message_days=BAN_MESSAGE_DELETE_DAYS
            )
            await message.channel.send(
                f'{member.mention} がBANされました\n'
                f'理由: 累積違反 {violation_count} 回 - {reason}'
            )
            del violation_tracker[guild_id][user_id]
            save_banlog()
            return "banned"
        except fluxer.Forbidden:
            await message.channel.send(
                f'{member.mention} がBAN条件を満たしましたが、権限不足でBANできませんでした'
            )
            return "failed"
    else:
        await message.channel.send(
            f'{member.mention} 違反 {violation_count}/{BAN_THRESHOLD}: {reason}\n'
            f'あと {BAN_THRESHOLD - violation_count} 回の違反でBANされます'
        )
        return "warning"

def check_profanity(message):
    if profanity.contains_profanity(message.content):
        return "不適切な言葉が検出されました"
    return None
    
def extract_urls_from_message(content):
    urls = []
    urls.extend(re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', content, re.IGNORECASE))
    www_urls = re.findall(r'www\.[^\s<>"{}|\\^`\[\]]+', content, re.IGNORECASE)
    urls.extend(www_urls)
    
    domain_pattern = r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?:/[^\s<>"{}|\\^`\[\]]*)?'
    domain_urls = re.findall(domain_pattern, content, re.IGNORECASE)
    
    for url in domain_urls:
        if not any(url in existing for existing in urls):
            if not re.search(r'@', url) and not url.endswith(('.py', '.js', '.css', '.html', '.txt', '.json', '.xml')):
                urls.append(url)
    
    return list(set(urls))

def check_token_send(message):
    token_patterns = [
        r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}',
        r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{38}',
        r'[\w-]{24}\.[\w-]{6}\.[\w-]{27}',
    ]
    
    for pattern in token_patterns:
        if re.search(pattern, message.content):
            return "トークンの送信が検出されました"
    return None

def check_invite_links(message):
    invite_patterns = [
        r'(?:https?://)?(?:www\.)?discord\.gg/([a-zA-Z0-9\-_]+)',
        r'(?:https?://)?(?:www\.)?discord\.com/invite/([a-zA-Z0-9\-_]+)',
        r'(?:https?://)?(?:www\.)?discordapp\.com/invite/([a-zA-Z0-9\-_]+)',
        r'(?:https?://)?(?:www\.)?discord\.io/([a-zA-Z0-9\-_]+)',
        r'(?:https?://)?(?:www\.)?discord\.me/([a-zA-Z0-9\-_]+)',
        r'(?:https?://)?(?:www\.)?discord\.li/([a-zA-Z0-9\-_]+)',
        r'(?:^|\s)discord\.gg/([a-zA-Z0-9\-_]+)',
        r'(?:^|\s)discord\.com/invite/([a-zA-Z0-9\-_]+)',
    ]
    
    for pattern in invite_patterns:
        match = re.search(pattern, message.content, re.IGNORECASE)
        if match:
            allowed_channels = invite_whitelist_channels.get(message.guild.id, set())
            if message.channel.id not in allowed_channels:
                return "許可されていないチャンネルでの招待リンク送信が検出されました"
            break
    
    return None

def check_shortlinks(message):
    urls = extract_urls_from_message(message.content)
    
    for url in urls:
        domain = url.lower()
        for prefix in ['https://', 'http://', 'www.']:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.split('/')[0]
        domain = domain.split(':')[0]
        
        for shortlink_domain in SHORTLINK_DOMAINS:
            if domain == shortlink_domain or domain.endswith('.' + shortlink_domain):
                return f"短縮リンクが検出されました ({domain})"
    return None

def check_malware_links(message):
    urls = extract_urls_from_message(message.content)
    
    for url in urls:
        check_url = url
        if not check_url.startswith(('http://', 'https://')):
            check_url = 'http://' + check_url
        
        if check_url_with_filter(check_url):
            return f"マルウェアリンクが検出されました ({url})"
    return None

def check_spam(message):
    user_id = message.author.id
    current_time = datetime.now()
    
    user_message_counts[user_id] = [
        (content, time) for content, time in user_message_counts[user_id]
        if current_time - time < timedelta(seconds=10)
    ]
    
    same_messages = sum(1 for content, _ in user_message_counts[user_id] 
                       if content == message.content)
    
    if same_messages >= 3:
        return "スパムが検出されました（同一メッセージの連投）"
    
    user_message_counts[user_id].append((message.content, current_time))
    return None

def check_flood(message):
    user_id = message.author.id
    current_time = datetime.now()
    
    recent_messages = [t for t in user_message_times[user_id] 
                      if current_time - t < timedelta(seconds=5)]
    
    if len(recent_messages) >= 5:
        return "フラッドが検出されました（短時間での大量メッセージ）"
    
    user_message_times[user_id].append(current_time)
    if len(user_message_times[user_id]) > 10:
        user_message_times[user_id] = user_message_times[user_id][-10:]
    
    return None

def check_emoji_spam(message):
    custom_emoji = len(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', message.content))
    unicode_emoji = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
                                   r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
                                   r'\U00002702-\U000027B0\U000024C2-\U0001F251]', message.content))
    
    total_emoji = custom_emoji + unicode_emoji
    if total_emoji > 0 and total_emoji / max(len(message.content.split()), 1) >= 0.5:
        return "絵文字スパムが検出されました"
    return None

def check_spoiler_spam(message):
    spoiler_count = message.content.count('||')
    if spoiler_count >= 10:
        return "スポイラースパムが検出されました"
    return None

def check_markdown_spam(message):
    markdown_patterns = [r'#{1,6}\s']
    
    markdown_count = 0
    for pattern in markdown_patterns:
        markdown_count += len(re.findall(pattern, message.content))
    
    if markdown_count >= 5:
        return "マークダウンスパムが検出されました"
    return None

if __name__ == "__main__":
    bot.run(TOKEN)
