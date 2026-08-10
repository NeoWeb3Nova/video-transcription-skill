# Video Transcription Skill

A portable Hermes skill for turning video URLs or local video files into timestamped transcripts, cleaned text, summaries, translations, and structured notes.

## What it does

- prefers native captions via `yt-dlp`;
- falls back to Whisper via Groq or OpenAI when captions are unavailable;
- extracts selected video frames with `ffmpeg` for visual context;
- removes rolling subtitle duplicates and formats timestamped text;
- guides the agent to distinguish transcript evidence, edited synthesis, and uncertain ASR.

## Install for Hermes

```bash
git clone https://github.com/NeoWeb3Nova/video-transcription-skill.git ~/.hermes/skills/video-transcription
```

Restart Hermes or start a new session. The skill is then available automatically; it can also be loaded explicitly with `/skill video-transcription`.

## Dependencies

Linux/WSL:

```bash
sudo apt update
sudo apt install ffmpeg
python3 -m pip install --user yt-dlp
```

macOS:

```bash
brew install ffmpeg yt-dlp
```

Windows PowerShell:

```powershell
winget install Gyan.FFmpeg
a py -m pip install --user yt-dlp
```

Run the preflight from the cloned skill directory:

```bash
python3 ~/.hermes/skills/video-transcription/scripts/setup.py --json
```

## Optional Whisper fallback

Create `~/.config/watch/.env` and add your own key:

```env
GROQ_API_KEY=...
```

or:

```env
OPENAI_API_KEY=...
```

Keys are never included in this repository. Native captions work without an API key.

## Usage

```text
/watch https://example.com/video
```

For local files:

```text
/watch /absolute/path/to/video.mp4
```

The bundled script can also be run directly:

```bash
python3 ~/.hermes/skills/video-transcription/scripts/watch.py VIDEO --detail transcript
```

See `SKILL.md` for the complete workflow and quality rules.

## License

MIT
