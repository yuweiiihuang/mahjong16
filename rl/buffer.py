
from collections import deque
import random

class ReplayBuffer:
    def __init__(self, capacity=100_000, seed=None):
        self.buf = deque(maxlen=capacity)
        self.rng = random.Random(seed)
    def push(self, x): self.buf.append(x)
    def sample(self, n): 
        idxs = [self.rng.randrange(len(self.buf)) for _ in range(n)]
        return [self.buf[i] for i in idxs]
    def __len__(self): return len(self.buf)
