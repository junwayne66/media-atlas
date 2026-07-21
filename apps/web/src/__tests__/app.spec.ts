import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App.vue";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({ status: "ok", service: "videoforge-api", version: "0.0.1" }),
      }),
    );
  });

  it("渲染标题并展示 API 健康状态", async () => {
    const wrapper = mount(App);
    expect(wrapper.text()).toContain("VideoForge 控制台");
    await flushPromises();
    expect(wrapper.text()).toContain("API 服务正常");
  });
});
