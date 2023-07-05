import requests
import json
import os, logging

url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
sample_params = {
    "key": "your hotpeper key",
    "lat": "35.44838095046963",
    "lng": "139.6303173696368",
    "keyword": "ホルモン",
    "order": "4",
    "count": "3",
    "format": "json",
    "free_drink": 1,
#    "type": "lite",
}


# load config
def load_config():
    config_file = os.path.dirname(__file__) + "/config.json"
    config = None
    with open(config_file, 'r') as file:
        config = json.load(file)
    return config

def query_hotpepper(params):
    config = load_config()
    params["key"] = config["hotpepper_api_key"]
    params["format"] = "json"
    logging.debug('param: %s', params)
    response = requests.get(url, params=params)
    data = response.json()
    return data


def filtered_response(data, filter):
    shops = []
    for shop in data["results"]["shop"]:
        shops.append({key: shop[key] for key in filter})
    return json.dumps(shops, indent=4, ensure_ascii=False)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(funcName)s[%(lineno)d] - %(message)s")
    data = query_hotpepper(sample_params)
    filter = ["name",
                "access",
                "card",
                "catch",
                "genre",
                "free_drink",
                "free_food"
                ]
    print(filtered_response(data, filter))

if __name__ == '__main__':
    main()