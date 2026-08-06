# AWS BedrockとGitHub OIDCの設定

## 1. 使用リージョン

既定値は`us-east-1`です。今回の5モデルは、Amazon BedrockのConverse APIを`us-east-1`から呼び出せます。

リポジトリ変数`AWS_REGION`を設定すると変更できますが、変更先で全モデルが利用可能かをAWS公式のモデルカードで確認してください。

## 2. モデル利用条件の確認

Amazon BedrockのModel catalogで、次のモデルを検索します。

- `openai.gpt-oss-20b-1:0`
- `anthropic.claude-3-haiku-20240307-v1:0`
- `google.gemma-3-4b-it`
- `amazon.nova-micro-v1:0`
- `mistral.ministral-3-3b-instruct`

第三者モデルでは、初回利用時に利用規約への同意またはAWS Marketplaceの購読が必要になる場合があります。GitHub Actionsを実行する前に、管理者がBedrockコンソールで利用可能な状態を確認してください。

Claude 3 Haikuは2026年9月10日にEOL予定です。EOL後は、失敗ログを残したうえで`config/models.json`の後継モデルへ更新してください。

## 3. GitHub OIDCプロバイダー

AWSアカウントにGitHub Actions用のOIDCプロバイダーがない場合は、次の値で作成します。

- Provider URL：`https://token.actions.githubusercontent.com`
- Audience：`sts.amazonaws.com`

長期アクセスキーは使用しません。

## 4. IAMロールの信頼ポリシー

`<AWS_ACCOUNT_ID>`を置き換え、GitHub Actionsから引き受けるIAMロールへ次の信頼ポリシーを設定します。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:tsuji-tomonori/jp-tag-question-bench:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

結果を別ブランチへコミットする場合は、`sub`をそのブランチへ限定して追加します。無条件のワイルドカードにはしないでください。

## 5. Bedrock呼び出しポリシー

IAMロールへ次のポリシーを付与します。リソースは、今回使用する5モデルに限定しています。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeBenchmarkModels",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/openai.gpt-oss-20b-1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/google.gemma-3-4b-it",
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/mistral.ministral-3-3b-instruct"
      ]
    }
  ]
}
```

リージョンを変更する場合は、ARNのリージョンも変更します。

## 6. GitHubリポジトリ変数

リポジトリの`Settings > Secrets and variables > Actions > Variables`で、次の変数を設定します。

| 変数 | 必須 | 例 |
|---|---|---|
| `AWS_BEDROCK_ROLE_ARN` | はい | `arn:aws:iam::123456789012:role/GitHubBedrockBenchmark` |
| `AWS_REGION` | いいえ | `us-east-1` |

AWSのアクセスキーをGitHub Secretsへ保存する必要はありません。

## 7. GitHub側の書き込み権限

ワークフローは`results/`を実行元ブランチへコミットします。リポジトリのActions設定で、`GITHUB_TOKEN`に書き込みを許可してください。

mainブランチを保護している場合は、次のいずれかを選びます。

1. GitHub Actions botに結果コミットのバイパスを限定的に許可します。
2. 信頼ポリシーへ結果用ブランチを追加し、そのブランチからワークフローを実行します。
3. コミット工程をPR作成方式へ変更します。

## 8. 初回確認

最初は`dry_run=true`、`replicates=1`で実行し、割付、成果物、結果コミット経路を確認します。次にモデルを一つだけ指定して実呼び出しを確認し、最後に`all`と4反復を実行してください。

