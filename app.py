import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import threading

# 環境変数読み込み
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Slack Bolt アプリ初期化
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

# LLM インスタンスを先に作成
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.8, openai_api_key=OPENAI_API_KEY)

# 1. タスク追加用プロンプトとチェーン
add_template = """以下のフォーマットでタスクを追加してください：
- タイトル: {{task}}
- 締め切り: {{due}}
ユーザーからの入力: 「{user_input}」"""
prompt_add = PromptTemplate(input_variables=["user_input", "task", "due"], template=add_template)
chain_add = LLMChain(llm=llm, prompt=prompt_add)

# 2. お礼メッセージ生成用プロンプトとチェーン
ack_template = """ユーザーがタスクを追加しました。AIはかわいらしく、フレンドリーにSlackで返信してください。

タスク情報:
{task_info}

---

【返信する文章】"""


prompt_ack = PromptTemplate(input_variables=["task_info"], template=ack_template)
chain_ack = LLMChain(llm=llm, prompt=prompt_ack)

# タスクストレージ設定
tasks = []  # 格納フォーマット: {'id', 'title', 'due', 'channel', 'completed'}
id_counter = 1
lock = threading.Lock()

# リマインダー処理
scheduler = BackgroundScheduler()
def check_reminders():
    now = datetime.now()
    with lock:
        for t in tasks:
            # 期限30分前リマインダー、かつ未通知のタスクのみ
            if not t['completed'] and not t.get('notified', False) and now >= t['due'] - timedelta(minutes=30):
                app.client.chat_postMessage(
                    channel=t['channel'],
                    text=f":alarm_clock: リマインダー：タスク『{t['title']}』の期限が近づいています！"
                )
                # 通知済みフラグを立てる
                t['notified'] = True
scheduler.add_job(check_reminders, 'interval', minutes=1)
scheduler.start()

# 3. Slash コマンドハンドラ
@app.command("/add-task")
def handle_add_task(ack, body, say):
    global id_counter
    ack()
    text = body.get("text", "")
    channel = body.get('channel_id')
    try:
        title, due_str = text.rsplit(" ", 1)
        due = datetime.fromisoformat(due_str)
    except ValueError:
        say("ごめんね💦 `/add-task タイトル YYYY-MM-DDThh:mm` の形式で入力してねっ🌸")
        return
    # AIでタスク登録内容を整形
    info = chain_add.run(user_input=text, task=title, due=due_str)
    # ストレージに保存
    with lock:
        tasks.append({
            'id': id_counter,
            'title': title,
            'due': due,
            'channel': channel,
            'completed': False
        })
        id_counter += 1
    # AIでお礼メッセージ生成
    reply = chain_ack.run(task_info=info)
    say(reply)

# /list-tasks: タスク一覧表示
@app.command("/list-tasks")
def handle_list_tasks(ack, body, say):
    ack()
    with lock:
        if not tasks:
            say("📋 タスクが登録されていません！")
            return
        message = "📋 現在のタスク一覧：\n"
        for t in tasks:
            status = '✅ 完了' if t['completed'] else '❌ 未完了'
            message += f"{t['id']}. {t['title']} - {status} - {t['due'].isoformat()}\n"
    say(message)

@app.command("/complete-task")
def handle_complete_task(ack, body, say):
    ack()
    text = body.get("text", "").strip()
    try:
        tid = int(text)
    except ValueError:
        say("使い方: `/complete-task タスクID` で完了マークをつけてね🌸")
        return
    with lock:
        for t in tasks:
            if t['id'] == tid:
                t['completed'] = True
                say(f":white_check_mark: タスク『{t['title']}』を完了にしたよ！")
                return
    say(f"ID {tid} のタスクが見つからなかったよ…❓")

    
# /add-task-modal: モーダルでタスク追加
@app.command("/add-task-modal")
def open_modal(ack, body, client):
    ack()
    client.views_open(
        trigger_id=body['trigger_id'],
        view={
            'type': 'modal',
            'callback_id': 'modal-add-task',
            'title': {'type': 'plain_text', 'text': 'タスク追加'},
            'submit': {'type': 'plain_text', 'text': '追加'},
            'blocks': [
                {
                    'type': 'input',
                    'block_id': 'title_block',
                    'element': {'type': 'plain_text_input', 'action_id': 'title_input'},
                    'label': {'type': 'plain_text', 'text': 'タイトル'}
                },
                {
                    'type': 'input',
                    'block_id': 'due_block',
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'due_input',
                        'placeholder': {'type': 'plain_text', 'text': 'YYYY-MM-DDThh:mm'}
                    },
                    'label': {'type': 'plain_text', 'text': '期限'}
                }
            ]
        }
    )

@app.view('modal-add-task')
def handle_modal_submission(ack, body, client, view):
    ack()
    title = view['state']['values']['title_block']['title_input']['value']
    due_str = view['state']['values']['due_block']['due_input']['value']
    try:
        due = datetime.fromisoformat(due_str)
    except ValueError:
        client.chat_postMessage(channel=body['user']['id'], text="期限フォーマットが正しくないよ…😢")
        return
    # コマンド処理に委譲
    pseudo_body = {'text': f"{title} {due_str}", 'user_id': body['user']['id'], 'channel_id': body['user']['id']}
    handle_add_task(lambda: None, pseudo_body, lambda msg: client.chat_postMessage(channel=body['user']['id'], text=msg))

if __name__ == '__main__':
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()