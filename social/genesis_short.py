#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

ELEVEN_BASE = "https://api.elevenlabs.io"
DEFAULT_VOICE_NAME = "Haven Sands"
DEFAULT_VOICE_ID = "x8xv0H8Ako6Iw3cKXLoC"

BG = (7, 10, 12)
CARD = (17, 21, 25)
CARD_ALT = (12, 16, 19)
TEXT = (240, 244, 247)
MUTED = (150, 160, 170)
GREEN = (82, 232, 134)
BORDER = (44, 52, 60)
RED = (255, 105, 105)


def font(size, bold=False):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, width):
    words = text.split()
    lines, line = [], ""
    for word in words:
        trial = word if not line else f"{line} {word}"
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_wrapped(draw, xy, text, fnt, fill, width, line_gap=10):
    x, y = xy
    lines = wrap(draw, text, fnt, width)
    line_h = fnt.getbbox("Ag")[3] - fnt.getbbox("Ag")[1]
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h + line_gap
    return y


def render_feed(ep, output_path):
    W = 1080
    pad = 70
    inner = W - pad * 2
    body_font = font(39)
    body_bold = font(39, True)
    small = font(27)
    label = font(25, True)
    title = font(58, True)
    big = font(86, True)

    # First pass estimates height generously; the feed is intentionally taller than 9:16.
    H = 3600
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    y = 68
    d.text((pad, y), "GENESIS", font=title, fill=TEXT)
    d.text((pad, y + 72), "EXPERIMENT FEED", font=small, fill=GREEN)
    y += 138

    # Mission banner
    d.rounded_rectangle((pad, y, W - pad, y + 260), radius=28, fill=CARD_ALT, outline=GREEN, width=3)
    d.text((pad + 34, y + 28), "THE MISSION", font=label, fill=GREEN)
    y2 = draw_wrapped(d, (pad + 34, y + 74), ep["mission"], body_bold, TEXT, inner - 68, 12)
    d.text((pad + 34, y2 + 12), "No audience. No inventory. No pretending failures are wins.", font=small, fill=MUTED)
    y += 305

    for idx, post in enumerate(ep["posts"], start=1):
        # estimate card height based on wrapped body and optional metric block
        lines = wrap(d, post["body"], body_font, inner - 76)
        line_h = body_font.getbbox("Ag")[3] - body_font.getbbox("Ag")[1] + 12
        card_h = 116 + len(lines) * line_h + 62
        if post.get("metric"):
            card_h += 130
        if post.get("error"):
            card_h += 98
        card_top = y
        card_bottom = y + card_h
        d.rounded_rectangle((pad, card_top, W - pad, card_bottom), radius=30, fill=CARD, outline=BORDER, width=2)
        d.text((pad + 36, card_top + 28), f"ENTRY {idx:03d}", font=label, fill=GREEN)
        if post.get("kicker"):
            kicker_w = d.textlength(post["kicker"], font=label)
            d.text((W - pad - 36 - kicker_w, card_top + 28), post["kicker"], font=label, fill=MUTED)
        body_y = card_top + 84
        body_y = draw_wrapped(d, (pad + 36, body_y), post["body"], body_font, TEXT, inner - 72, 12)
        if post.get("error"):
            err_y = body_y + 24
            d.rounded_rectangle((pad + 36, err_y, W - pad - 36, err_y + 70), radius=18, fill=(35, 18, 18))
            d.text((pad + 58, err_y + 16), post["error"], font=body_bold, fill=RED)
            body_y = err_y + 78
        if post.get("metric"):
            metric_y = body_y + 24
            d.text((pad + 36, metric_y), post["metric_label"], font=small, fill=MUTED)
            d.text((pad + 36, metric_y + 40), post["metric"], font=big, fill=GREEN)
        y = card_bottom + 30

    # Scoreboard
    score_top = y + 8
    score_h = 430
    d.rounded_rectangle((pad, score_top, W - pad, score_top + score_h), radius=32, fill=CARD_ALT, outline=GREEN, width=3)
    d.text((pad + 36, score_top + 30), "CURRENT SCOREBOARD", font=label, fill=GREEN)
    rows = ep["scoreboard"]
    ry = score_top + 88
    for k, v in rows.items():
        d.text((pad + 36, ry), k.upper(), font=small, fill=MUTED)
        val_w = d.textlength(str(v), font=body_bold)
        d.text((W - pad - 36 - val_w, ry), str(v), font=body_bold, fill=TEXT if k.lower() != "revenue" else GREEN)
        ry += 62
    d.text((pad + 36, score_top + score_h - 72), ep["end_line"], font=body_bold, fill=TEXT)
    y = score_top + score_h + 90

    # crop unused bottom space
    img = img.crop((0, 0, W, max(y, 2500)))
    img.save(output_path, quality=95)


