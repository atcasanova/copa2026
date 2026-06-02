const MAX_EXTERNAL_MATCHES = 200
const MAX_GOALS = 99

const isPlainObject = (value) => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
)

const normalizeTeamName = (value) => (
  String(value || '')
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .toLowerCase()
)

const parseExternalDateToUtcMinute = (value) => {
  if (typeof value !== 'string' || value.length > 40) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  return Math.round(parsed.getTime() / 60000)
}

const parseLocalKickoffToUtcMinute = (value) => {
  if (typeof value !== 'string' || !value) return null
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasTimezone ? value : `${value}Z`)
  if (Number.isNaN(parsed.getTime())) return null
  return Math.round(parsed.getTime() / 60000)
}

const makeMatchKey = (minute, homeTeam, awayTeam) => (
  `${minute}|${normalizeTeamName(homeTeam)}|${normalizeTeamName(awayTeam)}`
)

const isValidScore = (value) => (
  Number.isInteger(value) && value >= 0 && value <= MAX_GOALS
)

const buildLocalMatchIndex = (matches) => {
  const index = new Map()
  matches.forEach(match => {
    const minute = parseLocalKickoffToUtcMinute(match.kickoff_time)
    if (minute === null) return
    index.set(makeMatchKey(minute, match.team1_name, match.team2_name), match)
  })
  return index
}

export const analyzeExternalPredictionImport = ({ rawText, matches, isLocked }) => {
  const result = {
    roundName: '',
    totalMatches: 0,
    predictedMatches: 0,
    importable: [],
    skipped: [],
    errors: []
  }

  if (typeof rawText !== 'string' || !rawText.trim()) {
    result.errors.push('Cole ou selecione um arquivo JSON antes de validar.')
    return result
  }

  let parsed
  try {
    parsed = JSON.parse(rawText)
  } catch (err) {
    result.errors.push('JSON inválido. Verifique se o conteúdo foi copiado integralmente.')
    return result
  }

  if (!isPlainObject(parsed) || !isPlainObject(parsed.data) || !Array.isArray(parsed.data.matches)) {
    result.errors.push('Formato inválido: esperado objeto com data.matches[].')
    return result
  }

  if (parsed.data.matches.length > MAX_EXTERNAL_MATCHES) {
    result.errors.push(`Arquivo recusado: limite de ${MAX_EXTERNAL_MATCHES} partidas por importação.`)
    return result
  }

  result.roundName = typeof parsed.data.round_name === 'string' ? parsed.data.round_name.slice(0, 120) : ''
  result.totalMatches = parsed.data.matches.length
  const localIndex = buildLocalMatchIndex(matches)
  const importedMatchIds = new Set()

  parsed.data.matches.forEach((externalMatch, idx) => {
    if (!isPlainObject(externalMatch)) {
      result.skipped.push({ reason: 'Item inválido', detail: `Partida #${idx + 1}` })
      return
    }

    const homeTeam = externalMatch.home_team_name
    const awayTeam = externalMatch.away_team_name
    const prediction = externalMatch.user_prediction
    const homeScore = prediction?.predicted_home_score
    const awayScore = prediction?.predicted_away_score

    if (!isPlainObject(prediction) || homeScore === null || homeScore === undefined || awayScore === null || awayScore === undefined) {
      result.skipped.push({
        reason: 'Sem palpite',
        detail: `${String(homeTeam || 'Mandante').slice(0, 80)} x ${String(awayTeam || 'Visitante').slice(0, 80)}`
      })
      return
    }

    result.predictedMatches += 1

    if (typeof homeTeam !== 'string' || typeof awayTeam !== 'string' || homeTeam.length > 100 || awayTeam.length > 100) {
      result.skipped.push({ reason: 'Times inválidos', detail: `Partida #${idx + 1}` })
      return
    }

    if (!isValidScore(homeScore) || !isValidScore(awayScore)) {
      result.skipped.push({
        reason: 'Placar inválido',
        detail: `${homeTeam} x ${awayTeam}`
      })
      return
    }

    const minute = parseExternalDateToUtcMinute(externalMatch.date)
    if (minute === null) {
      result.skipped.push({ reason: 'Data inválida', detail: `${homeTeam} x ${awayTeam}` })
      return
    }

    const localMatch = localIndex.get(makeMatchKey(minute, homeTeam, awayTeam))
    if (!localMatch) {
      result.skipped.push({
        reason: 'Jogo não encontrado',
        detail: `${homeTeam} x ${awayTeam}`
      })
      return
    }

    if (isLocked(localMatch.kickoff_time)) {
      result.skipped.push({
        reason: 'Jogo bloqueado',
        detail: `${homeTeam} x ${awayTeam}`
      })
      return
    }

    if (importedMatchIds.has(localMatch.id)) {
      result.skipped.push({
        reason: 'Palpite duplicado',
        detail: `${homeTeam} x ${awayTeam}`
      })
      return
    }
    importedMatchIds.add(localMatch.id)

    result.importable.push({
      matchId: localMatch.id,
      homeTeam: localMatch.team1_name,
      awayTeam: localMatch.team2_name,
      kickoffTime: localMatch.kickoff_time,
      goalsTeam1: homeScore,
      goalsTeam2: awayScore
    })
  })

  return result
}
