import requests
from discord_webhook import DiscordWebhook
from datetime import datetime, timedelta
import os
import time
import sys
from dotenv import load_dotenv
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gc

# .envファイルの読み込み
load_dotenv()

# Discord Webhook URLs for each category
WEBHOOK_URLS = {
    'streamer': os.getenv('DISCORD_WEBHOOK_URL_STREAMER', ''),
    'friend': os.getenv('DISCORD_WEBHOOK_URL_FRIEND', ''),
    'smurf': os.getenv('DISCORD_WEBHOOK_URL_SMURF', ''),
    'troll': os.getenv('DISCORD_WEBHOOK_URL_TROLL', '')
}

# 有効なWebhook URLを持つカテゴリのみを取得
ACTIVE_CATEGORIES = {cat: url for cat, url in WEBHOOK_URLS.items() if url}

# 環境変数の読み込み部分
def load_player_list():
    categories = {
        'streamer': os.getenv('STREAMER_LIST', ''),
        'friend': os.getenv('FRIEND_LIST', ''),
        'smurf': os.getenv('SMURF_LIST', ''),
        'troll': os.getenv('TROLL_LIST', '')
    }

    player_dict = {}
    nickname_to_player = {}
    player_categories = {}

    for category, player_list_str in categories.items():
        # カテゴリが設定されていない場合はスキップ
        if not player_list_str:
            continue

        # このカテゴリのWebhook URLが設定されていない場合はスキップ
        if category not in ACTIVE_CATEGORIES:
            logging.info(f"カテゴリ '{category}' のWebhook URLが設定されていないため、プレイヤーをスキップします")
            continue

        for player_info in player_list_str.split(','):
            player_info = player_info.strip()
            if not player_info:  # 空の要素はスキップ
                continue

            if ':' in player_info:
                nickname, name = player_info.split(':')
                player_dict[name] = nickname
                nickname_to_player[nickname] = name
            else:
                # コロンがない場合は、ニックネームなしとして登録
                name = player_info
                player_dict[name] = None

            player_categories[name] = category

    return player_dict, nickname_to_player, player_categories

# グローバル変数として定義
PLAYER_DICT, NICKNAME_TO_PLAYER, PLAYER_CATEGORIES = load_player_list()

# 環境変数の検証
if not ACTIVE_CATEGORIES:
    raise ValueError("少なくとも1つのDiscord Webhook URLが設定されている必要があります。")

if not PLAYER_DICT:
    raise ValueError("有効なカテゴリに属するプレイヤーが1人も設定されていません。")

# 設定されたカテゴリごとにプレイヤーがいるかチェック
for category in ACTIVE_CATEGORIES.keys():
    category_players = [name for name, cat in PLAYER_CATEGORIES.items() if cat == category]
    if not category_players:
        logging.warning(f"カテゴリ '{category}' にプレイヤーが設定されていません。")

print("監視対象プレイヤー:")
for player_name, nickname in PLAYER_DICT.items():
    print(f"- {nickname} ({player_name})")

# 定数の設定
POROFESSOR_BASE_URL = "https://porofessor.gg/live/jp/"

# プレイヤーごとの最大保存マッチ数を2に変更
MAX_MATCHES_PER_PLAYER = 2

# 最後のマッチ情報を保存する辞書
last_match_info = {}

# ログの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 起動時のログ
logging.info("=== アプリケーション起動 ===")
logging.info(f"起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
logging.info("監視対象プレイヤー:")
for player_name, nickname in PLAYER_DICT.items():
    logging.info(f"- {nickname} ({player_name})")
logging.info("========================")

# 環境変数の読み込み
SAVE_HTML_LOG = os.getenv('SAVE_HTML_LOG', 'false').lower() == 'true'

def save_html_log(player_name, content):
    """HTMLレスポンスをログとして保存する関数（ログ出力なし）"""
    if not SAVE_HTML_LOG:
        return
        
    # logsディレクトリが存在しない場合は作成
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # プレイヤー名から安全なファイル名を作成
    safe_name = player_name.replace('#', '-').replace(':', '_')
    
    # 現在の日時をファイル名に含める
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_name}_{timestamp}.html"
    
    # ログファイルを保存
    log_path = log_dir / filename
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            for chunk in content.split('\n'):
                f.write(chunk + '\n')
    except Exception as e:
        logging.error(f"HTMLログの保存に失敗しました: {str(e)}")

