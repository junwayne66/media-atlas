/**
 * M-W4 分析产物的最小本地类型（只声明 UI 用到的字段）。
 * 产物由 `GET /v1/projects/{id}/analysis/{transcript|text-tracks|visual|blueprint}` 返回，
 * 形状对应 contracts-py 的 Transcript / TextTrackSet / VisualAnalysis / VideoBlueprint。
 */
import { getAnalysisArtifact } from "./projects";

export interface TranscriptWord {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
  low_confidence: boolean;
}

export interface TranscriptSegment {
  id: string;
  start_ms: number;
  end_ms: number;
  speaker_id: string | null;
  language: string;
  text: string;
  confidence: number;
  words: TranscriptWord[];
  low_confidence: boolean;
}

export interface Transcript {
  id: string;
  language: string;
  segments: TranscriptSegment[];
  duration_ms: number | null;
}

export type TextTrackKind =
  | "CAPTION"
  | "TITLE"
  | "LOWER_THIRD"
  | "UI"
  | "SCENE_TEXT"
  | "BRAND_MARK"
  | "UNKNOWN";

export interface TextTrack {
  id: string;
  kind: TextTrackKind;
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
  motion: string | null;
  low_confidence: boolean;
}

export interface TextTrackSet {
  id: string;
  tracks: TextTrack[];
  ocr_provider: string;
  ocr_version: string | null;
}

export interface FrameAnalysis {
  frame_time_ms: number;
  reasons: string[];
  /** null = 选中了但未分析（诚实，不编造）。 */
  caption: string | null;
  labels: string[];
  confidence: number | null;
}

export interface VisualAnalysis {
  id: string;
  frames: FrameAnalysis[];
  sampling_policy: string;
  vlm_provider: string | null;
}

export type ClaimSourceStatus = "VERIFIED" | "UNVERIFIED" | "DISPUTED" | "OPINION";

export interface EvidenceSpan {
  kind: string;
  ref_id: string;
  start_ms: number;
  end_ms: number;
}

export interface Claim {
  id: string;
  text: string;
  entities: string[];
  source_status: ClaimSourceStatus;
  evidence: EvidenceSpan[];
}

export interface RhetoricalBeat {
  id: string;
  kind: string;
  start_ms: number;
  end_ms: number;
  summary: string | null;
  claim_ids: string[];
}

export interface VisualBeat {
  id: string;
  kind: string;
  start_ms: number;
  end_ms: number;
  frame_time_ms: number | null;
}

export interface VideoBlueprint {
  id: string;
  duration_ms: number;
  claims: Claim[];
  rhetorical_beats: RhetoricalBeat[];
  visual_beats: VisualBeat[];
  coverage: number | null;
  fusion_provider: string | null;
}

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
