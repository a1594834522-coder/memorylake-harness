import type * as ReactNS from "react";

// The Console form for `memory_backend_configs.memorylake`.
//
// Field names and bounds mirror `memorylake_backend/config.py`; the backend
// validates on save. Workspace and actor are pickers fed by the plugin's own
// `POST /api/memorylake/discover`, which runs the CLI with the credentials the
// form is about to save (an unsaved key is used from a throwaway HOME and
// never written to disk by that call).

const React: typeof ReactNS = window.QwenPaw.host.React;
const { useState, useCallback, useEffect, useMemo } = React;
const {
  Alert,
  AutoComplete,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} = window.QwenPaw.host.antd;

const root = ["memory_backend_configs", "memorylake"];

type Region = { value: string; site: string; labelKey: "regionIntl" | "regionCn" };
const REGIONS: Region[] = [
  { value: "", site: "https://memorylake.ai", labelKey: "regionIntl" },
  { value: "https://app.memorylake.cn/openapi/memorylake", site: "https://memorylake.cn", labelKey: "regionCn" },
];

const messages = {
  en: {
    title: "Memory Lake",
    intro:
      "Long-term memory shared across projects, machines, and clients. If this machine is already set up for Claude Code, Codex, dsh, or opencode, leave every field empty: the shared ~/.memorylake configuration and login are used.",
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
    plainText:
      "The API key is masked here and in the API, but stored in agent.json in plain text, like other memory backends' credentials.",
  },
  zh: {
    title: "Memory Lake",
    intro:
      "跨项目、跨设备、跨客户端的长期记忆。如果这台机器已经为 Claude Code、Codex、dsh 或 opencode 配置过 Memory Lake，所有字段留空即可，会直接使用共享的 ~/.memorylake 配置和登录。",
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
    plainText:
      "API key 在表单和接口中会被遮罩，但和其他记忆后端的凭据一样，以明文保存在 agent.json 中。",
  },
} as const;

type Messages = (typeof messages)["en"];

function useMessages(): Messages {
  const locale = (window.QwenPaw.host.useLocale?.() || "en").toLowerCase();
  return (locale.startsWith("zh") ? messages.zh : messages.en) as Messages;
}

// Mirrors the host's buildAuthHeaders(): the Console keeps the selected agent
// in (session|local)Storage and identifies API calls with it.
function selectedAgentId(): string {
  try {
    const raw =
      sessionStorage.getItem("qwenpaw-agent-storage") ||
      localStorage.getItem("qwenpaw-agent-storage");
    return raw ? String(JSON.parse(raw)?.state?.selectedAgent ?? "") : "";
  } catch {
    return "";
  }
}

interface DiscoverResponse {
  ok: boolean;
  error?: string;
  error_kind?: string;
  login?: string;
  workspaces: { id: string; name: string }[];
  actors: { id: string; display_name: string; status: string }[];
  me?: string;
}