def check_all_players():
    match_groups = {}
    not_found_players = []
    
    # プレイヤーを一人ずつ順番にチェック
    for player_name in PLAYER_DICT.keys():
        try:
            result = check_player_status(player_name)
            
            if result:
                if result == "not_found":
                    not_found_players.append((player_name, PLAYER_DICT[player_name]))
                    logging.info(f"{PLAYER_DICT[player_name]}({player_name})の試合情報は見つかりませんでした")
                else:
                    match_id = result['match_id']
                    if match_id not in match_groups:
                        match_groups[match_id] = []
                    result['nickname'] = PLAYER_DICT[player_name]
                    match_groups[match_id].append(result)
                    logging.info(f"{PLAYER_DICT[player_name]}({player_name})の試合が見つかりました: {result['game_type']}")
                    
        except Exception as e:
            logging.error(f"エラーが発生しました（{PLAYER_DICT[player_name]}({player_name})）: {str(e)}")
            continue
        
        # プレイヤーごとに少し待機（サーバー負荷軽減のため）
        #time.sleep(1)
    
    # 結果の処理
    if match_groups or not_found_players:
        send_discord_notification(match_groups, not_found_players)
    
    # 使用済みデータの明示的なクリア
    match_groups.clear()
    not_found_players.clear()

def send_discord_notification(match_groups, not_found_players):
    category_messages = {category: [] for category in WEBHOOK_URLS.keys()}
    
    current_time = (datetime.now() + timedelta(hours=9)).strftime('%Y年%m月%d日 %H:%M:%S')
    
    for match_id, players in match_groups.items():
        # マッチごとにメッセージを作成
        match_message = f"> 🎮 **Match Found!**\n> {current_time}\n\n"
        match_message += f"▼ **試合情報**\n"
        
        # カテゴリごとのプレイヤーを分類
        category_players = {category: [] for category in WEBHOOK_URLS.keys()}
        game_type = players[0]['game_type']
        url = players[0]['url']
        
        for player in players:
            category = PLAYER_CATEGORIES.get(player['player_name'], 'friend')
            if player['nickname']:
                player_info = f"`{player['nickname']}:{player['player_name']}({player['champion']})`"
            else:
                player_info = f"`{player['player_name']}({player['champion']})`"
            category_players[category].append(player_info)
        
        # カテゴリごとにメッセージを作成
        for category, player_list in category_players.items():
            if player_list:  # そのカテゴリのプレイヤーが存在する場合
                category_message = match_message
                players_info = " / ".join(player_list)
                category_message += f"> プレイヤー：{players_info}\n"
                category_message += f"> 試合タイプ：`{game_type}`\n> {url}\n\n"
                category_messages[category].append(category_message)
    
    # カテゴリごとにWebhookを送信
    for category, messages in category_messages.items():
        if messages and WEBHOOK_URLS[category]:
            webhook = DiscordWebhook(url=WEBHOOK_URLS[category], content=''.join(messages))
            webhook.execute()

# グローバルセッションを作成
class SessionManager:
    _session = None
    
    @classmethod
    def get_session(cls):
        if cls._session is None:
            cls._session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            cls._session.mount("http://", adapter)
            cls._session.mount("https://", adapter)
        return cls._session

# グローバル変数として追加
not_found_player_notifications = {}  # {player_name: last_notification_time}

def get_player_webhook_url(player_name):
    """プレイヤーのカテゴリに基づいてWebhook URLを取得"""
    category = PLAYER_CATEGORIES.get(player_name, 'friend')
    return WEBHOOK_URLS.get(category, '')

