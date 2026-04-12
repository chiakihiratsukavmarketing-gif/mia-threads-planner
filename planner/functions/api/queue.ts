/// <reference types="@cloudflare/workers-types" />

type Env = {
  GITHUB_TOKEN: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  GITHUB_BRANCH: string;
  QUEUE_PATH: string;
};

type GitHubFileResponse = {
  sha: string;
  content: string; // base64
  encoding: "base64";
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
  for (const k of ["GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_BRANCH"] as const) {
    if (!env[k] || String(env[k]).trim() === "") missing.push(k);
  }
  if (missing.length) {
    throw new Error(`Missing Cloudflare env vars: ${missing.join(", ")}`);
  }
}

function queuePath(env: Env) {
  return (env.QUEUE_PATH && env.QUEUE_PATH.trim()) || "queue/posts.json";
}

function b64ToUtf8(b64: string) {
  const bin = atob(b64.replace(/\n/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder("utf-8").decode(bytes);
}

function utf8ToB64(text: string) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

async function githubGetFile(env: Env): Promise<{ data: any; sha: string; rawText: string }> {
  const path = queuePath(env);
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${encodeURI(
    path.replace(/^\//, ""),
  )}?ref=${encodeURIComponent(env.GITHUB_BRANCH)}`;

  const resp = await fetch(url, {
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "user-agent": "mei-threads-planner-ui",
    },
  });

  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`GitHub GET failed (${resp.status}): ${text.slice(0, 800)}`);
  }

  const meta = JSON.parse(text) as GitHubFileResponse;
  const rawText = b64ToUtf8(meta.content);
  const data = JSON.parse(rawText);
  return { data, sha: meta.sha, rawText };
}

async function githubPutFile(env: Env, newText: string, sha: string, message: string) {
  const path = queuePath(env);
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${encodeURI(
    path.replace(/^\//, ""),
  )}`;

  const body = {
    message,
    content: utf8ToB64(newText),
    sha,
    branch: env.GITHUB_BRANCH,
  };

  const resp = await fetch(url, {
    method: "PUT",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "content-type": "application/json",
      "user-agent": "mei-threads-planner-ui",
    },
    body: JSON.stringify(body),
  });

  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`GitHub PUT failed (${resp.status}): ${text.slice(0, 800)}`);
  }
  return JSON.parse(text);
}

function validateQueue(data: any) {
  if (!data || typeof data !== "object") throw new Error("Invalid JSON: root must be object");
  if (data.version !== 1) throw new Error("Invalid queue: version must be 1");
  if (!Array.isArray(data.posts)) throw new Error("Invalid queue: posts must be array");

  for (const p of data.posts) {
    if (!p || typeof p !== "object") throw new Error("Invalid queue: post must be object");
    if (!p.id || typeof p.id !== "string") throw new Error("Invalid queue: post.id required");
    if (!p.scheduled_at || typeof p.scheduled_at !== "string") throw new Error(`Invalid queue: scheduled_at required (${p.id})`);
    if (typeof p.text !== "string") throw new Error(`Invalid queue: text must be string (${p.id})`);
    if (p.text.length > 500) throw new Error(`Invalid queue: text too long (${p.id})`);
    if (p.status && typeof p.status !== "string") throw new Error(`Invalid queue: status must be string (${p.id})`);
  }
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  try {
    requireEnv(ctx.env);

    if (ctx.request.method === "GET") {
      const { data } = await githubGetFile(ctx.env);
      validateQueue(data);
      return json(data);
    }

    if (ctx.request.method === "PUT") {
      const incoming = await ctx.request.json();
      validateQueue(incoming);

      const { sha } = await githubGetFile(ctx.env);
      const newText = JSON.stringify(incoming, null, 2) + "\n";
      const msg = `chore(queue): update via planner ui (${new Date().toISOString()})`;
      await githubPutFile(ctx.env, newText, sha, msg);

      // Re-fetch to return canonical file
      const { data } = await githubGetFile(ctx.env);
      validateQueue(data);
      return json(data);
    }

    return json({ error: "method_not_allowed" }, { status: 405 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ error: msg }, { status: 500 });
  }
};
