# Rule Coverage Report

- Generated (UTC): `2026-02-08 14:51:40Z`
- Baseline profile: `taiwan_base`
- Total rules: `38`
- Required coverage: `32/33`
- Gap counts: `P0=1`, `P1=0`, `P2=2`, `P3=0`

## P0 Findings
- `si_gang_pai` (四槓牌): profile=True, engine=False, tests=False

## P1 Findings
- None

## P2 Findings
- `zha_hu_penalty` (詐胡): profile=True, engine=False, tests=False
- `dealer_streak_cap_10` (連莊上限十次): profile=True, engine=False, tests=False

## P3 Findings
- None

## Coverage Matrix

| rule_id | zh_name | required | in_profile | in_engine | in_tests | gap_level |
|---|---|:---:|:---:|:---:|:---:|:---:|
| `dealer` | 莊家 | Y | Y | Y | Y | - |
| `quan_feng_ke` | 圈風牌 | Y | Y | Y | Y | - |
| `men_feng_ke` | 風位牌 | Y | Y | Y | Y | - |
| `zheng_hua` | 正花牌 | Y | Y | Y | Y | - |
| `hua_gang` | 花槓 | Y | Y | Y | Y | - |
| `zimo` | 自摸 | Y | Y | Y | Y | - |
| `menqing` | 門清 | Y | Y | Y | Y | - |
| `menqing_zimo` | 門清自摸 | Y | Y | Y | Y | - |
| `ping_hu` | 平胡 | Y | Y | Y | Y | - |
| `dragon_pung` | 三元牌 | Y | Y | Y | Y | - |
| `san_an_ke` | 三暗刻 | Y | Y | Y | Y | - |
| `si_an_ke` | 四暗刻 | Y | Y | Y | Y | - |
| `wu_an_ke` | 五暗刻 | Y | Y | Y | Y | - |
| `peng_peng_hu` | 碰碰胡 | Y | Y | Y | Y | - |
| `hun_yi_se` | 混一色 | Y | Y | Y | Y | - |
| `qing_yi_se` | 清一色 | Y | Y | Y | Y | - |
| `zi_yi_se` | 字一色 | N | Y | Y | Y | - |
| `xiao_san_yuan` | 小三元 | Y | Y | Y | Y | - |
| `da_san_yuan` | 大三元 | Y | Y | Y | Y | - |
| `xiao_si_xi` | 小四喜 | Y | Y | Y | Y | - |
| `da_si_xi` | 大四喜 | Y | Y | Y | Y | - |
| `du_ting` | 獨聽 | Y | Y | Y | Y | - |
| `ting` | 聽牌 | N | Y | Y | Y | - |
| `quan_qiu_ren` | 全求人 | Y | Y | Y | Y | - |
| `he_di` | 河底撈魚 | Y | Y | Y | Y | - |
| `hai_di` | 海底撈月 | Y | Y | Y | Y | - |
| `qiang_gang` | 搶槓 | Y | Y | Y | Y | - |
| `gang_shang` | 槓上自摸 | Y | Y | Y | Y | - |
| `qi_qiang_yi` | 七搶一 | Y | Y | Y | Y | - |
| `ba_xian` | 八仙過海 | Y | Y | Y | Y | - |
| `di_ting` | 地聽 | Y | Y | Y | Y | - |
| `tian_ting` | 天聽 | Y | Y | Y | Y | - |
| `ren_hu` | 人胡 | N | Y | Y | Y | - |
| `di_hu` | 地胡 | Y | Y | Y | Y | - |
| `tian_hu` | 天胡 | Y | Y | Y | Y | - |
| `si_gang_pai` | 四槓牌 | Y | Y | N | N | P0 |
| `zha_hu_penalty` | 詐胡 | N | Y | N | N | P2 |
| `dealer_streak_cap_10` | 連莊上限十次 | N | Y | N | N | P2 |
