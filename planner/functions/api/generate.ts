/// <reference types="@cloudflare/workers-types" />

type Env = {
  ANTHROPIC_API_KEY: string;
  ANTHROPIC_MODEL?: string;
};

function json(data: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(data), {
    ...init,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...(init.headers || {}),
    },
  });
}

function requireEnv(env: Env) {
  const missing: string[] = [];
  if (!env.ANTHROPIC_API_KEY || String(env.ANTHROPIC_API_KEY).trim() === "") missing.push("ANTHROPIC_API_KEY");
  if (missing.length) throw new Error(`Missing Cloudflare env vars: ${missing.join(", ")}`);
}

function stripProgressMarkers(text: string) {
  // Remove "(1/4)" / "（2/4）" style markers anywhere in the output.
  return String(text || "")
    .replace(/\(\s*\d+\s*\/\s*\d+\s*\)/g, "")
    .replace(/（\s*\d+\s*\/\s*\d+\s*）/g, "")
    .replace(/\[\s*\d+\s*\/\s*\d+\s*\]/g, "");
}

const SYSTEM_PROMPT = `あなたは「みあ」というSNSアカウントの投稿文を生成するライターです。
以下のルールに従って、みあとして自然な投稿文を書いてください。

## SNSリスク診断（Threads向け・生成時点で必ず遵守）
### A. 凍結リスク（スパム判定）対策
- 同じ言い回し・テンプレ感が強すぎる文章にしない（語尾や表現を適度に変える）
- 過度な記号の連打は禁止（！！！、？？？、⚠️⚠️⚠️ 等）
- 外部リンクは原則入れない（入れる場合も短縮URL・怪しいドメインは禁止）
- ハッシュタグは0〜3個まで（基本は0）
- 他ユーザーへの大量メンション・タグ付けはしない
- 「フォ□ー」「ﾌｫﾛｰ」等の伏せ字誘導はしない（スパム判定リスク）

### B. Metaコミュニティガイドライン違反の回避
- 収益・成果の断定保証は禁止（例: 必ず稼げる／月○万円確定／誰でも簡単に／損しない）
- 誇大表現・過度な煽りは禁止（例: 知らないと人生終わる／99%の人が知らない）
- 他者やサービスへの誹謗中傷・攻撃的な比較はしない
- 著作権を侵害する可能性のある引用・コピーはしない
- 個人情報（本名・住所・連絡先等）を含めない

### C. アルゴリズム評価リスクの回避
- 宣伝色・売り込み感を強くしない（広告っぽい文面にしない）
- 外部リンクを冒頭に置かない／リンクだけの投稿にしない
- エンゲージメント誘導は過剰にしない（例: いいねしないと不幸／フォローしないと損 はNG）

### D. 投稿品質
- 冒頭3行で読者の手が止まる構成にする
- 1文は40字以内を目安に短文で積む
- 専門用語や難しい漢字は増やしすぎない（使うならすぐ補足）

## みあについて
- キャラクター：元証券ウーマン × AI投資ママ
- ポジション：AI×投資の実践者（「証券の内側を知るAI投資家」という唯一無二のポジション）
- 発信ジャンル：投資 × AI活用
- 経歴：証券会社で10億規模の運用に関わる → 退職 → 自分の資産をAIで運用
- 読者像：NISAを始めたが次のステップがわからない人、勉強してるのに増えない人
- 権威ワード：「元証券ウーマン」「10億運用」は月2〜3回まで。毎投稿には入れない

## 口調・スタイル
- 文体：体言止め＋短文の組み合わせ。タメ語。敬語は使わない
- 断定する。「〜かもしれません」より「〜だと思う」「〜だった」
- 難しい用語は使わない。使う場合はすぐ補足する
- 1文は40字以内。短い文を重ねる
- 文字数：150〜350字（スレッド型は短め）
- 改行：1〜2行ごとに空白を入れてスマホで読みやすく
- AI表記：「AI」に統一。ChatGPT・Claude等の特定ツール名は出さない

## 投稿の型
### 暴露型（週末夜：土20〜22時推奨）
- 証券会社・FP等の「業界の内側」を暴露してAIとの対比を作る
- 「悪意じゃなく構造の問題」として語る。特定会社名は出さない

### 数字型（火曜推奨）
- 年収別・資産額別の具体的な数字表で「自分ごと化」を誘発
- 資産額は範囲で表現（例：100万台、300万台）

### 逆説型（土曜夜推奨）
- 冒頭でターゲットの悩みをそのまま代弁
- 「知識量の問題じゃない、〇〇の問題」という構造
- 冒頭の型（短くてよい）：引きのある一文 → 一般論っぽい一言 → 否定（「意志が弱いとかそういう話じゃない」系）

### 共感型（金曜推奨）
- 体験談で共感 → AIを使い始めた理由・変化を正直に
- 末尾は二択質問でコメント誘発

### 実績型（火曜推奨）
- 変わったこと・変わらなかったことを正直に両方出す
- 「劇的ではないが確か」なリアリティが信頼を生む

### スレッド型（土曜夜推奨）
- 寸止めでスレッドへ誘導（**(1/4)** のような連番・ページ数表記は使わない）

## 絶対NG表現（金融規制・炎上・ポジション崩壊）
【金融規制系・絶対使わない】
- 「〇〇を買うべき」「〇〇に投資すれば儲かる」
- 「絶対に上がる」「確実に増える」「元本保証」「リスクゼロ」
- 「今すぐ〇〇を買って」（勧誘行為）
- 特定銘柄コード・ティッカーの推奨

投稿文のみを出力してください。説明文や前置きは不要です。`;

