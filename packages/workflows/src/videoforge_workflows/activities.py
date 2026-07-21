"""骨架阶段 Activity（Fake 实现）。

真实实现按路线图逐步替换：媒体 I/O、模型推理、平台请求只能出现在
Activity 里，Workflow 代码只做决定和编排（30 §4.2）。一个 Activity
对应一个可重试的媒体阶段，不逐帧建 Activity（ADR-002）。
"""

from temporalio import activity


@activity.defn
async def ingest_source(project_id: str) -> str:
    activity.logger.info("fake ingest for %s", project_id)
    return f"ingested:{project_id}"


@activity.defn
async def analyze_source(project_id: str) -> str:
    activity.logger.info("fake analyze for %s", project_id)
    return f"analyzed:{project_id}"


@activity.defn
async def render_output(project_id: str) -> str:
    activity.logger.info("fake render for %s", project_id)
    return f"rendered:{project_id}"


ALL_ACTIVITIES = [ingest_source, analyze_source, render_output]
