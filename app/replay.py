"""Record a bot hand or verify a private hand record offline."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from app.hand_store import backup_database, stored_hand, stored_hands, write_private_record

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
    export = commands.add_parser("export", help="匯出 SQLite 的私有牌譜")
    export.add_argument("path", type=Path)
    export.add_argument("--db", type=Path, required=True)
    export.add_argument("--hand-id", required=True)
    listing = commands.add_parser("list", help="列出已保存的牌局")
    listing.add_argument("--db", type=Path, required=True)
    backup = commands.add_parser("backup", help="一致性備份 SQLite（不覆寫）")
    backup.add_argument("path", type=Path)
    backup.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'list':
            print(json.dumps(stored_hands(args.db), ensure_ascii=False, indent=2))
            return
        if args.command == 'backup':
            backup_database(args.db, args.path)
            print('備份完成。')
            return
        if args.command == 'export':
            document = stored_hand(args.db, args.hand_id)
            write_private_record(args.path, document)
            print(f"已匯出：{document['storage_status']}，{len(document['steps'])} 步。")
            return
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
            write_private_record(args.path, document)
        else:
            document = json.loads(args.path.read_text(encoding="utf-8"))
            replay_hand(document)
        print(f"驗證成功：{len(document['steps'])} 步，{document['status']}，"
              f"收付分 {document['settlement']['payments'] if document['settlement'] else '未完成'}")
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"失敗：{exc}\n")


if __name__ == "__main__":
    main()
