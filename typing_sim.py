from random import choice, randint, uniform
import string
import time


class TypingSim:
    def __init__(self, to_type: str, wpm: int = 120,
                 variance_seconds: float = 0.1,
                 typo_percent: float = 0.5 # 1 in 200
                ) -> None:

        self.delay = 60 / (wpm * 5)
        self.variance_seconds = variance_seconds
        self.to_type = list(to_type)
        self.typo_percent = typo_percent

    def __iter__(self):
        return self

    def __next__(self) -> str:
        if not self.to_type:
            raise StopIteration
        char = self.to_type.pop(0)
        if uniform(0, 100) <= self.typo_percent:
            char = choice(string.ascii_lowercase if not char.isupper() else string.ascii_uppercase)
        time.sleep(self.delay + abs(uniform(-self.variance_seconds, +self.variance_seconds)))
        return char