def send_error_notification(player_name, error_message):
    """エラーノーティフィケーションを送信"""
    webhook_url = get_player_webhook_url(player_name)
    if webhook_url:
        webhook = DiscordWebhook(
            url=webhook_url,
            content=f"⚠️ **エラー**: `{PLAYER_DICT[player_name]}` (`{player_name}`) の情報取得中にエラーが発生しました。\n{error_message}"
        )
        webhook.execute()

def check_player_not_found(content, player_name):
    """プレイヤーが存在しないかチェック"""
    not_found_patterns = [
        'Summoner not found',
        'summoner not found',
        '404 - page not found',
        'summoner-not-found',
        'the summoner does not exist'
    ]
    return any(pattern in content for pattern in not_found_patterns)

def check_loading_state(content):
    """ローディング状態をチェック"""
    loading_patterns = [
        'damn, that\'s pretty slow to load',
        'loadmessage',
        'spinner'
    ]
    return any(pattern in content for pattern in loading_patterns)

def check_in_game(content):
    """試合中かチェック"""
    in_game_patterns = [
        'live-game-stats',
        'team stats',
        'game-status-ingame',
        'live game',
        'spectate'
    ]
    return any(pattern in content for pattern in in_game_patterns)

def extract_match_id(content):
    """コンテンツからマッチIDを抽出"""
    match_id = None
    result_td_start = content.find('class="resulttd"')
    if result_td_start != -1:
        href_start = content.find('href="https://www.leagueofgraphs.com/match/jp/', result_td_start)
        if href_start != -1:
            href_end = content.find('#', href_start)
            if href_end != -1:
                start_pos = href_start + len('href="https://www.leagueofgraphs.com/match/jp/')
                match_id = content[start_pos:href_end]
    return match_id

def extract_game_type(content):
    """コンテンツから試合タイプを抽出"""
    h2_start = content.find('<h2 class="left relative">')
    if h2_start != -1:
        h2_end = content.find('</h2>', h2_start)
        if h2_end != -1:
            game_type_text = content[h2_start:h2_end].split('\n')[1].strip().lower()
            type_mapping = {
                'ranked solo/duo': 'RANKED SOLO/DUO',
                'ranked flex': 'RANKED FLEX',
                'normal (quickplay)': 'NORMAL',
                'aram': 'ARAM',
                'arena': 'ARENA',
                'arurf 4v4': 'CUSTOM',
            }
            return type_mapping.get(game_type_text, "不明")
    return "不明"

def extract_champion(content, player_name):
    """コンテンツからチャンピオン名を抽出"""
    search_name = player_name.lower()
    card_start = content.find(f'<div class="card card-5" data-summonername="{search_name}"')
    if card_start == -1:
        return "不明"

    box_start = content.find('<div class="box championbox', card_start)
    if box_start == -1:
        box_start = content.find('class="championbox', card_start)
        if box_start == -1:
            return "不明"

    img_flex_start = content.find('<div class="imgflex', box_start)
    if img_flex_start == -1:
        return "不明"

    img_column_start = content.find('<div class="imgcolumn-champion', img_flex_start)
    if img_column_start == -1:
        return "不明"

    tooltip_start = content.find('<div class="relative requiretooltip', img_column_start)
    if tooltip_start == -1:
        return "不明"

    tooltip_class_start = content.find('tooltip="', tooltip_start)
    if tooltip_class_start == -1:
        return "不明"

    alt_start = content.find('alt="', tooltip_class_start)
    if alt_start == -1:
        return "不明"

    alt_end = content.find('"', alt_start + 5)
    if alt_end == -1:
        return "不明"

    return content[alt_start + 5:alt_end].capitalize()

