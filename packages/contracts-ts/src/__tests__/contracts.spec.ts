import { readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Project, TaskEnvelope } from "../index";

const here = path.dirname(fileURLToPath(import.meta.url));
const schemasDir = path.resolve(here, "../../../../schemas");
const generatedDir = path.resolve(here, "../generated");

describe("contracts-ts", () => {
  it("生成物与 schemas/ 一一对应", () => {
    const schemaStems = readdirSync(schemasDir)
      .filter((f) => f.endsWith(".schema.json"))
      .map((f) => f.replace(/\.schema\.json$/, ""))
      .sort();
    const generatedStems = readdirSync(generatedDir)
      .filter((f) => f.endsWith(".ts"))
      .map((f) => f.replace(/\.ts$/, ""))
      .sort();
    expect(schemaStems.length).toBeGreaterThan(0);
    expect(generatedStems).toEqual(schemaStems);
  });

  it("顶层合同类型可按 schema 字段构造（编译期约束）", () => {
    const project: Project = {
      schema_version: "1",
      id: "01J2ZK3AC9V6XW8YQ4R5T6U7V8",
      title: "AI 芯片新品热点二创",
      vertical: "ai-tech",
      source_language: "zh-CN",
      target_languages: ["en-US"],
      creation_mode: "STRUCTURE_REWRITE",
      status: "DRAFT",
      execution_policy: "LOCAL_PREFERRED",
      created_at: "2026-07-21T08:00:00Z",
      updated_at: "2026-07-21T08:00:00Z",
    };
    const envelope: TaskEnvelope = {
      schema_version: "1",
      task_id: "01J2ZK3AC9V6XW8YQ4R5T6U7W2",
      idempotency_key: "probe-01J2ZK3AC9-1",
      capability: "media.probe",
      attempt: 1,
      execution_policy: "LOCAL_PREFERRED",
      created_at: "2026-07-21T08:00:00Z",
    };
    expect(project.creation_mode).toBe("STRUCTURE_REWRITE");
    expect(envelope.attempt).toBe(1);
  });
});
