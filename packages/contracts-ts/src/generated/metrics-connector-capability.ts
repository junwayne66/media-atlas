/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AuthStatus = "AUTHORIZED" | "PENDING_REVIEW" | "UNAUTHORIZED" | "EXPIRED";
/**
 * 该数据源当前是否可用
 */
export type Available = boolean;
/**
 * 限流：最小调用间隔（秒）
 */
export type MinSecondsBetweenCalls = number;
export type Notes = string | null;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
/**
 * §10 指标字段名——用于连接器上报"我这个数据源能提供哪些字段"。
 */
export type MetricField =
  | "VIEWS"
  | "WATCH_TIME"
  | "AVG_WATCH_TIME"
  | "COMPLETION_RATE"
  | "LIKES"
  | "COMMENTS"
  | "SHARES"
  | "SAVES"
  | "FOLLOWS"
  | "IMPRESSIONS"
  | "CLICK_THROUGH_RATE";
export type ProvidedFields = MetricField[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;

/**
 * 指标连接器上报的能力 + 授权 + 限流（§3 "Connector 返回能力，不由 UI 猜" 的效果反馈版）。
 *
 * `provided_fields` 声明该数据源能提供哪些指标——让快照里的 null 是"源本就不提供"的有据缺失，
 * 而非漏抓。`min_seconds_between_calls` 是平台限流下的最小调用间隔，domain 据此排程。
 */
export interface MetricsConnectorCapability {
  auth_status: AuthStatus;
  available: Available;
  min_seconds_between_calls?: MinSecondsBetweenCalls;
  notes?: Notes;
  platform: PublishPlatform;
  provided_fields?: ProvidedFields;
  schema_version?: SchemaVersion;
}
