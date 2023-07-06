import openai
import json
import os
import sys
import logging
import langid



# 参考資料
# https://open-meteo.com/en/docs
# https://note.com/it_navi/n/ncc9f000967f2
# https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&daily=weathercode,temperature_2m_max,temperature_2m_min&current_weather=true&timezone=Asia%2FTokyo
# https://paiza.hatenablog.com/entry/2021/11/04/130000
# https://dev.classmethod.jp/articles/understand-openai-function-calling/

#
# Config
#
is_prompt_debug = True

#model01="gpt-4-0613"
model01="gpt-3.5-turbo-0613"
#model02="gpt-4-0613"
model02="gpt-3.5-turbo-0613"

get_weather_info_prompt = f'''
あなたは天気を説明するアナウンサーです
次の制約事項に従って入力文に簡潔に回答してください
#制約事項:
- 温度19度や湿度20%といった数字は今日の天気の場合もしくは大きな変動がある場合だけ使う
- 具体的な数字の代わりに暑苦しい、肌寒い、など感覚的な回答を行う
- 雨の可能性があれば傘をもって出かけるべきだと回答する
- 必ず30文字以内で答えよ
#入力文:
'''

get_pdf_info_prompt = f'''
次の条件に従って入力文に簡潔に回答してください
#条件:
複数の方法がある場合にはできるだけ複数の方法を答えよ
絶対に50文字以内で答えよ
わからない場合に嘘をついてはいけない。わからない場合にはわからないと答える。
#入力文:
'''

get_hotpepper_info_prompt = f'''
入力文から複数のレストランの情報をJSON形式で受け取ります。
おもわず行きたくなるうたい文句でレストランを簡潔に紹介しなさい。
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
    if(is_prompt_debug):
        print(f"選択された関数を呼び出す: {function_name}, {arguments}")
    if function_name == "get_weather_info":
        return get_weather_info(
            latitude=arguments.get("latitude"),
            longitude=arguments.get("longitude"),
        )
    elif function_name == "get_pdf_info":
        return get_pdf_info(arguments.get("query"))
    elif function_name == "get_hotpepper_info":
        #キーワードは日本語に変換する
        arguments['keyword'] = translate_text(arguments['keyword'], 'ja')
        return get_hotpepper_info(arguments)
    else:
        return None

# List of ISO 639-1 codes
# https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
#
ISO639 = {
    'ja': 'Japanese',
    'en': 'English',
    'zh': 'Chinese',
}
defualt_language = 'English'

def translate_text(text, lang):
    from_lang_id = langid.classify(text)[0]
    logging.info('from:%s(%s), to:%s(%s)',from_lang_id, ISO639[from_lang_id], lang, ISO639[lang])
    lang_to = ISO639.get(lang,defualt_language)
    lang_from = ISO639.get(from_lang_id, defualt_language)
    # lang に翻訳する
    if from_lang_id != lang:
        logging.info("%sに翻訳する:%s", ISO639.get(lang,defualt_language), text)
        completion = openai.ChatCompletion.create(
                # モデルを選択
                model     = "gpt-3.5-turbo-0613",
                # メッセージ
                messages  = [
                        {"role": "system", "content": f'You are a helpful assistant that translates {lang_from} to {lang_to}.'},
                        {"role": "user", "content": f'Translate the following {lang_from} text to {lang_to} :{text}. And Output only translated text'}
                        ] ,
                max_tokens  = 1024,             # 生成する文章の最大単語数
                n           = 1,                # いくつの返答を生成するか
                stop        = None,             # 指定した単語が出現した場合、文章生成を打ち切る
                temperature = 0,                # 出力する単語のランダム性（0から2の範囲） 0であれば毎回返答内容固定
            )
        text = completion.choices[0].message.content
    #
    if(is_prompt_debug):
        print(f"{lang_from}から{lang_to}に翻訳した:{text}")
    return text

def streaming_chat(input, callback):
    f_call = {'name': '', 'arguments': ''}
    final_response = ""
    #
    # 言語特定して多言語対応する
    # ja: Japanese
    # en: English
    #
    # 英語の場合には日本語に変換してから進める
    # function calling 毎のほうが良いかもしれない
    input_lang = langid.classify(input)[0]
    prompt_1 = translate_text("簡潔に答えよ。 ", input_lang) + input

    # 関数と引数を決定する
    # 関数を呼び出さない場合には ChatGPT が直接回答を返す
    #
    try:
        if(is_prompt_debug):
            print(f'prompt: {prompt_1}')
        response = openai.ChatCompletion.create(
            model=model01,
            messages=[{"role": "user", "content": prompt_1}],
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

    function_name = message["function_call"]["name"]
    #選択された関数に最適な prompt を選ぶ
    logging.info(f"選択された関数に最適な prompt を選ぶ: {function_name}")
    prompt_2 = f"絶対に{ISO639.get(input_lang, defualt_language)}で答えよ" + prompts[function_name] + input

    #
    # 入力文と同じ言語で回答文を作成する
    #
    prompt_2 = translate_text(prompt_2, input_lang)
    # text はここでかならず land_id になっていないとおかしい
    logging.info("prompt: %s, lang_id:%s", prompt_2, input_lang)

    try:
        if(is_prompt_debug):
            print(f'prompt: {prompt_2}')
        second_response = openai.ChatCompletion.create(
            model=model02,
            temperature = 0.2,
            stream = True,  # this time, we set stream=True
            messages=[
                {"role": "user", "content": prompt_2},
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

test_prompts = [
#    '横浜の明日の天気を教えてください',
#    '織田信長について教えて下さい',
#    'カーナビでインターネットを使いたい',
#    '桜木町の美味しいカフェを教えてください',
#   'Let me know what the weather will be like in Yokohama tomorrow.',
#    'Tell us about Nobunaga Oda.',
#    'I want to use the Internet with my car navigation system.',
    'Please let me know about good ramen in Sakuragicho.',
]

def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(filename)s:%(funcName)s[%(lineno)d] - %(message)s",
    )
    for prompt in test_prompts:
        print(chat(prompt, dummy_callback))

if __name__ == '__main__':
    main()