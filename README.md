# Fluxer Antispam bot

## 主な機能

- 招待リンク、短縮リンク、マルウェアリンクの検出
- 日本語・英語の不適切語フィルター
- スパム、連投、フラッド、絵文字・スポイラー・Markdownスパムの対策
- 違反時の警告と、累積違反時のBAN
- レイド対策とトークン送信防止
- nn.コマンドによる各機能・設定の管理

1. `pip install -r requirements.txt` で依存関係を入れます。
2. `.env` に `FLUXER_BOT_TOKEN=FluxerのBotトークン` を設定します。
3. Botにメッセージ閲覧/送信、メッセージ管理、メンバーのBAN/キック権限を付け、`python main.py` で起動します。

コマンドは `nn.` プレフィックスです。管理コマンドは実行者がサーバー所有者かを確認し、さらにメンバーの各ロールを取得して `ADMINISTRATOR` 権限ビットが含まれるか検査します。ロール照会に失敗した場合は安全側に倒して拒否します。

コマンド応答は通常の公開メッセージです。実行者だけに見えるエフェメラル返信には対応していません。

主なコマンド: `nn.help`, `nn.whitelist add/remove/list <channel_id>`, `nn.profanity enable/disable`, `nn.violation check/reset <user_id>`, `nn.unban <user_id>`, `nn.antiraid status/disable`, `nn.uninstall confirm`。

招待リンク、短縮リンク、トークン、日英不適切語、連投/フラッド、絵文字・Markdownスパム、マルウェアURLを検査します。違反1・2回目は警告し、3回目にBANします。レイド検知では状態を記録し、作成直後のアカウントを検出した場合はBotにキック権限があると確認できたときにキックします。レイドモード中のサーバー認証レベル変更APIは含みません。

## url_checker.pyで使用するオススメのフィルター
- [Online Malicious URL Blocklist](https://gitlab.com/malware-filter/urlhaus-filter)
- [Phishing URL Blocklist](https://gitlab.com/malware-filter/phishing-filter)
# 注記
safetextの依存関係でPythonのバージョンは3.12.xがいいかと思われます。
