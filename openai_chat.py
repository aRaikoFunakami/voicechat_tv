import openai
import json
import requests
import os
import sys
import logging
import box
import collections

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager

# 参考資料
# https://open-meteo.com/en/docs
# https://note.com/it_navi/n/ncc9f000967f2
# https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&daily=weathercode,temperature_2m_max,temperature_2m_min&current_weather=true&timezone=Asia%2FTokyo
# https://paiza.hatenablog.com/entry/2021/11/04/130000
# https://dev.classmethod.jp/articles/understand-openai-function-calling/

#
# Config
#
#model01="gpt-4-0613"
model01="gpt-3.5-turbo-0613"
#model02="gpt-4-0613"
model02="gpt-3.5-turbo-0613"

get_weather_info_prompt = f'''
あなたは天気を説明するアナウンサーです
次の条件に従って入力文に回答してください
#条件:
温度19度や湿度20%といった数字は今日の天気の場合もしくは大きな変動がある場合だけ使う
それ以外ではできれるだけ使わない
具体的な数字の代わりに暑苦しい、肌寒い、など感覚的な回答を行う
雨の可能性があれば傘をもって出かけるべきだと回答する
必ず50文字以内で答えよ
#入力文:
'''

get_manual_info_prompt = f'''
次の条件に従って入力文に回答してください
#条件:
簡潔に答えよ
複数の方法がある場合にはできるだけ複数の方法を答えよ
絶対に50文字以内で答えよ
わからない場合に嘘をついてはいけない。わからない場合にはわからないと答える。
#入力文:
'''

prompts = {
    "get_weather_info": get_weather_info_prompt,
    "get_manual_info" : get_manual_info_prompt,
}


# load config
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



def get_weather_info(latitude, longitude):
    base_url = "https://api.open-meteo.com/v1/forecast"
    parameters = {
        "latitude": latitude,
        "longitude": longitude,
        #        "current_weather": "true",
        "hourly": "temperature_2m,relativehumidity_2m",
        "timezone": "Asia/Tokyo"
    }
    response = requests.get(base_url, params=parameters)
    if response.status_code == 200:
        data = response.json()
        return json.dumps(data)
    else:
        return None

weather_function = {
    "name": "get_weather_info",
    "description": "緯度と経度の情報から現在の天気を取得します",
    "parameters": {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "string",
                "description": "緯度の情報",
            },
            "longitude": {
                "type": "string",
                "description": "経度の情報",
            },
        },
        "required": ["latitude", "longitude"],
    },
}

default_persist_directory = "./chroma_split_documents"
def get_manual_info(query):
    persist_directory = default_persist_directory
    config = load_config()
    openai.api_key = config["openai_api_key"]
    os.environ["OPENAI_API_KEY"] = openai.api_key
    logging.info("chatstart")
    # IF for asking OpenAI
    global llm, embeddings, vectorstore
    llm = ChatOpenAI(temperature=0, model_name=model01)
    embeddings = OpenAIEmbeddings()
    vectorstore = Chroma(embedding_function=embeddings,
                         persist_directory=persist_directory)
    docs = vectorstore.similarity_search(query, k=3)
    response = ""
    for i in docs:
        response = response + i.page_content + "\n"
    print(f'response:{response}')
    return response

# カーナビについての問い合わせにget_manual_infoを呼ぶ
# 例)
# カーナビに目的地を設定する方法を教えて
# カーナビでYouTubeを見る方法を教えて
#
manualpdf_function = {
    "name": "get_manual_info",
    "description": "カーナビの使用方法についての質問からカーナビの使い方を取得します",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "カーナビの使用方法についての質問",
            },
        },
        "required": ["query"],
    },
}

# 車についての問い合わせにget_manual_infoを呼ぶ
# 例) 
# 車の中のどこにUSBがあるの
#
manualpdf_function2 = {
    "name": "get_manual_info",
    "description": "車の使用方法についての質問から車の使い方を取得します",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "車の使用方法についての質問",
            },
        },
        "required": ["query"],
    },
}

def truncate_string(text, max):
    if(text is None):
        return ""
    if len(text) > max:
        return text[:max] + "..."
    else:
        return text

def non_streaming_chat(text):
    # 関数と引数を決定する
    try:
        response = openai.ChatCompletion.create(
            model=model01,
            messages=[{"role": "user", "content": text}],
            functions=[weather_function, manualpdf_function, manualpdf_function2],
            function_call="auto",
        )
    except openai.error.OpenAIError as e:
        error_string = f"An error occurred: {e}"
        print(error_string)
        return { "response": error_string, "finish_reason": "stop" }

    message = response["choices"][0]["message"]
    logging.info("message: %s", message)
    # 選択した関数を実行する
    if message.get("function_call"):
        function_name = message["function_call"]["name"]
        arguments=json.loads(message["function_call"]["arguments"])
        function_response = ""
        prompt = text
        # 選択された関数を呼び出す
        logging.info("選択された関数を呼び出す: %s", function_name)
        if function_name == "get_weather_info":
            function_response = get_weather_info(
                latitude=arguments.get("latitude"),
                longitude=arguments.get("longitude"),
            )
        #選択された関数に最適な prompt を選ぶ
        logging.info("選択された関数に最適な prompt を選ぶ")
        prompt = prompts[function_name] + text
        res = truncate_string(function_response, 100)
        logging.info("関数の回答:%s", res)
        try:
            second_response = openai.ChatCompletion.create(
                model=model02,
                temperature = 0.2,
                messages=[
                    {"role": "user", "content": prompt},
                    message,
                    {
                        "role": "function",
                        "name": function_name,
                        "content": function_response,
                    },
                ],
            )
        except openai.error.OpenAIError as e:
            error_string = f"An error occurred: {e}"
            print(error_string)
            return { "response": error_string, "finish_reason": "stop" }
        logging.info("関数を使って回答: %s", second_response.choices[0]["message"]["content"].strip())
        return { "response": second_response.choices[0]["message"]["content"].strip(), "finish_reason": "stop" }
    else:
        logging.info("ChatGPTが回答: %s", message.get("content"))
        return { "response": message.get("content"), "finish_reason": "stop" }

