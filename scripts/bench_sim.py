
from time import perf_counter
from core import Mahjong16Env, Ruleset
from bots import RandomBot

def main(n_games=50):
    env = Mahjong16Env(Ruleset(), seed=42)
    bot = RandomBot(seed=0)
    t0 = perf_counter()
    g = 0
    for _ in range(n_games):
        obs = env.reset()
        while True:
            a = bot.select(obs)
            obs, rew, done, info = env.step(a)
            if done:
                g += 1; break
    t1 = perf_counter()
    print(f"Played {g} games in {t1 - t0:.3f}s")

if __name__ == "__main__":
    main()
