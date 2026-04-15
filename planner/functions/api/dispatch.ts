/// <reference types="@cloudflare/workers-types" />

type Env = {
  GITHUB_TOKEN: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  GITHUB_BRANCH: string;
  // Optional. Default: "threads-queue.yml"
  GITHUB_WORKFLOW?: string;
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

function workflowFile(env: Env) {
  return (env.GITHUB_WORKFLOW && String(env.GITHUB_WORKFLOW).trim()) || "threads-queue.yml";
}

async function dispatchWorkflow(env: Env) {
  const wf = workflowFile(env);
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${encodeURIComponent(
    wf,
  )}/dispatches`;

  const resp = await fetch(url, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "content-type": "application/json",
      "user-agent": "mei-threads-planner-ui",
    },
    body: JSON.stringify({ ref: env.GITHUB_BRANCH }),
  });

  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`GitHub workflow dispatch failed (${resp.status}): ${text.slice(0, 800)}`);
  }
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  try {
    requireEnv(ctx.env);
    if (ctx.request.method !== "POST") return json({ error: "method_not_allowed" }, { status: 405 });

    await dispatchWorkflow(ctx.env);
    return json({ ok: true });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ error: msg }, { status: 500 });
  }
};