def call_defined_function(message):
    logging.info(message)
    function_name = message["function_call"]["name"]
    arguments=json.loads(message["function_call"]["arguments"])
    logging.info("選択された関数を呼び出す: %s", function_name)
    if function_name == "get_weather_info":
        return get_weather_info(
            latitude=arguments.get("latitude"),
            longitude=arguments.get("longitude"),
        )
    elif function_name == "get_manual_info":
        return get_manual_info(query=arguments.get("query"))
    else:
        return None

def streaming_chat(text, callback):
    f_call = {'name': '', 'arguments': ''}
    final_response = ""
    #
    # 関数と引数を決定する
    # 関数を呼び出さない場合には ChatGPT が直接回答を返す
    #
    try:
        text = "50文字以内で答えよ" + text
        response = openai.ChatCompletion.create(
            model=model01,
            messages=[{"role": "user", "content": text}],
            functions=[weather_function, manualpdf_function, manualpdf_function2],
            function_call="auto",
            stream=True
        )
        function_call = None
        for event in response:
            #print(f'event.choices[0] = {event.choices[0]}')
            delta = event.choices[0]["delta"]
            if (delta == {} and event.choices[0]["finish_reason"] == "function_call"):
                continue
            # 関数が見つかった場合は関数の情報を完成させて呼び出す
            # 関数が見つからない場合にはChatGPTがストリーミングでクライアントに回答する
            function_call = delta.get("function_call")
            if (function_call):
                # logging.info("関数が見つかった: %s", function_call)
                if (function_call.get("arguments")):
                    f_call['arguments'] = f_call['arguments'] + function_call.get("arguments")
                if (function_call.get("name")):
                    f_call['name'] = f_call['name'] + function_call.get("name")
            # 関数を使わない場合
            else:
                if event.choices[0]["finish_reason"] != "stop":
                    res = { "response": event.choices[0]["delta"]["content"], "finish_reason": ""}
                    callback(json.dumps(res))
                    final_response += res["response"]
                else:
                    res = { "response": "", "finish_reason": "stop"}
                    callback(json.dumps(res))
                    callback(None)
            # END: for event in response:

    except openai.error.OpenAIError as e:
        error_string = f"An error occurred: {e}"
        print(error_string)
        callback(error_string)
        callback(None)
        return { "response":error_string, "finish_reason": "stop"}
    #
    # 終了処理
    # 関数を利用しない場合は終了
    #
    logging.info('function_call:%s', f_call)
    if(not function_call):
        logging.info("ChatGPTが回答しました: %s", final_response)
        return { "response":final_response, "finish_reason": "stop"}
    #
    # 関数の呼び出し処理
    #
    message = {
        "content": None,
        "function_call": f_call,
        "role": "assistant"
    }
    function_response = call_defined_function(message)
    logging.info("関数の回答:%s", truncate_string(function_response, 100))
    #
    # ChatGPT呼び出しの初期化
    #
    prompt = text
    function_name = message["function_call"]["name"]
    #選択された関数に最適な prompt を選ぶ
    logging.info("選択された関数に最適な prompt を選ぶ")
    prompt = prompts[function_name] + text

    try:
        second_response = openai.ChatCompletion.create(
            model=model02,
            temperature = 0.2,
            stream = True,  # this time, we set stream=True
            messages=[
                {"role": "user", "content": prompt},
                message,
                {
                    "role": "function",
                    "name": function_name,
                    "content": function_response,
                },
            ],
        )
        final_response = ""
        for event in second_response:
            if event.choices[0]["finish_reason"] != "stop":
                res = { "response": event.choices[0]["delta"]["content"], "finish_reason": ""}
                callback(json.dumps(res))
                final_response = final_response + res["response"]
            else:
                res = { "response": "", "finish_reason": "stop"}
                callback(json.dumps(res))
                callback(None)
        logging.info("%s経由で回答しました: %s", function_name, final_response)
        return { "response": final_response, "finish_reason": "stop"}
    except openai.error.OpenAIError as e:
        error_string = f"An error occurred: {e}"
        print(error_string)
        callback(error_string)
        callback(None)
        return { "response": error_string, "finish_reason": "stop" }

def chat(text, callback = None):
    config = load_config()
    openai.api_key = config["openai_api_key"]
    logging.info("chatstart")
    if callback is None:
        return non_streaming_chat(text)
    else:
        return streaming_chat(text, callback)



def dummy_callback(response=None):
    if response is not None:
        logging.info(f'response:{response}')


def main(text):
    # non-streaming
    # print(chat(text))
    # streaming
    print(chat(text, dummy_callback))


question1 = "横浜の今日の天気を詳しく教えてください"
prompt1 = f'''
あなたは天気を説明するアナウンサーです
次の条件に従って入力文に回答してください
#条件:
温度19度や湿度20%といった数字はできるだけ使わず、暑苦しい、肌寒い、など感覚的な回答を行う
雨の可能性があれば傘をもって出かけるべきだと回答する
10文字以内で答えよ
#入力文:
{question1}
'''

question2 = "織田信長について答えよ"
prompt2 = f'''
10文字以内で答えよ
#入力文:
{question2}
'''

question3 = "インターネットを使いたい"
prompt3 = f'''
100文字以内で答えよ
#入力文:
{question3}
'''

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s:%(name)s - %(message)s")
    main(prompt1)
    main(prompt2)
    main(prompt3)