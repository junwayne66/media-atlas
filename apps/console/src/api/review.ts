/**
 * M-W7 审核：/v1/review-decisions（apps/api review.py）。列表**必须**带 entity_id。
 *
 * `ReviewDecision` 及其枚举取自合同包（type-only）；`ApprovalValidateResponse`
 * 是 review.py 自有的校验端点形状，保留本地声明。
 */
import type { ReviewDecision, ReviewDecisionKind, ReviewScope } from "@videoforge/contracts";

import { api } from "./client";

export type { ReviewDecision, ReviewDecisionKind, ReviewScope };

export interface ApprovalValidateResponse {
  valid: boolean;
  issues: string[];
}

export function listReviewDecisions(entityId: string, limit = 50): Promise<ReviewDecision[]> {
  return api.get<ReviewDecision[]>("/v1/review-decisions", { entity_id: entityId, limit });
}

/**
 * 审批有效性校验（§0.2 红线 8「审批绑定内容」）：实体版本/内容摘要变化 → valid=false，
 * issues 给出具体失效原因（SIGNATURE_MISMATCH / APPROVAL_STALE …）。
 */
export function validateReviewDecision(
  decisionId: string,
  body: { current_entity_version: number; current_content_digest: string; current_entity_id?: string | null },
): Promise<ApprovalValidateResponse> {
  return api.post<ApprovalValidateResponse>(
    `/v1/review-decisions/${encodeURIComponent(decisionId)}/validate`,
    {
      current_entity_version: body.current_entity_version,
      current_content_digest: body.current_content_digest,
      current_entity_id: body.current_entity_id ?? null,
    },
  );
}

export const DECISION_LABEL: Record<ReviewDecisionKind, string> = {
  APPROVED: "已批准",
  REJECTED: "已驳回",
  CHANGES_REQUESTED: "要求修改",
};

export const SCOPE_LABEL: Record<ReviewScope, string> = {
  VARIANT: "语言变体",
  PACKAGE: "成片包",
  TEMPLATE: "模板",
  PROJECT: "项目",
};
