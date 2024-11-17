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
    'streamer': os.getenv('DISCORD_WEBHOOK_URL_STREAMER'),
    'friend': os.getenv('DISCORD_WEBHOOK_URL_FRIEND'),
    'smurf': os.getenv('DISCORD_WEBHOOK_URL_SMURF'),
    'troll': os.getenv('DISCORD_WEBHOOK_URL_TROLL')
}

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
        if not player_list_str:  # 空文字列の場合はスキップ
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
if not PLAYER_DICT:
    raise ValueError("PLAYER_LIST環境変数が設定されていないか、無効な形式です。")

if not WEBHOOK_URLS['streamer']:
    raise ValueError("DISCORD_WEBHOOK_URL_STREAMER環境変数が設定されていません。")

if not WEBHOOK_URLS['friend']:
    raise ValueError("DISCORD_WEBHOOK_URL_FRIEND環境変数が設定されていません。")

if not WEBHOOK_URLS['smurf']:
    raise ValueError("DISCORD_WEBHOOK_URL_SMURF環境変数が設定されていません。")

if not WEBHOOK_URLS['troll']:
    raise ValueError("DISCORD_WEBHOOK_URL_TROLL環境変数が設定されていません。")

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
    """HTMLレスポンスをログとして保存する関数"""
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
        logging.info(f"HTMLログを保存しました: {filename}")
    except Exception as e:
        logging.error(f"HTMLログの保存に失敗しました: {str(e)}")

def check_all_players():
    match_groups = {}
    not_found_players = []
    
    # ThreadPoolExecutorを使用して並列処理を実装
    with ThreadPoolExecutor(max_workers=10) as executor:  # max_workersは同時実行数
        # 各プレイヤーの処理を並列で実行
        future_to_player = {
            executor.submit(check_player_status, player_name): player_name 
            for player_name in PLAYER_DICT.keys()
        }
        
        # 結果を収集
        for future in concurrent.futures.as_completed(future_to_player):
            player_name = future_to_player[future]
            try:
                result = future.result()
                if result:
                    if result == "not_found":
                        not_found_players.append((player_name, PLAYER_DICT[player_name]))
                    else:
                        match_id = result['match_id']
                        if match_id not in match_groups:
                            match_groups[match_id] = []
                        result['nickname'] = PLAYER_DICT[player_name]
                        match_groups[match_id].append(result)
                        
            except Exception as e:
                logging.error(f"エラーが発生しました（{PLAYER_DICT[player_name]}({player_name})）: {str(e)}")
                continue
    
    if match_groups or not_found_players:
        send_discord_notification(match_groups, not_found_players)
    
    logging.info("\n全プレイヤーのチェックが完了しました。5分後に再度チェックを開始します。")

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

