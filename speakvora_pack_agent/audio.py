"""Gives the pack's audio a web address (Twilio fetches it to play on a call) and converts the pack's .m4a to .mp3 when needed. Conversion uses ffmpeg if it is installed; mp3 and wav files are served as they are."""
import os, shutil, subprocess

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

    def serve(self, item_id):
        """(bytes, content_type) for GET /audio/<id>.mp3|wav, or None."""
        try:
            f = self.playable_file(item_id)
        except Exception:  # noqa: BLE001
            return None
        return open(f, "rb").read(), TYPES.get(os.path.splitext(f)[1].lower(), "application/octet-stream")
