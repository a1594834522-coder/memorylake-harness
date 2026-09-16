const t = window.QwenPaw.host.React, { useState: y, useCallback: O, useEffect: V, useMemo: L } = t, {
  Alert: u,
  AutoComplete: K,
  Button: W,
  Card: F,
  Collapse: N,
  Form: l,
  Input: z,
  InputNumber: g,
  Select: B,
  Space: w,
  Switch: _,
  Tag: T,
  Typography: k
} = window.QwenPaw.host.antd, n = ["memory_backend_configs", "memorylake"], I = [
  { value: "", site: "https://memorylake.ai", labelKey: "regionIntl" },
  { value: "https://app.memorylake.cn/openapi/memorylake", site: "https://memorylake.cn", labelKey: "regionCn" }
], P = {
  en: {
    title: "Memory Lake",
    intro: "Long-term memory shared across projects, machines, and clients. If this machine is already set up for Claude Code, Codex, dsh, or opencode, leave every field empty: the shared ~/.memorylake configuration and login are used.",
    region: "Deployment",
    regionIntl: "memorylake.ai (international)",
    regionCn: "memorylake.cn (China)",
    apiKey: "API key",
    apiKeyHelp: "Leave empty to reuse the memorylake CLI login already on this machine.",
    getKey: "Get an API key at",
    workspace: "Workspace",
    workspaceHelp: "Where memories live. Pick one, or paste an id.",
    actor: "Actor",
    actorHelp: "Facts are attributed to this actor. Without one, memory is read-only.",
    load: "Load from Memory Lake",
    reload: "Reload",
    loading: "Asking Memory Lake…",
    loaded: "Loaded",
    viaRequestKey: "using the key entered above",
    viaSavedKey: "using this Agent's saved key",
    viaShared: "using this machine's CLI login",
    me: "you",
    deleted: "deleted",
    noWorkspaces: "This account has no workspaces yet. Create one in the Memory Lake console.",
    noActors: "No actors are bound to this workspace.",
    errCli: "The memorylake CLI is not available and could not be installed",
    errAuth: "Not authenticated. Check the API key and deployment",
    errOther: "Could not reach Memory Lake",
    advanced: "Recall and runtime",
    autoRecall: "Automatic recall",
    autoRecallHelp: "Search memory with the user's message before every reply.",
    autoRecallTopK: "Results per automatic recall",
    topK: "Default results for memory_search",
    installCli: "Install the memorylake CLI automatically when missing",
    timeout: "CLI timeout",
    plainText: "The API key is masked here and in the API, but stored in agent.json in plain text, like other memory backends' credentials."
  },
  zh: {
    title: "Memory Lake",
    intro: "跨项目、跨设备、跨客户端的长期记忆。如果这台机器已经为 Claude Code、Codex、dsh 或 opencode 配置过 Memory Lake，所有字段留空即可，会直接使用共享的 ~/.memorylake 配置和登录。",
    region: "部署站点",
    regionIntl: "memorylake.ai（国际站）",
    regionCn: "memorylake.cn（中国站）",
    apiKey: "API key",
    apiKeyHelp: "留空则复用本机 memorylake CLI 已有的登录。",
    getKey: "在这里获取 API key：",
    workspace: "Workspace",
    workspaceHelp: "记忆所在的空间。从列表选择，或直接粘贴 id。",
    actor: "Actor",
    actorHelp: "写入的记忆归属于该 actor。不填则记忆只读。",
    load: "从 Memory Lake 读取",
    reload: "重新读取",
    loading: "正在查询 Memory Lake…",
    loaded: "已读取",
    viaRequestKey: "使用上面填写的 key",
    viaSavedKey: "使用该 Agent 已保存的 key",
    viaShared: "使用本机 CLI 的登录",
    me: "我",
    deleted: "已删除",
    noWorkspaces: "该账号还没有 workspace，请先到 Memory Lake 控制台创建。",
    noActors: "该 workspace 没有绑定任何 actor。",
    errCli: "memorylake CLI 不可用且自动安装失败",
    errAuth: "认证失败，请检查 API key 与部署站点",
    errOther: "无法连接 Memory Lake",
    advanced: "召回与运行参数",
    autoRecall: "自动召回",
    autoRecallHelp: "每次回复前用用户消息自动检索一次记忆。",
    autoRecallTopK: "每次自动召回的结果数",
    topK: "memory_search 的默认结果数",
    installCli: "缺少 memorylake CLI 时自动安装",
    timeout: "CLI 超时",
    plainText: "API key 在表单和接口中会被遮罩，但和其他记忆后端的凭据一样，以明文保存在 agent.json 中。"
  }
};
function q() {
  var r, c;
  return (((c = (r = window.QwenPaw.host).useLocale) == null ? void 0 : c.call(r)) || "en").toLowerCase().startsWith("zh") ? P.zh : P.en;
}
function j() {
  var e, r;
  try {
    const c = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage");
    return c ? String(((r = (e = JSON.parse(c)) == null ? void 0 : e.state) == null ? void 0 : r.selectedAgent) ?? "") : "";
  } catch {
    return "";
  }
}
async function Q(e) {
  const { getApiUrl: r, getApiToken: c } = window.QwenPaw.host, m = { "Content-Type": "application/json" }, i = c();
  i && (m.Authorization = `Bearer ${i}`);
  const d = j();
  d && (m["X-Agent-Id"] = d);
  const p = await fetch(r("/memorylake/discover"), {
    method: "POST",
    headers: m,
    body: JSON.stringify({ agent_id: d, ...e })
  });
  if (!p.ok)
    throw new Error(`HTTP ${p.status}`);
  return await p.json();
}
function $() {
  const e = q(), r = l.useFormInstance(), c = l.useWatch([...n, "api_key"], r) ?? "", m = l.useWatch([...n, "base_url"], r) ?? "", i = l.useWatch([...n, "workspace"], r) ?? "", d = l.useWatch([...n, "install_cli"], r) ?? !0, [p, C] = y(!1), [a, E] = y(null), [f, h] = y(""), [R, S] = y(""), b = I.find((o) => o.value === m) ?? I[0], v = O(
    async (o) => {
      C(!0), h("");
      try {
        const s = await Q({
          api_key: c,
          base_url: m,
          workspace: o ?? i,
          install_cli: d
        });
        if (E(s), S(o ?? i), !s.ok) {
          h(s.error_kind === "cli-missing" ? e.errCli : s.error_kind === "not-logged-in" ? e.errAuth : e.errOther);
          return;
        }
        !r.getFieldValue([...n, "workspace"]) && s.workspaces.length === 1 && r.setFieldValue([...n, "workspace"], s.workspaces[0].id), !r.getFieldValue([...n, "actor"]) && s.me && s.actors.some((A) => A.id === s.me && A.status === "ACTIVE") && r.setFieldValue([...n, "actor"], s.me);
      } catch (s) {
        E(null), h(`${e.errOther}: ${s.message}`);
      } finally {
        C(!1);
      }
    },
    [c, m, i, d, r, e]
  );
  V(() => {
    a != null && a.ok && i && i !== R && v(i);
  }, [i]);
  const x = L(
    () => (a != null && a.ok ? a.workspaces : []).map((o) => ({
      value: o.id,
      label: /* @__PURE__ */ t.createElement(w, { size: 6 }, /* @__PURE__ */ t.createElement("span", null, o.name || o.id), o.name ? /* @__PURE__ */ t.createElement(k.Text, { type: "secondary", style: { fontSize: 12 } }, o.id) : null)
    })),
    [a]
  ), M = L(
    () => (a != null && a.ok ? a.actors : []).map((o) => ({
      value: o.id,
      label: /* @__PURE__ */ t.createElement(w, { size: 6 }, /* @__PURE__ */ t.createElement("span", null, o.display_name || o.id), o.id === (a == null ? void 0 : a.me) ? /* @__PURE__ */ t.createElement(T, { color: "blue" }, e.me) : null, o.status && o.status !== "ACTIVE" ? /* @__PURE__ */ t.createElement(T, null, e.deleted) : null, /* @__PURE__ */ t.createElement(k.Text, { type: "secondary", style: { fontSize: 12 } }, o.id))
    })),
    [a, e]
  ), H = a != null && a.ok ? a.login === "request key" ? e.viaRequestKey : a.login === "saved key" ? e.viaSavedKey : e.viaShared : "";
  return /* @__PURE__ */ t.createElement(F, { title: e.title }, /* @__PURE__ */ t.createElement(u, { type: "info", showIcon: !0, message: e.intro, style: { marginBottom: 16 } }), /* @__PURE__ */ t.createElement(l.Item, { name: [...n, "base_url"], label: e.region, initialValue: "" }, /* @__PURE__ */ t.createElement(B, { options: I.map((o) => ({ value: o.value, label: e[o.labelKey] })) })), /* @__PURE__ */ t.createElement(
    l.Item,
    {
      name: [...n, "api_key"],
      label: e.apiKey,
      extra: /* @__PURE__ */ t.createElement("span", null, e.apiKeyHelp, " ", e.getKey, " ", /* @__PURE__ */ t.createElement(k.Link, { href: b.site, target: "_blank", rel: "noreferrer" }, b.site.replace("https://", "")))
    },
    /* @__PURE__ */ t.createElement(z.Password, { placeholder: "sk-...", autoComplete: "new-password" })
  ), /* @__PURE__ */ t.createElement(w, { style: { marginBottom: 16 }, wrap: !0 }, /* @__PURE__ */ t.createElement(W, { onClick: () => void v(), loading: p, type: a ? "default" : "primary" }, p ? e.loading : a ? e.reload : e.load), a != null && a.ok ? /* @__PURE__ */ t.createElement(k.Text, { type: "secondary" }, e.loaded, " · ", H) : null), f ? /* @__PURE__ */ t.createElement(u, { type: "error", showIcon: !0, message: f, description: a == null ? void 0 : a.error, style: { marginBottom: 16 } }) : null, a != null && a.ok && a.workspaces.length === 0 ? /* @__PURE__ */ t.createElement(u, { type: "warning", showIcon: !0, message: e.noWorkspaces, style: { marginBottom: 16 } }) : null, /* @__PURE__ */ t.createElement(l.Item, { name: [...n, "workspace"], label: e.workspace, extra: e.workspaceHelp }, /* @__PURE__ */ t.createElement(K, { options: x, allowClear: !0, placeholder: "ws-...", filterOption: !0 })), /* @__PURE__ */ t.createElement(l.Item, { name: [...n, "actor"], label: e.actor, extra: e.actorHelp }, /* @__PURE__ */ t.createElement(
    K,
    {
      options: M,
      allowClear: !0,
      placeholder: "actor-...",
      filterOption: !0,
      notFoundContent: a != null && a.ok && i ? e.noActors : null
    }
  )), /* @__PURE__ */ t.createElement(
    N,
    {
      items: [
        {
          key: "advanced",
          label: e.advanced,
          forceRender: !0,
          children: /* @__PURE__ */ t.createElement(t.Fragment, null, /* @__PURE__ */ t.createElement(
            l.Item,
            {
              name: [...n, "auto_recall"],
              label: e.autoRecall,
              tooltip: e.autoRecallHelp,
              valuePropName: "checked",
              initialValue: !0
            },
            /* @__PURE__ */ t.createElement(_, null)
          ), /* @__PURE__ */ t.createElement(
            l.Item,
            {
              name: [...n, "auto_recall_top_k"],
              label: e.autoRecallTopK,
              initialValue: 3,
              rules: [{ type: "number", min: 1, max: 10 }]
            },
            /* @__PURE__ */ t.createElement(g, { min: 1, max: 10, style: { width: "100%" } })
          ), /* @__PURE__ */ t.createElement(
            l.Item,
            {
              name: [...n, "top_k"],
              label: e.topK,
              initialValue: 5,
              rules: [{ type: "number", min: 1, max: 20 }]
            },
            /* @__PURE__ */ t.createElement(g, { min: 1, max: 20, style: { width: "100%" } })
          ), /* @__PURE__ */ t.createElement(
            l.Item,
            {
              name: [...n, "install_cli"],
              label: e.installCli,
              valuePropName: "checked",
              initialValue: !0
            },
            /* @__PURE__ */ t.createElement(_, null)
          ), /* @__PURE__ */ t.createElement(
            l.Item,
            {
              name: [...n, "timeout_seconds"],
              label: e.timeout,
              initialValue: 20,
              rules: [{ type: "number", min: 1, max: 120 }]
            },
            /* @__PURE__ */ t.createElement(g, { min: 1, max: 120, addonAfter: "s", style: { width: "100%" } })
          ))
        }
      ]
    }
  ), /* @__PURE__ */ t.createElement(u, { type: "warning", showIcon: !0, message: e.plainText, style: { marginTop: 16 } }));
}
window.QwenPaw.memoryBackends.register("memory-memorylake", {
  id: "memorylake",
  label: "Memory Lake",
  configPath: n,
  tabKey: "memorylakeMemory",
  ConfigComponent: $
});
