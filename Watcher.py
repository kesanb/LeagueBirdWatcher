import requests
from discord_webhook import DiscordWebhook
from datetime import datetime, timedelta
import os
import time
import sys
from dotenv import load_dotenv
import logging

# .envファイルの読み込み
load_dotenv()

# 環境変数から設定を読み込み
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# 環境変数の読み込み部分
def load_player_list():
    player_list_str = os.getenv('PLAYER_LIST', '')
    player_dict = {}
    nickname_to_player = {}
    for player_info in player_list_str.split(','):
        if ':' in player_info:
            nickname, name = player_info.strip().split(':')
            player_dict[name] = nickname
            nickname_to_player[nickname] = name
    return player_dict, nickname_to_player

# グローバル変数として定義
PLAYER_DICT, NICKNAME_TO_PLAYER = load_player_list()

# 環境変数の検証
if not PLAYER_DICT:
    raise ValueError("PLAYER_LIST環境変数が設定されていないか、無効な形式です。")

if not DISCORD_WEBHOOK_URL:
    raise ValueError("DISCORD_WEBHOOK_URL環境変数が設定されていません。")

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

def check_all_players():
    match_groups = {}
    not_found_players = []
    
    for player_name in PLAYER_DICT.keys():
        try:
            logging.info(f"\n{PLAYER_DICT[player_name]}({player_name})の状態をチェック中...")
            result = check_player_status(player_name)
            
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
    current_time = (datetime.now() + timedelta(hours=9)).strftime('%Y年%m月%d日 %H:%M:%S')
    message = f"> 🎮 **Match Found!**\n> {current_time}\n\n"
    
    # 試合中のプレイヤー情報を追加
    for match_id, players in match_groups.items():
        message += f"▼ **試合情報**\n"
        # ニックネーム:プレイヤー名(チャンピオン名)の形式で表示
        players_info = " / ".join([f"`{p['nickname']}:{p['player_name']}({p['champion']})`" for p in players])
        message += f"> プレイヤー：{players_info}\n"
        message += f"> 試合タイプ：`{players[0]['game_type']}`\n> {players[0]['url']}\n\n"
    
    # 存在しないプレイヤーの情報を追加
    if not_found_players:
        message += "▼ **存在しないプレイヤー**\n"
        message += "> 以下のプレイヤー名が見つかりませんでした。名前が間違っている可能性があります：\n"
        for player_name, nickname in not_found_players:
            message += f"> `{nickname}:{player_name}`\n"
    
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message)
    webhook.execute()

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
            return "not_found"  # 存在しないプレイヤーの場合の戻り値を変更
            
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
        if any(pattern in content for pattern in not_in_game_patterns):
            print('判定結果: プレイヤーは試合中ではありません')
            return None  # 試合中でい場合はNoneを返す
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

def main():
    while True:
        try:
            check_all_players()  # 全プレイヤーをチェック
            time.sleep(300)  # 5分（300秒）待機
        except Exception as e:
            print(f"予期せぬエラーが発生しました: {str(e)}")
            time.sleep(300)  # エラー時も5分待機
            continue

if __name__ == "__main__":
    main()