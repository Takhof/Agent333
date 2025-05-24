import os
from dotenv import load_dotenv
from slack_bolt import App
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from slack_bolt.adapter.socket_mode import SocketModeHandler


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
prompt = PromptTemplate(input_variables=["user_input", "task", "due"], template=add_template)
chain = LLMChain(llm=llm, prompt=prompt)

# 2. お礼メッセージ生成用プロンプトとチェーン
ack_template = """ユーザーがタスクを追加しました。AIはかわいらしく、フレンドリーにSlackで返信してください。

タスク情報:
{task_info}

---

【返信する文章】"""
ack_prompt = PromptTemplate(input_variables=["task_info"], template=ack_template)
ack_chain = LLMChain(llm=llm, prompt=ack_prompt)

# 3. Slash コマンドハンドラ
@app.command("/add-task")
def handle_add_task(ack, body, say):
    ack()
    text = body.get("text", "")
    try:
        task, due = text.split(" ", 1)
    except ValueError:
        say("ごめんね💦 `/add-task タイトル 期限` の形で送ってねっ🌸")
        return
    try:
        # タスク生成
        task_info = chain.run(user_input=text, task=task, due=due)
        # お礼メッセージ
        reply = ack_chain.run(task_info=task_info)
        say(reply)
    except Exception as e:
        say(f"エラーが起きちゃった…😢\n```{e}```")

if __name__ == '__main__':
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
