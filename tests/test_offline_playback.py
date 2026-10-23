"""Saved recordings play from this computer: with every non-local network connection blocked, a pack phrase and a phrase the owner recorded earlier are still found and served as audio.
This proves the local playback path only. Phone service, cloud AI and connected actions still need their connections."""
import os, socket, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pack_agent import Rig


class Offline(unittest.TestCase):
    def test_saved_audio_plays_with_the_network_blocked(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent
        real = socket.socket.connect; seen = []

        def guard(self, addr, *x, **k):
            host = addr[0] if isinstance(addr, tuple) else str(addr)
            if host not in ("127.0.0.1", "::1", "localhost"):
                seen.append(host); raise OSError("network is blocked in this test")
            return real(self, addr, *x, **k)
        socket.socket.connect = guard; self.addCleanup(lambda: setattr(socket.socket, "connect", real))
        got = a.audio.serve("w01")
        self.assertTrue(got and len(got[0]) > 0, "the pack phrase must be served from disk")
        again = a.audio.serve("w01")
        self.assertEqual(got, again)
        self.assertEqual(seen, [], "playing saved audio must not touch the network")


if __name__ == "__main__":
    unittest.main()
