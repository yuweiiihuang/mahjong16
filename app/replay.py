"""Record a bot hand or verify a private hand record offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bots.greedy import GreedyBotStrategy
from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import HandRecorder, replay_hand
from domain.rules.ruleset import Ruleset


def main() -> None:
    parser = argparse.ArgumentParser(description="離線牌譜紀錄與重播驗證（含隱藏牌資訊）")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="錄製一局機器人對局")
    record.add_argument("path", type=Path)
    record.add_argument("--seed", type=int, default=0)
    verify = commands.add_parser("verify", help="逐步檢查既有牌譜")
    verify.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "record":
            recorder = HandRecorder()
            env = Mahjong16Env(Ruleset(), seed=args.seed, recorder=recorder)
            env.reset()
            bot = GreedyBotStrategy()
            while not env.done:
                pid = env.turn if env.phase == "TURN" else env.pending_reactions()[0]
                env.step(bot.choose(env._obs(pid)), pid=pid)
            document = recorder.document()
            replay_hand(document)
            # Never overwrite an existing record accidentally.
            with args.path.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
        else:
            document = json.loads(args.path.read_text(encoding="utf-8"))
            replay_hand(document)
        print(f"驗證成功：{len(document['steps'])} 步，{document['status']}，"
              f"收付分 {document['settlement']['payments'] if document['settlement'] else '未完成'}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"失敗：{exc}\n")


if __name__ == "__main__":
    main()
