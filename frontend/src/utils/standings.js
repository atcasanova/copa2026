const isScored = (value) => value !== null && value !== undefined && value !== ''

const getTeamInfo = (match, side) => {
  const team = side === 1 ? match.team1 : match.team2
  const name = side === 1 ? match.team1_name : match.team2_name
  return {
    name,
    fifa_code: team?.fifa_code || '',
    flag_icon: team?.flag_icon || ''
  }
}

const createTeamRow = (team) => ({
  ...team,
  played: 0,
  wins: 0,
  draws: 0,
  losses: 0,
  goals_for: 0,
  goals_against: 0,
  goal_difference: 0,
  points: 0
})

const applyResult = (rowsByTeam, team1Name, team2Name, goals1, goals2) => {
  const row1 = rowsByTeam[team1Name]
  const row2 = rowsByTeam[team2Name]
  if (!row1 || !row2) return

  row1.played += 1
  row2.played += 1
  row1.goals_for += goals1
  row1.goals_against += goals2
  row2.goals_for += goals2
  row2.goals_against += goals1

  if (goals1 > goals2) {
    row1.wins += 1
    row1.points += 3
    row2.losses += 1
  } else if (goals1 < goals2) {
    row2.wins += 1
    row2.points += 3
    row1.losses += 1
  } else {
    row1.draws += 1
    row2.draws += 1
    row1.points += 1
    row2.points += 1
  }

  row1.goal_difference = row1.goals_for - row1.goals_against
  row2.goal_difference = row2.goals_for - row2.goals_against
}

const buildHeadToHeadRows = (teams, matches, getScore) => {
  const teamSet = new Set(teams)
  const rows = {}
  teams.forEach(team => {
    rows[team] = createTeamRow({ name: team })
  })

  matches.forEach(match => {
    if (!teamSet.has(match.team1_name) || !teamSet.has(match.team2_name)) return
    const score = getScore(match)
    if (!score) return
    applyResult(rows, match.team1_name, match.team2_name, score.goals1, score.goals2)
  })

  return rows
}

const sortStandings = (standings, matches, getScore) => {
  const primaryKey = (row) => `${row.points}:${row.goal_difference}:${row.goals_for}`

  return [...standings].sort((a, b) => {
    if (b.points !== a.points) return b.points - a.points
    if (b.goal_difference !== a.goal_difference) return b.goal_difference - a.goal_difference
    if (b.goals_for !== a.goals_for) return b.goals_for - a.goals_for

    const tiedTeams = standings
      .filter(row => primaryKey(row) === primaryKey(a))
      .map(row => row.name)

    if (tiedTeams.length > 1) {
      const h2hRows = buildHeadToHeadRows(tiedTeams, matches, getScore)
      const h2hA = h2hRows[a.name]
      const h2hB = h2hRows[b.name]
      if (h2hB.points !== h2hA.points) return h2hB.points - h2hA.points
      if (h2hB.goal_difference !== h2hA.goal_difference) return h2hB.goal_difference - h2hA.goal_difference
      if (h2hB.goals_for !== h2hA.goals_for) return h2hB.goals_for - h2hA.goals_for
    }

    return a.name.localeCompare(b.name, 'pt-BR')
  })
}

export const getActualScore = (match) => {
  if (!isScored(match.score_ft_team1) || !isScored(match.score_ft_team2)) return null
  return {
    goals1: Number(match.score_ft_team1),
    goals2: Number(match.score_ft_team2)
  }
}

export const getPredictionScore = (predictions) => (match) => {
  const prediction = predictions?.[match.id]
  if (!prediction || !isScored(prediction.goals_team1) || !isScored(prediction.goals_team2)) return null
  return {
    goals1: Number(prediction.goals_team1),
    goals2: Number(prediction.goals_team2)
  }
}

export const buildGroupStandings = (matches, getScore = getActualScore) => {
  const groupMatches = matches.filter(match => match.stage === 'Group Stage' && match.group_name)
  const groupsMap = {}

  groupMatches.forEach(match => {
    if (!groupsMap[match.group_name]) {
      groupsMap[match.group_name] = {
        groupName: match.group_name,
        matches: [],
        teams: {}
      }
    }

    groupsMap[match.group_name].matches.push(match)
    const team1 = getTeamInfo(match, 1)
    const team2 = getTeamInfo(match, 2)
    if (!groupsMap[match.group_name].teams[team1.name]) groupsMap[match.group_name].teams[team1.name] = team1
    if (!groupsMap[match.group_name].teams[team2.name]) groupsMap[match.group_name].teams[team2.name] = team2
  })

  return Object.values(groupsMap)
    .sort((a, b) => a.groupName.localeCompare(b.groupName, 'pt-BR', { numeric: true }))
    .map(group => {
      const rowsByTeam = {}
      Object.values(group.teams).forEach(team => {
        rowsByTeam[team.name] = createTeamRow(team)
      })

      group.matches.forEach(match => {
        const score = getScore(match)
        if (!score) return
        applyResult(rowsByTeam, match.team1_name, match.team2_name, score.goals1, score.goals2)
      })

      return {
        ...group,
        matches: [...group.matches].sort((a, b) => new Date(a.kickoff_time) - new Date(b.kickoff_time)),
        standings: sortStandings(Object.values(rowsByTeam), group.matches, getScore)
      }
    })
}

export const getGroupStandings = (matches, groupName, getScore = getActualScore) => (
  buildGroupStandings(matches, getScore).find(group => group.groupName === groupName)
)
