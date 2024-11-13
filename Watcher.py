import requests
from discord_webhook import DiscordWebhook
from datetime import datetime
import os
import time
import sys
from dotenv import load_dotenv
import logging

# .envファイルの読み込み
load_dotenv()

# 環境変数から設定を読み込み
PLAYER_LIST_STR = os.getenv('PLAYER_LIST', '')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# プレイヤーリストの作成
PLAYER_LIST = [player.strip() for player in PLAYER_LIST_STR.split(',') if player.strip()]

# 環境変数の検証
if not PLAYER_LIST:
    raise ValueError("PLAYER_LIST環境変数が設定されていないか、無効な形式です。")

if not DISCORD_WEBHOOK_URL:
    raise ValueError("DISCORD_WEBHOOK_URL環境変数が設定されていません。")

print("監視対象プレイヤー:")
for player in PLAYER_LIST:
    print(f"- {player}")

# 定数の設定
POROFESSOR_BASE_URL = "https://porofessor.gg/live/jp/"

# ログディレクトリの作成
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

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
for player in PLAYER_LIST:
    logging.info(f"- {player}")
logging.info("========================")

def save_response_to_log(content, status, url):
    # タイムスタンプを含むログファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(LOG_DIR, f"response_{timestamp}.log")
    
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"URL: {url}\n")
        f.write(f"Status Code: {status}\n")
        f.write("=" * 50 + "\n")
        f.write("Response Content:\n")
        f.write("=" * 50 + "\n")
        f.write(content)
    
    print(f"レスポンスをログファイルに保存しました: {log_filename}")

def check_all_players():
    for player_name in PLAYER_LIST:
        try:
            logging.info(f"\n{player_name}の状態をチェック中...")
            check_player_status(player_name)  # player_nameを引数として渡す
        except Exception as e:
            logging.error(f"エラーが発生しました（{player_name}）: {str(e)}")
            continue
    
    logging.info("\n全プレイヤーのチェックが完了しました。10分後に再度チェックを開始します。")

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
        
        session = requests.Session()
        response = session.get(main_url, headers=headers, timeout=10)
        content = response.text.lower()
        
        # ローディング状態の確認
        loading_patterns = [
            'damn, that\'s pretty slow to load',
            'loadmessage',
            'spinner'
        ]
        if any(pattern in content for pattern in loading_patterns):
            # APIエンドポイントを直接呼び出す
            api_url = f"https://porofessor.gg/partial/live-partial/jp/{url_player_name}"
            api_response = session.get(api_url, headers=headers, timeout=10)
            content = api_response.text.lower()


        # プレイヤーが存在しない場合の判定
        not_found_patterns = [
            'summoner not found',
            '404 - page not found',
            'summoner-not-found',
            'the summoner does not exist'
        ]
        if any(pattern in content for pattern in not_found_patterns):
            print('判定結果: プレイヤーが存在しません')
            return

        # 試合中の判定
        in_game_patterns = [
            'live-game-stats',
            'team stats',
            'game-status-ingame',
            'live game',
            'spectate'
        ]
        if any(pattern in content for pattern in in_game_patterns):
            # マッチIDの取得
            match_id = None
            result_td_start = content.find('class="resulttd"')
            if result_td_start != -1:
                href_start = content.find('href="https://www.leagueofgraphs.com/match/jp/', result_td_start)
                if href_start != -1:
                    href_end = content.find('#', href_start)
                    if href_end != -1:
                        start_pos = href_start + len('href="https://www.leagueofgraphs.com/match/jp/')
                        match_id = content[start_pos:href_end]

            if not match_id:
                logging.warning(f"マッチIDの取得に失敗しました: {player_name}")
                return
                
            # 試合タイプの判定
            game_type = "不明"
            
            # h2タグの内容を文字列検索で取得
            h2_start = content.find('<h2 class="left relative">')
            if h2_start != -1:
                h2_end = content.find('</h2>', h2_start)
                if h2_end != -1:
                    game_type_text = content[h2_start:h2_end].split('\n')[1].strip().lower()
                    
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
            card_start = content.find(f'<div class="card card-5" data-summonername="{search_name}"')
            if card_start == -1:
                return
            
            # 2. box championboxを探す（小文字で検索）
            box_start = content.find('<div class="box championbox', card_start)
            if box_start == -1:
                box_start = content.find('class="championbox', card_start)
                if box_start == -1:
                    return
            
            # 3. imgFlexを探す（小文字で検索）
            img_flex_start = content.find('<div class="imgflex', box_start)
            if img_flex_start == -1:
                return
            
            # 4. imgColumn-championを探す
            img_column_start = content.find('<div class="imgcolumn-champion', img_flex_start)
            if img_column_start == -1:
                return
            
            # 5. relative requireTooltipを探す
            tooltip_start = content.find('<div class="relative requiretooltip', img_column_start)
            if tooltip_start == -1:
                return
            
            # 6. tooltipの属性を探す
            tooltip_class_start = content.find('tooltip="', tooltip_start)
            if tooltip_class_start == -1:
                return
            
            # 7. img srcのalt属性を探す
            alt_start = content.find('alt="', tooltip_class_start)
            if alt_start == -1:
                return
            
            alt_end = content.find('"', alt_start + 5)
            if alt_end == -1:
                return
            
            champion = content[alt_start + 5:alt_end].capitalize()
            
            # 現在のマッチ情報を作成
            current_match = {
                'match_id': match_id,
                'player_name': player_name,
                'champion': champion,
                'game_type': game_type,
                'url': main_url,
                'timestamp': datetime.now().timestamp()
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
            
            # 現在の日時を取得
            current_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
            
            logging.info(f'判定結果: 試合中です（{game_type}）- {champion}')
            message = f"> ***Match Found!***\n> {current_time}\n> プレイヤー：`{player_name}`\n> チャンピオン：`{champion}`\n> 試合タイプ：`{game_type}`\n> マッチID：`{match_id}`\n> {main_url}"
            webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message)
            webhook.execute()
            return

        # 試合中ではない場合の判定
        not_in_game_patterns = [
            'the summoner is not in-game',
            'summoner-offline',
            'not in-game',
            'please retry later',
            'must be on the loading screen'
        ]
        if any(pattern in content for pattern in not_in_game_patterns):
            print('判定結果: プレイヤーは試合中ではありません')
            return
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
        
    except Exception as error:
        print('エラーが発生しました:', error)
        save_response_to_log(str(error), "ERROR", main_url)

def send_status_notification():
    current_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
    message = f"> **Watcher Status**\n> {current_time}\n> チェックを開始します。"
    try:
        webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message)
        webhook.execute()
        logging.info("ステータス通知を送信しました")
    except Exception as e:
        logging.error(f"ステータス通知の送信に失敗: {str(e)}")

def main():
    while True:
        try:
            send_status_notification()# チェック開始前に通知を送信
            check_all_players()  # 全プレイヤーをチェック
            time.sleep(300)  # 5分（300秒）待機
        except Exception as e:
            print(f"予期せぬエラーが発生しました: {str(e)}")
            time.sleep(300)  # エラー時も5分待機
            continue

if __name__ == "__main__":
    main()
