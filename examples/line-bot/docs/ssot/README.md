# SSOT（單一事實來源）目錄

## 精確導航

| 任務／程式路徑 | 正本 |
|---|---|
| src/main.py、src/handlers/ | [對應介面](../interface/webhook.md) |
| src/constants.py | [常數文件](constants.md) |
| src/config.py | [設定實作](../../src/config.py) |

已知正本可直接讀完整必要章節；不要求先讀本 index。常數值由程式正本定義，本目錄記錄契約。


## 原則
每個常數、關鍵字、訊息模板只在程式正本定義一次，其他地方 import 引用；此目錄記錄契約。

## 文件清單
- `constants.md`：關鍵字與訊息模板（對應 `src/constants.py`）