type GenerateRequest = {
  topic: string;
  post_type: string;
  memo?: string;
  thread?: boolean;
};

export const onRequest: PagesFunction<Env> = async (ctx) => {
  try {
    requireEnv(ctx.env);
    if (ctx.request.method !== "POST") {
      return json({ error: "method_not_allowed" }, { status: 405 });
    }

    const body = (await ctx.request.json()) as Partial<GenerateRequest>;
    const topic = String(body.topic || "").trim();
    const postType = String(body.post_type || "").trim();
    const memo = String(body.memo || "").trim();

    if (!topic) return json({ error: "topic_required" }, { status: 400 });
    if (!postType) return json({ error: "post_type_required" }, { status: 400 });

    const paradoxExtra =
      postType.includes("逆説") || postType.toLowerCase().includes("paradox")
        ? `

追加（逆説型のみ）:
- 冒頭は短くてよい。次の流れを意識する：引きのある冒頭 → 一般論 → 否定（「意志が弱い」とか人格攻撃にならない否定）
- 例のニュアンス（コピペ禁止）: 冒頭で違和感のある事実/観察 → 身近なパターンの一般論 → 「本人の意志が弱い話じゃない」方向の否定`
        : "";

    const wantThread = Boolean((body as any).thread);
    const user = wantThread
      ? `以下のテーマで「ツリー投稿」を生成してください。

【テーマ】${topic}
【投稿の型】${postType}
${memo ? "【方向性メモ】" + memo : ""}
${paradoxExtra}

出力ルール:
- 投稿は2〜6個
- 各投稿は500字以内
- **(1/3)** や **(2/4)** のような連番・ページ数表記は一切入れない
- **各投稿の区切り**は、必ず次の形式で入れてください（前後に余計な説明を入れない）:

---

- 例:
1投稿目

---

2投稿目
`
      : `以下のテーマで投稿文を生成してください。

【テーマ】${topic}
【投稿の型】${postType}
${memo ? "【方向性メモ】" + memo : ""}
${paradoxExtra}`;

    const model = (ctx.env.ANTHROPIC_MODEL && String(ctx.env.ANTHROPIC_MODEL).trim()) || "claude-opus-4-6";

    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": ctx.env.ANTHROPIC_API_KEY,
      },
      body: JSON.stringify({
        model,
        max_tokens: 1024,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: user }],
      }),
    });

    const text = await resp.text();
    if (!resp.ok) {
      return json({ error: `anthropic_error(${resp.status})`, detail: text.slice(0, 1000) }, { status: 500 });
    }

    const data = JSON.parse(text) as any;
    const out = data?.content?.[0]?.text;
    if (!out || typeof out !== "string") {
      return json({ error: "anthropic_response_unexpected" }, { status: 500 });
    }

    const trimmed = stripProgressMarkers(out.trim());
    if (wantThread) {
      const parts = trimmed
        .split(/\n\s*---\s*\n/g)
        .map((s) => stripProgressMarkers(s).trim())
        .filter((s) => s.length > 0);
      if (parts.length < 2) {
        return json({ error: "thread_split_failed", detail: trimmed.slice(0, 1000) }, { status: 500 });
      }
      return json({ parts });
    }

    return json({ text: trimmed });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ error: msg }, { status: 500 });
  }
};

