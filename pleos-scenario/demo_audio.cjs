// Builds a demo video's sound track from the runner's sound log (/api/sounds) instead of recording the PC speakers.
// Recording the emulator's live output crackled (8-12 clicks per second of sound in the 10-30 videos, 0 in the merge step),
// so each sound is placed at the moment the car made it: family clips are the exact files the car fetched, and car speech
// is the same sentence from a CLOVA Dubbing recording (car_speech_lines.json), or Edge TTS for a sentence not recorded yet
// (the emulator's Pleos TTS voice itself cannot be captured cleanly).
const { execFileSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const CAR_VOICE = "ko-KR-HyunsuMultilingualNeural"; // family voices are SunHi, so the car gets a distinct voice
const EDGE_TTS = ["run", "--no-project", "--with", "edge-tts==7.3.1", "edge-tts"];
const VOICE_DIR = process.env.PLEOS_VOICE_DIR || `${process.env.HOME}/Android/voice`;
const SPEECH_CACHE = path.join(VOICE_DIR, "car_speech");
const RECORDED_SPEECH_DIR = path.join(VOICE_DIR, "car_speech_clova");
const RECORDED_SPEECH = require("./car_speech_lines.json"); // car sentence -> recorded file name
// CLOVA Dubbing's free plan requires the credit on screen for the first 5 seconds (help.naver.com 출처 표기 방법)
const VOICE_CREDIT = "클로바더빙의 AI 보이스가 사용되었습니다.";

async function soundsSince(base, sinceMs) {
  const r = await fetch(`${base}/api/sounds?since=${sinceMs / 1000}`);
  if (!r.ok) throw new Error(`소리 기록을 받지 못했습니다 (HTTP ${r.status})`);
  return (await r.json()).sounds;
}

async function clipFile(base, audioId, dir) {
  const r = await fetch(`${base}/api/audio/${audioId}`);
  if (!r.ok) throw new Error(`응원 녹음 ${audioId}를 받지 못했습니다 (HTTP ${r.status}) — 실행기가 보관하는 녹음은 최근 20개뿐입니다`);
  const file = path.join(dir, `clip_${audioId}.audio`);
  fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
  return file;
}

// the recorded sentence when there is one, else one Edge TTS synthesis per sentence, kept across runs
function speechFile(text) {
  const recorded = RECORDED_SPEECH[text] && path.join(RECORDED_SPEECH_DIR, RECORDED_SPEECH[text]);
  if (recorded && fs.existsSync(recorded)) return recorded;
  fs.mkdirSync(SPEECH_CACHE, { recursive: true });
  const file = path.join(SPEECH_CACHE, `${crypto.createHash("sha1").update(`${CAR_VOICE}\n${text}`).digest("hex").slice(0, 16)}.mp3`);
  if (!fs.existsSync(file)) {
    const tmp = `${file}.part`;
    execFileSync("uv", [...EDGE_TTS, "--voice", CAR_VOICE, "--text", text, "--write-media", tmp], { stdio: ["ignore", "ignore", "pipe"] });
    fs.renameSync(tmp, file);
  }
  return file;
}

// [{ file, offsetMs }] for every sound the car made after the video started
async function collectSounds(base, videoStartMs, workDir) {
  const sounds = await soundsSince(base, videoStartMs);
  const placed = [];
  for (const s of sounds) {
    const file = s.kind === "clip" ? await clipFile(base, s.audio_id, workDir) : speechFile(s.text);
    placed.push({ file, offsetMs: Math.max(0, Math.round(s.ts * 1000 - videoStartMs)), kind: s.kind });
  }
  return placed;
}

function muxWithSounds(webm, placed, mp4) {
  if (!placed.length) {
    // some scenarios only post to the family chat (e.g. ev_charge), so the car stays silent: keep a silent track
    execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", webm, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
      "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28",
      "-c:a", "aac", "-b:a", "192k", "-shortest", mp4]);
    return;
  }
  const inputs = placed.flatMap(p => ["-i", p.file]);
  const delayed = placed.map((p, i) =>
    `[${i + 1}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay=${p.offsetMs}:all=1[s${i}]`);
  const mix = `${placed.map((_, i) => `[s${i}]`).join("")}amix=inputs=${placed.length}:normalize=0:duration=longest,`
    + "loudnorm=I=-18:TP=-2,aresample=48000,apad[aout]"; // loudnorm works at 192 kHz; pad after it so it never sees the endless silence
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", webm, ...inputs,
    "-filter_complex", [...delayed, mix].join(";"),
    "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28",
    "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-shortest", mp4]);
}

// fixed credit badge at the top of the page for the first 5 s of the video, added in the page itself
function mountVoiceCredit([text, ms]) {
  if (window.top !== window) return; // not again inside the phone iframe
  const el = document.createElement("div");
  el.id = "voice-credit";
  el.textContent = text;
  el.style.cssText = "position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:100000;padding:8px 18px;"
    + "background:rgba(0,0,0,.9);color:#fff;border-radius:8px;font:700 20px 'NanumSquareRound','Noto Sans CJK KR',sans-serif";
  // an init script runs before the HTML is parsed, so the root element may not exist yet
  const mount = () => document.documentElement.appendChild(el);
  if (document.documentElement) mount();
  else new MutationObserver((_, obs) => { if (document.documentElement) { obs.disconnect(); mount(); } })
    .observe(document, { childList: true });
  // performance.now() counts from this document's start, which is after the page (and its video) was created
  setTimeout(() => el.remove(), Math.max(0, ms - performance.now()));
}

// Call before context.newPage(). The video starts with the page, on a blank document that init scripts skip and
// that stays up until the runner answers, so the badge goes onto that blank page at once and onto every new document
// by init script. Each new document restarts its 5 s, so the recording scripts navigate only once (one page.goto).
async function addVoiceCredit(context, ms = 5000) {
  const args = [VOICE_CREDIT, ms];
  await context.addInitScript(mountVoiceCredit, args);
  context.on("page", page => page.evaluate(mountVoiceCredit, args).catch(() => {}));
}

// 기능 ③·④ are opt-in on the car, so a recording first turns them on as the driver would on the settings card, and
// waits until the car confirms it (a car app started after the command, or a hub reset, would lose it). The usage log
// is not touched: keep the family consent off (or --no-analytics) while recording.
async function driverOptsInForDemo(base, timeoutMs = 10000) {
  const feed = async () => (await (await fetch(`${base}/api/family/feed?after=0`)).json()).items;
  const lastSeq = Math.max(0, ...(await feed()).map(i => i.seq));
  const r = await fetch(`${base}/api/driver/settings`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cheer_voice: true, safety_alert: true }),
  });
  if (!r.ok) throw new Error(`운전자 설정을 켜지 못했습니다 (HTTP ${r.status})`);
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    if ((await feed()).some(i => i.seq > lastSeq && i.text.startsWith("운전자 설정: 응원 듣기 켬 · 안전 운전 응원 켬"))) return;
    await new Promise(res => setTimeout(res, 300));
  }
  throw new Error("차가 운전자 설정을 받지 못했습니다 — 차량 앱이 실행 중이고 가족 서버에 연결됐는지 확인하세요");
}

module.exports = { collectSounds, muxWithSounds, addVoiceCredit, driverOptsInForDemo };
