
from core import Mahjong16Env, Ruleset, hand_to_str, tile_to_str
from bots import RandomBot, RuleBot

def run_demo(rounds=1):
    env = Mahjong16Env(Ruleset(max_rounds=rounds), seed=42)
    bots = [RuleBot(), RandomBot(1), RandomBot(2), RandomBot(3)]
    obs = env.reset()
    step_no = 0
    print("=== mahjong16 demo (簡化版，含 drawn；尚未實作吃碰槓/胡) ===")
    while True:
        pid = obs["player"]
        bot = bots[pid]
        act = bot.select(obs)
        if act["type"] == "DISCARD":
            t = act["tile"]
            print(f"[{step_no:03d}] P{pid} DISCARD {tile_to_str(t)} | hand={hand_to_str(obs['hand'])} | drawn={tile_to_str(obs['drawn']) if obs['drawn'] is not None else None}")
        else:
            print(f"[{step_no:03d}] P{pid} {act['type']}")
        obs, rew, done, info = env.step(act)
        step_no += 1
        if done:
            print("=== round end ===")
            print("rewards:", rew)
            break

if __name__ == "__main__":
    run_demo()
