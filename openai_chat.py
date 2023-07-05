import openai
import json
import os
import sys
import logging


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

get_pdf_info_prompt = f'''
次の条件に従って入力文に回答してください
#条件:
簡潔に答えよ
複数の方法がある場合にはできるだけ複数の方法を答えよ
絶対に50文字以内で答えよ
わからない場合に嘘をついてはいけない。わからない場合にはわからないと答える。
#入力文:
'''

get_hotpepper_info_prompt = f'''
あなたは若い女性のアナウンサーです。
入力文から複数のレストランの情報をJSON形式で受け取ります。
それぞれのレストランの情報を30文字以内に要約してユーザーがその店に行きたくなるキャッチーな文章で答えなさい
#入力文:
'''


prompts = {
    "get_weather_info": get_weather_info_prompt,
    "get_pdf_info" : get_pdf_info_prompt,
    "get_hotpepper_info" : get_hotpepper_info_prompt,
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


#
# カーナビについての問い合わせに
#
from openai_function_weather import get_weather_info
from openai_function_weather import weather_function

#
# カーナビについての問い合わせに
#
from openai_function_pdf import get_pdf_info
from openai_function_pdf import pdf_function

#
# ホットペッパーでレストラン情報を取得する
#
from openai_function_hotpepper import get_hotpepper_info
from openai_function_hotpepper import hotpepper_function


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
    elif function_name == "get_pdf_info":
        return get_pdf_info(arguments.get("query"))
    elif function_name == "get_hotpepper_info":
        return get_hotpepper_info(arguments)
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
            functions=[weather_function, pdf_function, hotpepper_function],
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
                    callback(json.dumps(res, ensure_ascii=False))
                    final_response += res["response"]
                else:
                    res = { "response": "", "finish_reason": "stop"}
                    callback(json.dumps(res, ensure_ascii=False))
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
    logging.info("関数の回答:%s", function_response)
    #
    # ChatGPT呼び出しの初期化
    #
    prompt = text
    function_name = message["function_call"]["name"]
    #選択された関数に最適な prompt を選ぶ
    logging.info(f"選択された関数に最適な prompt を選ぶ: {function_name}")
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
                callback(json.dumps(res, ensure_ascii=False))
                final_response = final_response + res["response"]
            else:
                res = { "response": "", "finish_reason": "stop"}
                callback(json.dumps(res, ensure_ascii=False))
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
    return streaming_chat(text, callback)

#
# test codes
#
def dummy_callback(response=None):
    if response is not None:
        logging.info(f'response:{response}')

test_questions = []
test_prompts = []

test_questions.append("横浜の今日の天気を詳しく教えてください")
test_prompts.append(f'''
あなたは天気を説明するアナウンサーです
次の条件に従って入力文に回答してください
#条件:
温度19度や湿度20%といった数字はできるだけ使わず、暑苦しい、肌寒い、など感覚的な回答を行う
雨の可能性があれば傘をもって出かけるべきだと回答する
10文字以内で答えよ
#入力文:
{test_questions[0]}
''')

test_questions.append("織田信長について答えよ")
test_prompts.append(f'''
10文字以内で答えよ
#入力文:
{test_questions[1]}
''')

test_questions.append("カーナビでインターネットを使いたい")
test_prompts.append(f'''
100文字以内で答えよ
#入力文:
{test_questions[2]}
''')

test_questions.append("横浜の桜木町あたりで美味しいホルモンの店を３件紹介して")
test_prompts.append(f'''
100文字以内で答えよ
#入力文:
{test_questions[3]}
''')

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(filename)s:%(funcName)s[%(lineno)d] - %(message)s",
    )
    for prompt in test_prompts:
        print(chat(prompt, dummy_callback))

if __name__ == '__main__':
    main()