import { useEffect, useState, type FormEvent } from "react";

type LobbyViewProps = {
  createMessage: string;
  hostNickname: string;
  initialSheet: "create" | "join" | null;
  joinCode: string;
  joinMessage: string;
  joinNickname: string;
  message: string;
  roomTitle: string;
  onCreateRoom: (event: FormEvent) => void;
  onHostNicknameChange: (nickname: string) => void;
  onJoinCodeChange: (code: string) => void;
  onJoinNicknameChange: (nickname: string) => void;
  onJoinRoom: (event: FormEvent) => void;
  onRandomHostNickname: () => void;
  onRandomJoinNickname: () => void;
  onRoomTitleChange: (title: string) => void;
};

export function LobbyView({
  createMessage,
  hostNickname,
  initialSheet,
  joinCode,
  joinMessage,
  joinNickname,
  message,
  roomTitle,
  onCreateRoom,
  onHostNicknameChange,
  onJoinCodeChange,
  onJoinNicknameChange,
  onJoinRoom,
  onRandomHostNickname,
  onRandomJoinNickname,
  onRoomTitleChange,
}: LobbyViewProps) {
  const [activeSheet, setActiveSheet] = useState<"create" | "join" | null>(null);

  useEffect(() => {
    if (initialSheet) {
      setActiveSheet(initialSheet);
    }
  }, [initialSheet]);

  return (
    <main className="app-shell lobby-shell">
      <header className="topbar lobby-hero">
        <div>
          <p className="eyebrow">듣고, 먼저 맞히세요</p>
          <h1 className="hot-reload-test-title">한소절</h1>
          <div className="lobby-visual" aria-hidden="true">
            <span>♪</span>
            <span>♫</span>
            <span>♬</span>
          </div>
        </div>
      </header>

      <section className="lobby-actions">
        <button type="button" className="lobby-action primary" onClick={() => setActiveSheet("create")}>
          <span className="lobby-action-icon" aria-hidden="true">🎧</span>
          <span className="lobby-action-copy">
            <span>방 만들기</span>
            <small>닉네임만 정하고 바로 대기실로 이동</small>
          </span>
          <strong>방장</strong>
        </button>
        <button type="button" className="lobby-action secondary" onClick={() => setActiveSheet("join")}>
          <span className="lobby-action-icon" aria-hidden="true">🎤</span>
          <span className="lobby-action-copy">
            <span>방 참가</span>
            <small>받은 코드나 링크로 입장</small>
          </span>
          <strong>코드 입력</strong>
        </button>
      </section>

      {!activeSheet && message ? <p className="message">{message}</p> : null}

      <footer className="lobby-footer">
        <div className="footer-main">
          <span>© 2026 한소절 · Dezeli</span>
          <span className="mail-text">✉️ haterecursive@gmail.com</span>
        </div>
        <small>YouTube 음악 영상 및 음원은 비상업적 목적으로만 사용됩니다.</small>
      </footer>

      {activeSheet ? (
        <div className="sheet-backdrop" role="presentation" onClick={() => setActiveSheet(null)}>
          <section
            className="bottom-sheet"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sheet-handle" aria-hidden="true" />
            <div className="sheet-header">
              <h2>{activeSheet === "create" ? "방 만들기" : "방 참가"}</h2>
              <button
                type="button"
                className="secondary sheet-close"
                aria-label="닫기"
                onClick={() => setActiveSheet(null)}
              >
                X
              </button>
            </div>

            {activeSheet === "create" ? (
              <form onSubmit={onCreateRoom} className="stack">
                <div className="create-room-fields">
                  <label>
                    방 제목
                    <input value={roomTitle} onChange={(event) => onRoomTitleChange(event.target.value)} />
                  </label>
                  <label>
                    방장 닉네임
                    <span className="inline-input-action">
                      <input value={hostNickname} onChange={(event) => onHostNicknameChange(event.target.value)} />
                      <button type="button" className="secondary compact-button icon-refresh-button" aria-label="닉네임 새로고침" onClick={onRandomHostNickname}>
                        ↻
                      </button>
                    </span>
                  </label>
                </div>
                {createMessage ? <p className="message sheet-message error-message">{createMessage}</p> : null}
                <button type="submit">방 만들기</button>
              </form>
            ) : (
              <form onSubmit={onJoinRoom} className="stack">
                <div className="create-room-fields">
                  <label>
                    방 코드
                    <input
                      value={joinCode}
                      onChange={(event) => onJoinCodeChange(event.target.value.toUpperCase())}
                      placeholder="친구에게 받은 코드"
                    />
                  </label>
                  <label>
                    닉네임
                    <span className="inline-input-action">
                      <input value={joinNickname} onChange={(event) => onJoinNicknameChange(event.target.value)} />
                      <button type="button" className="secondary compact-button icon-refresh-button" aria-label="닉네임 새로고침" onClick={onRandomJoinNickname}>
                        ↻
                      </button>
                    </span>
                  </label>
                </div>
                {joinMessage ? <p className="message sheet-message error-message">{joinMessage}</p> : null}
                <button type="submit">참가하기</button>
              </form>
            )}
          </section>
        </div>
      ) : null}
    </main>
  );
}