async function discover(body: Record<string, unknown>): Promise<DiscoverResponse> {
  const { getApiUrl, getApiToken } = window.QwenPaw.host;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getApiToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const agentId = selectedAgentId();
  if (agentId) headers["X-Agent-Id"] = agentId;
  const response = await fetch(getApiUrl("/memorylake/discover"), {
    method: "POST",
    headers,
    body: JSON.stringify({ agent_id: agentId, ...body }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as DiscoverResponse;
}

function MemoryLakeConfigCard() {
  const text = useMessages();
  const form = Form.useFormInstance();
  const apiKey: string = Form.useWatch([...root, "api_key"], form) ?? "";
  const baseUrl: string = Form.useWatch([...root, "base_url"], form) ?? "";
  const workspace: string = Form.useWatch([...root, "workspace"], form) ?? "";
  const installCli: boolean = Form.useWatch([...root, "install_cli"], form) ?? true;

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiscoverResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [loadedFor, setLoadedFor] = useState<string>("");

  const region = REGIONS.find((r) => r.value === baseUrl) ?? REGIONS[0];

  const load = useCallback(
    async (ws?: string) => {
      setLoading(true);
      setError("");
      try {
        const data = await discover({
          api_key: apiKey,
          base_url: baseUrl,
          workspace: ws ?? workspace,
          install_cli: installCli,
        });
        setResult(data);
        setLoadedFor(ws ?? workspace);
        if (!data.ok) {
          setError(data.error_kind === "cli-missing" ? text.errCli
            : data.error_kind === "not-logged-in" ? text.errAuth
            : text.errOther);
          return;
        }
        // One workspace: pick it. The caller's own actor, if bound: pick it.
        const current = form.getFieldValue([...root, "workspace"]) as string;
        if (!current && data.workspaces.length === 1) {
          form.setFieldValue([...root, "workspace"], data.workspaces[0].id);
        }
        const currentActor = form.getFieldValue([...root, "actor"]) as string;
        if (!currentActor && data.me && data.actors.some((a) => a.id === data.me && a.status === "ACTIVE")) {
          form.setFieldValue([...root, "actor"], data.me);
        }
      } catch (e) {
        setResult(null);
        setError(`${text.errOther}: ${(e as Error).message}`);
      } finally {
        setLoading(false);
      }
    },
    [apiKey, baseUrl, workspace, installCli, form, text],
  );

  // Actors depend on the workspace: refresh them when the picked workspace
  // changes after a successful load.
  useEffect(() => {
    if (result?.ok && workspace && workspace !== loadedFor) {
      void load(workspace);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace]);

  const workspaceOptions = useMemo(
    () => (result?.ok ? result.workspaces : []).map((w) => ({
      value: w.id,
      label: (
        <Space size={6}>
          <span>{w.name || w.id}</span>
          {w.name ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>{w.id}</Typography.Text> : null}
        </Space>
      ),
    })),
    [result],
  );

  const actorOptions = useMemo(
    () => (result?.ok ? result.actors : []).map((a) => ({
      value: a.id,
      label: (
        <Space size={6}>
          <span>{a.display_name || a.id}</span>
          {a.id === result?.me ? <Tag color="blue">{text.me}</Tag> : null}
          {a.status && a.status !== "ACTIVE" ? <Tag>{text.deleted}</Tag> : null}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{a.id}</Typography.Text>
        </Space>
      ),
    })),
    [result, text],
  );

  const loginNote = result?.ok
    ? result.login === "request key" ? text.viaRequestKey
      : result.login === "saved key" ? text.viaSavedKey
      : text.viaShared
    : "";

  return (
    <Card title={text.title}>
      <Alert type="info" showIcon message={text.intro} style={{ marginBottom: 16 }} />

      <Form.Item name={[...root, "base_url"]} label={text.region} initialValue="">
        <Select options={REGIONS.map((r) => ({ value: r.value, label: text[r.labelKey] }))} />
      </Form.Item>

      <Form.Item
        name={[...root, "api_key"]}
        label={text.apiKey}
        extra={
          <span>
            {text.apiKeyHelp} {text.getKey}{" "}
            <Typography.Link href={region.site} target="_blank" rel="noreferrer">
              {region.site.replace("https://", "")}
            </Typography.Link>
          </span>
        }
      >
        <Input.Password placeholder="sk-..." autoComplete="new-password" />
      </Form.Item>

      <Space style={{ marginBottom: 16 }} wrap>
        <Button onClick={() => void load()} loading={loading} type={result ? "default" : "primary"}>
          {loading ? text.loading : result ? text.reload : text.load}
        </Button>
        {result?.ok ? (
          <Typography.Text type="secondary">
            {text.loaded} · {loginNote}
          </Typography.Text>
        ) : null}
      </Space>
      {error ? (
        <Alert type="error" showIcon message={error} description={result?.error} style={{ marginBottom: 16 }} />
      ) : null}
      {result?.ok && result.workspaces.length === 0 ? (
        <Alert type="warning" showIcon message={text.noWorkspaces} style={{ marginBottom: 16 }} />
      ) : null}

      <Form.Item name={[...root, "workspace"]} label={text.workspace} extra={text.workspaceHelp}>
        <AutoComplete options={workspaceOptions} allowClear placeholder="ws-..." filterOption />
      </Form.Item>

      <Form.Item name={[...root, "actor"]} label={text.actor} extra={text.actorHelp}>
        <AutoComplete
          options={actorOptions}
          allowClear
          placeholder="actor-..."
          filterOption
          notFoundContent={result?.ok && workspace ? text.noActors : null}
        />
      </Form.Item>

      <Collapse
        items={[
          {
            key: "advanced",
            label: text.advanced,
            forceRender: true,
            children: (
              <>
                <Form.Item
                  name={[...root, "auto_recall"]}
                  label={text.autoRecall}
                  tooltip={text.autoRecallHelp}
                  valuePropName="checked"
                  initialValue={true}
                >
                  <Switch />
                </Form.Item>
                <Form.Item
                  name={[...root, "auto_recall_top_k"]}
                  label={text.autoRecallTopK}
                  initialValue={3}
                  rules={[{ type: "number", min: 1, max: 10 }]}
                >
                  <InputNumber min={1} max={10} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name={[...root, "top_k"]}
                  label={text.topK}
                  initialValue={5}
                  rules={[{ type: "number", min: 1, max: 20 }]}
                >
                  <InputNumber min={1} max={20} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name={[...root, "install_cli"]}
                  label={text.installCli}
                  valuePropName="checked"
                  initialValue={true}
                >
                  <Switch />
                </Form.Item>
                <Form.Item
                  name={[...root, "timeout_seconds"]}
                  label={text.timeout}
                  initialValue={20}
                  rules={[{ type: "number", min: 1, max: 120 }]}
                >
                  <InputNumber min={1} max={120} addonAfter="s" style={{ width: "100%" }} />
                </Form.Item>
              </>
            ),
          },
        ]}
      />
      <Alert type="warning" showIcon message={text.plainText} style={{ marginTop: 16 }} />
    </Card>
  );
}

window.QwenPaw.memoryBackends.register("memory-memorylake", {
  id: "memorylake",
  label: "Memory Lake",
  configPath: root,
  tabKey: "memorylakeMemory",
  ConfigComponent: MemoryLakeConfigCard,
});
