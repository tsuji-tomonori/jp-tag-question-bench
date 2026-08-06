# リポジトリの初期設定

この文書では、リポジトリを作成してから、Amazon Bedrockベンチマークを安全に実行できる状態にするまでのGitHub側の設定を説明します。AWS側のOIDCとIAM設定は、[aws-setup.md](aws-setup.md)を参照してください。

## 1. 前提条件

設定には、対象リポジトリの管理権限と、AWSアカウントでIAMロールを作成できる権限が必要です。ワークフローは長期アクセスキーを使わず、GitHub OIDCから一時的なAWS認証情報を取得します。

ワークフローは既定ブランチへマージされるまで、GitHubの`Actions`画面に手動実行対象として表示されません。最初に実装PRを`main`へマージしてください。

## 2. GitHub Actionsの利用許可

リポジトリの`Settings > Actions > General`を開きます。

`Actions permissions`では、少なくとも次の公式Actionを許可します。

- `actions/checkout`
- `actions/setup-python`
- `actions/upload-artifact`
- `actions/download-artifact`
- `aws-actions/configure-aws-credentials`

公開Actionをすべて許可しない運用では、`actions/*`と`aws-actions/configure-aws-credentials@*`を許可対象へ加えてください。

ワークフロー自身が`contents: write`と`id-token: write`だけを明示的に要求しています。リポジトリまたは組織のポリシーで、この二つが禁止されていないことを確認します。`Allow GitHub Actions to create and approve pull requests`は、このワークフローでは使用しないため無効のままで構いません。

## 3. 結果コミットとブランチ保護

ベンチマークは、実行したブランチの`results/`へ結果をコミットします。運用方法を次のいずれかから選びます。

### mainへ直接記録する場合

`main`のルールセットで、GitHub Actionsによる結果コミットを許可します。必須PRや直書き禁止が有効なままでは、解析までは成功しても最後の`git push`が失敗します。

### 結果専用ブランチを使う場合

`main`から`benchmark-results`などのブランチを作成し、Actionsの`Run workflow`画面でそのブランチを選択します。結果はそのブランチへ蓄積されるため、必要な時点でPRを作成して`main`へ反映できます。

結果専用ブランチを使う場合は、AWS IAMロールの信頼ポリシーにも次の`sub`を追加します。

```text
repo:tsuji-tomonori/jp-tag-question-bench:ref:refs/heads/benchmark-results
```

## 4. リポジトリ変数

`Settings > Secrets and variables > Actions > Variables`で、次を登録します。

| 変数 | 必須 | 設定例 | 用途 |
|---|---|---|---|
| `AWS_BEDROCK_ROLE_ARN` | はい | `arn:aws:iam::123456789012:role/GitHubBedrockBenchmark` | OIDCで引き受けるIAMロール |
| `AWS_REGION` | いいえ | `us-east-1` | Bedrockの実行リージョン。未設定時は`us-east-1` |

AWSアクセスキーをGitHub Secretsへ登録しないでください。

## 5. AWS側の設定

[aws-setup.md](aws-setup.md)に従って、次を設定します。

1. GitHub用OIDCプロバイダーを作成します。
2. 対象リポジトリと実行ブランチだけを許可するIAM信頼ポリシーを設定します。
3. 対象モデルだけに限定した`bedrock:InvokeModel`権限を付与します。
4. BedrockのModel catalogで各モデルが利用可能であることを確認します。

## 6. 初回確認

設定後は、[actions-guide.md](actions-guide.md)の手順で次の順番に確認します。

1. `dry_run=true`、`replicates=1`で、AWSを呼ばずに割付と結果コミットを確認します。
2. `models=nova-micro`、`replicates=1`で、少量の実呼び出しを確認します。
3. `models=all`、`replicates=4`で、本実験を実行します。

## 7. 設定完了チェックリスト

- [ ] 実装が既定ブランチへマージされています。
- [ ] 必要なGitHub Actionsが許可されています。
- [ ] `contents: write`と`id-token: write`が組織ポリシーで禁止されていません。
- [ ] 結果を書き込むブランチを決め、ブランチ保護と整合させました。
- [ ] `AWS_BEDROCK_ROLE_ARN`を登録しました。
- [ ] IAM信頼ポリシーがリポジトリ名と実行ブランチを限定しています。
- [ ] Bedrockモデルの利用条件を確認しました。
- [ ] ドライランで`results/`へのコミットまで成功しました。

## 参考資料

- [GitHub Actionsのリポジトリ設定](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- [GitHub ActionsからAWSへOIDC接続する方法](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [ワークフローのpermissions構文](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)
