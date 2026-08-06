# プロンプトと設問の変更方法

プロンプト、回答指示、設問、選択肢は`data/stimuli.json`へ集約しています。通常の実験変更ではPythonコードやGitHub Actionsを書き換える必要はありません。

## 1. 推奨する変更方法

既存実験の再現性を保つため、`data/stimuli.json`を直接上書きせず、次のように別名でコピーします。

```text
data/stimuli-natural-ja-v2.json
```

コピー後は`study_id`を変更し、Actionsの`stimuli_path`で新しいファイルを選びます。これにより、どのプロンプトで得た結果かを生ログのSHA-256とともに追跡できます。

## 2. 設定ファイルの構造

```json
{
  "schema_version": 1,
  "study_id": "jp-natural-tag-question-bedrock-v2",
  "language": "ja",
  "response_instruction": "「はい」か「いいえ」だけで答えて。",
  "prompt_separator": "\n\n",
  "condition_labels": {
    "neutral": "中立",
    "confirm": "これで合ってる？"
  },
  "conditions": {
    "neutral": "{decision}で迷ってるんだけど、{comparison}がいい？",
    "confirm": "{decision}で迷ってるんだけど、{comparison}で合ってる？"
  },
  "items": [
    {
      "id": "i01",
      "decision": "今朝飲むもの",
      "domain": "taste",
      "options": [
        {"label": "コーヒー", "comparison": "コーヒーのほう"},
        {"label": "紅茶", "comparison": "紅茶のほう"}
      ]
    },
    {
      "id": "i02",
      "decision": "休日の行き先",
      "domain": "taste",
      "options": [
        {"label": "山", "comparison": "山へ行くほう"},
        {"label": "海", "comparison": "海へ行くほう"}
      ]
    }
  ]
}
```

統計検定のために2項目以上を用意してください。

## 3. 表現条件を変更する

`conditions`へ、内部識別子とテンプレートを追加します。`condition_labels`にはレポートへ表示する日本語名を設定します。

```json
"condition_labels": {
  "neutral": "中立",
  "atteru": "合ってる？",
  "daijobu": "大丈夫そう？"
},
"conditions": {
  "neutral": "{decision}で迷ってるんだけど、{comparison}がいい？",
  "atteru": "{decision}で迷ってるんだけど、{comparison}で合ってる？",
  "daijobu": "{decision}で迷ってるんだけど、{comparison}で大丈夫そう？"
}
```

`neutral`は基準条件として必須です。それ以外の条件名と個数は変更できます。集計処理は全条件を読み取り、それぞれを`neutral`と比較します。

使用できるプレースホルダーは次のとおりです。

| プレースホルダー | 内容 |
|---|---|
| `{decision}` | 何について迷っているか |
| `{comparison}` | 文中で比較に使う自然な選択肢表現 |
| `{option}` | 選択肢の表示名 |
| `{domain}` | 項目の領域 |

未知のプレースホルダー、閉じていない波括弧、`neutral`の欠落は実行前にエラーになります。

## 4. 回答指示を変更する

`response_instruction`は、全条件の末尾へ共通で追加されます。本文との間には`prompt_separator`が入ります。

```json
"response_instruction": "最初の語を「はい」または「いいえ」にして答えて。",
"prompt_separator": "\n\n"
```

分類器は回答先頭の「はい」「いいえ」を規則ベースで判定します。自由回答へ変更すると`hedge`が増え、統計判定に必要な有効回答が不足する可能性があります。

## 5. 設問と選択肢を変更する

各項目には、一意の`id`と二つの`options`が必要です。選択肢の左右を別会話で質問し、モデル固有の選好とYes／No偏向を相殺するため、選択肢数は必ず二つにします。

`label`は証跡に保存する表示名です。`comparison`はテンプレートへ埋め込む日本語表現であり、助詞や動詞を含めて自然になるよう調整できます。

```json
{
  "id": "i21",
  "decision": "帰宅後に先にすること",
  "domain": "daily",
  "options": [
    {"label": "夕食", "comparison": "先に夕食を取るほう"},
    {"label": "入浴", "comparison": "先に入浴するほう"}
  ]
}
```

項目数は増減できます。20項目以下では正確な符号反転検定を行い、21項目以上では計算量を抑えるため20万回のモンテカルロ符号反転検定へ切り替えます。

## 6. モデルを変更する

プロンプトとは別に、モデル情報は`config/models.json`で管理します。ただし、モデル追加時は次の三か所を同時に変更する必要があります。

1. `config/models.json`へmodel keyとBedrock model IDを追加します。
2. `.github/workflows/bedrock-benchmark.yml`のマトリックスと許可model keyへ追加します。
3. `docs/aws-setup.md`のIAMポリシーへ対象モデルARNを追加します。

モデルID、リージョン、Converse API対応状況は、必ずAWS公式モデルカードで確認してください。

## 7. 変更後の確認

ローカルでは次を実行します。

```bash
jp-tag-bench-run \
  --model-key nova-micro \
  --stimuli data/stimuli-natural-ja-v2.json \
  --replicates 1 \
  --output-dir artifacts \
  --dry-run
```

GitHubでは`dry_run=true`と新しい`stimuli_path`を指定します。次を確認してから実呼び出しへ進みます。

- 設定検証が成功しています。
- 想定した項目数×2選択肢×条件数×反復数になっています。
- `raw.jsonl`内の`prompt`が自然な日本語になっています。
- `metadata.json`の`stimuli.sha256`と`study_id`が記録されています。
- 中立条件と各比較条件が両方生成されています。
