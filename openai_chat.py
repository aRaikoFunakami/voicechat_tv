import openai
import json
import requests
import os, sys
import logging

# 参考資料
# https://open-meteo.com/en/docs
# https://note.com/it_navi/n/ncc9f000967f2
# https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&daily=weathercode,temperature_2m_max,temperature_2m_min&current_weather=true&timezone=Asia%2FTokyo
# https://paiza.hatenablog.com/entry/2021/11/04/130000
# https://dev.classmethod.jp/articles/understand-openai-function-calling/

# load config
def load_config():
    args = sys.argv
    config_file = os.path.dirname(__file__) + "/config.json" if len(args) <=1 else args[1]
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


get_weather_info_prompt=f'''
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
prompts={
    "get_weather_info": get_weather_info_prompt 
}

weather_function =  {
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
    # 関数と引数を決定する
	response = openai.ChatCompletion.create(
		model="gpt-3.5-turbo-0613",
		messages=[{"role": "user", "content": text}],
		functions=[weather_function],
		function_call="auto",
	)
	print(f"一段目の処理結果\n使用する引数と関数が決定\n{response}")
	message = response["choices"][0]["message"]

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
		print(f"\nfunction_response:\n{res}\n")
		if callback is None:
			stream = False
		else:
			stream = True
		second_response = openai.ChatCompletion.create(
			model="gpt-4-0613",
			temperature = 0.2,
			stream = stream,  # this time, we set stream=True
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
		# print(f'second_response:{second_response}')
		response = ""
		# stream=False
		if callback is None:
			response = second_response.choices[0]["message"]["content"].strip()
		# stream=True
		else:
			for event in second_response:
				# print(f'event:{event.choices[0]}')
				if event.choices[0]["finish_reason"] != "stop":
					res = { "response": event.choices[0]["delta"]["content"], "urls":[""]}
					callback(json.dumps(res))
					#callback(event.choices[0]["delta"]["content"])
					response += event.choices[0]["delta"]["content"]
					# print(f'event:{event.choices[0]["delta"]["content"]}')
				else:
					callback(None)

		nhk_weather = 'https://www3.nhk.or.jp/news/weather/weather_movie.html'
		return { "response": response, "urls": [nhk_weather,] }
	else:
    # 関数を使わない場合はメッセージをそのまま返す
		response = { "response": message.get("content"), "urls": ["",] }
		if callback is not None:
			callback(json.dumps(response))
			callback(None)
		return response


def dummy_callback(response=None):
    if response is not None:
        print(f'response:{response}')

    
def main(text):
    # non-streaming
	chat(text)
	# streaming
	return chat(text, dummy_callback)


question="横浜の今日の天気を詳しく教えてください"
prompt=f'''
あなたは天気を説明するアナウンサーです
次の条件に従って入力文に回答してください
#条件:
温度19度や湿度20%といった数字はできるだけ使わず、暑苦しい、肌寒い、など感覚的な回答を行う
雨の可能性があれば傘をもって出かけるべきだと回答する
100文字以内で答えよ
#入力文:
{question}
'''

if __name__ == '__main__':
	logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s:%(name)s - %(message)s")    
	print(main(prompt))
