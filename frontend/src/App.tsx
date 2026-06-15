import { useEffect } from "react";

import { useHealthStore } from "./stores/healthStore";

function App() {
  const { status, error, fetchHealth } = useHealthStore();

  useEffect(() => {
    void fetchHealth();
  }, [fetchHealth]);

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="eyebrow">Chart-based music quiz</p>
        <h1>Guess Song</h1>
        <p className="summary">
          차트 데이터와 공식 음원 후보 검증을 기반으로 자동 생성되는 음악 퀴즈 서비스입니다.
        </p>
        <div className="status-panel">
          <span>API status</span>
          <strong data-state={status}>{status}</strong>
          {error ? <small>{error}</small> : null}
        </div>
      </section>
    </main>
  );
}

export default App;
