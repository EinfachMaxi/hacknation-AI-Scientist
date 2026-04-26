import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  getRun,
  getRunEvents,
  getRunGraph,
  getRunMessages,
  getRunPlan,
  setActiveRunId,
} from "../../lib/api";
import { supabase } from "../../lib/supabase";
import type {
  AgentEvent,
  GraphEdge,
  GraphNode,
  RunGraphSnapshot,
} from "../../types/plan";
import "./LiveAgentProgress.css";

interface AgentLog {
  text: string;
  type: "default" | "primary" | "secondary" | "error";
}
interface AgentFeedMessage {
  id: string;
  from: string;
  to: string;
  text: string;
  level: "info" | "success" | "warn";
}
type AgentLogType = AgentLog["type"];
type AgentRuntimeState =
  | "idle"
  | "pending"
  | "ready"
  | "running"
  | "completed"
  | "failed"
  | "skipped";
type AgentColor = "secondary" | "primary" | "tertiary" | "dormant";
type GraphNodeKey = string;

interface AgentConfig {
  id: string;
  name: string;
  icon: string;
  baseColor: AgentColor;
}

interface AgentViewModel extends AgentConfig {
  progress: number;
  status: string;
  color: AgentColor;
  logs: AgentLog[];
  active: boolean;
  runtimeState: AgentRuntimeState;
}

const agentVisualMap: Record<string, { icon: string; baseColor: AgentColor }> =
  {
    planner: { icon: "psychology", baseColor: "primary" },
    literature: { icon: "menu_book", baseColor: "secondary" },
    protocol: { icon: "architecture", baseColor: "primary" },
    materials: { icon: "science", baseColor: "tertiary" },
    budget: { icon: "payments", baseColor: "secondary" },
    timeline: { icon: "calendar_month", baseColor: "primary" },
    review: { icon: "fact_check", baseColor: "dormant" },
  };

const fallbackVisual = { icon: "hub", baseColor: "secondary" as AgentColor };

const plannerOnlyDefault: AgentConfig[] = [
  {
    id: "planner",
    name: "Planner LLM",
    icon: agentVisualMap.planner.icon,
    baseColor: agentVisualMap.planner.baseColor,
  },
];

const statusLabels: Record<AgentRuntimeState, string> = {
  idle: "IDLE",
  pending: "PENDING",
  ready: "READY",
  running: "RUNNING",
  completed: "COMPLETED",
  failed: "FAILED",
  skipped: "SKIPPED",
};

const seededRandom = (seed: number): (() => number) => {
  let value = seed % 2147483647;
  if (value <= 0) {
    value += 2147483646;
  }
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
};

const layoutSeedFromRunId = (value: string): number =>
  value
    .split("")
    .reduce((acc, char, index) => acc + char.charCodeAt(0) * (index + 17), 811);

