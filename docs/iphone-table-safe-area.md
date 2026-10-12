# iPhone 橫向牌桌：滿版與安全操作區

查核日期：2026-10-12。此筆記保留原始研究依據；目前已實作背景滿版、安全區自動等比例縮放與頂部資訊共排。C 的倍率／上下位移滑桿僅供原型比較，未加入正式設定。

## 官方與開源專案怎麼處理

- **WebKit：背景可以滿版，重要內容避開安全區。** Safari 預設會內縮；`viewport-fit=cover` 讓頁面延伸到螢幕邊緣，再透過 `env(safe-area-inset-*)` 保護內容。安全區不取代一般操作間距。這能讓綠色背景填滿左右，而不是讓可點擊手牌貼到 Home indicator。[WebKit 官方範例](https://webkit.org/blog/7929/designing-websites-for-iphone-x/)
- **Phaser：等比例完整顯示與等比例填滿是兩種取捨。** `FIT` 保留比例並完整放進容器，可能留邊；`ENVELOP` 保留比例並覆蓋容器，可能超出而裁切；`RESIZE` 直接改變 canvas 尺寸，不等同整組內容等比例放大。[Phaser 3.90.0 原始碼](https://github.com/phaserjs/phaser/blob/v3.90.0/src/scale/const/SCALE_MODE_CONST.js)
- **Godot：互動控制項使用安全矩形。** `DisplayServer.get_display_safe_area()` 回傳不被遮擋、適合放控制項的區域；原生 Android/iOS 有實作。這個概念可借用，但不能把原生 API 當成 Safari 網頁 API。[Godot 官方文件](https://docs.godotengine.org/en/stable/classes/class_displayserver.html#class-displayserver-method-get-display-safe-area)
- **Safari：可用視窗大小會改變。** `dvh` 隨動態 viewport 改變，`svh` 對應最小 viewport，`lvh` 對應最大 viewport。因此工具列開啟、隱藏與主畫面模式不能共用一個固定高度假設。[WebKit Safari 15.4 說明](https://webkit.org/blog/12445/new-webkit-features-in-safari-15-4/)

## 白色橫桿與網頁限制

白色橫桿是系統 Home indicator。UIKit 原生 App 可以要求延後邊緣系統手勢；這是原生 View Controller 的能力，不能直接用於 Safari/PWA。網頁應避免把常用操作放進那個區域，不能承諾關掉 Home 手勢。[Apple 原生 API](https://developer.apple.com/documentation/uikit/uiviewcontroller/preferredscreenedgesdeferringsystemgestures)

WebKit issue 236445 有主畫面網頁與 Safari 的 bottom inset 行為不同的回報；回報者指出加入 `viewport-fit=cover` 有改善。這是歷史問題及個別測試證據，不表示目前所有 iOS 都有同一個 bug，也不是保證通用的修法。[官方 issue 與重現步驟](https://bugs.webkit.org/show_bug.cgi?id=236445)

## Mahjong16 建議

1. **背景滿版，完整牌桌在安全操作區內統一等比縮放。** 維持四家手牌、副露、牌河的相對比例。先扣除左右安全 inset、底部 inset，再用完整牌桌內容 bounds 計算倍率；不要用包含大量空白的整張 canvas 計算。
2. **底部保留操作緩衝。** 以 bottom inset 再加 8–12 CSS px 當第一版候選，讓手牌點擊區與白色橫桿分開；這個額外值是設計假設，必須實機調整，不能保證零誤觸。
3. **上下位置可以調，但有邊界。** 原型 C 的位移調整用來比較構圖；正式版本採安全區內自動置中，不提供手動位移設定。
4. **工具列獨立留在安全區。** 設定、退出等按鈕避免跟牌桌一起被裁切。若原始牌桌比例與安全區比例不同，背景填滿剩餘空間；若強制內容填滿左右，必須接受上下裁切或重新排列，不能三者兼得。
5. **三種模式都實機測試。** 預設 Safari、隱藏工具列、主畫面模式；橫向左右兩個方向；含滿副露、滿牌河、聽牌提示及吃牌選項。模擬時畫出安全矩形、動態島與 Home indicator，檢查實際點擊區，不只看牌面。

未做實機誤觸測試；安全 inset 只提供佈局依據，不能代替觸控驗證。
