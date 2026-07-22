import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App.vue";

describe("App", () => {
  beforeEach(() => {
    // healthz → 健康对象；trend-clusters → 空列表
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("healthz")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ status: "ok", service: "videoforge-api", version: "0.0.1" }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }),
    );
  });

  it("渲染标题并展示 API 版本与热点看板", async () => {
    const wrapper = mount(App);
    expect(wrapper.text()).toContain("VideoForge 控制台");
    await flushPromises();
    expect(wrapper.text()).toContain("API 0.0.1");
    expect(wrapper.text()).toContain("热点池");
  });
});