def check_player_status(player_name):
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
        
        # コンテンツを直接処理し、変数に保持しない
        save_html_log(player_name, response.text)
        content_lower = response.text.lower()
        
        # 大きなレスポンスデータの参照を削除
        response = None
        
        # ローディング状態の確認
        loading_patterns = [
            'damn, that\'s pretty slow to load',
            'loadmessage',
            'spinner'
        ]
        if any(pattern in content_lower for pattern in loading_patterns):
            # APIエンドポイントを直接呼び出す
            api_url = f"https://porofessor.gg/partial/live-partial/jp/{url_player_name}"
            api_response = session.get(api_url, headers=headers, timeout=10)
            content = api_response.text
            
            # APIレスポンスのHTMLログも保存
            save_html_log(f"{player_name}_api", content)
            
            content_lower = content.lower()
        
        # プレイヤーが存在しない場合の判定
        not_found_patterns = [
            'summoner not found',
            '404 - page not found',
            'summoner-not-found',
            'the summoner does not exist'
        ]
        if any(pattern in content_lower for pattern in not_found_patterns):
            print('判定結果: プレイヤーが存在しません')
            return "not_found"  # 存在しないプレイヤーの場合の戻り値を変更
            
        # 試合中の判定
        in_game_patterns = [
            'live-game-stats',
            'team stats',
            'game-status-ingame',
            'live game',
            'spectate'
        ]
        if any(pattern in content_lower for pattern in in_game_patterns):
            # マッチIDの取得
            match_id = None
            result_td_start = content_lower.find('class="resulttd"')
            if result_td_start != -1:
                href_start = content_lower.find('href="https://www.leagueofgraphs.com/match/jp/', result_td_start)
                if href_start != -1:
                    href_end = content_lower.find('#', href_start)
                    if href_end != -1:
                        start_pos = href_start + len('href="https://www.leagueofgraphs.com/match/jp/')
                        match_id = content_lower[start_pos:href_end]

            if not match_id:
                logging.warning(f"マッチIDの取得に失敗しました: {player_name}")
                return
                
            # 試合タイプの判定
            game_type = "不明"
            
            # h2タグの内容を文字列検索で取得
            h2_start = content_lower.find('<h2 class="left relative">')
            if h2_start != -1:
                h2_end = content_lower.find('</h2>', h2_start)
                if h2_end != -1:
                    game_type_text = content_lower[h2_start:h2_end].split('\n')[1].strip().lower()
                    
                    # 試合タイプのマッピング
                    type_mapping = {
                        'ranked solo/duo': 'RANKED SOLO/DUO',
                        'ranked flex': 'RANKED FLEX',
                        'normal (quickplay)': 'NORMAL',
                        'aram': 'ARAM',
                        'arena': 'ARENA',
                        'custom game': 'CUSTOM'
                    }
                    
                    game_type = type_mapping.get(game_type_text, "不明")

            # チャンピオンの判定
            champion = "不明"
            search_name = player_name.lower()
            
            # 1. プレイヤーのカードを見つける
            card_start = content_lower.find(f'<div class="card card-5" data-summonername="{search_name}"')
            if card_start == -1:
                return
            
            # 2. box championboxを探す（小文字で検索）
            box_start = content_lower.find('<div class="box championbox', card_start)
            if box_start == -1:
                box_start = content_lower.find('class="championbox', card_start)
                if box_start == -1:
                    return
            
            # 3. imgFlexを探す（小文字で検索）
            img_flex_start = content_lower.find('<div class="imgflex', box_start)
            if img_flex_start == -1:
                return
            
            # 4. imgColumn-championを探す
            img_column_start = content_lower.find('<div class="imgcolumn-champion', img_flex_start)
            if img_column_start == -1:
                return
            
            # 5. relative requireTooltipを探す
            tooltip_start = content_lower.find('<div class="relative requiretooltip', img_column_start)
            if tooltip_start == -1:
                return
            
            # 6. tooltipの属性を探す
            tooltip_class_start = content_lower.find('tooltip="', tooltip_start)
            if tooltip_class_start == -1:
                return
            
            # 7. img srcのalt属性を探す
            alt_start = content_lower.find('alt="', tooltip_class_start)
            if alt_start == -1:
                return
            
            alt_end = content_lower.find('"', alt_start + 5)
            if alt_end == -1:
                return
            
            champion = content_lower[alt_start + 5:alt_end].capitalize()
            
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

        # 試合中ではない場合の判定
        not_in_game_patterns = [
            'the summoner is not in-game',
            'summoner-offline',
            'not in-game',
            'please retry later',
            'must be on the loading screen'
        ]
        if any(pattern in content_lower for pattern in not_in_game_patterns):
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
        print('レスポンス内容の一部:', content_lower[:500])
        print('判定結果: 状態を特定できません')
        
    except Exception as error:
        print('エラーが発生しました:', error)

def cleanup_old_data():
    """古いデータを定期的に削除（1.5時間以上経過したものを対象）"""
    current_time = datetime.now().timestamp()
    cleanup_threshold = 5400  # 1.5時間 = 5400秒
    
    for player in list(last_match_info.keys()):
        matches = last_match_info[player]
        # 1.5時間以上前のデータを削除
        last_match_info[player] = [
            match for match in matches 
            if current_time - match['timestamp'] < cleanup_threshold
        ]
        
        # データが削除された場合はログに記録
        removed_count = len(matches) - len(last_match_info[player])
        if removed_count > 0:
            logging.info(f"{player}の古いマッチデータ{removed_count}件を削除しました")

def main():
    cleanup_counter = 0
    gc_counter = 0
    while True:
        try:
            check_all_players()
            
            # 1時間半以上経過したにデータをクリーンアップ
            cleanup_old_data()

            gc_counter += 1
            # 15分ごとにガベージコレクション実行
            if gc_counter >= 3:
                gc.collect()
                gc_counter = 0
                
            time.sleep(300)
            
        except Exception as e:
            logging.error(f"予期せぬエラーが発生しました: {str(e)}")
            time.sleep(300)
            continue

if __name__ == "__main__":
    main()