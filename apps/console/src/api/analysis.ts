/**
 * M-W4 分析产物。
 *
 * 产物由 `GET /v1/projects/{id}/analysis/{transcript|text-tracks|visual|blueprint}` 返回，
 * 后端直接吐 contracts-py 的 Transcript / TextTrackSet / VisualAnalysis / VideoBlueprint 的
 * `model_dump(mode="json")`，因此这里**直接复用合同生成类型**（type-only，运行时零依赖），
 * 不再手写子集——手写子集容易与合同漂移。
 */
import type {
  TextTrackSet,
  Transcript,
  VideoBlueprint,
  VisualAnalysis,
} from "@videoforge/contracts";

import { getAnalysisArtifact } from "./projects";

export type {
  BBox,
  Claim,
  ClaimSourceStatus,
  EvidenceSpan,
  FrameAnalysis,
  FrameSampleReason,
  RhetoricalBeat,
  RhetoricalBeatKind,
  TextObservation,
  TextTrack,
  TextTrackKind,
  TextTrackSet,
  Transcript,
  TranscriptModels,
  TranscriptSegment,
  TranscriptWord,
  VideoBlueprint,
  VisualAnalysis,
  VisualBeat,
  VisualBeatKind,
} from "@videoforge/contracts";

export function fetchTranscript(projectId: string): Promise<Transcript> {
  return getAnalysisArtifact(projectId, "transcript") as Promise<unknown> as Promise<Transcript>;
}

export function fetchTextTracks(projectId: string): Promise<TextTrackSet> {
  return getAnalysisArtifact(projectId, "text-tracks") as Promise<unknown> as Promise<TextTrackSet>;
}

export function fetchVisual(projectId: string): Promise<VisualAnalysis> {
  return getAnalysisArtifact(projectId, "visual") as Promise<unknown> as Promise<VisualAnalysis>;
}

export function fetchBlueprint(projectId: string): Promise<VideoBlueprint> {
  return getAnalysisArtifact(projectId, "blueprint") as Promise<unknown> as Promise<VideoBlueprint>;
}
