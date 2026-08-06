# GitHub Actionsの実行手順

この文書では、`Amazon Bedrock benchmark`ワークフローの起動、進捗確認、成果物確認、再実行方法を説明します。初回実行前に、[repository-setup.md](repository-setup.md)と[aws-setup.md](aws-setup.md)の設定を完了してください。

## 1. ワークフローを開く

1. GitHubでリポジトリの`Actions`タブを開きます。
2. 左側の一覧から`Amazon Bedrock benchmark`を選びます。
3. `Run workflow`を選びます。
4. 結果を書き込むブランチを選択します。
5. 入力値を設定して実行します。

`Run workflow`が表示されない場合は、ワークフローファイルが既定ブランチへマージ済みか、リポジトリでActionsが許可されているかを確認してください。

## 2. 入力値

| 入力 | 既定値 | 説明 |
|---|---|---|
| `models` | `all` | `all`またはmodel keyのカンマ区切りです。空白は入れません |
| `replicates` | `4` | 各「項目×選択肢×条件」の反復数です |
| `temperature` | `1.0` | Bedrockへ渡す生成温度です |
| `max_workers` | `4` | モデルごとの同時リクエスト数です |
| `dry_run` | `false` | 有効にするとBedrockを呼ばずに割付と集計経路だけを確認します |
| `stimuli_path` | `data/stimuli.json` | 使用するプロンプト設定JSONです |

指定できるmodel keyは次のとおりです。

```text
gpt-oss-20b
claude-3-haiku
gemma-3-4b-it
nova-micro
ministral-3b
```

一部だけを同時に実行する例です。

```text
gpt-oss-20b,gemma-3-4b-it,nova-micro
```

## 3. 推奨する実行順序

### 設定確認

```text
models: all
replicates: 1
temperature: 1.0
max_workers: 1
dry_run: true
stimuli_path: data/stimuli.json
```

Bedrockを呼ばないため、AWS利用料は発生しません。全モデル分の割付、Artifact、レポート、結果コミットを確認できます。

### 少量の実呼び出し

```text
models: nova-micro
replicates: 1
temperature: 1.0
max_workers: 1
dry_run: false
stimuli_path: data/stimuli.json
```

モデル利用許可、OIDC、IAM、クォータを少量の呼び出しで確認します。

### 本実験

```text
models: all
replicates: 4
temperature: 1.0
max_workers: 4
dry_run: false
stimuli_path: data/stimuli.json
```

既定設定では、1モデル当たり960回、5モデル合計4,800回呼び出します。実行前に料金とクォータを確認してください。

## 4. 実行中の確認

`run-model`はモデルごとのマトリックスジョブです。一つのモデルが失敗しても、他のモデルと集計処理は継続します。

各モデルでは、次の順番で処理します。

1. 対象モデルかを判定します。
2. OIDCでAWS認証情報を取得します。
3. 独立したBedrock Converseリクエストを実行します。
4. 生ログとメタデータをArtifactへ保存します。
5. 有効回答が一件もない場合は、証跡を保存してからジョブを失敗にします。

`aggregate-and-commit`は取得できた全モデルの証跡を検証・解析し、結果を実行ブランチへコミットします。

## 5. 結果の確認

実行画面の`Summary`には、`results/latest.md`と同じ概要が表示されます。詳細は次の場所で確認できます。

- Actions Artifact：モデル単位の実行証跡と集計レポート
- `results/latest.md`：最新の人向けレポート
- `results/latest.json`：最新の機械可読集計
- `results/latest-rates.csv`：条件別肯定率
- `results/latest-contrasts.csv`：中立条件との差と検定結果
- `results/runs/<run-id>/raw/`：全プロンプト、生回答、エラー、レイテンシー、トークン数

結果コミットのメッセージは次の形式です。

```text
results: Bedrock benchmark <run-id>-<run-attempt>
```

## 6. 再実行

同じ設定でやり直す場合は、実行画面の`Re-run jobs`を使用できます。再実行では`run_attempt`が増えるため、以前の証跡を上書きせず別の実行ディレクトリへ保存します。

プロンプトを変更した実験は、同じ実行の再試行として扱わず、新しい`study_id`とファイル名で新規実行してください。変更方法は[prompt-customization.md](prompt-customization.md)を参照してください。

## 7. 主な失敗と確認箇所

| 症状 | 確認箇所 |
|---|---|
| OIDC認証に失敗する | IAM信頼ポリシーのリポジトリ名、ブランチ名、`aud`を確認します |
| AccessDeniedになる | IAMのモデルARN、リージョン、`bedrock:InvokeModel`を確認します |
| モデルだけ失敗する | Bedrock Model catalogの利用可否、EOL、Marketplace条件を確認します |
| Throttlingが続く | `max_workers`を1へ下げ、クォータを確認します |
| 結果のpushに失敗する | ブランチ保護と`contents: write`を確認します |
| `stimuli_path`が拒否される | `data/`以下の既存JSONを指定し、`..`や空白を含めないようにします |
| 統計判定が出ない | 全項目で中立条件と比較条件の有効な「はい／いいえ」がそろっているか確認します |
