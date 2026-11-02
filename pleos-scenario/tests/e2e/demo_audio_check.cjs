// Drives demo_audio.cjs against a running scenario server: the car says a recorded sentence at ~1 s and fetches a cheer clip
// at ~2 s, then the sound track is rebuilt onto a 4 s test video. Prints what was placed and where sound starts in the result.
// Usage: PLEOS_VOICE_DIR=<dir with car_speech_clova/car_08.wav> node demo_audio_check.cjs <base url> <work dir> <cheer wav>
const { execFileSync, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { collectSounds, muxWithSounds } = require("../../demo_audio.cjs");

const [base, work, cheerWav] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const post = (url, body, type) => fetch(base + url, { method: "POST", headers: { "Content-Type": type }, body });

function onsets(mp4) {
  // silencedetect reports on stderr
  const out = spawnSync("ffmpeg", ["-hide_banner", "-i", mp4, "-af", "silencedetect=n=-40dB:d=0.2", "-f", "null", "-"],
    { encoding: "utf8" }).stderr;
  return [...out.matchAll(/silence_end: ([\d.]+)/g)].map(m => Number(m[1]));
}

function audioStream(mp4) {
  const [codec, rate] = execFileSync("ffprobe", ["-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name,sample_rate",
    "-of", "csv=p=0", mp4], { encoding: "utf8" }).trim().split(",");
  return { codec, rate: Number(rate) };
}

(async () => {
  const video = path.join(work, "video.mp4");
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=4", video]);

  const start = Date.now();
  await sleep(1000);
  await post("/api/car/event", JSON.stringify({ kind: "speak", text: "알겠어요. 가족에게 전할게요." }), "application/json");
  await sleep(1000);
  const cheer = await (await post(`/api/family/cheer?sender=${encodeURIComponent("엄마")}&text=${encodeURIComponent("조심히 와")}`,
    fs.readFileSync(cheerWav), "audio/wav")).json();
  await (await fetch(`${base}/api/audio/${cheer.audio_id}`)).arrayBuffer(); // the car fetching the clip is when it plays

  const placed = await collectSounds(base, start, work);
  const mixed = path.join(work, "mixed.mp4");
  muxWithSounds(video, placed, mixed);
  const silent = path.join(work, "silent.mp4");
  muxWithSounds(video, [], silent);
  console.log(JSON.stringify({
    placed: placed.map(p => ({ kind: p.kind, file: p.file, offsetMs: p.offsetMs })),
    onsets: onsets(mixed), mixed: audioStream(mixed), silent: audioStream(silent),
  }));
})().catch(e => { console.error(e); process.exit(1); });
