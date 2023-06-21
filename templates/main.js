import { playAudioByVoiceVox } from "./playAudioByVoiceVox.js";
let isPushedMicButton = false;
let isSpeechRecognizing = false;
let isCanceledSpeechRecognition = false;
let eventSource = null;

const video = document.getElementById('video');
const microphone = document.getElementById('microphone');
microphone.disabled = true; // クリック禁止　スペースのみOK
const status = document.getElementById('status');
const answer = document.getElementById('answer');
const characterImage = document.getElementById('characterImage');

window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = new SpeechRecognition();
recognition.lang = 'ja-JP';

// zundamon
const zundamon = true;
let zundamon_speaking = false;
var zundamon_controller = null;
zundamon_controller = new AbortController();  // リクエスト中断用のAbortController


microphone.addEventListener('mousedown', startProcessing);
microphone.addEventListener('mouseup', stopProcessing);
window.addEventListener('keydown', (e) => {
	if (e.code === 'Space') startProcessing();
});
window.addEventListener('keyup', (e) => {
	if (e.code === 'Space') stopProcessing();
});

// 背景動画の音声を再生する 初期値は muted でないとautoplayできないためのダミー処理
document.addEventListener("mousedown", function () {
	video.play();
	video.muted = false;
});

// スクリーンショットを撮影し、画像URLを取得する処理
function screenshotImage() {
	// スクリーンショットを撮りたい要素を取得する
	const element = document.getElementById("video");

	// キャンバスを作成して要素のサイズに合わせる
	const canvas = document.createElement("canvas");
	canvas.width = element.offsetWidth;
	canvas.height = element.offsetHeight;

	// キャンバスに要素の内容を描画する
	const context = canvas.getContext("2d");
	context.drawImage(element, 0, 0, canvas.width, canvas.height);

	// キャンバスの内容を画像として表示するための新しいイメージ要素を作成
	const image = new Image();
	image.src = canvas.toDataURL(); // キャンバスの内容をデータURLに変換して設定
	return image;
}

// element 領域をアニメーションさせながら消す
//
// element.style.display = 'none'
// element.innerHTML=''
//
function hide_element_with_animation(element) {
	setTimeout(() => {
		// 画面を半分に縮小
		// 初期の状態を保存
		const initialTransform = element.style.transform;
		const initialTransition = element.style.transition;
		element.style.transform = "scale(0.5)";
		element.style.transition = "transform 0.5s";
		setTimeout(() => {
			// 要素の状態をリセット
			element.style.transform = initialTransform;
			element.style.transition = initialTransition;
			// 要素を隠す
			element.style.display = 'none';
			element.innerHTML = "";
		}, 1500);
	}, 1000);
}


recognition.addEventListener('start', function () {
	console.log('音声認識 開始');
	video.muted = true;
});

recognition.addEventListener('end', function () {
	console.log('音声認識 終了');
	isSpeechRecognizing = false;
	video.muted = false;
});

recognition.addEventListener('nomatch', function (event) {
	// 音声認識が一致しない結果を返した場合の処理
	onsole.log('音声認識 音声認識が一致しない結果を返した');
	isSpeechRecognizing = false;
	video.muted = false;
});

