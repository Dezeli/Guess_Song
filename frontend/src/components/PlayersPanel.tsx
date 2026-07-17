import type { ReactNode } from "react";

import type { Participant, RoomState } from "../shared/types";

type PlayersPanelProps = {
  canKick?: boolean;
  currentParticipantId?: number | null;
  lobbyAction?: ReactNode;
  onKickParticipant?: (participantId: number) => void;
  onTeamChange?: (teamId: number) => void;
  orderedParticipants: Participant[];
  room: RoomState;
  showScores?: boolean;
};

export function PlayersPanel({
  canKick = false,
  currentParticipantId = null,
  lobbyAction = null,
  onKickParticipant,
  onTeamChange,
  orderedParticipants,
  room,
  showScores = true,
}: PlayersPanelProps) {
  const isTeamMode = room.settings.play_mode === "TEAM";
  const canSelectTeam = isTeamMode && room.settings.team_assign_mode === "SELF_SELECT" && room.status === "waiting";
  const orderedTeams = [...room.teams].sort((a, b) => b.score - a.score || a.order - b.order);
  const teamSlots = Array.from({ length: 4 }, (_, index) => orderedTeams[index] ?? null);

  if (!showScores) {
    const currentParticipant = orderedParticipants.find((participant) => participant.id === currentParticipantId) ?? null;
    const visibleParticipants = orderedParticipants
      .filter((participant) => participant.status !== "LEFT")
      .slice(0, 10);
    const participantSlots = Array.from({ length: 10 }, (_, index) => visibleParticipants[index] ?? null);

    return (
      <section className="panel lobby-participants-panel">
        <div className="section-heading participants-heading">
          <h2>참여자</h2>
          {canSelectTeam && currentParticipant && onTeamChange ? (
            <div className="team-choice-row" aria-label="팀 선택">
              {room.teams.map((team) => (
                <button
                  key={team.id}
                  type="button"
                  className={currentParticipant.team_id === team.id ? "selected" : "secondary"}
                  onClick={() => onTeamChange(team.id)}
                >
                  {team.name}
                </button>
              ))}
            </div>
          ) : (
            <div className="team-choice-row team-choice-placeholder" aria-hidden="true">
              <button type="button" tabIndex={-1}>TEAM1</button>
              <button type="button" tabIndex={-1}>TEAM2</button>
              <button type="button" tabIndex={-1}>TEAM3</button>
              <button type="button" tabIndex={-1}>TEAM4</button>
            </div>
          )}
        </div>
        <ul className="lobby-participant-list">
          {participantSlots.map((participant, index) => {
            if (!participant) {
              return (
                <li key={`empty-${index}`} className="empty-slot">
                  <span className="participant-avatar" aria-hidden="true">
                    +
                  </span>
                  <span className="participant-name" aria-hidden="true" />
                </li>
              );
            }

            const canKickParticipant = canKick && !participant.is_host && participant.id !== currentParticipantId;

            return (
              <li
                key={participant.id}
                className={[
                  participant.id === currentParticipantId ? "is-me" : "",
                  canKickParticipant ? "can-kick" : "",
                ].filter(Boolean).join(" ") || undefined}
              >
                <span className="participant-avatar" aria-hidden="true">
                  {getParticipantIcon(participant.id)}
                </span>
                <span className="participant-name">
                  {participant.nickname}
                  {participant.is_host ? <small>방장</small> : null}
                  {participant.team_name ? <small>{participant.team_name}</small> : null}
                </span>
                {canKickParticipant ? (
                  <button
                    type="button"
                    className="kick-participant-button"
                    aria-label={`${participant.nickname} 강퇴`}
                    onClick={() => onKickParticipant?.(participant.id)}
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                ) : participant.id === currentParticipantId ? (
                  <strong>나</strong>
                ) : null}
              </li>
            );
          })}
        </ul>
        {lobbyAction ? <div className="lobby-participant-action">{lobbyAction}</div> : null}
      </section>
    );
  }

  const scoreParticipants = orderedParticipants
    .filter((participant) => participant.status !== "LEFT")
    .slice(0, 10);
  const scoreSlots = Array.from({ length: 10 }, (_, index) => scoreParticipants[index] ?? null);

  return (
    <section className="panel game-players-panel">
      <h2>{showScores && isTeamMode ? "팀 순위" : "점수판"}</h2>
      {showScores && isTeamMode ? (
        <ul className="team-list primary-scoreboard">
          {teamSlots.map((team, index) => {
            if (!team) {
              return (
                <li key={`team-empty-${index}`} className="empty-slot team-empty-slot">
                  <span aria-hidden="true" />
                  <strong aria-hidden="true" />
                </li>
              );
            }
            return (
              <li key={team.id}>
                <span>
                  <strong>{team.name}</strong>
                  <small>{team.participant_count}명</small>
                </span>
                <strong>{team.score}</strong>
              </li>
            );
          })}
        </ul>
      ) : null}

      {showScores && isTeamMode ? <h3 className="subsection-title">참가자</h3> : null}
      <ul className={isTeamMode ? "scoreboard participant-list" : "scoreboard"}>
        {scoreSlots.map((participant, index) => {
          if (!participant) {
            return (
              <li key={`score-empty-${index}`} className="empty-slot score-empty-slot">
                <span className="score-rank" aria-hidden="true">{index + 1}</span>
                <span aria-hidden="true" />
                <strong aria-hidden="true" />
              </li>
            );
          }

          return (
            <li
              key={participant.id}
              className={[
                participant.status !== "ACTIVE" ? "inactive" : "",
                participant.id === currentParticipantId ? "is-me" : "",
              ].filter(Boolean).join(" ") || undefined}
            >
              <span className="score-rank" aria-label={`${index + 1}위`}>
                {getRankLabel(index + 1)}
              </span>
              <span>
                {participant.nickname}
                {participant.is_host ? <small>방장</small> : null}
                {participant.team_name ? <small>{participant.team_name}</small> : null}
                {participant.status === "AWAY" ? <small>자리비움</small> : null}
              </span>
              {!showScores ? (
                <strong>{getParticipantStatusLabel(participant.status)}</strong>
              ) : isTeamMode ? (
                <strong>{getParticipantStatusLabel(participant.status)}</strong>
              ) : (
                <strong>{participant.score}</strong>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function getParticipantStatusLabel(status: Participant["status"]) {
  if (status === "ACTIVE") {
    return "참가 중";
  }
  if (status === "AWAY") {
    return "자리비움";
  }
  return "나감";
}

function getParticipantIcon(id: number) {
  const icons = ["🎧", "🎤", "🎵", "🎶", "💿", "🎹", "🥁", "🎸"];
  return icons[id % icons.length];
}

function getRankLabel(rank: number) {
  if (rank === 1) {
    return "🥇";
  }
  if (rank === 2) {
    return "🥈";
  }
  if (rank === 3) {
    return "🥉";
  }
  return rank;
}
