# NoteVault

iCloudを使わずに、iPhoneのApple NotesをPCまたはUSBへ一括エクスポートするローカルファースト・ツールです。
WindowsPC上に保存された標準のiTunes / Finderバックアップから直接動作します。

> **ステータス: MVP-1（テキスト救出）** — コアの縦断スライスが動作しています。
> フォルダ階層の再現とリッチテキスト（Protobuf）対応は後続マイルストーンで予定しています。

---

## 目次

- [前提条件](#前提条件)
- [インストール](#インストール)
- [クイックスタート](#クイックスタート)
- [ステップごとの使い方](#ステップごとの使い方)
- [出力サンプル](#出力サンプル)
- [トラブルシューティング](#トラブルシューティング)
- [既知の制限](#既知の制限)

---

## 前提条件

| 要件 | 備考 |
|------|------|
| Python 3.11以上 | [python.org](https://www.python.org/) |
| iTunesまたはFinderのバックアップ | **暗号化なし**でローカルに保存されていること |
| Windows 10 / 11 | 主要ターゲット。macOS/Linuxはベストエフォート対応 |

### 暗号化なしのローカルバックアップを作成する

1. **iTunes**（Macでは**Finder**）を開き、iPhoneを接続します。
2. 「バックアップ」の項目で**「このコンピュータ」**を選択します。
3. **「ローカルバックアップを暗号化」**が**オフ**になっていることを確認します。
4. **「今すぐバックアップ」**をクリックして完了を待ちます。

バックアップはWindowsの以下のいずれかに保存されます：

```
%APPDATA%\Apple Computer\MobileSync\Backup\
%USERPROFILE%\Apple\MobileSync\Backup\
```

---

## インストール

```bash
# クローンして開発モードでインストール
git clone https://github.com/your-org/notevault.git
cd notevault
pip install -e .

# 開発ツール付き (pytest, ruff, mypy)
pip install -e ".[dev]"
```

---

## クイックスタート

```bash
# 1. バックアップを探す
notevault list-backups

# 2. バックアップからノートをエクスポート
notevault export --backup "C:\Users\you\AppData\Roaming\Apple Computer\MobileSync\Backup\<UUID>" --output "./my-notes"
```

以上です。ノートは `my-notes/notes/` に、レポートは `my-notes/reports/` に出力されます。

---

## ステップごとの使い方

### 1 — 利用可能なバックアップを一覧表示する

```
notevault list-backups
```

```
[OK] iPhone  2024-11-15 22:31  C:\Users\...\Backup\a1b2c3d4...
[OK] iPhone  2024-09-03 10:12  C:\Users\...\Backup\e5f6g7h8...
```

機械可読な出力には `--json` を使います：

```bash
notevault list-backups --json
```

標準以外の場所をスキャンするには `--path` を使います：

```bash
notevault list-backups --path "D:\MyBackups"
```

---

### 2 — NoteStore.sqlite を確認する（省略可・推奨）

エクスポート前に、スキーマのバリアントを確認し NoteStore.sqlite が読み取れるかを検証できます：

```bash
notevault inspect-db --sqlite "path\to\NoteStore.sqlite"
```

```
Variant          : VARIANT_B
Tables           : ZICCLOUDSYNCINGOBJECT, ZICNOTEDATA, ZFOLDER, ...
Note table       : ZICCLOUDSYNCINGOBJECT
ID columns       : ['ZIDENTIFIER']
Title columns    : ['ZTITLE1']
Date columns     : ['ZCREATIONDATE1', 'ZMODIFICATIONDATE1']
Blob columns     : ['ZDATA']
Folder tables    : ['ZFOLDER']
Folder join hints: 1 found
Requires gzip    : True
May need protobuf: False
Notes count      : 142
```

`--json` を追加すると、テーブルごとのカラム定義を含む完全な機械可読ダンプを出力します。

---

### 3 — ノートをエクスポートする

```bash
notevault export \
  --backup "C:\...\Backup\<UUID>" \
  --output "./my-notes" \
  --format md
```

オプション：

| フラグ | デフォルト | 説明 |
|--------|-----------|------|
| `--backup` / `-b` | *(必須)* | UUIDバックアップフォルダのパス |
| `--output` / `-o` | `./export` | 出力先ディレクトリ |
| `--format` / `-f` | `md` | 出力形式：`md` または `txt` |
| `--fail-fast` | オフ | スキップせず最初のエラーで中断する |

```
Source  : C:\...\Backup\a1b2c3d4...
Output  : .\my-notes
Format  : md
Done. Exported 142/142 notes to .\my-notes\notes
```

---

## 出力サンプル

### ディレクトリ構成

```
my-notes/
  notes/
    UUID-001_shopping-list.md
    UUID-002_meeting-notes.md
    hash-3f8a1c2e_untitled.md
  reports/
    export_log.json
    summary.txt
```

### Markdownノート（`UUID-001_shopping-list.md`）

```markdown
# 買い物リスト

りんご
バナナ
オレンジ

---
note_id: A4B9C2D1-E3F4-5678-ABCD-123456789ABC
created_at: 2024-10-01T09:00:00+00:00
updated_at: 2024-11-14T18:32:00+00:00
folder: Groceries
source_variant: VARIANT_B
```

### TXTノート（`UUID-001_shopping-list.txt`）

```
買い物リスト
============

りんご
バナナ
オレンジ
```

### `reports/export_log.json`

```json
{
  "total_notes": 142,
  "exported_notes": 141,
  "skipped_notes": 0,
  "failed_notes": 1,
  "output_format": "md",
  "schema_variant": "VARIANT_B",
  "export_started_at": "2024-11-15T13:00:00+00:00",
  "export_finished_at": "2024-11-15T13:00:04+00:00",
  "warnings": [],
  "failures": [
    {
      "note_id": "UUID-XYZ",
      "title": "壊れたノート",
      "reason": "body requires protobuf decoding (not yet implemented)"
    }
  ]
}
```

### `reports/summary.txt`

```
NoteVault エクスポートサマリー
==============================
総ノート数    : 142
エクスポート  : 141
スキップ      : 0
失敗          : 1
形式          : md
スキーマ      : VARIANT_B
開始          : 2024-11-15T13:00:00+00:00
終了          : 2024-11-15T13:00:04+00:00

失敗 (1):
  - [UUID-XYZ] '壊れたノート': body requires protobuf decoding (not yet implemented)
```

---

## トラブルシューティング

### `No backups found`（バックアップが見つかりません）

- iTunes / Finder でローカルバックアップが作成済みであることを確認してください（iCloudのみのバックアップは対象外）。
- バックアップのルートを直接指定してみてください：`notevault list-backups --path "D:\Backups"`

### list-backups で `[ENCRYPTED]` と表示される

- バックアップが暗号化されています。先に復号してください：
  iTunes → デバイスを選択 →「ローカルバックアップを暗号化」→ チェックを外してパスワードを入力。
- 暗号化されたバックアップは MVP-1 では対応していません。

### `Could not locate NoteStore.sqlite`

- バックアップフォルダが不完全な可能性があります。新しいバックアップを作成してお試しください。
- UUIDフォルダ内に `Manifest.db` が存在することを確認してください。

### `body requires protobuf decoding` でノートがエクスポートされない

- iOS 14以降の一部のノートで、本文がProtobufエンベロープに格納されている場合に発生します。該当ノートは `export_log.json` の `failures` に記録されます。
- Protobuf対応は将来のマイルストーンで予定しています。

### ファイル名の文字化け / エンコードの問題

- 出力はすべてUTF-8です。エディタやファイルエクスプローラーがUTF-8に対応していることをご確認ください。
- Windows: コンソールで文字が化ける場合は `chcp 65001` でUTF-8に切り替えてください。

---

## 既知の制限

| 制限事項 | ステータス |
|---------|-----------|
| 暗号化バックアップ | 未対応（MVP-1） |
| Protobuf本文デコード（iOS 14以降） | 未実装（予定あり） |
| 出力のフォルダ階層 | フラット構造。フォルダはメタデータのみに記録 |
| 添付ファイル（画像、PDFなど） | 未抽出（MVP-3で予定） |
| macOS / Linuxのパス | ベストエフォート対応。主要ターゲットはWindows |
| iCloudバックアップ | 未対応。ローカルバックアップのみ |

---

## 開発

```bash
# テスト実行
pytest

# リント
ruff check .

# フォーマット
ruff format .

# 型チェック
mypy src
```

CIはすべてのプッシュおよびプルリクエストで GitHub Actions（`.github/workflows/ci.yml`）により自動実行されます。
