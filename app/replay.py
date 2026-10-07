"""Record a bot hand or verify a private hand record offline."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from app.hand_store import (
    backup_database, open_private_record, stored_hand, stored_hands, write_private_record,
)
from app.training_export import SOURCES, decision_samples

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
    dataset = commands.add_parser('dataset', help='匯出玩家視角的 JSONL 決策資料')
    dataset.add_argument('path', type=Path)
    inputs = dataset.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--db', type=Path)
    inputs.add_argument('--record', type=Path)
    dataset.add_argument('--hand-id', help='只匯出 SQLite 的指定牌局')
    dataset.add_argument('--source', choices=(*SOURCES, 'all'), default='human')
    dataset.add_argument('--include-incomplete', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'dataset':
            if args.hand_id and not args.db:
                raise ValueError('--hand-id 只能搭配 --db。')
            if args.db:
                ids = ([args.hand_id] if args.hand_id else
                       [row['hand_id'] for row in stored_hands(args.db)
                        if args.include_incomplete or row['status'] == 'completed'])
                documents = [stored_hand(args.db, hand_id) for hand_id in ids]
            else:
                documents = [json.loads(args.record.read_text(encoding='utf-8'))]
            # ponytail: validate this small friends' dataset in memory before writing;
            # use a temporary streaming output if archives become too large for memory.
            rows = [row for document in documents for row in decision_samples(
                document, source=args.source, include_incomplete=args.include_incomplete)]
            with open_private_record(args.path) as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(f'已匯出 {len(rows)} 筆決策（來源：{args.source}）。')
            return
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
