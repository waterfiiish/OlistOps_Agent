import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

type Health = {
  status: string;
  database: null | {
    database: string;
    version: string;
    vector_enabled: string;
  };
  model: {
    status: string;
    configured_model: string;
    available_models?: string[];
  };
  rag?: null | {
    retrieval_mode: string;
    embedding_provider: string;
    document_count: number;
    chunk_count: number;
    embedded_chunk_count: number;
    embedding_coverage: number;
  };
  error?: string | null;
};

type TimelineEvent = {
  id: number;
  type: string;
  label: string;
  detail?: string;
};

const DEMO_QUERY =
  "分析 2018 年 7 月的配送表现，找出延期率最高且订单量不少于 20 的卖家和商品类别，比较延期订单与按时订单的平均评分，并给出改进建议。";

const SCENARIOS = [
  {
    label: "经营总览",
    code: "OVERVIEW",
    query:
      "分析 2018 年全年的经营总览，包括订单状态、取消与不可用订单、销售代理值、整体延期率和平均评分。"
  },
  {
    label: "月度趋势",
    code: "TREND",
    query:
      "分析 2017 年 1 月到 2018 年 8 月的月度趋势，比较订单量、GMV 代理值、延期率、配送天数和评分变化。"
  },
  {
    label: "配送异常",
    code: "DELIVERY",
    query: DEMO_QUERY
  },
  {
    label: "地区履约",
    code: "REGION",
    query:
      "比较 2018 年各州地区的履约表现，订单量至少 100，找出延期率、平均配送天数和评分表现异常的区域。"
  },
  {
    label: "运费结构",
    code: "FREIGHT",
    query:
      "分析 2018 年运费结构，先给出整体运费占比，再找出订单量不少于 100 且运费占比较高的商品类别。"
  },
  {
    label: "支付方式",
    code: "PAYMENT",
    query:
      "分析 2018 年支付方式构成，比较各支付方式的金额占比、参与订单量、平均最大分期数和支付序列数。"
  },
  {
    label: "低分评论",
    code: "REVIEW",
    query:
      "分析 2018 年低分评论样本，区分延期与非延期订单，结合处理规范总结可核查的问题和改进方向。"
  }
];

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [query, setQuery] = useState(DEMO_QUERY);
  const [answer, setAnswer] = useState("");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const eventId = useRef(0);

  useEffect(() => {
    fetch("/healthz")
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  function append(type: string, label: string, detail?: string) {
    eventId.current += 1;
    setTimeline((current) => [
      ...current,
      { id: eventId.current, type, label, detail }
    ]);
  }

  async function runAnalysis(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || running) return;
    setRunning(true);
    setError("");
    setAnswer("");
    setTimeline([]);

    try {
      let activeSessionId = sessionId;
      if (!activeSessionId) {
        const sessionResponse = await fetch("/api/v1/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "OlistOps 多场景分析" })
        });
        if (!sessionResponse.ok) throw new Error("创建会话失败");
        const session = await sessionResponse.json();
        activeSessionId = session.id;
        setSessionId(activeSessionId);
      }

      const runResponse = await fetch(
        `/api/v1/sessions/${activeSessionId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: query })
        }
      );
      if (!runResponse.ok) throw new Error("提交分析任务失败");
      const run = await runResponse.json();
      append("run", "运行已排队", run.run_id);

      const stream = new EventSource(run.events_url);
      const close = () => {
        stream.close();
        setRunning(false);
      };
      stream.addEventListener("run.started", () =>
        append("run", "工作流开始")
      );
      stream.addEventListener("node.started", (message) => {
        const payload = JSON.parse((message as MessageEvent).data);
        append("node", `节点：${payload.node}`);
      });
      stream.addEventListener("tool.completed", (message) => {
        const payload = JSON.parse((message as MessageEvent).data);
        append(
          "tool",
          payload.tool_name,
          `${payload.permission} · ${payload.result_summary.row_count} rows`
        );
      });
      stream.addEventListener("retrieval.completed", (message) => {
        const payload = JSON.parse((message as MessageEvent).data);
        const topTitles = (payload.results ?? [])
          .slice(0, 2)
          .map((item: { title?: string }) => item.title)
          .filter(Boolean)
          .join(" / ");
        append(
          "rag",
          `混合检索：${payload.result_count} 个证据片段`,
          `${String(payload.mode).toUpperCase()} · ${topTitles || "无匹配知识"}`
        );
      });
      stream.addEventListener("assistant.delta", (message) => {
        const payload = JSON.parse((message as MessageEvent).data);
        setAnswer((current) => current + payload.content);
      });
      stream.addEventListener("run.completed", (message) => {
        const payload = JSON.parse((message as MessageEvent).data);
        append("done", "分析完成", payload.model_used);
        close();
      });
      stream.addEventListener("run.failed", (message) => {
        const payload = JSON.parse((message as MessageEvent).data);
        setError(payload.error?.message ?? payload.error ?? "运行失败");
        close();
      });
      stream.onerror = () => {
        if (stream.readyState === EventSource.CLOSED) close();
      };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "未知错误");
      setRunning(false);
    }
  }

  const databaseOk = health?.database?.vector_enabled === "true";
  const modelOk = health?.model.status === "ok";

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">LOCAL ENTERPRISE AGENT · OLIST 2016—2018</p>
          <h1>
            履约数据有答案，
            <br />
            每个结论都有证据。
          </h1>
          <p className="lede">
            确定性指标、知识检索与有限状态工作流协同运行。
            数据事实、业务推断和行动建议各自分层。
          </p>
        </div>
        <section className="system-card" aria-label="System status">
          <div className="status-heading">
            <span>系统状态</span>
            <span className={`status-pill ${health?.status ?? "loading"}`}>
              {health?.status ?? "checking"}
            </span>
          </div>
          <dl>
            <div>
              <dt>PostgreSQL</dt>
              <dd>{databaseOk ? `v${health?.database?.version}` : "不可用"}</dd>
            </div>
            <div>
              <dt>pgvector</dt>
              <dd>{databaseOk ? "已启用" : "待检查"}</dd>
            </div>
            <div>
              <dt>本地模型</dt>
              <dd>
                {modelOk ? health?.model.configured_model : "模板回退可用"}
              </dd>
            </div>
            <div>
              <dt>Hybrid RAG</dt>
              <dd>
                {health?.rag
                  ? `${health.rag.embedded_chunk_count}/${health.rag.chunk_count} vectors`
                  : "待检查"}
              </dd>
            </div>
          </dl>
        </section>
      </header>

      <section className="scenario-library" aria-label="分析场景库">
        <div className="scenario-heading">
          <div>
            <span className="step-number">00</span>
            <h2>分析场景库</h2>
          </div>
          <span className="scope">7 deterministic routes</span>
        </div>
        <p>
          选择一个场景会填入可直接运行的问题。所有数字仍由受约束工具计算，
          模型只负责组织通过混合检索、证据门控和 Critic 检查的结果。
        </p>
        <div className="scenario-grid">
          {SCENARIOS.map((scenario) => (
            <button
              className="scenario-button"
              type="button"
              key={scenario.code}
              onClick={() => setQuery(scenario.query)}
              disabled={running}
            >
              <span>{scenario.label}</span>
              <small>{scenario.code}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="workspace-grid">
        <form className="query-panel" onSubmit={runAnalysis}>
          <div className="panel-heading">
            <div>
              <span className="step-number">01</span>
              <h2>分析任务</h2>
            </div>
            <span className="scope">
              {sessionId ? `session ${sessionId.slice(0, 8)}` : "只读 MART"}
            </span>
          </div>
          <label htmlFor="query">自然语言请求</label>
          <textarea
            id="query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={8}
          />
          <div className="guardrail">
            <span>安全边界</span>
            指标由受约束工具计算；写操作需要审批；不执行任意 SQL。
          </div>
          <button type="submit" disabled={running || !databaseOk}>
            {running ? "正在分析…" : "运行证据分析"}
            <span aria-hidden="true">→</span>
          </button>
          {error && <p className="error">{error}</p>}
        </form>

        <section className="trace-panel">
          <div className="panel-heading">
            <div>
              <span className="step-number">02</span>
              <h2>实时 Trace</h2>
            </div>
            <span className="scope">{timeline.length} events</span>
          </div>
          <div className="timeline">
            {timeline.length === 0 ? (
              <div className="empty">
                运行后，这里会展示节点、工具权限、混合检索与 Critic。
              </div>
            ) : (
              timeline.map((item) => (
                <div className={`timeline-row ${item.type}`} key={item.id}>
                  <span className="timeline-dot" />
                  <div>
                    <strong>{item.label}</strong>
                    {item.detail && <small>{item.detail}</small>}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </section>

      <section className="answer-panel">
        <div className="panel-heading">
          <div>
            <span className="step-number">03</span>
            <h2>有依据的报告</h2>
          </div>
          <span className="scope">事实 / 推断 / 建议</span>
        </div>
        {answer ? (
          <article className="markdown">
            <ReactMarkdown>{answer}</ReactMarkdown>
          </article>
        ) : (
          <div className="answer-placeholder">
            <span>KPI</span>
            <span>卖家 / 类别</span>
            <span>评论评分差</span>
            <span>知识引用</span>
            <span>Critic</span>
          </div>
        )}
      </section>
    </main>
  );
}

export default App;