def check_player_status(player_name):
    """プレイヤーの試合状態をチェック"""
    url_player_name = player_name.replace('#', '-')
    main_url = f"https://porofessor.gg/live/jp/{url_player_name}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': 'https://porofessor.gg/',
        'Cache-Control': 'no-cache'
    }

    try:
        logging.info(f"検索URL: {main_url}")

        session = SessionManager.get_session()
        response = session.get(main_url, headers=headers, timeout=10)
        if response is None:
            send_error_notification(player_name, "レスポンスがNoneです。プレイヤー名が間違っている可能性があります。")
            print(f'エラーが発生しました: レスポンスが None です')
            return "error"

        content = response.text.lower()

        save_html_log(player_name, content)

        display_name = PLAYER_DICT[player_name] if PLAYER_DICT[player_name] else player_name

        # プレイヤーが存在しない場合の判定
        if check_player_not_found(content, player_name):
            current_time = datetime.now().timestamp()
            last_notification = not_found_player_notifications.get(player_name, 0)
            
            # 3時間（10800秒）経過していれば通知
            if current_time - last_notification >= 10800:
                not_found_player_notifications[player_name] = current_time
                # プレイヤーのカテゴリを取得
                category = PLAYER_CATEGORIES.get(player_name, 'friend')
                webhook = DiscordWebhook(
                    url=WEBHOOK_URLS[category],
                    content=f"⚠️ **注意**: プレイヤー `{display_name}` が存在しません。プレイヤー名を確認してください。"
                )
                webhook.execute()
            
            print('判定結果: プレイヤーが存在しません')
            return "not_found"
        
        # 大きなレスポンスデータの参照を削除してメモリ解放
        response = None
        content = None  # contentも明示的に解放
        
        # ローディング状態の確認
        if check_loading_state(content):
            # APIエンドポイントを直接呼び出す
            api_url = f"https://porofessor.gg/partial/live-partial/jp/{url_player_name}"
            api_response = session.get(api_url, headers=headers, timeout=10)
            content = api_response.text

            # APIレスポンスのHTMLログも保存
            save_html_log(f"{player_name}_api", content)

            content = content.lower()

        # 試合中の判定
        if check_in_game(content):
            # マッチIDの取得
            match_id = extract_match_id(content)
            if not match_id:
                logging.warning(f"マッチIDの取得に失敗しました: {player_name}")
                return

            # 試合タイプの判定
            game_type = extract_game_type(content)

            # チャンピオンの判定
            champion = extract_champion(content, player_name)
            if champion == "不明":
                return
            
            # 現在のマッチ情報を作成
            current_match = {
                'match_id': match_id,
                'player_name': player_name,
                'champion': champion,
                'game_type': game_type,
                'url': main_url,
                'timestamp': (datetime.now() + timedelta(hours=9)).timestamp()
            }
            
            # プレイヤーの履歴を管理
            if player_name not in last_match_info:
                last_match_info[player_name] = []
            
            # 同じマッチがあるかチェック
            for match in last_match_info[player_name]:
                if match['match_id'] == current_match['match_id']:
                    logging.info(f"同じマッチをプレイ中のため、通知をスキップします: {player_name} (Match ID: {match_id})")
                    return
            
            # 新しいマッチを追加
            last_match_info[player_name].append(current_match)
            
            # 2マッチを超え場合、最も古いマッチを削除
            if len(last_match_info[player_name]) > MAX_MATCHES_PER_PLAYER:
                # タイムスタンプで並び替えて古いものを削除
                last_match_info[player_name].sort(key=lambda x: x['timestamp'], reverse=True)
                last_match_info[player_name] = last_match_info[player_name][:MAX_MATCHES_PER_PLAYER]
            
            logging.info(f'判定結果: 試合中です（{game_type}）- {champion}')
            return current_match  # マッチ情報を返すのみ

        # 試合中ではない場合��判定
        not_in_game_patterns = [
            'the summoner is not in-game',
            'summoner-offline',
            'not in-game',
            'please retry later',
            'must be on the loading screen'
        ]
        if any(pattern in content for pattern in not_in_game_patterns):
            print('判定結果: プレイヤーは試合中ではありません')
            return None  # 試合中でない場合はNoneを返す
        else:
            # ゲーム中でない場合の処理
            if player_name in last_match_info:
                # 最新の5マッチは保持
                matches = last_match_info[player_name]
                if matches:
                    matches.sort(key=lambda x: x['timestamp'], reverse=True)
                    last_match_info[player_name] = matches[:MAX_MATCHES_PER_PLAYER]
        print('レスポンスステータス:', response.status_code)
        print('レスポンス内容の一部:', content[:500])
        print('判定結果: 状態を特定できません')
        
    except Exception as e:
        error_message = f"プレイヤー名が間違っている可能性があります。確認をお願いします。\nエラー詳細: {str(e)}"
        send_error_notification(player_name, error_message)
        print(f'エラーが発生しました: {str(e)}')
        return "error"

