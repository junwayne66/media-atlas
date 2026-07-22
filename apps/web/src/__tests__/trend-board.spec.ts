import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TrendBoard from "../components/TrendBoard.vue";

function cluster(over: Record<string, unknown> = {}) {
  return {
    id: "c1",
    version: 1,
    title: "AI 芯片热点",
    canonical_topic: "ai-chip",
    keywords: [],
    entities: [],
    member_item_ids: ["dy-1", "tt-1"],
    snapshot_ids: [],
    first_seen_at: "2026-07-22T00:00:00Z",
    last_seen_at: "2026-07-22T00:00:00Z",
    stage: "RISING",
    sub_scores: null,
    hot_score: 0.72,
    weights_version: "v1",
    reason_codes: ["HIGH_ACCELERATION", "CROSS_PLATFORM"],
    vertical: "ai-tech",
    source_confidence: 0.85,
    ...over,
  };
}

describe("TrendBoard", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([cluster()]) }),
    );
  });

  it("列出聚类并展示热度与理由码", async () => {
    const wrapper = mount(TrendBoard);
    await flushPromises();
    const rows = wrapper.findAll('[data-test="cluster-row"]');
    expect(rows).toHaveLength(1);
    expect(wrapper.text()).toContain("72"); // hot_score → 百分数
    expect(wrapper.text()).toContain("HIGH_ACCELERATION");
    expect(wrapper.text()).toContain("RISING");
  });

  it("点击行发出 select 事件", async () => {
    const wrapper = mount(TrendBoard);
    await flushPromises();
    await wrapper.find('[data-test="cluster-row"]').trigger("click");
    expect(wrapper.emitted("select")?.[0]).toEqual(["c1"]);
  });

  it("阶段过滤把参数带进请求", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(TrendBoard);
    await flushPromises();
    await wrapper.find("select").setValue("PEAK");
    await flushPromises();
    const lastUrl = fetchMock.mock.calls.at(-1)?.[0] as string;
    expect(lastUrl).toContain("stage=PEAK");
    expect(wrapper.text()).toContain("暂无热点聚类");
  });

  it("加载失败显示错误而非静默空", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, text: () => Promise.resolve("boom") }),
    );
    const wrapper = mount(TrendBoard);
    await flushPromises();
    expect(wrapper.text()).toContain("加载失败");
  });
});
