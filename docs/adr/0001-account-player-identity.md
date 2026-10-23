# 帳號由可信閘道驗證，牌桌保存獨立玩家 ID

狀態：已實作；2026-10-23 切換 Windows 公開部署，保留本機隔離驗證。

## 背景

瀏覽器 Cookie 只能維持原瀏覽器的座位，原牌譜代號每個房間重建。
朋友需要跨裝置識別與未來戰績／風格分析，但遊戲引擎不應處理登入憑證。
名稱可能重複或修改；Passkey 也可能新增、移除或恢復，因此兩者不能作為玩家主鍵。

## 決策

- Pocket ID／OIDC 代理負責驗證。Caddy 先刪除外部 `X-Qinghe-Subject`，
  再將成功驗證回應的 `X-Auth-Request-User` 改名傳入私有牌桌。
- 牌桌只有明確啟用 `--trusted-identity-issuer` 才接受這條整合。
  每個請求須同時具備私有閘道 Basic 憑證與單一、非空的 subject。
  不允許舊通行碼 Cookie 取代這份每次請求的憑證，也不相信請求 body 的 player ID。
- issuer 是管理員固定的伺服器設定，不接受瀏覽器送入的 issuer；目前 subject 限制為
  最多 255 個非空白 ASCII 字元且不含逗號，拒絕重複／合併的身分標頭。
- `HandStore.account_players` 將 `(issuer, subject)` 對應至隨機 UUID。
  SQLite 中的映射會保存；記憶體內的座位與練習桌仍不會在服務重啟後恢復。
- 牌譜、接管事件與決策只保存玩家 UUID、當時名稱與控制來源，不保存原始 issuer、
  subject、Cookie、Passkey credential ID 或登入 token。訓練輸出沿用原本 player_id 欄位。
- 帳號模式不讀取匿名身分 Cookie。同帳號多裝置共用一個房間座位；換帳號不繼承座位。
  未啟用整合時維持既有匿名 Cookie 流程與單機練習，不要求所有本機使用者登入。

映射表是對既有 version-1 私有資料庫的相容擴充，保留 user_version=1，
不改 hands 表或舊牌譜。舊版仍可讀取牌譜並忽略此表；回復部署亦須回復對應的
啟動參數與閘道設定。回復後匿名流程的新牌譜不會自動取得固定身分。

## 取捨與邊界

以名稱／email 合併帳號可能錯認兩個人；直接把 issuer/subject 寫進每筆牌譜則提高
隱私耦合與之後更換驗證服務的成本。獨立 UUID 避免這些問題，但其映射也必須備份。
新增驗證服務或更改 issuer 不會依名稱自動合併；若要延續原玩家 ID，需要管理員
明確的遷移流程，這次不提供帳號合併功能。

閘道持有後端憑證，閘道失守即可能冒用身分；這不是獨立的第二道登入驗證。
私有網路、憑證保護、驗證失敗時阻擋，以及原本座位／版本／操作檢查仍然必要。
SQLite 寫入失敗時回傳 503，不降級建立匿名玩家。沒有新增服務副本、戰績頁或
公開牌譜下載。正式 HTTPS、Windows Docker 與管理員 Passkey 註冊已驗證；
iPhone 及真人跨裝置／還原後金鑰登入尚待實機驗收。

2026-10-23 session 撤銷決策：代理採用官方 Redis session store，登出刪除對應
session，其他裝置不受影響。Redis 不持久化，重建只要求重新登入。
Pocket ID v2.19.1 的 userinfo 不足以判斷停用帳號，因此透過 offline_access 和
每秒 refresh token 檢查重新確認資格；不自行實作 token 簽章或密鑰驗證。
Caddy 另逐次驗證 access token，Pocket ID／Redis／代理故障皆阻擋牌桌請求。
這是有刷新間隔的撤銷，不保證零延遲或取消進行中的請求。刷新會延長 session TTL，
不把 12 小時 cookie 設定誤當成絕對登入期限。
