import os
import sys


def normalize(char):
    if char in ("\r", "\n"):
        return "enter"
    if char in ("\x08", "\x7f"):
        return "backspace"
    if char == "\x1b":
        return "esc"
    if char == "\t":
        return "tab"
    if char == "\x03":
        raise KeyboardInterrupt
    if not char or not char.isprintable():
        return None
    return char


if os.name == "nt":
    import msvcrt

    SPECIAL_KEYS = {
        "H": "up",
        "P": "down",
        "K": "left",
        "M": "right",
        "I": "pageup",
        "Q": "pagedown",
        "G": "home",
        "O": "end",
    }

    class KeyReader:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            if not msvcrt.kbhit():
                return None
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                return SPECIAL_KEYS.get(msvcrt.getwch())
            return normalize(char)

else:
    import select
    import termios
    import tty

    ESCAPE_SEQUENCES = {
        "[A": "up",
        "[B": "down",
        "[C": "right",
        "[D": "left",
        "[5~": "pageup",
        "[6~": "pagedown",
        "[H": "home",
        "[F": "end",
        "OH": "home",
        "OF": "end",
    }

    class KeyReader:
        def __enter__(self):
            self.enabled = sys.stdin.isatty()
            if self.enabled:
                self.fd = sys.stdin.fileno()
                self.saved = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            return self

        def __exit__(self, *exc):
            if self.enabled:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
            return False

        def _ready(self, timeout=0.0):
            return bool(select.select([sys.stdin], [], [], timeout)[0])

        def _read_char(self):
            return os.read(self.fd, 1).decode(errors="ignore")

        def read(self):
            if not self.enabled or not self._ready():
                return None
            char = self._read_char()
            if char != "\x1b":
                return normalize(char)
            sequence = ""
            while len(sequence) < 4 and self._ready(0.01):
                sequence += self._read_char()
                if sequence[-1].isalpha() or sequence[-1] == "~":
                    break
            if not sequence:
                return "esc"
            return ESCAPE_SEQUENCES.get(sequence)
