import { documentArtifactReferences } from "./document-references";
import { DatabaseSync } from "node:sqlite";
import { createHash, randomUUID } from "node:crypto";
import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  existsSync,
  realpathSync,
  statSync,
  chmodSync,
} from "node:fs";
import path from "node:path";
import {
  recordInputSchema,
  metricSchema,
  type ResearchRecord,
  type Artifact,
  type Activity,
  type Workspace,
  type Relation,
  type ChartLink,
} from "./schema";
import { z } from "zod";

import {
  dataDir,
  StoreError,
  activeWorkspace,
  workspaceDataDir,
  getResearchRoot,
} from "./workspaces";
export { dataDir, researchRoot, StoreError } from "./workspaces";
const connections = new Map<string, DatabaseSync>();
const transactions = new Set<DatabaseSync>();

export function db() {
  const folder = workspaceDataDir();
  const existing = connections.get(folder);
  if (existing) return existing;
  mkdirSync(path.join(folder, "artifacts"), { recursive: true, mode: 0o700 });
  chmodSync(folder, 0o700);
  const connection = new DatabaseSync(path.join(folder, "parallax.sqlite"));
  chmodSync(path.join(folder, "parallax.sqlite"), 0o600);
  connection.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS revisions (record_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(record_id, revision));
    CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, record_id TEXT, title TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS imports (source TEXT PRIMARY KEY, hash TEXT NOT NULL, record_id TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chart_links (id TEXT PRIMARY KEY, experimentId TEXT NOT NULL REFERENCES records(id), metricName TEXT NOT NULL, recordId TEXT NOT NULL REFERENCES records(id), UNIQUE(experimentId,metricName,recordId));
    CREATE TABLE IF NOT EXISTS relations (id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES records(id), target TEXT NOT NULL REFERENCES records(id), type TEXT NOT NULL, label TEXT NOT NULL, UNIQUE(source, target, type));
  `);
  connections.set(folder, connection);
  return connection;
}

export function transaction<T>(fn: () => T): T {
  const database = db();
  if (transactions.has(database)) return fn();
  database.exec("BEGIN IMMEDIATE");
  transactions.add(database);
  try {
    const result = fn();
    database.exec("COMMIT");
    return result;
  } catch (error) {
    database.exec("ROLLBACK");
    throw error;
  } finally {
    transactions.delete(database);
  }
}

function log(
  action: string,
  recordId: string | null,
  title: string,
  actor: string,
) {
  db()
    .prepare(
      "INSERT INTO activity(action, record_id, title, actor, created_at) VALUES (?, ?, ?, ?, ?)",
    )
    .run(action, recordId, title, actor, new Date().toISOString());
}

export function listRecords(query = "", kind = ""): ResearchRecord[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  return (
    db().prepare("SELECT payload FROM records").all() as { payload: string }[]
  )
    .map((row) => JSON.parse(row.payload) as ResearchRecord)
    .filter(
      (r) =>
        (!kind || r.kind === kind) &&
        terms.every((t) =>
          `${r.title} ${r.content} ${r.tags.join(" ")} ${JSON.stringify(r.provenance)}`
            .toLowerCase()
            .includes(t),
        ),
    )
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function getRecord(id: string): ResearchRecord {
  const row = db()
    .prepare("SELECT payload FROM records WHERE id = ?")
    .get(id) as { payload: string } | undefined;
  if (!row) throw new StoreError("Record not found", 404);
  const record = JSON.parse(row.payload);
  return { ...recordInputSchema.parse(record), ...record };
}

function validateLinks(ids: string[]) {
  for (const id of ids) getRecord(id);
}

function persist(record: ResearchRecord, action: string, actor: string) {
  const previousContent =
    action === "updated" ? getRecord(record.id).content : "";
  const payload = JSON.stringify(record);
  db()
    .prepare(
      "INSERT INTO records(id, payload) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
    )
    .run(record.id, payload);
  db()
    .prepare(
      "INSERT INTO revisions(record_id, revision, payload) VALUES (?, ?, ?)",
    )
    .run(record.id, record.revision, payload);
  log(action, record.id, record.title, actor);
  if (action === "created" || action === "updated") {
    const previous = new Set(
      documentArtifactReferences(previousContent).map(
        (ref) => `${ref.workspaceId}:${ref.id}`,
      ),
    );
    for (const ref of documentArtifactReferences(record.content)) {
      if (previous.has(`${ref.workspaceId}:${ref.id}`)) continue;
      if (ref.workspaceId !== activeWorkspace().id)
        throw new StoreError(
          "Document figures and files must belong to this workspace",
        );
      const { artifact } = getArtifact(ref.id);
      if (!artifact.recordIds.includes(record.id))
        updateArtifactLinks(
          artifact.id,
          [...artifact.recordIds, record.id],
          artifact.revision,
          actor,
        );
    }
  }
  return record;
}

export function createRecord(input: unknown, actor = "Julien") {
  const value = recordInputSchema.parse(input);
  return transaction(() => {
    validateLinks(value.linkedIds);
    const now = new Date().toISOString();
    return persist(
      {
        ...value,
        id: randomUUID(),
        createdAt: now,
        updatedAt: now,
        revision: 1,
        author: actor,
      },
      "created",
      actor,
    );
  });
}

export function updateRecord(
  id: string,
  input: unknown,
  revision: number,
  actor = "Julien",
) {
  return transaction(() => {
    const existing = getRecord(id);
    if (existing.revision !== revision)
      throw new StoreError(
        "This record changed elsewhere. Reopen it before saving.",
        409,
      );
    if (existing.kind === "journal")
      throw new StoreError(
        "Journal entries are immutable. Add a new entry linked to this one.",
        409,
      );
    const value = recordInputSchema.parse(input);
    if (value.kind !== existing.kind)
      throw new StoreError("Record type cannot be changed");
    validateLinks(value.linkedIds);
    return persist(
      {
        ...existing,
        ...value,
        updatedAt: new Date().toISOString(),
        revision: existing.revision + 1,
      },
      "updated",
      actor,
    );
  });
}

export function togglePin(id: string, revision: number) {
  return transaction(() => {
    const record = getRecord(id);
    if (record.revision !== revision)
      throw new StoreError("Record changed. Refresh and try again.", 409);
    return persist(
      {
        ...record,
        pinned: !record.pinned,
        revision: record.revision + 1,
        updatedAt: new Date().toISOString(),
      },
      record.pinned ? "unpinned" : "pinned",
      "Julien",
    );
  });
}

/** Remove a record and its links. Revisions and the activity log are kept. */
export function deleteRecord(id: string, revision: number, actor = "Julien") {
  return transaction(() => {
    const record = getRecord(id);
    if (record.revision !== revision)
      throw new StoreError("Record changed. Refresh and try again.", 409);
    if (record.kind === "journal")
      throw new StoreError("Journal entries are immutable.", 409);
    const others = listRecords().filter((r) => r.linkedIds.includes(id));
    const journal = others.find((r) => r.kind === "journal");
    if (journal)
      throw new StoreError(
        `Referenced by the journal entry "${journal.title}", which is immutable.`,
        409,
      );
    for (const r of others)
      persist(
        {
          ...r,
          linkedIds: r.linkedIds.filter((x) => x !== id),
          revision: r.revision + 1,
          updatedAt: new Date().toISOString(),
        },
        "updated",
        actor,
      );
    for (const a of listArtifacts().filter((a) => a.recordIds.includes(id)))
      updateArtifactLinks(
        a.id,
        a.recordIds.filter((x) => x !== id),
        a.revision,
        actor,
      );
    for (const sql of [
      "DELETE FROM relations WHERE source = ?1 OR target = ?1",
      "DELETE FROM chart_links WHERE experimentId = ?1 OR recordId = ?1",
      "DELETE FROM imports WHERE record_id = ?1",
      "DELETE FROM records WHERE id = ?1",
    ])
      db().prepare(sql).run(id);
    log("deleted", id, record.title, actor);
    return { removed: id };
  });
}

export function appendMetrics(
  id: string,
  input: unknown,
  actor = "Claude Code",
) {
  const metrics = z.array(metricSchema).min(1).max(5000).parse(input);
  return transaction(() => {
    const record = getRecord(id);
    if (record.kind !== "experiment")
      throw new StoreError("Metrics belong to an experiment");
    const keys = new Set(record.metrics.map((m) => `${m.name}:${m.step}`));
    for (const metric of metrics) {
      const key = `${metric.name}:${metric.step}`;
      if (keys.has(key))
        throw new StoreError(
          `Metric ${key} already exists. Use a new step or revise the record explicitly.`,
          409,
        );
      keys.add(key);
    }
    const value = recordInputSchema.parse({
      ...record,
      metrics: [...record.metrics, ...metrics],
    });
    return persist(
      {
        ...record,
        ...value,
        revision: record.revision + 1,
        updatedAt: new Date().toISOString(),
      },
      "logged metrics for",
      actor,
    );
  });
}

export function getRevisions(id: string) {
  getRecord(id);
  return (
    db()
      .prepare(
        "SELECT payload FROM revisions WHERE record_id = ? ORDER BY revision DESC",
      )
      .all(id) as { payload: string }[]
  ).map((r) => JSON.parse(r.payload) as ResearchRecord);
}

export const fileTypes: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".pdf": "application/pdf",
  ".csv": "text/csv",
  ".tsv": "text/tab-separated-values",
  ".json": "application/json",
  ".jsonl": "text/plain",
  ".md": "text/markdown",
  ".txt": "text/plain",
  ".ipynb": "application/x-ipynb+json",
  ".html": "text/html",
  ".toml": "text/plain",
  ".yaml": "text/plain",
};
export const maxFileSize = 25 * 1024 * 1024;
export const sha256 = (value: Buffer | string) =>
  createHash("sha256").update(value).digest("hex");

export function addArtifact(
  buffer: Buffer,
  filename: string,
  options: {
    recordId?: string;
    recordIds?: string[];
    caption?: string;
    sourcePath?: string;
    actor?: string;
  } = {},
): Artifact {
  if (buffer.length > maxFileSize || !buffer.length)
    throw new StoreError("Files must be nonempty and at most 25 MB");
  const name = path
    .basename(filename)
    .replace(/[\x00-\x1f]/g, "")
    .slice(0, 240);
  const mime = fileTypes[path.extname(name).toLowerCase()];
  if (!mime)
    throw new StoreError(
      "Unsupported format. Use an image, PDF, notebook, HTML, Markdown, config or data file.",
    );
  if ((options.caption?.length || 0) > 4000)
    throw new StoreError("Caption is too long");
  const recordIds = z
    .array(z.string().uuid())
    .max(50)
    .parse([
      ...new Set([
        ...(options.recordIds || []),
        ...(options.recordId ? [options.recordId] : []),
      ]),
    ]);
  validateLinks(recordIds);
  db();
  const hash = sha256(buffer);
  const storagePath = path.join(workspaceDataDir(), "artifacts", hash);
  try {
    writeFileSync(storagePath, buffer, { flag: "wx", mode: 0o600 });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  }
  const artifact: Artifact = {
    id: randomUUID(),
    name,
    mime,
    size: buffer.length,
    hash,
    recordId: recordIds[0] || null,
    recordIds,
    revision: 1,
    caption: options.caption || "",
    createdAt: new Date().toISOString(),
    sourcePath: options.sourcePath || "",
  };
  return transaction(() => {
    db()
      .prepare("INSERT INTO artifacts(id, payload) VALUES (?, ?)")
      .run(artifact.id, JSON.stringify(artifact));
    log("attached", artifact.recordId, name, options.actor || "Julien");
    return artifact;
  });
}

export function attachLocalFile(
  filePath: string,
  options: {
    recordId?: string;
    recordIds?: string[];
    caption?: string;
    actor?: string;
  } = {},
) {
  const canonical = realpathSync(filePath);
  const roots = [getResearchRoot(), process.cwd()]
    .filter((p) => p && existsSync(/* turbopackIgnore: true */ p))
    .map((p) => realpathSync(p));
  if (!roots.some((root) => canonical.startsWith(root + path.sep)))
    throw new StoreError(
      "File must be inside the research repository or Parallax workspace",
    );
  if (
    existsSync(dataDir) &&
    (canonical === realpathSync(dataDir) ||
      canonical.startsWith(realpathSync(dataDir) + path.sep))
  )
    throw new StoreError("Application storage cannot be imported");
  if (
    canonical
      .split(path.sep)
      .some(
        (p) =>
          p.startsWith(".") ||
          (["node_modules", "data"].includes(p) &&
            canonical.startsWith(realpathSync(process.cwd()) + path.sep)),
      )
  ) {
    throw new StoreError(
      "Hidden files and application storage cannot be imported",
    );
  }
  const stat = statSync(canonical);
  if (!stat.isFile() || stat.size > maxFileSize)
    throw new StoreError("File must be a regular file under 25 MB");
  return addArtifact(readFileSync(canonical), path.basename(canonical), {
    ...options,
    sourcePath: canonical,
  });
}

export function listArtifacts(): Artifact[] {
  return (
    db().prepare("SELECT payload FROM artifacts").all() as { payload: string }[]
  )
    .map((r) => {
      const a = JSON.parse(r.payload);
      return {
        ...a,
        recordIds: a.recordIds ?? (a.recordId ? [a.recordId] : []),
        revision: a.revision ?? 1,
      } as Artifact;
    })
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}
export function getArtifact(id: string) {
  const artifact = listArtifacts().find((a) => a.id === id);
  if (!artifact) throw new StoreError("Artifact not found", 404);
  return {
    artifact,
    buffer: readFileSync(
      path.join(workspaceDataDir(), "artifacts", artifact.hash),
    ),
  };
}

const settingsSchema = z.object({
  pilotBudget: z.number().positive().max(1000000),
  fellowshipBudget: z.number().positive().max(1000000),
  phase: z.enum(["pilot", "fellowship"]),
  project: z.string().trim().min(1).max(120),
});
export function getSettings(): Workspace["settings"] {
  const row = db()
    .prepare("SELECT value FROM settings WHERE key = 'workspace'")
    .get() as { value: string } | undefined;
  return row
    ? JSON.parse(row.value)
    : {
        pilotBudget: 500,
        fellowshipBudget: 15000,
        phase: "pilot",
        project:
          activeWorkspace().id === "default"
            ? "Eval gaming under pressure"
            : activeWorkspace().name,
      };
}
export function saveSettings(input: unknown) {
  const value = settingsSchema.parse(input);
  db()
    .prepare(
      "INSERT INTO settings(key,value) VALUES ('workspace',?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    )
    .run(JSON.stringify(value));
  return value;
}

export function getWorkspace(): Workspace {
  return {
    info: activeWorkspace(),
    chartLinks: listChartLinks(),
    records: listRecords(),
    artifacts: listArtifacts(),
    relations: listRelations(),
    activity: db()
      .prepare(
        "SELECT id, action, record_id AS recordId, title, actor, created_at AS createdAt FROM activity ORDER BY id DESC LIMIT 60",
      )
      .all() as Activity[],
    settings: getSettings(),
    researchRoot: getResearchRoot(),
    dataDir: workspaceDataDir(),
    storageRoot: dataDir,
    mcpPath: path.join(process.cwd(), "mcp/server.ts"),
  };
}

export const relationSchema = z.object({
  source: z.string().uuid(),
  target: z.string().uuid(),
  type: z.enum(["supports", "contradicts", "extends", "uses", "relates"]),
  label: z.string().max(300).default(""),
});
export function linkRecords(input: unknown, actor = "Julien") {
  const value = relationSchema.parse(input);
  if (value.source === value.target)
    throw new StoreError("Choose two different records");
  return transaction(() => {
    const source = getRecord(value.source);
    getRecord(value.target);
    const existing = db()
      .prepare(
        "SELECT * FROM relations WHERE source = ? AND target = ? AND type = ?",
      )
      .get(value.source, value.target, value.type) as Relation | undefined;
    if (existing) return { ...existing };
    const relation: Relation = { id: randomUUID(), ...value };
    db()
      .prepare(
        "INSERT INTO relations(id,source,target,type,label) VALUES (?,?,?,?,?)",
      )
      .run(
        relation.id,
        relation.source,
        relation.target,
        relation.type,
        relation.label,
      );
    log("linked", value.source, source.title, actor);
    return relation;
  });
}
export function listRelations(): Relation[] {
  return db().prepare("SELECT * FROM relations").all() as Relation[];
}

export function updateTask(
  id: string,
  patch: unknown,
  revision: number,
  actor = "Julien",
) {
  const update = recordInputSchema
    .pick({ status: true, priority: true, assignee: true, dueDate: true })
    .partial()
    .parse(patch);
  const record = getRecord(id);
  if (record.kind !== "task") throw new StoreError("Not a task");
  return updateRecord(id, { ...record, ...update }, revision, actor);
}

export function exportWorkspace() {
  return {
    format: "parallax.v2",
    exportedAt: new Date().toISOString(),
    ...getWorkspace(),
    revisions: (
      db()
        .prepare("SELECT payload FROM revisions ORDER BY record_id, revision")
        .all() as { payload: string }[]
    ).map((r) => JSON.parse(r.payload)),
    activity: db().prepare("SELECT * FROM activity ORDER BY id").all(),
    artifacts: listArtifacts().map((a) => ({
      ...a,
      base64: getArtifact(a.id).buffer.toString("base64"),
    })),
  };
}

export function closeDatabases() {
  for (const connection of connections.values()) connection.close();
  connections.clear();
}

/** Change metadata without changing the preserved file or journal contents. */
export function updateArtifactLinks(
  id: string,
  recordIds: string[],
  revision: number,
  actor = "Julien",
) {
  const ids = [...new Set(z.array(z.string().uuid()).max(50).parse(recordIds))];
  return transaction(() => {
    const { artifact } = getArtifact(id);
    if (artifact.revision !== revision)
      throw new StoreError(
        "This file was updated elsewhere. Refresh and try again.",
        409,
      );
    validateLinks(ids);
    const updated = {
      ...artifact,
      recordIds: ids,
      recordId: ids[0] || null,
      revision: artifact.revision + 1,
    };
    db()
      .prepare("UPDATE artifacts SET payload = ? WHERE id = ?")
      .run(JSON.stringify(updated), id);
    log("updated file links for", updated.recordId, artifact.name, actor);
    return updated;
  });
}

export const chartLinkSchema = z.object({
  experimentId: z.string().uuid(),
  metricName: z.string().trim().min(1).max(100),
  recordId: z.string().uuid(),
});
export function linkChart(input: unknown, actor = "Julien"): ChartLink {
  const value = chartLinkSchema.parse(input);
  return transaction(() => {
    const source = getRecord(value.experimentId);
    const target = getRecord(value.recordId);
    if (source.id === target.id)
      throw new StoreError(
        "This chart is already part of its source experiment",
      );
    if (
      source.kind !== "experiment" ||
      !source.metrics.some((m) => m.name === value.metricName)
    )
      throw new StoreError("Choose a measured metric from an experiment");
    const existing = db()
      .prepare(
        "SELECT * FROM chart_links WHERE experimentId = ? AND metricName = ? AND recordId = ?",
      )
      .get(value.experimentId, value.metricName, value.recordId) as
      ChartLink | undefined;
    if (existing) return { ...existing };
    const link = { id: randomUUID(), ...value };
    db()
      .prepare(
        "INSERT INTO chart_links(id,experimentId,metricName,recordId) VALUES (?,?,?,?)",
      )
      .run(link.id, link.experimentId, link.metricName, link.recordId);
    log("linked chart to", target.id, target.title, actor);
    return link;
  });
}
export function unlinkChart(id: string, actor = "Julien") {
  return transaction(() => {
    const link = listChartLinks().find((link) => link.id === id);
    if (!link) throw new StoreError("Chart link not found", 404);
    db().prepare("DELETE FROM chart_links WHERE id = ?").run(id);
    log(
      "unlinked chart from",
      link.recordId,
      getRecord(link.recordId).title,
      actor,
    );
    return { removed: id };
  });
}
export function listChartLinks(): ChartLink[] {
  return db()
    .prepare("SELECT * FROM chart_links")
    .all()
    .map((row) => ({ ...row })) as ChartLink[];
}