def cleanup_old_data():
    """古いデータを定期的に削除（1.5時間以上経過したものを対象）"""
    current_time = datetime.now().timestamp()
    cleanup_threshold = 5400  # 1.5時間 = 5400秒

    players_to_remove = []

    for player in list(last_match_info.keys()):
        matches = last_match_info[player]
        original_count = len(matches)

        # 1.5時間以上前のデータを削除
        filtered_matches = [
            match for match in matches
            if current_time - match['timestamp'] < cleanup_threshold
        ]

        if filtered_matches:
            last_match_info[player] = filtered_matches
            removed_count = original_count - len(filtered_matches)
            if removed_count > 0:
                logging.info(f"{player}の古いマッチデータ{removed_count}件を削除しました")
        else:
            # 全てのデータが古い場合はプレイヤーごと削除
            players_to_remove.append(player)
            logging.info(f"{player}の全マッチデータを削除しました")

    # 不要なプレイヤーを削除
    for player in players_to_remove:
        del last_match_info[player]

    # 明示的なガベージコレクション
    gc.collect()

    # メモリ使用量のログ出力（デバッグ用）
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        import psutil
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        logging.debug(".1f")

def cleanup_old_notifications():
    """3時間以上経過した通知履歴を削除"""
    current_time = datetime.now().timestamp()
    for player_name in list(not_found_player_notifications.keys()):
        if current_time - not_found_player_notifications[player_name] >= 10800:
            del not_found_player_notifications[player_name]

def main():
    """メイン監視ループ"""
    logging.info("=== LeagueBirdWatcher 起動 ===")
    logging.info(f"監視対象プレイヤー数: {len(PLAYER_DICT)}")
    logging.info("有効カテゴリ: " + ", ".join(ACTIVE_CATEGORIES.keys()))

    for player_name, nickname in PLAYER_DICT.items():
        category = PLAYER_CATEGORIES.get(player_name, 'friend')
        logging.info(f"- {nickname or player_name} ({player_name}) [{category}]")

    cycle_count = 0

    while True:
        try:
            cycle_count += 1
            logging.info(f"=== 監視サイクル {cycle_count} 開始 ===")

            # 定期的なデータクリーンアップ（10サイクルごと）
            if cycle_count % 10 == 0:
                logging.info("定期クリーンアップを実行します")
                cleanup_old_data()
                cleanup_old_notifications()
            else:
                # 軽量クリーンアップ
                cleanup_old_notifications()

            # 全プレイヤーのチェック
            check_all_players()

            # Northflank最適化: メモリ使用量ログ（デバッグ時のみ）
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                try:
                    import psutil
                    memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                    logging.debug(".1f")
                except ImportError:
                    pass

            logging.info(f"監視サイクル {cycle_count} 完了。次のチェックまで300秒待機します")
            time.sleep(300)

        except Exception as e:
            logging.error(f"予期せぬエラーが発生しました: {str(e)}")
            logging.error(f"エラー詳細: {type(e).__name__}: {e}", exc_info=True)
            time.sleep(300)
            continue

if __name__ == "__main__":
    main()