import os
import sys
import platform
import logging
import json

import openai
import chromadb
import langchain
from typing import Any

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager
from langchain.llms import OpenAI
from langchain.schema import AgentAction, AgentFinish, LLMResult


model_name = "gpt-3.5-turbo-0613"
# model_name = "gpt-4-0613"

default_persist_directory = "./chroma_split_documents"
# persist_directory="./chroma_load_and_split"

queries = [
    #    "Webブラウザを使いたい",
    "インターネットを使いたい",
    #    "YouTubeを見たい",
    #    "Google Mapを使いたい",
    # "カーナビの使い方を教えて",
    # "カーナビで目的地を検索したい",
    # "車の中のどこにUSBがあるの",
]

chat_history = []

q_template = '''
次の「制限事項」を満たした上で「入力文」に答えなさい

制限事項：
100文字以内の口語調で回答する。
あなたはすべての語尾に「なのだ」か「のだ」のうち自然な方を語尾につけて質問に答える。
YouTubeを利用したい場合は、WebブラウザでYouTubeのWebサイトを開く方法を答える。
Webサービスを利用したい場合は、WebブラウザでWebサービスのサイトを開く方法を答える。
Web動画サービスを利用したい場合は、WebブラウザでWeb動画サービスのサイトを開く方法を答える。
わからない場合に嘘をついてはいけない。わからない場合にはわからないと答える。

入力文:
'''


def load_config():
    args = sys.argv
    config_file = os.path.dirname(
        __file__) + "/config.json" if len(args) <= 1 else args[1]
    logging.info(config_file)
    with open(config_file, 'r') as file:
        config = json.load(file)
    return {
        "openai_api_key": config['openai_api_key'],
    }


llm = None
embeddings = None
vectorstore = None
pdf_qa = None


def init_chatPDF(streaming=False, persist_directory=None, callback = None):
    if (persist_directory is None):
        persist_directory = default_persist_directory
    config = load_config()
    openai.api_key = config["openai_api_key"]
    os.environ["OPENAI_API_KEY"] = openai.api_key
    logging.info("chatstart")
    # IF for asking OpenAI
    global llm, embeddings, vectorstore, pdf_qa
    llm = ChatOpenAI(streaming=streaming, temperature=0, model_name=model_name, callback_manager=CallbackManager([MyCustomCallbackHandler(callback)]))
    embeddings = OpenAIEmbeddings()
    vectorstore = Chroma(embedding_function=embeddings,
                         persist_directory=persist_directory)
    pdf_qa = ConversationalRetrievalChain.from_llm(
        llm, vectorstore.as_retriever(), return_source_documents=True)


def chat(text, callback = None):
    init_chatPDF(streaming = True, callback=callback)
    logging.info("callback: %s", callback)
    question = q_template + text
    result = pdf_qa({"question": question, "chat_history": chat_history})
    print(f'{model_name}:質問:{text}')
    print(f'{model_name}:回答:{result["answer"]}')
    # print(result)


def dummy_callback(response=None):
    if response is not None:
        logging.info(f'response:{response}')

class MyCustomCallbackHandler(BaseCallbackHandler):
    # constructor
    streaming_handler = None
    def __init__(self, callback):
        self.streaming_handler = callback

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        response = {"response": token, "finish_reason": ""}
        self.streaming_handler(json.dumps(response))

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        response = {"response": "", "finish_reason": "stop"}
        self.streaming_handler(json.dumps(response))


def main():
    # non-streaming
    init_chatPDF()
    for query in queries:
        print(chat(query))
    # streaming
    init_chatPDF(streaming=True)
    for query in queries:
        print(chat(query, dummy_callback))


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s:%(name)s - %(message)s")
    main()
