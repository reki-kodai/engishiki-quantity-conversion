# engishiki-quantity-conversion
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/reki-kodai/engishiki-quantity-conversion/blob/main/run_on_colab.ipynb)

上のボタンから Google Colaboratory で開くと、ブラウザ上で実行して結果を確認できます（Google アカウントが必要です）。

延喜式巻24主計式上の物品貢納量を丁数へ換算し、国別集計等を行うための処理コードです。
入力XMLデータおよび出力例も併せて収録しています。

ファイル
・換算処理コード.py
・engishiki_v24.xml
・engishiki_taxonomy_standoff_master.xml
・結果（国別集計）.txt
・結果（rule確認）.txt
・結果（ログ）.txt
・run_on_colab.ipynb（Colab 用ノートブック）

入力ファイル　実行時に以下のファイルのパスを入力してください（何も入力せずEnterで、本コードと同じフォルダのファイルを使います）。
・engishiki_v24.xml
・engishiki_taxonomy_standoff_master.xml
・出力先フォルダ

コマンドライン引数で渡すこともできます。

```
python 換算処理コード.py engishiki_v24.xml engishiki_taxonomy_standoff_master.xml output
```

出力ファイル　指定した保存先フォルダに以下のファイルが出力されます。
・結果（国別集計）.txt
・結果（rule確認）.txt
・結果（ログ）.txt

備考
本コードは研究用途です。

ライセンス
・コード（換算処理コード.py、run_on_colab.ipynb）: MIT ライセンス（[LICENSE](LICENSE)）
・データ（engishiki_v24.xml、engishiki_taxonomy_standoff_master.xml、結果（国別集計）.txt、結果（rule確認）.txt、結果（ログ）.txt）: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja)（延喜式サイトの利用条件と同じ）

著作権者
・人間文化研究機構広領域連携型基幹研究プロジェクト「異分野融合による総合書物学の拡張的研究」歴博ユニット「延喜式のデジタル技術による汎用化」
・学術変革領域研究（A）「歴史情報学の創成」（領域代表）内 計画研究「TEIを中心とした高度な歴史テキスト構築」JP25H01244
