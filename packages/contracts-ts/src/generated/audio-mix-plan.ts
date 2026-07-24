/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type AttackMs = number;
/**
 * 压缩比 ≥ 1
 */
export type Ratio = number;
/**
 * 被压轨下探目标（-8dB 常见）
 */
export type ReductionDb = number;
export type ReleaseMs = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * Ducking sidechain 触发源。
 */
export type DuckingSidechain = "VOICE_ACTIVITY" | "CUT_POINT" | "NONE";
/**
 * 触发阈值（dB）
 */
export type ThresholdDb = number;
export type Id = string;
/**
 * 整体积分响度目标（LUFS）
 */
export type Lufs = number;
/**
 * ±LUFS 容差
 */
export type LufsTolerance = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * True Peak 硬顶（dBTP）；QA TRUE_PEAK_CLIP 触发 BLOCKER
 */
export type TruePeakMaxDbtp = number;
/**
 * 配音段间的背景噪；空则允许绝对静音
 */
export type RoomToneArtifactId = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type TotalDurationMs = number;
/**
 * 被哪条轨 Ducking 的 track id；一般 MUSIC/AMBIENCE 被 VOICE_* 压
 */
export type DuckedBy = string | null;
export type EndMs = number;
export type GainDb = number;
export type Id1 = string;
/**
 * 分轨类型（§9 分轨设计）。
 */
export type AudioMixTrackKind = "ORIGINAL_VOICE" | "VOICE_DUB" | "MUSIC" | "SFX" | "AMBIENCE";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
/**
 * 音频 artifact；VOICE_DUB 常来自 TTSManifest
 */
export type SourceArtifactId = string | null;
export type StartMs = number;
/**
 * VOICE_DUB 关联 TTS Manifest（可选）
 */
export type TtsManifestId = string | null;
export type Tracks = AudioMixTrack[];

/**
 * 一次音频合成计划。tracks + ducking + loudness_target + room_tone。
 */
export interface AudioMixPlan {
  created_at: CreatedAt;
  ducking?: DuckingPolicy | null;
  id: Id;
  loudness_target: LoudnessTarget;
  room_tone_artifact_id?: RoomToneArtifactId;
  schema_version?: SchemaVersion2;
  total_duration_ms: TotalDurationMs;
  tracks?: Tracks;
}
/**
 * Ducking 参数（单位与 ffmpeg sidechaincompress 兼容）。
 */
export interface DuckingPolicy {
  attack_ms?: AttackMs;
  ratio?: Ratio;
  reduction_db?: ReductionDb;
  release_ms?: ReleaseMs;
  schema_version?: SchemaVersion;
  sidechain: DuckingSidechain;
  threshold_db?: ThresholdDb;
}
/**
 * 响度目标（§9 平台/模板配置）。True Peak Gate = 硬顶（QA BLOCKER 已定义）。
 */
export interface LoudnessTarget {
  lufs?: Lufs;
  lufs_tolerance?: LufsTolerance;
  schema_version?: SchemaVersion1;
  true_peak_max_dbtp?: TruePeakMaxDbtp;
}
/**
 * 一条参与合成的音轨。
 */
export interface AudioMixTrack {
  ducked_by?: DuckedBy;
  end_ms: EndMs;
  gain_db?: GainDb;
  id: Id1;
  kind: AudioMixTrackKind;
  schema_version?: SchemaVersion3;
  source_artifact_id?: SourceArtifactId;
  start_ms: StartMs;
  tts_manifest_id?: TtsManifestId;
}
