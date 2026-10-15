import { z } from "zod";

export const kinds = [
  "note",
  "journal",
  "finding",
  "experiment",
  "reference",
  "task",
  "paper",
] as const;
export const statuses = [
  "draft",
  "planned",
  "running",
  "completed",
  "inconclusive",
  "blocked",
] as const;
export const metricSchema = z
  .object({
    name: z.string().trim().min(1).max(100),
    step: z.number().finite().nonnegative(),
    value: z.number().finite(),
    unit: z.string().max(30).default(""),
    n: z.number().int().positive().optional(),
    lower: z.number().finite().optional(),
    upper: z.number().finite().optional(),
  })
  .refine(
    (m) => m.lower === undefined || m.upper === undefined || m.lower <= m.upper,
    "Lower bound must not exceed upper bound",
  );
export const provenanceSchema = z.object({
  repository: z.string().max(2000).default(""),
  commit: z.string().max(100).default(""),
  seed: z.number().int().nullable().default(null),
  model: z.string().max(300).default(""),
  dataset: z.string().max(2000).default(""),
  config: z.string().max(30000).default(""),
  command: z.string().max(4000).default(""),
  sourcePath: z.string().max(2000).default(""),
  sourceHash: z.string().max(64).default(""),
});
export const recordInputSchema = z.object({
  kind: z.enum(kinds),
  title: z.string().trim().min(1).max(200),
  content: z.string().max(300000).default(""),
  status: z.enum(statuses).default("draft"),
  tags: z.array(z.string().trim().min(1).max(50)).max(20).default([]),
  pinned: z.boolean().default(false),
  sensitive: z.boolean().default(true),
  evidence: z
    .enum(["unverified", "observed", "replicated"])
    .default("unverified"),
  linkedIds: z.array(z.string().uuid()).max(50).default([]),
  provenance: provenanceSchema.default(() => provenanceSchema.parse({})),
  metrics: z
    .array(metricSchema)
    .max(20000)
    .refine(
      (items) =>
        new Set(items.map((m) => `${m.name}:${m.step}`)).size === items.length,
      "Metric names and steps must be unique",
    )
    .default([]),
  costUsd: z.number().finite().nonnegative().nullable().default(null),
  estimateUsd: z.number().finite().nonnegative().nullable().default(null),
  gpuHours: z.number().finite().nonnegative().nullable().default(null),
  decision: z.enum(["pending", "go", "no-go", "revise"]).default("pending"),
  gate: z.string().max(4000).default(""),
  priority: z.enum(["low", "medium", "high", "urgent"]).default("medium"),
  dueDate: z
    .string()
    .refine((v) => !v || /^\d{4}-\d{2}-\d{2}$/.test(v), "Use YYYY-MM-DD")
    .default(""),
  assignee: z.string().max(100).default("Julien"),
});
export type RecordInput = z.infer<typeof recordInputSchema>;
export type ResearchRecord = RecordInput & {
  id: string;
  createdAt: string;
  updatedAt: string;
  revision: number;
  author: string;
};
export type Artifact = {
  id: string;
  name: string;
  mime: string;
  size: number;
  hash: string;
  recordId: string | null;
  recordIds: string[];
  revision: number;
  caption: string;
  createdAt: string;
  sourcePath: string;
};
export type Activity = {
  id: number;
  action: string;
  recordId: string | null;
  title: string;
  actor: string;
  createdAt: string;
};
export type Relation = {
  id: string;
  source: string;
  target: string;
  type: "supports" | "contradicts" | "extends" | "uses" | "relates";
  label: string;
};
export type WorkspaceInfo = {
  id: string;
  name: string;
  description: string;
  researchRoot: string;
  createdAt: string;
};
export type ChartLink = {
  id: string;
  experimentId: string;
  metricName: string;
  recordId: string;
};
export type Workspace = {
  info: WorkspaceInfo;
  chartLinks: ChartLink[];
  records: ResearchRecord[];
  artifacts: Artifact[];
  activity: Activity[];
  relations: Relation[];
  settings: {
    pilotBudget: number;
    fellowshipBudget: number;
    phase: "pilot" | "fellowship";
    project: string;
  };
  researchRoot: string;
  dataDir: string;
  storageRoot: string;
  mcpPath: string;
};
