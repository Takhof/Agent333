import os
from slack_bolt import App
from langchain import  LLMChain
from langchain.prompts import PromptTemplate
from openai import OpenAI
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI



load_dotenv()


SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)


template = """以下のフォーマットでタスクを追加してください：
- タイトル: {{task}}
- 締め切り: {{due}}
ユーザーからの入力: 「{user_input}」"""

prompt = PromptTemplate(input_variables=["user_input", "task", "due"], template=template)
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2, openai_api_key=OPENAI_API_KEY)
chain = LLMChain(llm=llm, prompt=prompt)

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
        result = chain.run(user_input=text, task=task, due=due)
        say(f"タスク追加したよっ💕\n{result}")
    except Exception as e:
        say(f"エラーが起きちゃった…😢\n```{e}```")

if __name__ == "__main__":
    app.start(port=int(os.getenv("PORT", 3000)))