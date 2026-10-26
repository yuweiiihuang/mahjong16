// Mahjong16 process protocol, 2026-10-26. Original search stays in isolated vendor/.
#include "vendor/MctsLibrary/MctsPlayer.h"
#include <sstream>
#include <stdexcept>
#include <algorithm>

int number(std::istringstream& in, int low, int high) {
    int value;
    if (!(in >> value) || value < low || value > high) throw std::runtime_error("integer");
    return value;
}

class BridgePlayer : public MctsPlayer {
public:
    explicit BridgePlayer(const MctsPlayerConfig& config) : MctsPlayer(config) {}
    Move turn(const PlayerTile& hand, const RemainTile_t& unseen, const vector<Move>& legal) {
        resetup(hand, unseen);
        m_iDrawCount = DrawCountTable::getDrawCount(hand.getMinLack(), unseen.getRemainDrawNumber()/4);
        m_vLegalMoves = legal;
        runMcts();
        Move best = getBestMove();
        reset();
        return best;
    }
};

int main() {
    // Keep upstream diagnostics off the framed protocol, without changing search behavior.
    std::ostream protocol(std::cout.rdbuf());
    std::cout.rdbuf(std::cerr.rdbuf());
    try {
        Ini ini("config.ini");
        for (const string& key : {"MCTS.UseTime", "BaseConfig.UseTime", "MCTS.ThreadNum",
                                  "Multithread.ThreadNum", "Sgf.LogTreeSgf", "Sgf.LogGameSgf",
                                  "Debug.PrintDebugMsg", "TooManyMeldsStrategy.UseTooManyMeldsStrategy"})
            if (ini.getIntIni(key) != 0) throw std::runtime_error("config");
        if (!ini.getIntIni("MCTS.WaitReleaseTree") || !ini.getIntIni("MCTS.UseFlatMCMeld"))
            throw std::runtime_error("config");
        TileGroup::g_bFirstInit = true;
        MinLackTable_old::makeTable(MJGameType2::MJGameType_16);
        ExplorationTermTable::makeTable();
        MctsPlayerConfig config(ini);
        BridgePlayer player(config);
        protocol << "READY 1" << std::endl;
        string line;
        int lastSequence = 0;
        while (std::getline(std::cin, line)) {
            if (line.size() > 2048) throw std::runtime_error("frame");
            std::istringstream in(line);
            if (number(in, 1, 1) != 1) throw std::runtime_error("version");
            int sequence = number(in, 1, 1000000000);
            if (sequence <= lastSequence) throw std::runtime_error("sequence");
            lastSequence = sequence;
            int reaction = number(in, 0, 1), draws = number(in, 0, 120);
            array<int, 34> handCounts;
            for (int tile = 0; tile < 34; ++tile) handCounts[tile] = number(in, 0, 4);
            string handText;
            for (int suit = 0; suit < 4; ++suit) {
                string ranks;
                for (int rank = 0; rank < (suit < 3 ? 9 : 7); ++rank)
                    ranks += string(handCounts[(suit < 3 ? suit*9 : 27) + rank], char('1' + rank));
                if (!ranks.empty()) handText += ranks + (suit < 3 ? string(1, 'a'+suit) : "A") + " ";
            }
            if (handText.empty()) throw std::runtime_error("empty-hand");
            handText.pop_back();
            HandTile_t concealed(handText);
            vector<MeldTile> melds;
            int meldCount = number(in, 0, 5);
            for (int n = 0; n < meldCount; ++n) {
                int kind = number(in, 3, 6), tile = number(in, 0, 33);
                if (kind == 3 && (tile >= 27 || tile % 9 > 6))
                    throw std::runtime_error("chow");
                melds.emplace_back(Tile(tile), static_cast<MeldType>(kind));
            }
            if (concealed.getTileNumber() + 3 * meldCount != (reaction ? 16 : 17))
                throw std::runtime_error("hand-size");
            PlayerTile hand(concealed, melds);
            string counts;
            for (int tile = 0; tile < 34; ++tile) counts += char('0' + number(in, 0, 4));
            RemainTile_t unseen(counts, RemainTileType::Type_Playing);
            unseen.decreaseRemainDrawCount(unseen.getRemainDrawNumber() - draws);
            vector<Move> legal;
            int moveCount = number(in, 1, 64);
            for (int n = 0; n < moveCount; ++n) {
                int kind = number(in, 1, 10), tile = number(in, -1, 33);
                if ((reaction && kind != 1 && !(kind >= 4 && kind <= 8)) ||
                    (!reaction && kind != 3 && kind != 9 && kind != 10) ||
                    (kind == 1 ? tile != -1 : tile < 0)) throw std::runtime_error("move");
                legal.emplace_back(static_cast<MoveType>(kind), tile < 0 ? Tile() : Tile(tile));
            }
            string extra;
            if (in >> extra) throw std::runtime_error("extra");
            Move best;
            if (reaction) {
                GodMoveSampling_v3 sampling(hand, unseen);
                sampling.reset();
                for (const Move& move : legal)
                    sampling.makeMeldSamplingData(move.getTargetTile(), move.getMoveType());
                best = sampling.makeMoveDecision().m_oAction;
            } else {
                best = player.turn(hand, unseen, legal);
                bool hasKong = std::any_of(legal.begin(), legal.end(), [](const Move& move) {
                    return move.getMoveType() != MoveType::Move_Throw;
                });
                if (hasKong && best.getMoveType() == MoveType::Move_Throw) {
                    vector<Move> discards;
                    for (const Move& move : legal)
                        if (move.getMoveType() == MoveType::Move_Throw) discards.push_back(move);
                    best = player.turn(hand, unseen, discards);
                }
            }
            auto found = std::find_if(legal.begin(), legal.end(), [&](const Move& move) {
                return move.getMoveType() == best.getMoveType() &&
                       move.getTargetTile() == best.getTargetTile();
            });
            if (found == legal.end()) throw std::runtime_error("illegal-answer");
            protocol << "OK " << sequence << " " << std::distance(legal.begin(), found) << std::endl;
        }
    } catch (const std::exception& error) {
        protocol << "ERR " << error.what() << std::endl;
        return 2;
    }
    return 0;
}