recognition.addEventListener('error', function (event) {
	onsole.log('音声認識 エラーが発生');
	isSpeechRecognizing = false;
	video.muted = false;
});
// 音声認識の途中結果が利用可能になったときの処理
//
// 1. 認識したテキストをChatGPTに送信して回答を受信する
// 2. ローカルで処理してしまうもの
// - スクリーンショット処理
//
recognition.addEventListener('result', (e) => {
	console.log('音声認識したテキスト:' + e.results[0][0].transcript);
	// 音声認識のためにミュートしていたのを解除
	video.muted = false;
	// キャンセル処理されている場合は処理を中断
	if (isCanceledSpeechRecognition) return;

	// 処理するテキスト
	const text = e.results[0][0].transcript;
	status.innerText = `"${text}" を認識しました`;

	// ローカルでの処理してしまう
	// スクリーンショット
	if (text.includes("スクリーンショット")) {
		console.log("スクリーンショットを実行する");
		// answer 領域を表示する
		answer.style.display = 'block';
		characterImage.style.display = 'blcok';
		// screenshot を撮影して answerへ表示
		const image = screenshotImage();
		answer.innerHTML = "";
		answer.appendChild(image);
		// status をアップデート
		status.innerText = 'スクリーンショットを撮影しました';
		// answer 領域をアニメーションさせながら消す
		hide_element_with_animation(answer);
		characterImage.style.display = 'none';
		return;
	}

	//
	// 音声読み上げ処理
	//
	const synth = window.speechSynthesis;
	// ストリーム受信したテキストを読み上げるためのバッファとフラグ
	let buffer = ''; // まだ読み上げていない文字を保持するバッファ
	let activeUtterances = 0;  // ストリームできているデータの全ての読み上げが終了したことを判定するためのカウンタ
	let endCallback = null;    // 全ての読み上げが終わった後に呼び出すコールバック関数
	const maxBufferSize = 40; // 最大バッファサイズ（これを超えたら読み上げを開始する）
	let delimiters = null; // 読み上げを開始するタイミングは デリミタを受信する、もしくはmaxBufferSizeを越えた場合
	if(!zundamon)
		delimiters = ['。', '.']; 
	else
		delimiters =  ['。','、',',', '.'];  // ずんだもんの場合には '、' や '', 'で切っても読みがおかしくならない
	
	// 音声読み上げ終了したら表示していたエリアを消す
	function endSpeakCallback() {
		hide_element_with_animation(answer);
		characterImage.style.display = 'none';
		status.innerText = '音声再生終了';
		video.muted = false;
		if(zundamon)
			zundamon_speaking = false;
	}

	// バッファのデータの読み上げとクリア
	function speakBuffer(callback) {
		// 全ての読み上げが終わった後に呼び出すコールバック関数を設定
		const endCallback = callback;
		// 音声再生前にビデオはミュートしてから再生する
		video.muted = true;
		status.innerText = "[ミュート中]"
		status.innerText = status.innerText + '音声再生中';
		// バッファにデータが残っていたら再生する
		if (buffer.trim() !== '' && !zundamon) {
			const utterThis = new SpeechSynthesisUtterance(buffer);
			// バッファにデータが残っていたら読み上げを続ける
			utterThis.onend = () => {
				// データが残っていれば読み上げる
				if (buffer !== '') {
					speakBuffer();
				}
				activeUtterances--;
				if (activeUtterances === 0 && typeof endCallback === 'function') {
					endCallback();
					status.innerText = '音声再生終了';
				}
			};
			// speak メソッドを呼び出す前にカウンタをインクリメント
			activeUtterances++;
			// 実際の読み上げ処理を行う。バッファ内のデータは読み上げ処理用のバッファに追加済みなのでクリアする
			synth.speak(utterThis);
			buffer = '';
		}else{
			// 実際の読み上げ処理を行う。バッファ内のデータは読み上げ処理用のバッファに追加済みなのでクリアする
			playAudioByVoiceVox(buffer, zundamon_controller.signal, endCallback);
			zundamon_speaking = true;
			buffer = '';   
		}
	}

	//
	// 認識したテキストをChatGPTに送信して回答を受信する
	// 
	// EventSourceでストリームデータを取得
	eventSource = new EventSource(`http://127.0.0.1:8001/input?text=${encodeURIComponent(text)}`);

	// ストリームで受け取ったデータを画面表示しつつ読み上げる
	eventSource.onmessage = function (event) {
		// const data = event.data;
		// event.dataをJSONにパース
		let jsonData = JSON.parse(event.data);
		const data = jsonData.response;
		// ストリームで受け取ったデータを徐々に表示する
		answer.style.display = 'block';
		characterImage.style.display = 'block';
		answer.innerHTML = answer.innerHTML + data;
		// レスポンス領域を自動スクロール
		answer.scrollTop = answer.scrollHeight;
		// ストリームデータを音声再生
		buffer += data;
		// デリミタが届いたか、バッファが最大サイズを超えたらバッファを読み上げてバッファを空にする
		if (delimiters.includes(data) || buffer.length >= maxBufferSize) {
			speakBuffer(endSpeakCallback);
		}
	};

	// connection が切れた場合も onerror が呼ばれるので close して自動で再接続を防ぐ
	eventSource.onerror = function (event) {
		console.error('Error occurred:', event);
		eventSource.close();
		// ステータス変更
		status.innerText = 'サーバーとの接続が終了しました。';
		// バッファが残っている場合はすべて読み上げる
		speakBuffer(endSpeakCallback);
		// ボリュームを戻す
		//video.muted = false;
	};

	eventSource.onopen = function (event) {
		console.log('Connection opened');
		status.innerText = `"${text}" をサーバーに送信しています...`;
	};
});

function startProcessing() {
	// Micボタンは一度 Down すると UP するまで再度 Down できない
	if (isPushedMicButton) return;
	isPushedMicButton = true;
	// 音声入力中の場合は無視する
	if (isSpeechRecognizing) return;
	// 
	// すでに動いている処理をキャンセル
	//
	// 読み上げ中なら読み上げをキャンセルする
	if (window.speechSynthesis.speaking) {
		window.speechSynthesis.cancel();
		console.log('読み上げをキャンセルしました');
		status.innerText = '読み上げをキャンセルしました';
		video.muted = false;
	}
	if (zundamon_speaking){
      // abort関数でシグナルオブジェクトに中断を送信
		zundamon_controller.abort();
		console.log('Request aborted!');
		zundamon_controller = new AbortController(); 
	}
	// ネットワークが接続中なら切る
	if (eventSource && eventSource.readyState !== EventSource.CLOSED) {
		console.log('ネットワーク接続の強制切断');
		eventSource.close();

	}
	// answer 画面が表示されている場合は消す
	if (answer.style.display != 'none'){
		answer.innerText = "";
		answer.style.display = 'none';
		characterImage.style.display = 'none';
	}
	//
	// 音声認識処理
	//
	isSpeechRecognizing = true;
	isCanceledSpeechRecognition = false;
	// Micボタンの色味変更
	microphone.style.filter = "brightness(0%) sepia(1000%) hue-rotate(0deg)";
	video.muted = true;
	status.innerText = "[ミュート中]"
	status.innerText = status.innerText + '音声認識を開始しています...';
	console.log('音声認識を開始する');
	recognition.start();
}

function stopProcessing() {
	// Micボタンは一度 Down すると UP するまで再度 Down できない
	isPushedMicButton = false;
	microphone.style.filter = "invert(100%) sepia(100%) saturate(0%) hue-rotate(0deg)";
	// 音声入力中の場合はキャンセル処理
	if (isSpeechRecognizing) {
		console.log('音声認識をキャンセルする');
		recognition.stop();
		isCanceledSpeechRecognition = true;
		status.innerText = '音声認識処理をキャンセルしました';
		return;
	}
}