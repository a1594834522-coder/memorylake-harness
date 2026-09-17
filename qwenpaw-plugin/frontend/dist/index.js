const e = window.QwenPaw.host.React, { useState: g, useCallback: B, useEffect: F, useMemo: E } = e, {
  Alert: d,
  AutoComplete: v,
  Button: z,
  Card: M,
  Collapse: q,
  Form: r,
  Input: Q,
  InputNumber: h,
  Select: $,
  Space: w,
  Switch: C,
  Tag: S,
  Typography: p
} = window.QwenPaw.host.antd, o = ["memory_backend_configs", "memorylake"], f = [
  { value: "", site: "https://memorylake.ai", labelKey: "regionIntl" },
  { value: "https://app.memorylake.cn/openapi/memorylake", site: "https://memorylake.cn", labelKey: "regionCn" }
], K = {
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
    sync: "Conversation sync",
    syncHelp: "Record this Agent's conversations in Memory Lake so it can distill memories from them. Only the text of what the user says and what the Agent replies is sent, in batches after every N user turns. Tool calls, tool results, and reasoning never leave this machine.",
    syncSwitch: "Record conversations to Memory Lake",
    project: "Project",
    projectHelp: "The Memory Lake project the conversation is filed under. Required for sync.",
    noProjects: "This workspace has no projects yet. Create one in the Memory Lake console.",
    syncInterval: "Send every N user turns",
    syncIntervalHelp: "1 sends after every reply. Batches are also sent when the context is compacted and on /new.",
    syncNeedsActor: "Sync needs an actor: the user's messages are attributed to it.",
    syncNeedsProject: "Sync needs a project.",
    maxMessageChars: "Max characters per recorded message",
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
    sync: "对话同步",
    syncHelp: "把该 Agent 的对话记录到 Memory Lake，由它在后台提炼记忆。只发送用户说的话和 Agent 回复的文字，每 N 轮用户对话批量发送一次。工具调用、工具结果和推理过程不会离开本机。",
    syncSwitch: "将对话记录到 Memory Lake",
    project: "Project",
    projectHelp: "对话归档到的 Memory Lake project。开启同步时必填。",
    noProjects: "该 workspace 还没有 project，请先到 Memory Lake 控制台创建。",
    syncInterval: "每 N 轮用户对话发送一次",
    syncIntervalHelp: "填 1 表示每次回复后就发送。上下文压缩和 /new 时也会发送。",
    syncNeedsActor: "同步需要 actor：用户的消息会归属于它。",
    syncNeedsProject: "同步需要选择 project。",
    maxMessageChars: "每条记录消息的最大字数",
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
function D() {
  var l, i;
  return (((i = (l = window.QwenPaw.host).useLocale) == null ? void 0 : i.call(l)) || "en").toLowerCase().startsWith("zh") ? K.zh : K.en;
}
function G() {
  var t, l;
  try {
    const i = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage");
    return i ? String(((l = (t = JSON.parse(i)) == null ? void 0 : t.state) == null ? void 0 : l.selectedAgent) ?? "") : "";
  } catch {
    return "";
  }
}
async function J(t) {
  const { getApiUrl: l, getApiToken: i } = window.QwenPaw.host, m = { "Content-Type": "application/json" }, s = i();
  s && (m.Authorization = `Bearer ${s}`);
  const y = G();
  y && (m["X-Agent-Id"] = y);
  const u = await fetch(l("/memorylake/discover"), {
    method: "POST",
    headers: m,
    body: JSON.stringify({ agent_id: y, ...t })
  });
  if (!u.ok)
    throw new Error(`HTTP ${u.status}`);
  return await u.json();
}
function U() {
  const t = D(), l = r.useFormInstance(), i = r.useWatch([...o, "api_key"], l) ?? "", m = r.useWatch([...o, "base_url"], l) ?? "", s = r.useWatch([...o, "workspace"], l) ?? "", y = r.useWatch([...o, "install_cli"], l) ?? !0, u = r.useWatch([...o, "actor"], l) ?? "", T = r.useWatch([...o, "project"], l) ?? "", k = r.useWatch([...o, "sync_conversations"], l) ?? !1, [b, A] = g(!1), [a, L] = g(null), [x, I] = g(""), [R, H] = g(""), j = f.find((n) => n.value === m) ?? f[0], P = B(
    async (n) => {
      A(!0), I("");
      try {
        const c = await J({
          api_key: i,
          base_url: m,
          workspace: n ?? s,
          install_cli: y
        });
        if (L(c), H(n ?? s), !c.ok) {
          I(c.error_kind === "cli-missing" ? t.errCli : c.error_kind === "not-logged-in" ? t.errAuth : t.errOther);
          return;
        }
        !l.getFieldValue([...o, "workspace"]) && c.workspaces.length === 1 && l.setFieldValue([...o, "workspace"], c.workspaces[0].id), !l.getFieldValue([...o, "actor"]) && c.me && c.actors.some((_) => _.id === c.me && _.status === "ACTIVE") && l.setFieldValue([...o, "actor"], c.me);
      } catch (c) {
        L(null), I(`${t.errOther}: ${c.message}`);
      } finally {
        A(!1);
      }
    },
    [i, m, s, y, l, t]
  );
  F(() => {
    a != null && a.ok && s && s !== R && P(s);
  }, [s]);
  const N = E(
    () => (a != null && a.ok ? a.workspaces : []).map((n) => ({
      value: n.id,
      label: /* @__PURE__ */ e.createElement(w, { size: 6 }, /* @__PURE__ */ e.createElement("span", null, n.name || n.id), n.name ? /* @__PURE__ */ e.createElement(p.Text, { type: "secondary", style: { fontSize: 12 } }, n.id) : null)
    })),
    [a]
  ), O = E(
    () => (a != null && a.ok ? a.actors : []).map((n) => ({
      value: n.id,
      label: /* @__PURE__ */ e.createElement(w, { size: 6 }, /* @__PURE__ */ e.createElement("span", null, n.display_name || n.id), n.id === (a == null ? void 0 : a.me) ? /* @__PURE__ */ e.createElement(S, { color: "blue" }, t.me) : null, n.status && n.status !== "ACTIVE" ? /* @__PURE__ */ e.createElement(S, null, t.deleted) : null, /* @__PURE__ */ e.createElement(p.Text, { type: "secondary", style: { fontSize: 12 } }, n.id))
    })),
    [a, t]
  ), V = E(
    () => (a != null && a.ok ? a.projects ?? [] : []).map((n) => ({
      value: n.id,
      label: /* @__PURE__ */ e.createElement(w, { size: 6 }, /* @__PURE__ */ e.createElement("span", null, n.name || n.id), n.name ? /* @__PURE__ */ e.createElement(p.Text, { type: "secondary", style: { fontSize: 12 } }, n.id) : null)
    })),
    [a]
  ), W = a != null && a.ok ? a.login === "request key" ? t.viaRequestKey : a.login === "saved key" ? t.viaSavedKey : t.viaShared : "";
  return /* @__PURE__ */ e.createElement(M, { title: t.title }, /* @__PURE__ */ e.createElement(d, { type: "info", showIcon: !0, message: t.intro, style: { marginBottom: 16 } }), /* @__PURE__ */ e.createElement(r.Item, { name: [...o, "base_url"], label: t.region, initialValue: "" }, /* @__PURE__ */ e.createElement($, { options: f.map((n) => ({ value: n.value, label: t[n.labelKey] })) })), /* @__PURE__ */ e.createElement(
    r.Item,
    {
      name: [...o, "api_key"],
      label: t.apiKey,
      extra: /* @__PURE__ */ e.createElement("span", null, t.apiKeyHelp, " ", t.getKey, " ", /* @__PURE__ */ e.createElement(p.Link, { href: j.site, target: "_blank", rel: "noreferrer" }, j.site.replace("https://", "")))
    },
    /* @__PURE__ */ e.createElement(Q.Password, { placeholder: "sk-...", autoComplete: "new-password" })
  ), /* @__PURE__ */ e.createElement(w, { style: { marginBottom: 16 }, wrap: !0 }, /* @__PURE__ */ e.createElement(z, { onClick: () => void P(), loading: b, type: a ? "default" : "primary" }, b ? t.loading : a ? t.reload : t.load), a != null && a.ok ? /* @__PURE__ */ e.createElement(p.Text, { type: "secondary" }, t.loaded, " · ", W) : null), x ? /* @__PURE__ */ e.createElement(d, { type: "error", showIcon: !0, message: x, description: a == null ? void 0 : a.error, style: { marginBottom: 16 } }) : null, a != null && a.ok && a.workspaces.length === 0 ? /* @__PURE__ */ e.createElement(d, { type: "warning", showIcon: !0, message: t.noWorkspaces, style: { marginBottom: 16 } }) : null, /* @__PURE__ */ e.createElement(r.Item, { name: [...o, "workspace"], label: t.workspace, extra: t.workspaceHelp }, /* @__PURE__ */ e.createElement(v, { options: N, allowClear: !0, placeholder: "ws-...", filterOption: !0 })), /* @__PURE__ */ e.createElement(r.Item, { name: [...o, "actor"], label: t.actor, extra: t.actorHelp }, /* @__PURE__ */ e.createElement(
    v,
    {
      options: O,
      allowClear: !0,
      placeholder: "actor-...",
      filterOption: !0,
      notFoundContent: a != null && a.ok && s ? t.noActors : null
    }
  )), /* @__PURE__ */ e.createElement(M, { type: "inner", title: t.sync, style: { marginBottom: 16 } }, /* @__PURE__ */ e.createElement(p.Paragraph, { type: "secondary", style: { marginBottom: 12 } }, t.syncHelp), /* @__PURE__ */ e.createElement(
    r.Item,
    {
      name: [...o, "sync_conversations"],
      label: t.syncSwitch,
      valuePropName: "checked",
      initialValue: !1
    },
    /* @__PURE__ */ e.createElement(C, null)
  ), k && !u ? /* @__PURE__ */ e.createElement(d, { type: "warning", showIcon: !0, message: t.syncNeedsActor, style: { marginBottom: 12 } }) : null, k && !T ? /* @__PURE__ */ e.createElement(d, { type: "warning", showIcon: !0, message: t.syncNeedsProject, style: { marginBottom: 12 } }) : null, /* @__PURE__ */ e.createElement(r.Item, { name: [...o, "project"], label: t.project, extra: t.projectHelp }, /* @__PURE__ */ e.createElement(
    v,
    {
      options: V,
      allowClear: !0,
      placeholder: "proj-...",
      filterOption: !0,
      disabled: !k,
      notFoundContent: a != null && a.ok && s ? t.noProjects : null
    }
  )), /* @__PURE__ */ e.createElement(
    r.Item,
    {
      name: [...o, "sync_interval"],
      label: t.syncInterval,
      extra: t.syncIntervalHelp,
      initialValue: 1,
      rules: [{ type: "number", min: 1, max: 20 }]
    },
    /* @__PURE__ */ e.createElement(h, { min: 1, max: 20, disabled: !k, style: { width: "100%" } })
  )), /* @__PURE__ */ e.createElement(
    q,
    {
      items: [
        {
          key: "advanced",
          label: t.advanced,
          forceRender: !0,
          children: /* @__PURE__ */ e.createElement(e.Fragment, null, /* @__PURE__ */ e.createElement(
            r.Item,
            {
              name: [...o, "auto_recall"],
              label: t.autoRecall,
              tooltip: t.autoRecallHelp,
              valuePropName: "checked",
              initialValue: !0
            },
            /* @__PURE__ */ e.createElement(C, null)
          ), /* @__PURE__ */ e.createElement(
            r.Item,
            {
              name: [...o, "auto_recall_top_k"],
              label: t.autoRecallTopK,
              initialValue: 3,
              rules: [{ type: "number", min: 1, max: 10 }]
            },
            /* @__PURE__ */ e.createElement(h, { min: 1, max: 10, style: { width: "100%" } })
          ), /* @__PURE__ */ e.createElement(
            r.Item,
            {
              name: [...o, "top_k"],
              label: t.topK,
              initialValue: 5,
              rules: [{ type: "number", min: 1, max: 20 }]
            },
            /* @__PURE__ */ e.createElement(h, { min: 1, max: 20, style: { width: "100%" } })
          ), /* @__PURE__ */ e.createElement(
            r.Item,
            {
              name: [...o, "max_message_chars"],
              label: t.maxMessageChars,
              initialValue: 8e3,
              rules: [{ type: "number", min: 500, max: 64e3 }]
            },
            /* @__PURE__ */ e.createElement(h, { min: 500, max: 64e3, step: 500, style: { width: "100%" } })
          ), /* @__PURE__ */ e.createElement(
            r.Item,
            {
              name: [...o, "install_cli"],
              label: t.installCli,
              valuePropName: "checked",
              initialValue: !0
            },
            /* @__PURE__ */ e.createElement(C, null)
          ), /* @__PURE__ */ e.createElement(
            r.Item,
            {
              name: [...o, "timeout_seconds"],
              label: t.timeout,
              initialValue: 20,
              rules: [{ type: "number", min: 1, max: 120 }]
            },
            /* @__PURE__ */ e.createElement(h, { min: 1, max: 120, addonAfter: "s", style: { width: "100%" } })
          ))
        }
      ]
    }
  ), /* @__PURE__ */ e.createElement(d, { type: "warning", showIcon: !0, message: t.plainText, style: { marginTop: 16 } }));
}
window.QwenPaw.memoryBackends.register("memory-memorylake", {
  id: "memorylake",
  label: "Memory Lake",
  configPath: o,
  tabKey: "memorylakeMemory",
  ConfigComponent: U
});
