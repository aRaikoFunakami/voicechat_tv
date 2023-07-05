import openai
import json
import os
import logging
import query_hotpepper

#
# Config
#
model = "gpt-3.5-turbo-0613"

# load config
def load_config():
    config_file = os.path.dirname(__file__) + "/config.json"
    config = None
    with open(config_file, "r") as file:
        config = json.load(file)
    return config

def filtered_response(data, filter):
    shops = []
    for shop in data["results"]["shop"]:
        shops.append({key: shop[key] for key in filter})
    return shops


default_filter = ["name",
#            "access",
#           "card",
        "catch",
#            "genre",
#            "free_drink",
#           "free_food"
        ]

#
# call by openai functional calling
#
def get_hotpepper_info(params, filter = default_filter):
    logging.debug("params %s", params)
    shops = query_hotpepper.query_hotpepper(params)
    logging.debug("shops:%s", json.dumps(shops, indent=2, ensure_ascii=False))
    filtered_shops = filtered_response(shops, filter)
    logging.info("shops:%s", json.dumps(filtered_shops, indent=2, ensure_ascii=False))
    return json.dumps(filtered_shops, indent=2, ensure_ascii=False)

hotpepper_function = {
    "name": "get_hotpepper_info",
    "description": "レストラン情報を取得する",
    "parameters": {
        "type": "object",
        "properties": {
            "lat": {
                "type": "string",
                "description": "ある地点からの範囲内のお店の検索を行う場合の緯度です。",
                "example": "35.669220",
            },
            "lng": {
                "type": "string",
                "description": "ある地点からの範囲内のお店の検索を行う場合の経度です。",
                "example": "139.761457",
            },
            "keyword": {
                "type": "string",
                "description": "レストランのジャンル名を指定する。",
                "example": "139.761457",
            },
            "range": {
                "type": "integer",
                "description": "ある地点からの範囲内のお店の検索を行う場合の範囲を5段階で指定できます。たとえば300m以内の検索ならrange=1を指定します.500m以内ならrange=2.初期値は1000mでrange=3, 2000m以内ならrange=4, 3000以内ならrange=5",
                "example": "1",
                "notes": "1: 300m, 2: 500m, 3: 1000m (初期値), 4: 2000m, 5: 3000m",
            },
            "free_drink": {
                "type": "integer",
                "description": "「飲み放題」という条件で絞り込むかどうかを指定します。",
                "example": "0",
                "notes": "0:絞り込まない（初期値）, 1:絞り込む",
            },
            "free_food": {
                "type": "integer",
                "description": "「食べ放題」という条件で絞り込むかどうかを指定します。",
                "example": "0",
                "notes": "0:絞り込まない（初期値）, 1:絞り込む",
            },
			"count" : {
				"type": "integer",
				"description": "検索結果の最大出力データ数を指定します。",
				"example": "",
				"notes": "初期値:10、最小1、最大100",
			},
        },
        "required": [
            "lat",
            "lng",
            "keyword",
        ],
    },
}


def call_defined_function(message):
    function_name = message["function_call"]["name"]
    logging.debug("選択された関数を呼び出す: %s", function_name)
    arguments = json.loads(message["function_call"]["arguments"])
    if function_name == "get_hotpepper_info":
        return get_hotpepper_info(arguments)
    else:
        return None


def non_streaming_chat(text):
    # 関数と引数を決定する
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": text}],
            functions=[hotpepper_function],
            function_call="auto",
        )
    except openai.error.OpenAIError as e:
        error_string = f"An error occurred: {e}"
        print(error_string)
        return {"response": error_string, "finish_reason": "stop"}

    message = response["choices"][0]["message"]
    logging.debug("message: %s", message)
    # 選択した関数を実行する
    if message.get("function_call"):
        function_response = call_defined_function(message)
        #
        # Returns the name of the function called for unit test
        #
        return message["function_call"]["name"]
    else:
        return "chatgpt"


def chat(text):
    logging.debug(f"chatstart:{text}")
    config = load_config()
    openai.api_key = config["openai_api_key"]
    # situation = guess_situation(text)
    # q = guess_template.format(situation, text)
    q = template.format(text)
    return non_streaming_chat(q)


template = """'
条件:
- 50文字以内で回答せよ

入力文:
{}
"""


queries = [
    ["東京でおすすめの飲み放題プランのある中華レストランを3件教えて", "get_hotpepper_info"],
    ["東京でおすすめの食べ放題プランのあるイタリアンを教えて", "get_hotpepper_info"],
    ["大阪で安い居酒屋を探してください", "get_hotpepper_info"],
#    ["京都で有名な寿司店を教えてください", "get_hotpepper_info"],
#    ["札幌で人気のカフェを教えてください", "get_hotpepper_info"],
#    ["福岡で美味しいラーメン屋を探しています", "get_hotpepper_info"],
#    ["名古屋でおしゃれなバーを教えてください", "get_hotpepper_info"],
#    ["沖縄で海鮮料理が楽しめるレストランを探しています", "get_hotpepper_info"],
#    ["仙台でランチにおすすめのカレーレストランを教えてください", "get_hotpepper_info"],
#    ["神戸でハンバーガーが食べられるお店を探しています", "get_hotpepper_info"],
#    ["広島で居心地の良いカフェを教えてください", "get_hotpepper_info"],
]


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(filename)s:%(funcName)s[%(lineno)d] - %(message)s",
    )
    for query in queries:
        response = chat(query[0])
        print(f"[{query[1] == response}] 期待:{query[1]}, 実際:{response}, 質問:{query[0]}")

if __name__ == "__main__":
    main()
