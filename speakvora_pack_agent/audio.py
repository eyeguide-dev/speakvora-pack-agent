"""Gives the pack's audio a web address (Twilio fetches it to play on a call) and converts the pack's .m4a to .mp3 when needed. Conversion uses ffmpeg if it is installed; mp3 and wav files are served as they are."""
import hashlib, os, re, shutil, subprocess, time

TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}


class AudioError(Exception):
    pass


class AudioStore:
    def __init__(self, pack, cache_dir, public_base_url="", ffmpeg="ffmpeg"):
        self.pack, self.cache, self.base, self.ffmpeg = pack, os.path.join(cache_dir, "audio-cache"), public_base_url.rstrip("/"), ffmpeg
        os.makedirs(self.cache, exist_ok=True)

    def playable_file(self, ref):
        """A file Twilio can play (mp3 or wav) for this phrase, converting if needed."""
        src = self.pack.audio_path(ref); ext = os.path.splitext(src)[1].lower()
        if ext in (".mp3", ".wav"):
            return src
        out = os.path.join(self.cache, str(self.pack.get(ref)["id"]).replace(":", "_") + ".mp3")
        if os.path.exists(out):
            return out
        if not shutil.which(self.ffmpeg):
            raise AudioError("This pack's audio is .m4a, which phone calls cannot play. Install ffmpeg (for example 'brew install ffmpeg' or 'apt install ffmpeg') so the agent can convert it, or use the 'workflow lines' that come as mp3.")
        r = subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", src, "-ar", "22050", "-ac", "1", "-b:a", "48k", out], capture_output=True, timeout=60)
        if r.returncode != 0:
            raise AudioError("ffmpeg could not convert " + os.path.basename(src))
        return out

    def url(self, ref):
        if not self.base:
            raise AudioError("Set 'public_base_url' in agent.json: the public address where Twilio can reach this agent (for example an https tunnel to port 8787).")
        f = self.playable_file(ref)                                                # fails early (with a clear message) if the clip cannot be played
        return f"{self.base}/audio/{self.pack.get(ref)['id']}{os.path.splitext(f)[1].lower()}"

    def put_dynamic(self, data, ext, text, keep=False):
        """Stores one freshly voiced line (a live AI answer) and returns the address Twilio plays it from. Lines are cached by their words, so a repeated answer costs nothing, and kept for 30 days."""
        name = ("keep_" if keep else "talk_") + hashlib.sha1(text.encode("utf-8")).hexdigest()[:14]; out = os.path.join(self.cache, name + ".mp3")
        if not os.path.exists(out):
            raw = os.path.join(self.cache, name + ext)
            with open(raw, "wb") as f:
                f.write(data)
            if ext != ".mp3":
                if not shutil.which(self.ffmpeg):
                    raise AudioError("ffmpeg is needed to play new lines on a call")
                r = subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", raw, "-ar", "22050", "-ac", "1", "-b:a", "48k", out], capture_output=True, timeout=30)
                if r.returncode != 0:
                    raise AudioError("ffmpeg could not convert a new line")
            with open(os.path.join(self.cache, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(text)
            now = time.time()
            for fn in os.listdir(self.cache):
                if fn.startswith("talk_") and now - os.path.getmtime(os.path.join(self.cache, fn)) > 30 * 86400:
                    try:
                        os.remove(os.path.join(self.cache, fn))
                    except OSError:
                        pass
        if not self.base:
            raise AudioError("Set 'public_base_url' in agent.json.")
        return f"{self.base}/audio/{name}.mp3"

    def cached_dynamic(self, text, keep=False):
        name = ("keep_" if keep else "talk_") + hashlib.sha1(text.encode("utf-8")).hexdigest()[:14]
        return f"{self.base}/audio/{name}.mp3" if self.base and os.path.exists(os.path.join(self.cache, name + ".mp3")) else ""

    def dynamic_text(self, item_id):
        try:
            with open(os.path.join(self.cache, os.path.basename(item_id) + ".txt"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def serve(self, item_id):
        """(bytes, content_type) for GET /audio/<id>.mp3|wav, or None."""
        if re.fullmatch(r"(talk|keep)_[0-9a-f]{14}", item_id):
            try:
                return open(os.path.join(self.cache, item_id + ".mp3"), "rb").read(), "audio/mpeg"
            except OSError:
                return None
        try:
            f = self.playable_file(item_id)
        except Exception:  # noqa: BLE001
            return None
        return open(f, "rb").read(), TYPES.get(os.path.splitext(f)[1].lower(), "application/octet-stream")