def get_voice_id(api_key, voice_name):
    headers = {"xi-api-key": api_key}
    # Prefer a voice already available in the account.
    r = requests.get(f"{ELEVEN_BASE}/v2/voices", headers=headers, params={"search": voice_name, "page_size": 100}, timeout=30)
    if r.ok:
        for v in r.json().get("voices", []):
            if v.get("name", "").strip().lower() == voice_name.lower():
                return v["voice_id"]

    # Haven Sands public library ID is known, but the API may require adding the shared voice to My Voices.
    # Search the shared library so we can safely add the exact matching voice when needed.
    s = requests.get(f"{ELEVEN_BASE}/v1/shared-voices", headers=headers, params={"search": voice_name, "page_size": 100}, timeout=30)
    if s.ok:
        exact = [v for v in s.json().get("voices", []) if v.get("name", "").strip().lower() == voice_name.lower()]
        if len(exact) == 1:
            v = exact[0]
            owner_id = v.get("public_owner_id")
            voice_id = v.get("voice_id")
            if owner_id and voice_id:
                add = requests.post(
                    f"{ELEVEN_BASE}/v1/voices/add/{owner_id}/{voice_id}",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"new_name": voice_name, "bookmarked": True},
                    timeout=30,
                )
                if add.ok:
                    return add.json().get("voice_id", voice_id)
                # If already added, the public ID can still be usable.
                if add.status_code in (400, 409, 422):
                    return voice_id

    # Last attempt: use the public Haven Sands ID directly.
    if voice_name.lower() == DEFAULT_VOICE_NAME.lower():
        return DEFAULT_VOICE_ID
    raise RuntimeError(f"Could not resolve ElevenLabs voice: {voice_name}")


def synthesize(api_key, voice_id, text, output_path):
    r = requests.post(
        f"{ELEVEN_BASE}/v1/text-to-speech/{voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.36,
                "similarity_boost": 0.78,
                "style": 0.32,
                "use_speaker_boost": True,
                "speed": 1.04,
            },
        },
        timeout=120,
    )
    if not r.ok:
        safe = r.text[:500]
        raise RuntimeError(f"ElevenLabs TTS failed ({r.status_code}): {safe}")
    Path(output_path).write_bytes(r.content)


def audio_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return max(1.0, float(result.stdout.strip()))


def render_video(feed_path, audio_path, output_path):
    dur = audio_duration(audio_path)
    # Hold the opening frame briefly, then continuously scroll to the scoreboard by the end.
    start_hold = min(2.5, dur * 0.1)
    y_expr = f"(ih-oh)*max(0,min(1,(t-{start_hold:.3f})/{max(0.1, dur-start_hold):.3f}))"
    filt = f"scale=1080:-2,crop=1080:1920:0:'{y_expr}',fps=30,format=yuv420p"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(feed_path), "-i", str(audio_path),
            "-vf", filt, "-map", "0:v:0", "-map", "1:a:0", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-shortest", str(output_path),
        ],
        check=True,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("episode")
    p.add_argument("--output-dir", default="social/output")
    args = p.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")

    episode_path = Path(args.episode)
    ep = json.loads(episode_path.read_text())
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    feed = out / "feed.png"
    audio = out / "narration.mp3"
    video = out / ep["output_filename"]
    caption = out / "caption.txt"

    render_feed(ep, feed)
    voice_name = ep.get("voice_name", DEFAULT_VOICE_NAME)
    voice_id = get_voice_id(api_key, voice_name)
    print(f"Using ElevenLabs voice: {voice_name} ({voice_id})")
    synthesize(api_key, voice_id, ep["voiceover"], audio)
    render_video(feed, audio, video)
    caption.write_text(ep["caption"].strip() + "\n")
    print(f"Rendered: {video}")


if __name__ == "__main__":
    main()
