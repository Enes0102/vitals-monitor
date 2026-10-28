from collections import deque

BLOCKS = "▁▂▃▄▅▆▇█"


class History:
    def __init__(self, size=120):
        self.size = size
        self.series = {}

    def add(self, name, value):
        if name not in self.series:
            self.series[name] = deque(maxlen=self.size)
        self.series[name].append(value)

    def get(self, name):
        return list(self.series.get(name, []))

    def sustained(self, name, threshold, samples):
        values = self.get(name)
        if len(values) < samples:
            return False
        return all(value > threshold for value in values[-samples:])


def sparkline(values, width, maximum=None):
    values = values[-width:]
    if not values:
        return " " * width
    top = maximum if maximum is not None else max(values)
    chars = []
    for value in values:
        if top <= 0:
            chars.append(BLOCKS[0])
            continue
        level = int(min(max(value, 0), top) / top * (len(BLOCKS) - 1) + 0.5)
        chars.append(BLOCKS[level])
    return " " * (width - len(chars)) + "".join(chars)
