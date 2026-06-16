import type { Participant, RoomState } from "../shared/types";

type PlayersPanelProps = {
  orderedParticipants: Participant[];
  room: RoomState;
};

export function PlayersPanel({ orderedParticipants, room }: PlayersPanelProps) {
  const isTeamMode = room.settings.play_mode === "TEAM";
  const orderedTeams = [...room.teams].sort((a, b) => b.score - a.score || a.order - b.order);

  return (
    <section className="panel">
      <h2>{isTeamMode ? "팀 순위" : "참가자"}</h2>
      {isTeamMode ? (
        <ul className="team-list primary-scoreboard">
          {orderedTeams.map((team) => (
            <li key={team.id}>
              <span>
                <strong>{team.name}</strong>
                <small>{team.participant_count}명</small>
              </span>
              <strong>{team.score}</strong>
            </li>
          ))}
        </ul>
      ) : null}

      <h3 className="subsection-title">{isTeamMode ? "참가자" : "점수판"}</h3>
      <ul className={isTeamMode ? "scoreboard participant-list" : "scoreboard"}>
        {orderedParticipants.map((participant) => (
          <li key={participant.id} className={participant.status !== "ACTIVE" ? "inactive" : undefined}>
            <span>
              {participant.nickname}
              {participant.is_host ? " (방장)" : ""}
              {participant.team_name ? ` / ${participant.team_name}` : ""}
              {participant.status === "AWAY" ? " (자리비움)" : ""}
              {participant.status === "LEFT" ? " (나감)" : ""}
            </span>
            {isTeamMode ? (
              <strong>{getParticipantStatusLabel(participant.status)}</strong>
            ) : (
              <strong>{participant.score}</strong>
            )}
          </li>
        ))}
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
