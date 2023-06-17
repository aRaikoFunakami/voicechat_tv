# https://commons.wikimedia.org/wiki/File:Big_Buck_Bunny_4K.webm
# https://upload.wikimedia.org/wikipedia/commons/transcoded/c/c0/Big_Buck_Bunny_4K.webm/Big_Buck_Bunny_4K.webm.720p.webm
from flask import Flask, render_template, request
import json
#import openai_chat
#import selenium_browsing
import logging
import openai_chat

# フリー素材: https://icooon-mono.com/
app = Flask(__name__, static_folder='./templates', static_url_path='')


@app.route('/input', methods=["GET"])
def input():
    logging.info(request)
    input=request.args['text']
    return openai_chat.chat(input)

@app.route('/')
def index():
    return render_template('index.html')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s:%(name)s - %(message)s")    
app.run(port=8001, debug=True)
