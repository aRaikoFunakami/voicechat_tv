# original site of video
# https://commons.wikimedia.org/wiki/File:Big_Buck_Bunny_4K.webm
# https://upload.wikimedia.org/wikipedia/commons/transcoded/c/c0/Big_Buck_Bunny_4K.webm/Big_Buck_Bunny_4K.webm.720p.webm
from flask import Flask, render_template, request
import flask
import queue
import logging
import openai_chat
import threading

# フリー素材: https://icooon-mono.com/
app = Flask(__name__, static_folder='./templates', static_url_path='')


@app.route('/input', methods=["GET"])
def input():
    logging.info(request)
    input=request.args['text']
    qa_stream = queue.Queue() 
    def dummy_callback(response=None):
        qa_stream.put(response)
        #if response is not None:
        #    logging.info("response:%s",response)

    # callbackの処理を並行して動かすので別スレッドで ChatGPT に問い合わせる
    producer_thread = threading.Thread(target=openai_chat.chat, args=(input,dummy_callback))
    # LEXUS のマニュアルについて回答する
    # producer_thread = threading.Thread(target=openai_chatPDF.chat, args=(input,dummy_callback))
    producer_thread.start() 

    #
    def stream():
        while True:
            msg = qa_stream.get()
            # print(msg)
            if msg is None:
                break 
            yield f'data: {msg}\n\n'

    stream_res = flask.Response(stream(), mimetype='text/event-stream')
    return stream_res

@app.route('/')
def index():
    return render_template('index.html')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s:%(filename)s:%(funcName)s - %(message)s")
app.run(port=8001, debug=True)
