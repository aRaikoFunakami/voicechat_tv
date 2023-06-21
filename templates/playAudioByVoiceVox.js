let audioPlayQueue = Promise.resolve();
let audioGenerationQueue = [];

export function playAudioByVoiceVox(
	textData, 
	abortSignal=null,
	callback=null,
	audioQueryUrl = "http://127.0.0.1:50021/audio_query?speaker=1", 
	synthesisUrl = "http://127.0.0.1:50021/synthesis?speaker=1"
) {
	var audioQueryData = "&text=" + encodeURIComponent(textData);
	audioQueryUrl = audioQueryUrl + audioQueryData;

	let audioGeneration = fetch(audioQueryUrl, {
		method: "POST",
		headers: {
			"Content-Type": "application/x-www-form-urlencoded"
		},
		body: "",
		signal: abortSignal
	})
	.then(response => response.json())
	.then(data => {
		var jsonData = JSON.stringify(data);

		return fetch(synthesisUrl, {
			method: "POST",
			headers: {
				"Content-Type": "application/json"
			},
			body: jsonData,
			signal: abortSignal
		});
	})
	.then(response => response.blob())
	.then(blob => {
		var audio = new Audio();
		audio.src = URL.createObjectURL(blob);
		return audio;
	})
	.catch(error => {
		console.error("音声生成エラー:", error);
	});

	audioGenerationQueue.push(audioGeneration);

	audioPlayQueue = audioPlayQueue.then(() => {
		let nextAudio = audioGenerationQueue.shift();
		return nextAudio.then(audio => new Promise((resolve, reject) => {
			const handleAbort = () => {
				audio.pause();
				audio.src = '';
				audio.onended = null;
				URL.revokeObjectURL(audio.src);
				reject(new DOMException('Audio playback aborted', 'AbortError'));
			};
			
			if (abortSignal) {
				abortSignal.addEventListener('abort', handleAbort);
			}

			audio.onended = () => {
				if (abortSignal) {
					abortSignal.removeEventListener('abort', handleAbort);
				}
				if (audioGenerationQueue.length === 0 && callback) {
					callback();
				}
				resolve();
			};
			audio.play().catch(reject);
		}));
	})
	.catch(error => {
		console.error("再生エラー:", error);
	});
}