export default function LiveAgentProgress() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [graph, setGraph] = useState<RunGraphSnapshot | null>(null);
  const [runMessages, setRunMessages] = useState<AgentFeedMessage[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [streamError, setStreamError] = useState<string | null>(null);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const seenRunSeqRef = useRef<Set<string>>(new Set());
  const hypothesis =
    (location.state as { hypothesis?: string } | null)?.hypothesis ??
    "No hypothesis text provided yet.";
  const runId =
    (location.state as { runId?: string } | null)?.runId ?? id ?? "";

  const colorMap: Record<string, string> = useMemo(
    () => ({
      secondary: "var(--on-surface)",
      primary: "var(--primary)",
      tertiary: "var(--outline)",
      dormant: "var(--outline-variant)",
    }),
    [],
  );

  const mapEventToAgent = (event: AgentEvent): string => event.agent;

  const runtimeStateFromEvent = (event: AgentEvent): AgentRuntimeState => {
    if (event.phase === "error" || event.status === "failed") {
      return "failed";
    }
    if (event.phase === "complete" || event.status === "completed") {
      return "completed";
    }
    return "running";
  };

  const ingestEvent = (event: AgentEvent): void => {
    const seqKey = `${event.run_id}:${event.sequence}`;
    if (
      seenEventIdsRef.current.has(event.event_id) ||
      seenRunSeqRef.current.has(seqKey)
    ) {
      return;
    }
    seenEventIdsRef.current.add(event.event_id);
    seenRunSeqRef.current.add(seqKey);
    setEvents((prev) =>
      [...prev, event].sort((a, b) => a.sequence - b.sequence),
    );
  };

  const agents = useMemo<AgentViewModel[]>(() => {
    const graphNodes = graph?.nodes ?? [];
    // Nur Nodes anzeigen, die schon vom Planner gespawnt wurden.
    // Der Planner selbst ist immer sichtbar.
    const visibleNodes = graphNodes.filter(
      (node) => node.id === "planner" || node.state !== "pending",
    );
    const dynamicConfig: AgentConfig[] = visibleNodes.map((node) => {
      const visual = agentVisualMap[node.id] ?? fallbackVisual;
      return {
        id: node.id,
        name: node.label,
        icon: visual.icon,
        baseColor: visual.baseColor,
      };
    });
    const configList = dynamicConfig.length
      ? dynamicConfig
      : plannerOnlyDefault;
    const grouped = new Map<string, AgentEvent[]>();
    events.forEach((event) => {
      const key = mapEventToAgent(event);
      grouped.set(key, [...(grouped.get(key) ?? []), event]);
    });
    return configList.map((config) => {
      const agentEvents = grouped.get(config.id) ?? [];
      const lastEvent = agentEvents[agentEvents.length - 1];
      const graphNode = visibleNodes.find((node) => node.id === config.id);
      const runtimeState: AgentRuntimeState = graphNode
        ? (graphNode.state as AgentRuntimeState)
        : lastEvent
          ? runtimeStateFromEvent(lastEvent)
          : "idle";
      const progress =
        graphNode?.progress_pct ??
        (runtimeState === "completed"
          ? 100
          : runtimeState === "running"
            ? 60
            : 0);
      const color: AgentColor =
        runtimeState === "failed"
          ? "tertiary"
          : runtimeState === "skipped"
            ? "dormant"
            : config.baseColor;
      const logs: AgentLog[] = agentEvents
        .slice(-4)
        .reverse()
        .map((event) => {
          const logType: AgentLogType =
            event.phase === "error" ? "error" : "default";
          return {
            text: `> ${event.agent}: ${event.phase}${event.message ? ` - ${event.message}` : ""}`,
            type: logType,
          };
        });

      return {
        ...config,
        progress,
        status: statusLabels[runtimeState],
        color,
        logs,
        active: runtimeState !== "idle" && runtimeState !== "pending",
        runtimeState,
      };
    });
  }, [events, graph]);

  const messages = useMemo<AgentFeedMessage[]>(
    () => runMessages,
    [runMessages],
  );

  const graphEdges = useMemo(() => graph?.edges ?? [], [graph]);

  const graphNodes = useMemo(
    () =>
      Object.fromEntries(agents.map((agent) => [agent.id, agent])) as Record<
        string,
        AgentViewModel
      >,
    [agents],
  );

  const isInitializing = useMemo(() => {
    if (streamError) {
      return false;
    }
    const hasEvents = events.length > 0;
    const hasMessages = runMessages.length > 0;
    const hasActiveGraphState = (graph?.nodes ?? []).some(
      (node) =>
        node.state === "ready" ||
        node.state === "running" ||
        node.state === "completed" ||
        node.state === "failed",
    );
    return !hasEvents && !hasMessages && !hasActiveGraphState;
  }, [events.length, graph, runMessages.length, streamError]);

  const graphLayout = useMemo<
    Record<GraphNodeKey, { x: number; y: number; label: string }>
  >(() => {
    const rand = seededRandom(
      layoutSeedFromRunId(runId || "fallback-graph-seed"),
    );
    const nodeKeys = agents.map((agent) => agent.id);
    const points: Array<{ x: number; y: number }> = [];
    const viewWidth = 120;
    const viewHeight = 100;
    const paddingX = 10;
    const paddingY = 12;
    const minDist = 14;
    const makePoint = (): { x: number; y: number } => ({
      x: paddingX + rand() * (viewWidth - paddingX * 2),
      y: paddingY + rand() * (viewHeight - paddingY * 2),
    });

    nodeKeys.forEach(() => {
      let candidate = makePoint();
      let attempts = 0;
      while (
        attempts < 120 &&
        points.some(
          (p) => Math.hypot(p.x - candidate.x, p.y - candidate.y) < minDist,
        )
      ) {
        candidate = makePoint();
        attempts += 1;
      }
      points.push(candidate);
    });

    return nodeKeys.reduce(
      (acc, nodeKey, index) => {
        acc[nodeKey] = {
          x: points[index].x,
          y: points[index].y,
          label: agents.find((agent) => agent.id === nodeKey)?.name ?? nodeKey,
        };
        return acc;
      },
      {} as Record<GraphNodeKey, { x: number; y: number; label: string }>,
    );
  }, [agents, runId]);

  const toolBadgeForNode = (node: GraphNode | undefined): string | null => {
    if (!node?.tooling) return null;
    if (node.tooling.last_tool_status === "fallback_mode")
      return "fallback_mode";
    if (node.tooling.last_tool_status === "error") return "tool_error";
    if (node.tooling.last_tool_status === "extracting") return "extracting";
    if (node.tooling.last_tool_status === "searching") return "searching";
    return null;
  };

  useEffect(() => {
    const i = setInterval(() => setElapsed((p) => p + 1), 1000);
    return () => clearInterval(i);
  }, []);
  useEffect(() => {
    let isCancelled = false;
    let poll: ReturnType<typeof setInterval> | null = null;
    let channel: { unsubscribe?: () => void } | null = null;
    const syncMissingEvents = async (knownSeq: number): Promise<number> => {
      const latestEvents = await getRunEvents(runId);
      let nextKnownSeq = knownSeq;
      latestEvents
        .filter((event) => event.sequence > knownSeq)
        .sort((a, b) => a.sequence - b.sequence)
        .forEach((event) => {
          nextKnownSeq = Math.max(nextKnownSeq, event.sequence);
          ingestEvent(event);
        });
      const [latestGraph, latestMessages] = await Promise.all([
        getRunGraph(runId),
        getRunMessages(runId),
      ]);
      setGraph(latestGraph);
      setRunMessages(
        latestMessages
          .slice()
          .reverse()
          .slice(0, 8)
          .map((message) => ({
            id: `${message.run_id}:${message.sequence}`,
            from: message.from_agent ?? "system",
            to: message.to_agent ?? "UI",
            text:
              message.message ??
              `${message.message_type}${message.subject ? ` - ${message.subject}` : ""}`,
            level:
              message.message_type === "response"
                ? "success"
                : message.message_type === "system"
                  ? "warn"
                  : "info",
          })),
      );
      return nextKnownSeq;
    };
    const run = async (): Promise<void> => {
      try {
        if (!runId) {
          throw new Error("run_id missing. Please restart the run.");
        }
        setActiveRunId(runId);
        setEvents([]);
        seenEventIdsRef.current.clear();
        seenRunSeqRef.current.clear();

        const [history, snapshot, initialMessages] = await Promise.all([
          getRunEvents(runId),
          getRunGraph(runId),
          getRunMessages(runId),
        ]);
        history.forEach(ingestEvent);
        setGraph(snapshot);
        setRunMessages(
          initialMessages
            .slice()
            .reverse()
            .slice(0, 8)
            .map((message) => ({
              id: `${message.run_id}:${message.sequence}`,
              from: message.from_agent ?? "system",
              to: message.to_agent ?? "UI",
              text:
                message.message ??
                `${message.message_type}${message.subject ? ` - ${message.subject}` : ""}`,
              level:
                message.message_type === "response"
                  ? "success"
                  : message.message_type === "system"
                    ? "warn"
                    : "info",
            })),
        );

        let knownSeq = history.length
          ? Math.max(...history.map((e) => e.sequence))
          : 0;
        const channelName = `run-${runId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        channel = supabase
          ? supabase
              .channel(channelName)
              .on(
                "postgres_changes",
                {
                  event: "INSERT",
                  schema: "public",
                  table: "agent_events",
                  filter: `run_id=eq.${runId}`,
                },
                (payload) => {
                  const event = payload.new as AgentEvent;
                  if (event.sequence > knownSeq) {
                    knownSeq = event.sequence;
                    ingestEvent(event);
                  }
                },
              )
              .on(
                "postgres_changes",
                {
                  event: "INSERT",
                  schema: "public",
                  table: "agent_messages",
                  filter: `run_id=eq.${runId}`,
                },
                () => {
                  void syncMissingEvents(knownSeq);
                },
              )
              .subscribe(async (status) => {
                if (isCancelled) {
                  return;
                }
                if (
                  status === "SUBSCRIBED" ||
                  status === "CHANNEL_ERROR" ||
                  status === "TIMED_OUT"
                ) {
                  knownSeq = await syncMissingEvents(knownSeq);
                }
              })
          : null;

        poll = setInterval(async () => {
          if (isCancelled) return;
          knownSeq = await syncMissingEvents(knownSeq);
          let status;
          try {
            status = await getRun(runId);
          } catch (error) {
            // The run row can appear a moment after start in some environments.
            // Keep polling instead of failing the whole page on transient 404.
            if (
              error instanceof Error &&
              error.message.includes("Could not load run status")
            ) {
              return;
            }
            throw error;
          }
          if (status.status === "completed" && status.plan_id) {
            const plan = await getRunPlan(runId);
            setActiveRunId(null);
            if (!isCancelled) {
              navigate(`/experiments/${plan.plan_id}`, { state: { plan } });
            }
          } else if (status.status === "failed") {
            setActiveRunId(null);
            setStreamError(status.error_message ?? "Run failed");
          }
        }, 1500);
      } catch (error) {
        if (isCancelled) {
          return;
        }
        setStreamError(
          error instanceof Error
            ? error.message
            : "Unbekannter Streaming-Fehler",
        );
      }
    };

    void run();
    return () => {
      isCancelled = true;
      if (poll) {
        clearInterval(poll);
      }
      if (channel && supabase) {
        supabase.removeChannel(channel as never);
      }
    };
  }, [hypothesis, navigate, runId]);

  const fmt = (s: number) =>
    `${Math.floor(s / 3600)
      .toString()
      .padStart(2, "0")}:${Math.floor((s % 3600) / 60)
      .toString()
      .padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;

  return (
    <div className="live-progress" id="live-agent-progress-page">
      <div className="live-progress__container">
        <section
          className="live-progress__banner animate-fadeIn"
          id="hypothesis-banner"
        >
          <div className="live-progress__banner-gradient"></div>
          <div className="live-progress__banner-content">
            <div className="live-progress__banner-icon">
              <span
                className="material-symbols-outlined animate-pulse"
                style={{ fontSize: 26, color: "var(--on-surface-variant)" }}
              >
                model_training
              </span>
              <div className="live-progress__ping"></div>
              <div className="live-progress__ping-static"></div>
            </div>
            <div style={{ flex: 1 }}>
              <h1
                className="font-headline-md"
                style={{
                  color: "var(--on-surface)",
                  marginBottom: 8,
                  fontWeight: 500,
                  letterSpacing: "-0.01em",
                }}
              >
                Generating Experimental Protocol
              </h1>
              <p
                className="font-body-base"
                style={{ color: "var(--on-surface-variant)", maxWidth: 800 }}
              >
                <span
                  className="font-label-caps"
                  style={{ color: "var(--outline)", marginRight: 8 }}
                >
                  HYPOTHESIS
                </span>
                {hypothesis}
              </p>
            </div>
            <div style={{ flexShrink: 0, textAlign: "right" }}>
              <div
                className="font-data-mono"
                style={{
                  color: "var(--on-surface)",
                  marginBottom: 6,
                  fontSize: 13,
                }}
              >
                T+ {fmt(elapsed)}
              </div>
              <div className="live-progress__swarm-badge font-label-caps">
                SWARM ACTIVE
              </div>
            </div>
          </div>
        </section>

        {isInitializing ? (
          <section
            className="live-progress__init-box animate-fadeIn"
            role="status"
            aria-live="polite"
            id="agents-initialize-status"
          >
            <div className="live-progress__init-row">
              <span className="material-symbols-outlined live-progress__init-gear">
                settings
              </span>
              <span className="font-label-caps">Initialize...</span>
            </div>
            <p className="live-progress__init-copy">
              Booting the agent runtime and syncing the first signals.
            </p>
            <div
              className="live-progress__init-progress-track"
              aria-hidden="true"
            >
              <div className="live-progress__init-progress-fill" />
            </div>
          </section>
        ) : null}

        <section className="live-progress__workspace" id="agent-grid">
          <aside className="live-progress__agents-column">
            <div className="live-progress__column-title font-label-caps">
              <span
                className="material-symbols-outlined"
                style={{ fontSize: 14 }}
              >
                dns
              </span>
              Agent Runtime
            </div>
            {agents.map((agent, i) => {
              const node = graph?.nodes.find((item) => item.id === agent.id);
              const toolBadge = toolBadgeForNode(node);
              return (
                <div
                  key={agent.id}
                  className={`agent-card agent-card--${agent.runtimeState} ${!agent.active ? "agent-card--dormant" : ""} animate-fadeIn`}
                  style={{ animationDelay: `${0.1 + i * 0.1}s` }}
                  id={`agent-card-${agent.id}`}
                >
                  <div className="agent-card__progress-track">
                    <div
                      className="agent-card__progress-fill"
                      style={{
                        width: `${Math.round(agent.progress)}%`,
                        background: colorMap[agent.color],
                        transition: "width 0.5s ease",
                      }}
                    />
                  </div>
                  <div className="agent-card__header">
                    <div className="agent-card__header-left">
                      <div
                        className={`agent-card__icon agent-card__icon--${agent.color}`}
                      >
                        <span
                          className="material-symbols-outlined"
                          style={{ fontSize: 16 }}
                        >
                          {agent.icon}
                        </span>
                      </div>
                      <h3 className="agent-card__name">{agent.name}</h3>
                    </div>
                    <span
                      className="font-data-mono"
                      style={{ color: colorMap[agent.color], fontSize: 13 }}
                    >
                      {Math.round(agent.progress)}%
                    </span>
                  </div>
                  {toolBadge ? (
                    <div
                      className="font-label-caps"
                      style={{
                        color: "var(--on-surface-variant)",
                        marginBottom: 6,
                        fontSize: 10,
                      }}
                    >
                      TOOL · {toolBadge}
                    </div>
                  ) : null}
                  <div
                    className={`agent-card__terminal ${!agent.active ? "agent-card__terminal--dormant" : ""}`}
                  >
                    {agent.active ? (
                      agent.logs.map((log, j) => (
                        <div
                          key={j}
                          className={`agent-card__log agent-card__log--${log.type}`}
                        >
                          {log.text}
                        </div>
                      ))
                    ) : (
                      <div className="agent-card__waiting">
                        <span
                          className="material-symbols-outlined"
                          style={{ opacity: 0.5, marginBottom: 8 }}
                        >
                          hourglass_empty
                        </span>
                        <div>Waiting for upstream signals...</div>
                      </div>
                    )}
                  </div>
                  <div className="agent-card__footer">
                    <span
                      className="font-label-caps"
                      style={{ color: "var(--outline)", fontSize: 10 }}
                    >
                      STATUS: {agent.status}
                    </span>
                    <div className="agent-card__bars">
                      {Array.from({ length: 5 }, (_, k) => (
                        <div
                          key={k}
                          className="agent-card__bar"
                          style={{
                            background:
                              k < Math.round((agent.progress / 100) * 5)
                                ? colorMap[agent.color]
                                : "var(--progress-empty-bar)",
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </aside>

          <div className="live-progress__network-column glass-panel animate-fadeIn">
            <div className="live-progress__network-column-header">
              <div className="live-progress__column-title font-label-caps">
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: 14 }}
                >
                  hub
                </span>
                Agents Network
              </div>
              {!streamError && !isInitializing ? (
                <span
                  className="material-symbols-outlined live-progress__network-gear"
                  role="status"
                  aria-label="Activity: agent network running"
                  title="Agent network active"
                >
                  settings
                </span>
              ) : null}
            </div>
            <div className="network-graph">
              <svg
                className="network-graph__canvas"
                viewBox="0 0 120 100"
                preserveAspectRatio="xMidYMid meet"
                aria-hidden="true"
              >
                <g className="network-graph__dust">
                  {Array.from({ length: 26 }, (_, i) => (
                    <circle
                      key={`dust-${i}`}
                      cx={8 + ((i * 37) % 84)}
                      cy={10 + ((i * 29) % 80)}
                      r={(i % 4) * 0.25 + 0.18}
                      className="network-graph__dust-point"
                    />
                  ))}
                </g>
                <defs>
                  <marker
                    id="network-arrow-idle"
                    markerWidth="5"
                    markerHeight="5"
                    refX="4.5"
                    refY="2.5"
                    orient="auto"
                  >
                    <path
                      d="M0,0 L5,2.5 L0,5 z"
                      className="network-graph__arrow network-graph__arrow--idle"
                    />
                  </marker>
                  <marker
                    id="network-arrow-active"
                    markerWidth="5"
                    markerHeight="5"
                    refX="4.5"
                    refY="2.5"
                    orient="auto"
                  >
                    <path
                      d="M0,0 L5,2.5 L0,5 z"
                      className="network-graph__arrow network-graph__arrow--active"
                    />
                  </marker>
                  <marker
                    id="network-arrow-failed"
                    markerWidth="5"
                    markerHeight="5"
                    refX="4.5"
                    refY="2.5"
                    orient="auto"
                  >
                    <path
                      d="M0,0 L5,2.5 L0,5 z"
                      className="network-graph__arrow network-graph__arrow--failed"
                    />
                  </marker>
                </defs>
                {graphEdges.map((edge: GraphEdge) => {
                  const from = graphLayout[edge.from];
                  const to = graphLayout[edge.to];
                  if (!from || !to) return null;
                  const failed = edge.state === "failed";
                  const active =
                    !failed &&
                    (edge.state === "active" || edge.state === "completed");
                  const cx = (from.x + to.x) / 2;
                  const cy = (from.y + to.y) / 2;
                  const offset = from.y < to.y ? 8 : -8;
                  const variant = failed
                    ? "failed"
                    : active
                      ? "active"
                      : "idle";
                  return (
                    <path
                      key={`${edge.from}->${edge.to}`}
                      d={`M ${from.x} ${from.y} Q ${cx} ${cy + offset} ${to.x} ${to.y}`}
                      className={`network-graph__line network-graph__line--${variant}`}
                      markerEnd={`url(#network-arrow-${variant})`}
                    >
                      <title>
                        {`${edge.from} -> ${edge.to}: ${edge.state}`}
                        {edge.last_tool_error
                          ? ` (${edge.last_tool_error})`
                          : ""}
                      </title>
                    </path>
                  );
                })}
                {(Object.keys(graphLayout) as GraphNodeKey[]).map((nodeKey) => {
                  const cfg = graphLayout[nodeKey];
                  const agent = graphNodes[nodeKey];
                  const state = agent?.runtimeState ?? "idle";
                  const progress = Math.round(agent?.progress ?? 0);
                  return (
                    <g
                      key={nodeKey}
                      className={`network-graph__node-group network-graph__node-group--${state}`}
                      transform={`translate(${cfg.x}, ${cfg.y})`}
                    >
                      <title>{`${cfg.label}: ${statusLabels[state]} (${progress}%)`}</title>
                      <circle className="network-graph__node-ring" r="2.6" />
                      <circle className="network-graph__node-core" r="1.85" />
                      <text
                        className="network-graph__node-label"
                        x="3.4"
                        y="-2.8"
                        textAnchor="start"
                      >
                        {cfg.label}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
            <div className="network-messages">
              <h3 className="font-label-caps network-messages__title">
                Inter-Agent Communication
              </h3>
              <div className="network-messages__feed" aria-live="polite">
                {messages.length === 0 ? (
                  <div className="network-messages__item network-messages__item--info">
                    Warte auf erste Nachrichten zwischen den Agents...
                  </div>
                ) : (
                  messages.map((message) => (
                    <div
                      key={message.id}
                      className={`network-messages__item network-messages__item--${message.level}`}
                    >
                      <span className="font-label-caps">
                        {message.from} → {message.to}
                      </span>
                      <p>{message.text}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
            {streamError ? (
              <div className="network-messages__item network-messages__item--warn">
                <span className="font-label-caps">Stream Error</span>
                <p>{streamError}</p>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
