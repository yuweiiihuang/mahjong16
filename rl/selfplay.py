
from typing import Callable, Any

def self_play(env_ctor: Callable[[], Any], bot, n_episodes: int=10):
    dataset = []
    for _ in range(n_episodes):
        env = env_ctor()
        obs = env.reset()
        while True:
            act = bot.select(obs)
            nxt, rew, done, info = env.step(act)
            dataset.append((obs, act, rew, done))
            obs = nxt
            if done: break
    return dataset
