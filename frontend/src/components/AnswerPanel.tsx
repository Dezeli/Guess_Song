import type { FormEvent } from "react";

import type { CurrentRound } from "../shared/types";

type AnswerPanelProps = {
  answer: string;
  canSubmit: boolean;
  hint: string;
  submissions: CurrentRound["answer_submissions"];
  onAnswerChange: (answer: string) => void;
  onSubmitAnswer: (event: FormEvent) => void;
};

export function AnswerPanel({
  answer,
  canSubmit,
  hint,
  submissions,
  onAnswerChange,
  onSubmitAnswer,
}: AnswerPanelProps) {
  return (
    <section className="panel answer-panel">
      <p className="muted">{hint}</p>
      <ul className="answer-chat-list" aria-label="정답 채팅">
        {submissions.length ? (
          submissions.map((submission) => (
            <li key={submission.id} className={submission.score_awarded > 0 ? "scored" : undefined}>
              {submission.score_awarded > 0 ? (
                <span>{submission.nickname}님이 정답으로 {submission.score_awarded}점 획득하셨습니다</span>
              ) : (
                <>
                  <strong>{submission.nickname}</strong>
                  <span>{submission.answer}</span>
                </>
              )}
            </li>
          ))
        ) : (
          <li className="empty-chat" aria-hidden="true" />
        )}
      </ul>
      <form onSubmit={onSubmitAnswer} className="answer-chat-form">
        <input
          value={answer}
          onChange={(event) => onAnswerChange(event.target.value)}
          placeholder="정답을 입력하세요"
          disabled={!canSubmit}
        />
        <button type="submit" disabled={!canSubmit || !answer.trim()}>
          전송
        </button>
      </form>
    </section>
  );
}
