import openai
import json
import requests
import os
import sys
import logging
import box
import collections

# 参考資料
# https://open-meteo.com/en/docs
# https://note.com/it_navi/n/ncc9f000967f2
# https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&daily=weathercode,temperature_2m_max,temperature_2m_min&current_weather=true&timezone=Asia%2FTokyo
# https://paiza.hatenablog.com/entry/2021/11/04/130000
# https://dev.classmethod.jp/articles/understand-openai-function-calling/

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


get_weather_info_prompt = f'''
あなたは天気を説明するアナウンサーです
次の条件に従って入力文に回答してください
#条件:
温度19度や湿度20%といった数字は今日の天気の場合もしくは大きな変動がある場合だけ使う
それ以外ではできれるだけ使わない
具体的な数字の代わりに暑苦しい、肌寒い、など感覚的な回答を行う
雨の可能性があれば傘をもって出かけるべきだと回答する
150文字以内で答えよ
#入力文:
'''
prompts = {
    "get_weather_info": get_weather_info_prompt
}

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


def truncate_string(text, max):
    if len(text) > max:
        return text[:max] + "..."
    else:
        return text


def chat(text, callback=None):
    config = load_config()
    openai.api_key = config["openai_api_key"]
    logging.info("chatstart")

    # Non-Streaming
    if callback is None:
        # 関数と引数を決定する
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-0613",
                messages=[{"role": "user", "content": text}],
                functions=[weather_function],
                function_call="auto",
            )
        except openai.error.OpenAIError as e:
            error_string = f"An error occurred: {e}"
            print(error_string)
            return error_string
        
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
                    model="gpt-4-0613",
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
                return error_string
        
            return second_response.choices[0]["message"]["content"].strip()
        else:
            return { "response": message.get("content"), "urls": ["",] }
    # Streaming
    else:
        f_call = {'name': '', 'arguments': ''}
        final_response = ""
        # 関数と引数を決定する
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-0613",
                messages=[{"role": "user", "content": text}],
                functions=[weather_function],
                function_call="auto",
                stream=True
            )
            function_call = None
            for event in response:
                delta = event.choices[0]["delta"]
                if (delta == {}):
                    continue
                
                # 関数が見つかった場合は関数の情報を完成させて呼び出す
                # 関数が見つからない場合にはストリーミングでクライアントに回答する
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
                        res = { "response": event.choices[0]["delta"]["content"], "urls": [""]}
                        callback(json.dumps(res))
                        # callback(event.choices[0]["delta"]["content"])
                        final_response += res["response"]
                        
                    else:
                        callback(None) 
        except openai.error.OpenAIError as e:
            error_string = f"An error occurred: {e}"
            print(error_string)
            callback(error_string) 
            callback(None)
            return error_string
        # END: for event in response:
        
        # 関数を利用しない場合は終了
        if(not function_call):
            return { "response":final_response, "urls": [""]}
        
        # message を構築
        message = {
            "content": None,
            "function_call": f_call,
            "role": "assistant"
        }
        # 関数呼び出しの初期化
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
                model="gpt-4-0613",
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
                    res = { "response": event.choices[0]["delta"]["content"], "urls":[""]}
                    callback(json.dumps(res))
                    final_response = final_response + res["response"]
                else:
                    callback(None)
            return { "response": final_response, "urls": ["",] }
        except openai.error.OpenAIError as e:
            error_string = f"An error occurred: {e}"
            print(error_string)
            callback(error_string) 
            callback(None)
            return { "response": error_string, "urls": ["",] }
        

    # END: if callback is None:


def dummy_callback(response=None):
    if response is not None:
        logging.info(f'response:{response}')


def main(text):
    # non-streaming
    print(chat(text))
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

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s:%(name)s - %(message)s")
    main(prompt1)
    main(prompt2)
