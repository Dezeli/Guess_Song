import type { FormEvent } from "react";

import type { SubmitAnswerResponse } from "../shared/types";

type AnswerPanelProps = {
  answer: string;
  canSubmit: boolean;
  hint: string;
  lastAnswerResult: SubmitAnswerResponse | null;
  onAnswerChange: (answer: string) => void;
  onSubmitAnswer: (event: FormEvent) => void;
};

export function AnswerPanel({
  answer,
  canSubmit,
  hint,
  lastAnswerResult,
  onAnswerChange,
  onSubmitAnswer,
}: AnswerPanelProps) {
  return (
    <section className="panel">
      <h2>정답 제출</h2>
      <p className="muted">{hint}</p>
      <form onSubmit={onSubmitAnswer} className="stack">
        <input
          value={answer}
          onChange={(event) => onAnswerChange(event.target.value)}
          placeholder="정답을 입력하세요"
          disabled={!canSubmit}
        />
        <button type="submit" disabled={!canSubmit || !answer.trim()}>
          제출
        </button>
      </form>
      {lastAnswerResult ? (
        <p className={lastAnswerResult.is_correct ? "result correct" : "result wrong"}>
          {lastAnswerResult.is_correct ? "정답" : "오답"} /{" "}
          {lastAnswerResult.matched_fields.length
            ? lastAnswerResult.matched_fields.join(", ")
            : "인정된 항목 없음"}{" "}
          / +{lastAnswerResult.score_awarded} / 합계 {lastAnswerResult.total_score}
        </p>
      ) : null}
    </section>
  );
}
