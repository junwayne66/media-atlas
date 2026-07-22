import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TrendDetail from "../components/TrendDetail.vue";

const cluster = {
  id: "c1",
  version: 3,
  title: "AI 芯片热点",
  canonical_topic: "ai-chip",
  keywords: [],
  entities: [],
  member_item_ids: ["dy-1", "tt-1"],
  snapshot_ids: ["s1"],
  first_seen_at: "2026-07-22T00:00:00Z",
  last_seen_at: "2026-07-22T00:00:00Z",
  stage: "RISING",
  sub_scores: {
    velocity: 0.8,
    acceleration: 0.6,
    engagement_efficiency: 0.4,
    cross_platform_score: 1.0,
    topic_fit: 0.0,
    novelty: 0.0,
    source_quality: 0.0,
    saturation: 0.2,
    decay: 0.0,
  },
  hot_score: 0.72,
  weights_version: "v1",
  reason_codes: ["HIGH_ACCELERATION", "CROSS_PLATFORM"],
  vertical: "ai-tech",
  source_confidence: 0.85,
};

function jsonResp(body: unknown) {
  return { ok: true, json: () => Promise.resolve(body) };
}

describe("TrendDetail", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(jsonResp(cluster));
    vi.stubGlobal("fetch", fetchMock);
  });

  it("展示子分数、理由码与成员证据", async () => {
    const wrapper = mount(TrendDetail, { props: { clusterId: "c1" } });
    await flushPromises();
    expect(wrapper.text()).toContain("速度");
    expect(wrapper.text()).toContain("80"); // velocity 0.8 → 80
    expect(wrapper.text()).toContain("CROSS_PLATFORM");
    expect(wrapper.text()).toContain("dy-1");
  });

  it("重算遇 409 冲突时提示人工而非静默吞掉", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResp(cluster)) // 初始 get
      .mockResolvedValueOnce({ ok: false, status: 409, text: () => Promise.resolve("版本冲突") })
      .mockResolvedValueOnce(jsonResp({ ...cluster, version: 5 })); // 冲突后 reload
    const wrapper = mount(TrendDetail, { props: { clusterId: "c1" } });
    await flushPromises();
    await wrapper.find('[data-test="rescore"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-test="action-error"]').text()).toContain("已被他人修改");
  });

  it("一键创建 Project 调用 projects 端点并发出事件", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResp(cluster)) // 初始 get
      .mockResolvedValueOnce(jsonResp({ id: "proj-123", title: "x", trend_cluster_id: "c1", creation_mode: "STRUCTURE_REWRITE" }));
    const wrapper = mount(TrendDetail, { props: { clusterId: "c1" } });
    await flushPromises();
    await wrapper.find('[data-test="create-project"]').trigger("click");
    await flushPromises();
    const [url, opts] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toContain("/c1/projects");
    expect(opts.method).toBe("POST");
    expect(wrapper.emitted("projectCreated")?.[0]).toEqual(["proj-123"]);
    expect(wrapper.text()).toContain("已创建 Project");
  });

  it("重算热度用当前 version（乐观锁）", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResp(cluster))
      .mockResolvedValueOnce(jsonResp({ ...cluster, version: 4, hot_score: 0.9 }));
    const wrapper = mount(TrendDetail, { props: { clusterId: "c1" } });
    await flushPromises();
    await wrapper.find('[data-test="rescore"]').trigger("click");
    await flushPromises();
    const [url, opts] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toContain("/c1/rescore");
    expect(JSON.parse(opts.body as string)).toEqual({ expected_version: 3 });
    expect(wrapper.emitted("changed")).toBeTruthy();
  });
});
