import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

test("real MCP stdio client: tools, records, metrics, tasks, graph, attachments and handoff", async () => {
  const temp = mkdtempSync(path.join(os.tmpdir(), "parallax-mcp-test-"));
  const repo = path.join(temp, "research");
  mkdirSync(repo);
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["--import", "tsx", "mcp/server.ts"],
    cwd: process.cwd(),
    env: {
      ...(process.env as Record<string, string>),
      PARALLAX_DATA_DIR: path.join(temp, "data"),
      PARALLAX_RESEARCH_ROOT: repo,
    },
    stderr: "pipe",
  });
  const client = new Client({
    name: "parallax-verification",
    version: "1.0.0",
  });
  const call = async (name: string, args: Record<string, unknown> = {}) => {
    const result = await client.callTool({ name, arguments: args });
    assert.notEqual(result.isError, true, JSON.stringify(result));
    return JSON.parse(
      (result.content as { type: string; text: string }[])[0].text,
    );
  };
  try {
    await client.connect(transport);
    const tools = await client.listTools();
    assert.equal(tools.tools.length, 18);
    const experiment = await call("create_record", {
      kind: "experiment",
      title: "Fixture only: MCP baseline",
      provenance: { seed: 123, commit: "test-only" },
    });
    const metrics = await call("log_metrics", {
      experimentId: experiment.id,
      metrics: [{ name: "fixture_only", step: 0, value: 0.25, n: 4 }],
    });
    assert.equal(metrics.metrics[0].n, 4);
    const finding = await call("create_record", {
      kind: "finding",
      title: "Fixture only: observation",
      linkedIds: [experiment.id],
    });
    await call("link_records", {
      source: experiment.id,
      target: finding.id,
      type: "supports",
    });
    const graph = await call("get_knowledge_graph");
    assert.ok(
      graph.edges.some((e: { target: string }) => e.target === finding.id),
    );
    const task = await call("create_record", {
      kind: "task",
      title: "Fixture only: task",
      status: "planned",
    });
    const moved = await call("update_task", {
      id: task.id,
      revision: task.revision,
      status: "running",
    });
    assert.equal(moved.status, "running");
    const file = path.join(repo, "fixture.csv");
    writeFileSync(file, "x,y\n1,2\n");
    const artifact = await call("attach_file", {
      path: file,
      recordId: experiment.id,
    });
    assert.equal(artifact.name, "fixture.csv");
    const linkedFile = await call("link_artifact", {
      artifactId: artifact.id,
      recordIds: [experiment.id, finding.id],
      revision: artifact.revision,
    });
    assert.equal(linkedFile.recordIds.length, 2);
    assert.equal(
      (await call("get_record", { id: finding.id })).artifacts.length,
      1,
    );
    const chart = await call("link_chart", {
      experimentId: experiment.id,
      metricName: "fixture_only",
      recordId: finding.id,
    });
    assert.equal(
      (await call("get_record", { id: finding.id })).chartLinks.length,
      1,
    );
    await call("unlink_chart", { id: chart.id });
    const second = await call("create_workspace", {
      name: "Fixture second project",
    });
    assert.equal((await call("list_workspaces")).length, 2);
    assert.equal(
      (await call("search_research", { workspaceId: second.id })).length,
      0,
    );
    const privateNote = await call("create_record", {
      workspaceId: second.id,
      kind: "note",
      title: "Fixture: isolated",
    });
    assert.equal(
      (await call("workspace_summary", { workspaceId: second.id })).records,
      1,
    );
    assert.equal(
      (await call("search_research", { query: "isolated" })).length,
      0,
    );
    const foreign = await client.callTool({
      name: "get_record",
      arguments: { workspaceId: second.id, id: experiment.id },
    });
    assert.equal(foreign.isError, true);
    assert.equal(
      (await call("get_record", { workspaceId: second.id, id: privateNote.id }))
        .record.id,
      privateNote.id,
    );
    const record = await call("get_record", { id: experiment.id });
    assert.equal(record.artifacts.length, 1);
    assert.equal(record.revisions.length, 2);
    const found = await call("search_research", { query: "MCP baseline" });
    assert.equal(found.length, 1);
    const handoff = await call("session_handoff");
    assert.ok(
      handoff.activeTasks.some((r: { id: string }) => r.id === task.id),
    );
    const invalid = await client.callTool({
      name: "update_task",
      arguments: { id: task.id, revision: 1, status: "completed" },
    });
    assert.equal(invalid.isError, true);
    const resource = await client.readResource({
      uri: "parallax://research-contract",
    });
    const contract = resource.contents[0];
    assert.ok("text" in contract);
    assert.match(contract.text, /Never fabricate/);
  } finally {
    await client.close();
    rmSync(temp, { recursive: true, force: true });
  }
});
