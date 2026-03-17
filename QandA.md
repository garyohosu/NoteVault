# NoteVault Q&A / Clarifications (Finalized)

## Technical Strategy

1. **Tech Stack Selection**
   - **Decision:** Python 3.11+
   - **Libraries:** `typer` (CLI), `sqlite3`, `pathlib`, `json`/`csv`/`logging`.
   - **Reasoning:** Prioritizing the fastest prototype for MVP-1 "text rescue".

2. **Supported Backup Formats**
   - **Decision:** Standard Apple iTunes / Finder local backups only.
   - **Reasoning:** Avoid complexity of third-party formats for the first release.

3. **Encrypted Backups**
   - **Decision:** Not supported in MVP-1. Detect and show a "Not Supported" message.
   - **Reasoning:** Focus on core rescue logic first.

4. **Target iOS Versions**
   - **Decision:** iOS 15+ (Official), iOS 13-14 (Best effort).
   - **Reasoning:** Reduce schema fragmentation issues during initial development.

## Implementation Details

5. **Rich Text to Markdown Conversion**
   - **Decision:** Plain text extraction priority. Basic Markdown (bold, italic, lists) if feasible. No tables/complex checklists in MVP-1.
   - **Reasoning:** "Text rescue comes first."

6. **Duplicate Title Handling**
   - **Decision:** Filename format: `{note_id}_{slugified_title}.md`.
   - **Reasoning:** Guarantees uniqueness and safety on Windows filesystems.

7. **Attachment Storage (MVP-3)**
   - **Decision:** `attachments/{note_id}/` flat structure. Relative links in note body.

8. **Output Default Format**
   - **Decision:** Markdown (Default), TXT (Optional).

## Project Management

9. **Repository Structure**
   - **Decision:** `src/` layout.
   ```text
   NoteVault/
     src/
       notevault/
         cli.py
         backup_discovery.py
         ...
   ```

10. **Testing Data**
    - **Decision:** Developer-generated backups (Small/Medium/Large). No distribution of real user data.

## Additional Decisions

11. **Windows Backup Path Detection**
    - **Decision:** Auto-detect standard paths; allow manual override.

12. **note_id Definition**
    - **Decision:** Use stable internal Notes DB ID (Z_PK or similar). Fallback to stable hash of metadata.

13. **Incremental Export**
    - **Decision:** Change detection based on `note_id` + `updated_at`.

14. **Folder Nested Structure**
    - **Decision:** Single-layer folder guarantee in MVP-1; nested is best effort.

---

## Additional Decisions (Resolved 2026-03-17)

15. **`list-backups` の出力形式と自動検出パス**
    - **Decision:** 標準Windowsパスを自動スキャン。デフォルトは人間向けの一覧表示。`--json` オプションで機械処理向け出力も提供。
    - **スキャン候補パス:**
      - `%APPDATA%\Apple Computer\MobileSync\Backup`（主候補）
      - `%USERPROFILE%\Apple\MobileSync\Backup`（補助候補）
    - **表示項目:** `backup_id`, `path`, `device_name`, `last_backup_date`, `is_encrypted`, `is_valid`
    - **Reasoning:** SPEC.md F-001 が「一覧表示＋複数時は選択可能」を要求。人間向け一覧を基本とし、スクリプト連携を見越して `--json` を添える。

16. **`export --backup` が受け取るパスの粒度**
    - **Decision:** `--backup` は UUID のバックアップ実体フォルダを直接受け取る。親ディレクトリの解決は `list-backups` や自動選択の責務とする。
    - **推奨CLI:**
      ```
      notevault backups list
      notevault export --backup "C:\...\Backup\<UUID>" --dest "D:\export"
      ```
    - **Reasoning:** バックアップ選択とエクスポート対象指定を混ぜると CLI の責務が曖昧になる。SPEC.md F-001 の「一覧→選択→検証」の流れに合わせ、`export` には「選ばれた1件」を渡す設計にする。

17. **Apple Notes Protobuf パーサーの選定**
    - **Decision:** MVP-1 では Protobuf への依存を確定させない。まず `NoteStore.sqlite` から安定して取得できるフィールドを優先抽出する。
    - **実装順序:**
      1. タイトル・作成日・更新日・識別子など DB から素直に読めるものを確定
      2. 本文に `ZDATA` のデコードが必須と判明した時点で依存追加を検討
      3. 第一候補: メンテ継続・ライセンス・テスト容易性を確認したうえで既存パーサーを薄くラップ
      4. 第二候補: `protobuf` 導入による自前実装
    - **Reasoning:** SPEC.md は MVP-1 を「Text Rescue」と定義しており、完全忠実再現は非目標。依存追加は必要が確定してから。野良実装への全面依存は避ける。

18. **`note_id` の定義（`Z_PK` vs `ZIDENTIFIER`）**
    - **Decision:** `ZIDENTIFIER`（UUID文字列）を外部向け `note_id` の第一候補とする。`Z_PK` は内部 JOIN・デバッグ用に限定。
    - **決定ルール:**
      - `ZIDENTIFIER` が存在すればそれを採用
      - 存在しない場合は安定ハッシュにフォールバック: `sha1(title + created_at + updated_at + folder_name)`
      - `Z_PK` は外部 ID には使わない
    - **Reasoning:** `Z_PK` はローカル DB 内の連番でバックアップ再生成時に揺れる可能性がある。増分エクスポート（Q13: `note_id + updated_at` で変更検知）の土台として安定した識別子が必須。`Z_PK` を使うと「同じノートなのに別物扱い」の静かな事故が起きやすい。

19. **ノートエクスポート失敗時の挙動**
    - **Decision:** デフォルトはスキップして続行。`--fail-fast` オプションで即中断も可能にする。
    - **レポート仕様:**
      - `reports/export_log.json`
      - `reports/summary.txt`
      - 記録項目: `total`, `success`, `skipped`, `failed`, `failed_note_ids`, `failure_reason`, `source_backup_id`
    - **Reasoning:** SPEC.md N-004・AT-004 が「一部のノートが壊れていても全体を止めない」「失敗は記録して続行」を明示。ほぼ仕様確定事項として扱う。SPEC.md F-010 の出力構造にも対応。

20. **`format` パラメータの変数名衝突**
    - **Decision:** `output_format` に改名。
    - **対象:** `cli.py:21`
    - **Reasoning:** Python 組み込み関数 `format()` を隠蔽するため修正必須。`fmt` でも可だが、CLI オプションとコード可読性を考慮すると `output_format` が無難。

21. **開発用依存パッケージと CI**
    - **Decision:** 開発初期から導入する。
    - **dev 依存:**
      - `pytest` — テスト
      - `ruff` — lint / format
      - `mypy` — 型チェック（任意だが推奨）
    - **CI:** GitHub Actions で push / PR 時に最小構成を実行
      ```
      pytest
      ruff check .
      ruff format --check .
      ```
    - **Reasoning:** パス処理・例外処理・バックアップ解析を伴うツールは足場なしで育てると転びやすい。今のうちに CI を置く価値は高い。
