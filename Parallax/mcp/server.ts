import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { hasSupportingExperiment } from "../lib/research.js";

// Resolve app paths even when Claude launches from the Python repository.
const home = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
process.chdir(home);
const store = await import("../lib/store.js");
const spaces = await import("../lib/workspaces.js");
const { recordInputSchema, metricSchema, kinds } =
  await import("../lib/schema.js");
const { initializeWorkspace, importRepository } =
  await import("../lib/importer.js");
initializeWorkspace();
const server = new McpServer({ name: "parallax", version: "0.2.0" });
const workspaceId = z
  .string()
  .optional()
  .describe(
    "Workspace ID from list_workspaces. Omit to use PARALLAX_WORKSPACE_ID or the original default workspace. Browser switching does not change the agent's default.",
  );
function result(fn: () => unknown, id?: string) {
  try {
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(spaces.runInWorkspace(id, fn), null, 2),
        },
      ],
    };
  } catch (error) {
    return {
      isError: true,
      content: [
        {
          type: "text" as const,
          text: error instanceof Error ? error.message : "Operation failed",
        },
      ],
    };
  }
}
server.registerTool(
  "list_workspaces",
  {
    description:
      "List private workspaces and their IDs. Pass workspaceId on subsequent calls to choose the correct project.",
    inputSchema: {},
  },
  () => result(spaces.listWorkspaces),
);
server.registerTool(
  "create_workspace",
  {
    description:
      "Create an empty private workspace with separate records, files, graph, imports and budget. Optional researchRoot must be an existing absolute folder. Does not import or execute code.",
    inputSchema: spaces.workspaceInputSchema.shape,
  },
  (input) => result(() => spaces.createWorkspace(input)),
);
server.registerTool(
  "search_research",
  {
    description:
      "Search private research by title, tags, full text and provenance. Omit query to list all. Imported claims are not verified.",
    inputSchema: {
      workspaceId,
      query: z.string().default(""),
      kind: z.enum(kinds).optional(),
    },
  },
  ({ workspaceId, query, kind }) =>
    result(() => store.listRecords(query, kind), workspaceId),
);
server.registerTool(
  "get_record",
  {
    description:
      "Read a record, linked files, metric chart links and revision history.",
    inputSchema: { workspaceId, id: z.string().uuid() },
  },
  ({ workspaceId, id }) =>
    result(
      () => ({
        record: store.getRecord(id),
        revisions: store.getRevisions(id),
        artifacts: store
          .listArtifacts()
          .filter((a) => a.recordIds.includes(id)),
        chartLinks: store
          .listChartLinks()
          .filter((l) => l.recordId === id || l.experimentId === id),
      }),
      workspaceId,
    ),
);
server.registerTool(
  "create_record",
  {
    description:
      "Save a note, immutable journal, finding, experiment or reference. Use Markdown and link supporting IDs. Never invent results or provenance; mark evidence honestly. Keep sensitive work private. Paid compute needs a separate estimate and explicit human approval. This tool cannot launch jobs.",
    inputSchema: { ...recordInputSchema.shape, workspaceId },
  },
  ({ workspaceId, ...input }) =>
    result(() => store.createRecord(input, "Claude Code"), workspaceId),
);
server.registerTool(
  "update_record",
  {
    description:
      "Replace a record with revision history. Read first and supply its revision to prevent stale edits. Journals are immutable; add a linked correction.",
    inputSchema: {
      workspaceId,
      id: z.string().uuid(),
      revision: z.number().int().positive(),
      record: recordInputSchema,
    },
  },
  ({ workspaceId, id, revision, record }) =>
    result(
      () => store.updateRecord(id, record, revision, "Claude Code"),
      workspaceId,
    ),
);
server.registerTool(
  "log_metrics",
  {
    description:
      "Append measured metrics to an experiment. Include real sample sizes and bounds when available. Duplicate name+step pairs are rejected. Never log illustrative values as measured results.",
    inputSchema: {
      workspaceId,
      experimentId: z.string().uuid(),
      metrics: z.array(metricSchema).min(1).max(5000),
    },
  },
  ({ workspaceId, experimentId, metrics }) =>
    result(() => store.appendMetrics(experimentId, metrics), workspaceId),
);
server.registerTool(
  "attach_file",
  {
    description:
      "Copy a figure, notebook, CSV, HTML, PDF or Markdown file into private content-addressed storage (max 25 MB). File must be in this workspace's research repository or the Parallax app folder. Link it to several entries with recordIds; recordId remains supported. Never upload secrets or model weights.",
    inputSchema: {
      workspaceId,
      path: z.string(),
      recordId: z.string().uuid().optional(),
      recordIds: z.array(z.string().uuid()).max(50).optional(),
      caption: z.string().max(4000).optional(),
    },
  },
  ({ workspaceId, path: filePath, ...options }) =>
    result(
      () =>
        store.attachLocalFile(filePath, { ...options, actor: "Claude Code" }),
      workspaceId,
    ),
);
server.registerTool(
  "link_artifact",
  {
    description:
      "Set the entries linked to an existing file without copying its bytes. Include all desired recordIds; an empty list detaches it. Supply its current revision from list_artifacts or get_record to protect concurrent edits. Journal content is unchanged.",
    inputSchema: {
      workspaceId,
      artifactId: z.string().uuid(),
      recordIds: z.array(z.string().uuid()).max(50),
      revision: z.number().int().positive(),
    },
  },
  ({ workspaceId, artifactId, recordIds, revision }) =>
    result(
      () =>
        store.updateArtifactLinks(
          artifactId,
          recordIds,
          revision,
          "Claude Code",
        ),
      workspaceId,
    ),
);
server.registerTool(
  "list_artifacts",
  {
    description:
      "List saved figures, notebooks and files with their linked recordIds and revisions.",
    inputSchema: { workspaceId },
  },
  ({ workspaceId }) => result(store.listArtifacts, workspaceId),
);
server.registerTool(
  "link_chart",
  {
    description:
      "Embed a particular measured metric chart from an experiment into a note, journal, finding or other entry. It stays connected to the source metrics and provenance; this link alone does not establish scientific support. Idempotent.",
    inputSchema: { ...store.chartLinkSchema.shape, workspaceId },
  },
  ({ workspaceId, ...input }) =>
    result(() => store.linkChart(input, "Claude Code"), workspaceId),
);
server.registerTool(
  "unlink_chart",
  {
    description:
      "Remove a chart's link to an entry, preserving the source metrics and journal text.",
    inputSchema: { workspaceId, id: z.string().uuid() },
  },
  ({ workspaceId, id }) =>
    result(() => store.unlinkChart(id, "Claude Code"), workspaceId),
);
server.registerTool(
  "import_repository",
  {
    description:
      "Snapshot README and docs from this workspace's configured repository. Skip unchanged files; create new linked snapshots for changed files. Does not execute code.",
    inputSchema: { workspaceId },
  },
  ({ workspaceId }) => result(importRepository, workspaceId),
);
server.registerTool(
  "workspace_summary",
  {
    description:
      "Get workspace identity, counts, budget settings and recent activity. Recorded costs are not billing-provider totals.",
    inputSchema: { workspaceId },
  },
  ({ workspaceId }) =>
    result(() => {
      const w = store.getWorkspace();
      return {
        workspace: w.info,
        settings: w.settings,
        records: w.records.length,
        artifacts: w.artifacts.length,
        chartLinks: w.chartLinks,
        recordedCostUsd: w.records
          .filter((r) => r.kind === "experiment")
          .reduce((n, r) => n + (r.costUsd || 0), 0),
        activity: w.activity.slice(0, 12),
        researchRoot: w.researchRoot,
      };
    }, workspaceId),
);
server.registerTool(
  "update_task",
  {
    description:
      "Move a Kanban task or set priority, assignee and due date. Supply current revision. Never mark work complete unless actually done.",
    inputSchema: {
      workspaceId,
      id: z.string().uuid(),
      revision: z.number().int().positive(),
      status: z
        .enum(["draft", "planned", "running", "blocked", "completed"])
        .optional(),
      priority: z.enum(["low", "medium", "high", "urgent"]).optional(),
      assignee: z.string().optional(),
      dueDate: z.string().optional(),
    },
  },
  ({ workspaceId, id, revision, ...patch }) =>
    result(
      () => store.updateTask(id, patch, revision, "Claude Code"),
      workspaceId,
    ),
);
server.registerTool(
  "link_records",
  {
    description:
      "Add a directed graph edge. Use supports or contradicts only when the source provides evidence for or against the target. Other types: extends, uses, relates.",
    inputSchema: { ...store.relationSchema.shape, workspaceId },
  },
  ({ workspaceId, ...input }) =>
    result(() => store.linkRecords(input, "Claude Code"), workspaceId),
);
server.registerTool(
  "get_knowledge_graph",
  {
    description:
      "Get persistent nodes and typed edges, plus chart and shared-file connections. Record linkedIds are reference edges.",
    inputSchema: { workspaceId },
  },
  ({ workspaceId }) =>
    result(
      () => ({
        nodes: store
          .listRecords()
          .map(({ id, title, kind, tags, evidence, linkedIds }) => ({
            id,
            title,
            kind,
            tags,
            evidence,
            linkedIds,
          })),
        edges: store.listRelations(),
        chartLinks: store.listChartLinks(),
        artifacts: store
          .listArtifacts()
          .map(({ id, name, recordIds }) => ({ id, name, recordIds })),
      }),
      workspaceId,
    ),
);
server.registerTool(
  "session_handoff",
  {
    description:
      "Get active work, blockers, recent journals, unverified findings and draft manuscripts for the next session.",
    inputSchema: { workspaceId },
  },
  ({ workspaceId }) =>
    result(() => {
      const r = store.listRecords(),
        relations = store.listRelations();
      return {
        workspace: spaces.activeWorkspace(),
        activeTasks: r.filter(
          (r) => r.kind === "task" && r.status !== "completed",
        ),
        recentJournals: r.filter((r) => r.kind === "journal").slice(0, 3),
        reviewQueue: r.filter(
          (f) =>
            f.kind === "finding" &&
            (f.evidence === "unverified" ||
              !hasSupportingExperiment(f, r, relations)),
        ),
        papers: r.filter((r) => r.kind === "paper"),
        recentActivity: store.getWorkspace().activity.slice(0, 10),
      };
    }, workspaceId),
);
server.registerResource(
  "research-contract",
  "parallax://research-contract",
  {
    mimeType: "text/plain",
    description: "Research recording rules and privacy expectations.",
  },
  async (uri) => ({
    contents: [
      {
        uri: uri.href,
        text: "All data is private and local. Never fabricate results, numbers or citations. Preserve seeds, code commit, dataset revision/hash, configs, exact commands, sample sizes and uncertainty. Paid compute requires a separate cost estimate and explicit human approval. Journals are immutable; add linked corrections. Findings need linked evidence. Imported claims are unverified. This server cannot rent or launch compute. Use list_workspaces and explicitly pass workspaceId for the intended project. Browser workspace switching never changes an agent's default.",
      },
    ],
  }),
);
await server.connect(new StdioServerTransport());
